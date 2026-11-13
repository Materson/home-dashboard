"""Accounts over the API:

- ``/api/me`` — the current user + merged permissions for the SPA shell;
- ``/api/setup`` — first-time setup on a fresh install (public, CSRF-checked);
- ``/api/invites/{token}`` — set a password through a one-time link (public);
- ``/api/users`` — accounts, managed by admins.

Problems come back as 422 ``{"detail": code}`` (``codes``: the password
rules a password broke) for the SPA to translate."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from django.contrib.auth import login
from django.http import HttpRequest
from ninja import Router, Schema

from apps.access.context import get_ctx
from apps.core.security import anonymous_with_csrf

from . import selectors, services
from .models import PasswordLink, User

router = Router()  # /me
setup_router = Router()
invites_router = Router()
users_router = Router()

Locale = Literal["pl", "en"]


def _problem(exc: ValueError) -> tuple[int, dict[str, Any]]:
    codes = exc.codes if isinstance(exc, services.PasswordRejected) else []
    return 422, {"detail": str(exc), "codes": codes}


def _log_in(request: HttpRequest, user: User) -> None:
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")


# -------------------- /me --------------------


class MeOut(Schema):
    id: int
    email: str
    locale: str
    first_name: str
    last_name: str


class PermissionsOut(Schema):
    modules: dict[str, dict[str, bool]]  # {"finance": {"view": True, "edit": True, ...}, ...}
    person_ids: list[str]  # Person UUIDs the caller can at least view (any module)
    is_admin: bool


@router.get("/", response=MeOut)
def me(request: HttpRequest) -> MeOut:
    u = request.user
    return MeOut(
        id=u.id, email=u.email, locale=u.locale, first_name=u.first_name, last_name=u.last_name
    )


@router.get("/permissions", response=PermissionsOut)
def permissions(request: HttpRequest) -> PermissionsOut:
    ctx = get_ctx(request)
    return PermissionsOut(
        modules=ctx.module_summary(),
        person_ids=[str(pid) for pid in ctx.visible_person_ids()],
        is_admin=ctx.is_admin,
    )


# -------------------- First-time setup --------------------


class SetupStatus(Schema):
    needs_setup: bool


class SetupIn(Schema):
    email: str
    password: str
    name: str
    locale: Locale = "pl"


@setup_router.get("", response=SetupStatus, auth=None)
def setup_status(request: HttpRequest) -> SetupStatus:
    return SetupStatus(needs_setup=selectors.needs_setup())


@setup_router.post("", response={200: dict, 422: dict}, auth=anonymous_with_csrf)
def run_setup(request: HttpRequest, payload: SetupIn):
    """The first account (main admin), logged in straight away."""
    try:
        user = services.run_setup(**payload.dict())
    except ValueError as exc:
        return _problem(exc)
    _log_in(request, user)
    return {"ok": True}


# -------------------- One-time links --------------------


class LinkInfo(Schema):
    email: str
    name: str
    purpose: str  # invite | reset


class AcceptIn(Schema):
    password: str


def _name(user: User) -> str:
    person = getattr(user, "person", None)
    return user.first_name or (person.display_name if person else "")


@invites_router.get("/{token}", response={200: LinkInfo, 404: dict}, auth=None)
def link_info(request: HttpRequest, token: str):
    link = selectors.find_link(token)
    if link is None:
        return 404, {"detail": "link_invalid"}
    return LinkInfo(email=link.user.email, name=_name(link.user), purpose=link.purpose)


@invites_router.post("/{token}", response={200: dict, 422: dict}, auth=anonymous_with_csrf)
def accept_link(request: HttpRequest, token: str, payload: AcceptIn):
    """Sets the password and logs in."""
    try:
        user = services.accept_link(token, payload.password)
    except ValueError as exc:
        return _problem(exc)
    _log_in(request, user)
    return {"ok": True}


# -------------------- Accounts (admins) --------------------


class RoleRef(Schema):
    id: int
    name: str


class PersonRef(Schema):
    id: UUID
    display_name: str
    color: str


class OpenLink(Schema):
    purpose: str
    expires_at: datetime


class UserOut(Schema):
    id: int
    email: str
    name: str
    locale: str
    is_active: bool
    is_main_admin: bool  # superuser: everything, always
    has_password: bool
    last_login: datetime | None
    roles: list[RoleRef]
    person: PersonRef | None
    open_link: OpenLink | None  # an invite / reset not used yet


class UserIn(Schema):
    email: str
    name: str
    locale: Locale = "pl"
    role_ids: list[int] = []
    person_id: UUID | None = None
    new_person: bool = False  # no person_id: make them a new Person


class UserEdit(Schema):
    email: str
    name: str
    locale: Locale
    is_active: bool
    role_ids: list[int]
    person_id: UUID | None


class LinkOut(Schema):
    token: str  # shown once — the SPA turns it into /invite/<token>
    purpose: str
    expires_at: datetime


class CreatedOut(Schema):
    user: UserOut
    link: LinkOut


def _user_out(user: User) -> UserOut:
    person = getattr(user, "person", None)
    links = getattr(user, "open_links", None)
    if links is None:  # not from list_users' prefetch
        links = list(user.password_links.filter(used_at__isnull=True).order_by("-created_at"))
    return UserOut(
        id=user.pk,
        email=user.email,
        name=_name(user),
        locale=user.locale,
        is_active=user.is_active,
        is_main_admin=user.is_superuser,
        has_password=user.has_usable_password(),
        last_login=user.last_login,
        roles=[RoleRef(id=g.pk, name=g.name) for g in user.groups.all()],
        person=PersonRef(id=person.id, display_name=person.display_name, color=person.color)
        if person
        else None,
        open_link=OpenLink(purpose=links[0].purpose, expires_at=links[0].expires_at)
        if links
        else None,
    )


def _link_out(link: PasswordLink, token: str) -> LinkOut:
    return LinkOut(token=token, purpose=link.purpose, expires_at=link.expires_at)


@users_router.get("", response=list[UserOut])
def list_users(request: HttpRequest) -> list[UserOut]:
    return [_user_out(u) for u in selectors.list_users(get_ctx(request))]


@users_router.post("", response={200: CreatedOut, 422: dict})
def create_user(request: HttpRequest, payload: UserIn):
    ctx = get_ctx(request)
    try:
        user, link, token = services.create_user(ctx, **payload.dict())
    except ValueError as exc:
        return _problem(exc)
    return CreatedOut(user=_user_out(selectors.get_user(ctx, user.pk)), link=_link_out(link, token))


@users_router.put("/{user_id}", response={200: UserOut, 422: dict})
def update_user(request: HttpRequest, user_id: int, payload: UserEdit):
    ctx = get_ctx(request)
    try:
        services.update_user(ctx, user_id, **payload.dict())
    except ValueError as exc:
        return _problem(exc)
    return _user_out(selectors.get_user(ctx, user_id))


@users_router.post("/{user_id}/link", response={200: LinkOut, 422: dict})
def new_link(request: HttpRequest, user_id: int):
    """A fresh invite / reset link (the old one stops working)."""
    try:
        link, token = services.issue_link(get_ctx(request), user_id)
    except ValueError as exc:
        return _problem(exc)
    return _link_out(link, token)
