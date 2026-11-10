from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from django.db.models import QuerySet
from django.http import Http404

from .models import Person

if TYPE_CHECKING:
    from apps.access.context import AccessContext


def list_people(ctx: AccessContext) -> QuerySet[Person]:
    qs = Person.objects.filter(archived_at__isnull=True).select_related("user")
    return ctx.scope_by_person(module="people", qs=qs, person_field="id", level="view")


def get_person(ctx: AccessContext, person_id: UUID, level: str = "view") -> Person:
    """A person the caller may see (``level="edit"``: may edit) — 404 otherwise."""
    qs = Person.objects.filter(archived_at__isnull=True).select_related("user")
    person = (
        ctx.scope_by_person(module="people", qs=qs, person_field="id", level=level)
        .filter(pk=person_id)
        .first()
    )
    if person is None:
        raise Http404("not found")
    return person


def editable_person_ids(ctx: AccessContext) -> set[UUID]:
    """Ids of people the caller may edit (for the UI's edit buttons)."""
    return set(
        ctx.scope_by_person(
            module="people",
            qs=Person.objects.filter(archived_at__isnull=True),
            person_field="id",
            level="edit",
        ).values_list("id", flat=True)
    )
