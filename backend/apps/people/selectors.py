from __future__ import annotations

from typing import TYPE_CHECKING

from django.db.models import QuerySet

from .models import Person

if TYPE_CHECKING:
    from apps.access.context import AccessContext


def list_people(ctx: "AccessContext") -> QuerySet[Person]:
    qs = Person.objects.filter(archived_at__isnull=True)
    return ctx.scope_by_person(module="people", qs=qs, person_field="id", level="view")
