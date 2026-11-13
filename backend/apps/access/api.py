"""Roles and grants, edited by admins (Settings → Roles and access, and an
account's own exceptions). Users read their merged view via
``/api/me/permissions``. Problems: 422 ``{"detail": code}``."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from django.http import HttpRequest
from ninja import Router, Schema

from . import services
from .context import get_ctx
from .models import AccessGrant
from .permissions import LEVELS, MODULES
from .roles import ROLES

router = Router()


def _problem(exc: ValueError) -> tuple[int, dict[str, Any]]:
    return 422, {"detail": str(exc)}


class MetaOut(Schema):
    modules: list[str]
    levels: list[str]


class GrantOut(Schema):
    id: UUID
    user_id: int | None
    group_id: int | None  # the role
    module: str
    level: str
    effect: str
    subjects: str
    person_ids: list[str]
    data_from: date | None
    data_to: date | None
    valid_until: datetime | None


class GrantIn(Schema):
    user_id: int | None = None
    group_id: int | None = None
    module: str
    level: Literal["view", "edit", "manage"]
    effect: Literal["allow", "deny"] = "allow"
    subjects: Literal["all", "self", "selected"] = "all"
    person_ids: list[str] = []
    data_from: date | None = None
    data_to: date | None = None
    valid_until: datetime | None = None


class RoleOut(Schema):
    id: int
    name: str
    builtin: bool  # Admin / Parent / Child: can't be renamed or deleted
    members: int
    grants: list[GrantOut]


class RoleIn(Schema):
    name: str


def _role_out(group: Any) -> RoleOut:
    return RoleOut(
        id=group.pk,
        name=group.name,
        builtin=group.name in ROLES,
        members=group.members,
        grants=[GrantOut.from_orm(g) for g in group.access_grants.all()],
    )


@router.get("/meta", response=MetaOut)
def meta(request: HttpRequest) -> MetaOut:
    """The modules and levels a grant can name."""
    get_ctx(request).require("admin", "manage")
    return MetaOut(modules=list(MODULES), levels=list(LEVELS))


# -------------------- Roles --------------------


@router.get("/roles", response=list[RoleOut])
def list_roles(request: HttpRequest) -> list[RoleOut]:
    return [_role_out(g) for g in services.list_roles(get_ctx(request))]


@router.post("/roles", response={200: RoleOut, 422: dict})
def create_role(request: HttpRequest, payload: RoleIn):
    try:
        return _role_out(services.create_role(get_ctx(request), payload.name))
    except ValueError as exc:
        return _problem(exc)


@router.put("/roles/{role_id}", response={200: RoleOut, 422: dict})
def rename_role(request: HttpRequest, role_id: int, payload: RoleIn):
    try:
        return _role_out(services.rename_role(get_ctx(request), role_id, payload.name))
    except ValueError as exc:
        return _problem(exc)


@router.delete("/roles/{role_id}", response={200: dict, 422: dict})
def delete_role(request: HttpRequest, role_id: int):
    try:
        services.delete_role(get_ctx(request), role_id)
    except ValueError as exc:
        return _problem(exc)
    return {"deleted": True}


# -------------------- Grants --------------------


@router.get("/grants", response=list[GrantOut])
def list_grants(
    request: HttpRequest, user_id: int | None = None, role_id: int | None = None
) -> list[AccessGrant]:
    return list(services.list_grants(get_ctx(request), user_id=user_id, role_id=role_id))


@router.post("/grants", response={200: GrantOut, 422: dict})
def create_grant(request: HttpRequest, payload: GrantIn):
    try:
        return services.save_grant(get_ctx(request), payload.dict())
    except ValueError as exc:
        return _problem(exc)


@router.put("/grants/{grant_id}", response={200: GrantOut, 422: dict})
def update_grant(request: HttpRequest, grant_id: UUID, payload: GrantIn):
    try:
        return services.save_grant(get_ctx(request), payload.dict(), grant_id)
    except ValueError as exc:
        return _problem(exc)


@router.delete("/grants/{grant_id}", response={200: dict, 422: dict})
def delete_grant(request: HttpRequest, grant_id: UUID):
    try:
        services.delete_grant(get_ctx(request), grant_id)
    except ValueError as exc:
        return _problem(exc)
    return {"deleted": True}
