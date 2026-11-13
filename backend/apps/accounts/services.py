"""Account writes: first-time setup, accounts made by an admin, one-time
password links (invites and resets).

There's no sign-up: the first account comes from ``run_setup`` on a fresh
install (whoever opens the app first — it's LAN/VPN only), every other one
from an admin, who passes on the one-time link to set a password. Problems
are ``ValueError`` with a short code the SPA translates; a rejected password
is ``PasswordRejected`` with Django's validator codes."""

from __future__ import annotations

import secrets
from datetime import timedelta
from typing import TYPE_CHECKING, Any
from uuid import UUID

from django.contrib.auth.models import Group
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import PermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone

from apps.access.roles import ADMIN, PARENT, seed_roles
from apps.access.services import keeping_admin
from apps.people.models import Person

from .models import PasswordLink, User
from .selectors import find_link, token_hash

if TYPE_CHECKING:
    from apps.access.context import AccessContext

LINK_DAYS = 7
UNSET: Any = object()  # "leave as is", for update_user's optional fields


class PasswordRejected(ValueError):
    def __init__(self, codes: list[str]) -> None:
        super().__init__("password")
        self.codes = codes


def _check_password(password: str, user: User) -> None:
    try:
        validate_password(password, user)
    except DjangoValidationError as exc:
        raise PasswordRejected([e.code or "invalid" for e in exc.error_list]) from exc


def _clean_email(email: str, *, exclude: int | None = None) -> str:
    email = User.objects.normalize_email(email.strip())
    try:
        validate_email(email)
    except DjangoValidationError as exc:
        raise ValueError("email_invalid") from exc
    if User.objects.filter(email__iexact=email).exclude(pk=exclude).exists():
        raise ValueError("email_taken")
    return email


# -------------------- First-time setup --------------------


def run_setup(*, email: str, password: str, name: str, locale: str) -> User:
    """A fresh install's first account: a main admin (superuser) with the
    Admin and Parent roles, and their own Person. Refused once any account
    exists. No ``ctx`` — nobody is logged in yet."""
    name = " ".join(name.split())
    if not name:
        raise ValueError("name_required")
    with transaction.atomic():
        seed_roles()
        # Locks the Admin role's row: two setups at once run one after the other.
        admin = Group.objects.select_for_update().get(name=ADMIN)
        if User.objects.exists():
            raise ValueError("already_set_up")
        user = User(
            email=_clean_email(email),
            first_name=name,
            locale=locale,
            is_staff=True,
            is_superuser=True,
        )
        _check_password(password, user)
        user.set_password(password)
        user.save()
        user.groups.add(admin, Group.objects.get(name=PARENT))
        Person.objects.create(display_name=name, user=user)
    return user


# -------------------- Accounts (admins) --------------------


def _roles(role_ids: list[int]) -> list[Group]:
    roles = list(Group.objects.filter(pk__in=role_ids))
    if len(roles) != len(set(role_ids)):
        raise ValueError("unknown_role")
    return roles


def _link_person(user: User, person_id: UUID | None) -> None:
    """``user``'s own Person becomes ``person_id`` (None: none)."""
    if person_id is not None:
        person = Person.objects.filter(pk=person_id, archived_at__isnull=True).first()
        if person is None:
            raise ValueError("unknown_person")
        if person.user_id not in (None, user.pk):
            raise ValueError("person_taken")
    Person.objects.filter(user=user).exclude(pk=person_id).update(user=None)
    if person_id is not None:
        Person.objects.filter(pk=person_id).update(user=user)


def _issue(ctx: AccessContext, user: User, purpose: str) -> tuple[PasswordLink, str]:
    """A new one-time link (any older open one stops working)."""
    PasswordLink.objects.filter(user=user, used_at__isnull=True).delete()
    token = secrets.token_urlsafe(32)
    link = PasswordLink.objects.create(
        user=user,
        token_hash=token_hash(token),
        purpose=purpose,
        expires_at=timezone.now() + timedelta(days=LINK_DAYS),
        created_by_id=ctx.user_id,
    )
    return link, token


def create_user(
    ctx: AccessContext,
    *,
    email: str,
    name: str,
    locale: str,
    role_ids: list[int],
    person_id: UUID | None = None,
    new_person: bool = False,
) -> tuple[User, PasswordLink, str]:
    """An account with no password yet, and its invite link (shown once).
    It's someone's own Person: ``person_id``, or a new one (``new_person``)."""
    ctx.require("admin", "manage")
    name = " ".join(name.split())
    with transaction.atomic():
        user = User(email=_clean_email(email), first_name=name, locale=locale)
        user.set_unusable_password()
        user.save()
        user.groups.set(_roles(role_ids))
        if person_id is not None:
            _link_person(user, person_id)
        elif new_person:
            Person.objects.create(display_name=name or user.email.split("@")[0], user=user)
        link, token = _issue(ctx, user, PasswordLink.Purpose.INVITE)
    return user, link, token


def update_user(
    ctx: AccessContext,
    user_id: int,
    *,
    email: str = UNSET,
    name: str = UNSET,
    locale: str = UNSET,
    is_active: bool = UNSET,
    role_ids: list[int] = UNSET,
    person_id: UUID | None = UNSET,
) -> User:
    """Change an account (only the given fields). Nobody switches themself
    off; only a main admin changes another main admin's roles or status."""
    ctx.require("admin", "manage")
    user = get_object_or_404(User, pk=user_id)
    changes_status = is_active is not UNSET and is_active != user.is_active
    changes_roles = role_ids is not UNSET and set(role_ids) != set(
        user.groups.values_list("id", flat=True)
    )
    if user.is_superuser and not ctx.is_admin and (changes_status or changes_roles):
        raise PermissionDenied("only a main admin changes a main admin")
    if user.pk == ctx.user_id and is_active is False:
        raise ValueError("deactivate_self")
    with keeping_admin(ctx):
        if email is not UNSET:
            user.email = _clean_email(email, exclude=user.pk)
        if name is not UNSET:
            user.first_name = " ".join(name.split())
        if locale is not UNSET:
            user.locale = locale
        if is_active is not UNSET:
            user.is_active = is_active
            if not is_active:  # an open invite / reset stops working too
                PasswordLink.objects.filter(user=user, used_at__isnull=True).delete()
        user.save()
        if role_ids is not UNSET:
            user.groups.set(_roles(role_ids))
        if person_id is not UNSET:
            _link_person(user, person_id)
    return user


def issue_link(ctx: AccessContext, user_id: int) -> tuple[PasswordLink, str]:
    """A fresh one-time link: an invite while the account has no password,
    else a reset (e.g. a forgotten password)."""
    ctx.require("admin", "manage")
    user = get_object_or_404(User, pk=user_id)
    if not user.is_active:
        raise ValueError("inactive")
    purpose = (
        PasswordLink.Purpose.RESET if user.has_usable_password() else PasswordLink.Purpose.INVITE
    )
    return _issue(ctx, user, purpose)


def accept_link(token: str, password: str) -> User:
    """Set the password through a one-time link; the link is used up."""
    with transaction.atomic():
        link = find_link(token)
        if link is None:
            raise ValueError("link_invalid")
        user = link.user
        _check_password(password, user)
        user.set_password(password)
        user.save(update_fields=["password"])
        link.used_at = timezone.now()
        link.save(update_fields=["used_at", "updated_at"])
    return user
