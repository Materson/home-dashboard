"""Note reads: only your own notes and those shared with you — a notes grant
only lets you *use* notes, it never shows anyone else's."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.db.models import Q, QuerySet
from django.http import Http404

from .models import Note

if TYPE_CHECKING:
    from apps.access.context import AccessContext


def _require(ctx: AccessContext) -> None:
    if not ctx.user_id or not ctx.has("notes", "view"):
        raise PermissionDenied("notes:view denied")


def _visible(ctx: AccessContext) -> QuerySet[Note]:
    return (
        Note.objects.filter(Q(owner_id=ctx.user_id) | Q(shares__user_id=ctx.user_id))
        .distinct()
        .select_related("owner__person")
        .prefetch_related("shares__user__person", "remind_others")
    )


def list_notes(
    ctx: AccessContext,
    *,
    scope: str = "all",
    q: str | None = None,
    archived: bool = False,
) -> QuerySet[Note]:
    """``scope``: all / mine / shared (with me). Archived notes only when asked."""
    _require(ctx)
    qs = _visible(ctx).filter(archived_at__isnull=not archived)
    if scope == "mine":
        qs = qs.filter(owner_id=ctx.user_id)
    elif scope == "shared":
        qs = qs.exclude(owner_id=ctx.user_id)
    if q:
        # Checklist text is JSON; a plain contains works on its serialized form.
        qs = qs.filter(Q(title__icontains=q) | Q(body__icontains=q) | Q(checklist__icontains=q))
    return qs


def get_note(ctx: AccessContext, note_id: UUID, level: str = "view") -> Note:
    """Someone else's private note answers 404, not 403 — no hint it exists."""
    _require(ctx)
    note = _visible(ctx).filter(pk=note_id).first()
    if note is None:
        raise Http404
    if level != "view" and not note.can_edit(ctx.user_id):
        raise PermissionDenied("view only")
    return note


def display_name(user) -> str:
    person = getattr(user, "person", None)
    return (person and person.display_name) or user.get_full_name() or user.email


def family_users(ctx: AccessContext) -> list:
    """People with a login (to share with / remind), you excluded."""
    _require(ctx)
    return list(
        get_user_model()
        .objects.filter(is_active=True, person__isnull=False, person__archived_at__isnull=True)
        .exclude(pk=ctx.user_id)
        .select_related("person")
        .order_by("person__display_name")
    )
