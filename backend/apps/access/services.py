"""Roles (Django groups) and access grants, edited by admins in the app.

Every change runs inside ``keeping_admin``: if it would take away the acting
admin's own ``admin:manage`` (their last way back in), it's rolled back and
``ValueError("lose_admin")`` raised. Validation problems are ``ValueError``
with a short code the SPA translates."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from typing import Any
from uuid import UUID

from django.contrib.auth.models import Group
from django.db import transaction
from django.db.models import Count, Prefetch, QuerySet
from django.shortcuts import get_object_or_404

from .context import AccessContext
from .models import AccessGrant
from .permissions import LEVELS, MODULES
from .roles import ROLES


@contextmanager
def keeping_admin(ctx: AccessContext) -> Iterator[None]:
    """Run a change; undo it if the acting user would lose admin access.
    (A main admin — superuser — never can.)"""
    from apps.accounts.models import User  # noqa: PLC0415

    with transaction.atomic():
        yield
        if not ctx.is_admin:
            me = User.objects.get(pk=ctx.user_id)
            if not me.is_active or not AccessContext.for_user(me).has("admin", "manage"):
                raise ValueError("lose_admin")


# -------------------- Roles --------------------


def list_roles(ctx: AccessContext) -> QuerySet[Group]:
    """Every role with its grants and how many accounts have it."""
    ctx.require("admin", "manage")
    return (
        Group.objects.annotate(members=Count("user", distinct=True))
        .prefetch_related(
            Prefetch("access_grants", queryset=AccessGrant.objects.order_by("module", "level"))
        )
        .order_by("name")
    )


def _role(ctx: AccessContext, role_id: int) -> Group:
    return get_object_or_404(list_roles(ctx), pk=role_id)


def _clean_name(name: str, *, exclude: int | None = None) -> str:
    name = " ".join(name.split())
    if not name:
        raise ValueError("name_required")
    if Group.objects.filter(name__iexact=name).exclude(pk=exclude).exists():
        raise ValueError("role_taken")
    return name


def create_role(ctx: AccessContext, name: str) -> Group:
    ctx.require("admin", "manage")
    group = Group.objects.create(name=_clean_name(name))
    return _role(ctx, group.pk)


def rename_role(ctx: AccessContext, role_id: int, name: str) -> Group:
    """Built-in roles keep their names (the start-up seed finds them by name)."""
    group = _role(ctx, role_id)
    if group.name in ROLES:
        raise ValueError("builtin_role")
    group.name = _clean_name(name, exclude=group.pk)
    group.save(update_fields=["name"])
    return _role(ctx, group.pk)


def delete_role(ctx: AccessContext, role_id: int) -> None:
    """Its members lose it, with its grants. Built-in roles stay."""
    group = _role(ctx, role_id)
    if group.name in ROLES:
        raise ValueError("builtin_role")
    with keeping_admin(ctx):
        group.delete()


# -------------------- Grants --------------------


def list_grants(
    ctx: AccessContext, *, user_id: int | None = None, role_id: int | None = None
) -> QuerySet[AccessGrant]:
    ctx.require("admin", "manage")
    qs = AccessGrant.objects.order_by("module", "level")
    if user_id is not None:
        qs = qs.filter(user_id=user_id)
    if role_id is not None:
        qs = qs.filter(group_id=role_id)
    return qs


def _check_grant(data: dict[str, Any]) -> dict[str, Any]:
    from apps.accounts.models import User  # noqa: PLC0415
    from apps.people.models import Person  # noqa: PLC0415

    if (data.get("user_id") is None) == (data.get("group_id") is None):
        raise ValueError("grant_owner")  # exactly one: an account or a role
    if data["user_id"] is not None and not User.objects.filter(pk=data["user_id"]).exists():
        raise ValueError("unknown_user")
    if data["group_id"] is not None and not Group.objects.filter(pk=data["group_id"]).exists():
        raise ValueError("unknown_role")
    if data["module"] not in MODULES or data["level"] not in LEVELS:
        raise ValueError("unknown_module")
    persons = [str(p) for p in data.get("person_ids") or []]
    if data.get("subjects") == AccessGrant.Subjects.SELECTED:
        if not persons:
            raise ValueError("persons_required")
        if Person.objects.filter(pk__in=persons).count() != len(set(persons)):
            raise ValueError("unknown_person")
    else:
        persons = []
    data_from: date | None = data.get("data_from")
    data_to: date | None = data.get("data_to")
    if data_from and data_to and data_from > data_to:
        raise ValueError("dates_order")
    return {**data, "person_ids": persons}


def save_grant(
    ctx: AccessContext, data: dict[str, Any], grant_id: UUID | None = None
) -> AccessGrant:
    """Create (``grant_id`` None) or change a grant of a role or an account."""
    ctx.require("admin", "manage")
    data = _check_grant(data)
    with keeping_admin(ctx):
        if grant_id is None:
            grant = AccessGrant.objects.create(**data)
        else:
            grant = get_object_or_404(AccessGrant, pk=grant_id)
            for k, v in data.items():
                setattr(grant, k, v)
            grant.save()
    return grant


def delete_grant(ctx: AccessContext, grant_id: UUID) -> None:
    ctx.require("admin", "manage")
    with keeping_admin(ctx):
        get_object_or_404(AccessGrant, pk=grant_id).delete()
