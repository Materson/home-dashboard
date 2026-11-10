from __future__ import annotations

from datetime import date
from uuid import UUID

from django.http import HttpRequest
from ninja import Router, Schema

from apps.access.context import get_ctx

from . import selectors, services
from .models import Person

router = Router()


class PersonIn(Schema):
    display_name: str
    birth_date: date | None = None
    color: str = "#4c6ef5"


class PersonOut(PersonIn):
    id: UUID
    has_login: bool
    # What the caller may do with this person (drives the UI buttons).
    can_edit: bool

    @staticmethod
    def resolve_has_login(obj: Person) -> bool:
        return obj.user_id is not None


@router.get("/", response=list[PersonOut])
def list_people(request: HttpRequest) -> list[Person]:
    ctx = get_ctx(request)
    editable = selectors.editable_person_ids(ctx)
    people = list(selectors.list_people(ctx))
    for p in people:
        p.can_edit = p.id in editable
    return people


@router.post("/", response=PersonOut)
def create_person(request: HttpRequest, payload: PersonIn) -> Person:
    person = services.create_person(get_ctx(request), **payload.dict())
    person.can_edit = True
    return person


@router.put("/{person_id}", response=PersonOut)
def update_person(request: HttpRequest, person_id: UUID, payload: PersonIn) -> Person:
    person = services.update_person(get_ctx(request), person_id, **payload.dict())
    person.can_edit = True
    return person


@router.delete("/{person_id}")
def archive_person(request: HttpRequest, person_id: UUID) -> dict[str, bool]:
    services.archive_person(get_ctx(request), person_id)
    return {"archived": True}
