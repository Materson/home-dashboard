"""Admin-only API for managing grants (bulk/edit UI uses this).

Users read their own merged view via ``/api/me/permissions``."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from django.http import HttpRequest
from django.shortcuts import get_object_or_404
from ninja import Router, Schema

from .context import get_ctx
from .models import AccessGrant

router = Router()


class GrantOut(Schema):
    id: UUID
    user_id: int | None
    group_id: int | None
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


@router.get("/grants", response=list[GrantOut])
def list_grants(request: HttpRequest) -> list[AccessGrant]:
    get_ctx(request).require("admin", "manage")
    return list(AccessGrant.objects.all().order_by("module", "level"))


@router.post("/grants", response=GrantOut)
def create_grant(request: HttpRequest, payload: GrantIn) -> AccessGrant:
    get_ctx(request).require("admin", "manage")
    return AccessGrant.objects.create(**payload.dict())


@router.delete("/grants/{grant_id}")
def delete_grant(request: HttpRequest, grant_id: UUID) -> dict[str, bool]:
    get_ctx(request).require("admin", "manage")
    grant = get_object_or_404(AccessGrant, pk=grant_id)
    grant.delete()
    return {"deleted": True}
