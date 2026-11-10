"""People writes.

* add a person / archive one: ``people:manage`` (parents);
* edit a person: ``people:edit`` *within that grant's people* — a child given
  "people: edit, self" can update only their own profile.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from django.core.exceptions import PermissionDenied
from django.utils import timezone

from .models import Person
from .selectors import get_person

if TYPE_CHECKING:
    from apps.access.context import AccessContext


def create_person(ctx: AccessContext, **fields: Any) -> Person:
    ctx.require("people", "manage")
    return Person.objects.create(**fields)


def update_person(ctx: AccessContext, person_id: UUID, **fields: Any) -> Person:
    if not ctx.has("people", "edit"):
        raise PermissionDenied("people:edit denied")
    person = get_person(ctx, person_id, level="edit")
    for k, v in fields.items():
        setattr(person, k, v)
    person.save()
    return person


def archive_person(ctx: AccessContext, person_id: UUID) -> None:
    ctx.require("people", "manage")
    person = get_person(ctx, person_id, level="manage")
    person.archived_at = timezone.now()
    person.save(update_fields=["archived_at", "updated_at"])
