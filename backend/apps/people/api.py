from __future__ import annotations

from datetime import date
from uuid import UUID

from django.http import HttpRequest
from ninja import Router, Schema

from apps.access.context import get_ctx

from . import selectors
from .models import Person

router = Router()


class PersonOut(Schema):
    id: UUID
    display_name: str
    birth_date: date | None
    color: str


class PersonIn(Schema):
    display_name: str
    birth_date: date | None = None
    color: str = "#4c6ef5"


@router.get("/", response=list[PersonOut])
def list_people(request: HttpRequest) -> list[Person]:
    ctx = get_ctx(request)
    return list(selectors.list_people(ctx))


@router.post("/", response=PersonOut)
def create_person(request: HttpRequest, payload: PersonIn) -> Person:
    ctx = get_ctx(request)
    ctx.require("people", "manage")
    return Person.objects.create(**payload.dict())
