"""Account reads: whether first-time setup is due, the user list (admins),
and looking up a one-time password link."""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

from django.db.models import Prefetch, QuerySet
from django.shortcuts import get_object_or_404
from django.utils import timezone

from .models import PasswordLink, User

if TYPE_CHECKING:
    from apps.access.context import AccessContext


def needs_setup() -> bool:
    """A fresh install: no account at all yet."""
    return not User.objects.exists()


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _open_links() -> QuerySet[PasswordLink]:
    return PasswordLink.objects.filter(used_at__isnull=True, expires_at__gt=timezone.now())


def list_users(ctx: AccessContext) -> QuerySet[User]:
    """Every account, with its roles, person and open link (admins only)."""
    ctx.require("admin", "manage")
    return (
        User.objects.select_related("person")
        .prefetch_related(
            "groups",
            Prefetch(
                "password_links",
                queryset=_open_links().order_by("-created_at"),
                to_attr="open_links",
            ),
        )
        .order_by("-is_active", "first_name", "email")
    )


def get_user(ctx: AccessContext, user_id: int) -> User:
    return get_object_or_404(list_users(ctx), pk=user_id)


def find_link(token: str) -> PasswordLink | None:
    """The unused, unexpired link for ``token`` (of an active account)."""
    return (
        _open_links()
        .select_related("user", "user__person")
        .filter(token_hash=token_hash(token), user__is_active=True)
        .first()
    )
