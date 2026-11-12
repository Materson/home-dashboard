"""Notes REST API — thin wrappers over selectors/services."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from django.contrib.contenttypes.models import ContentType
from django.http import HttpRequest
from django.utils import timezone
from ninja import Router, Schema

from apps.access.context import get_ctx
from apps.core.models import Attachment

from . import quickadd, selectors, services

router = Router()


class ChecklistItem(Schema):
    text: str
    done: bool = False


class NoteIn(Schema):
    title: str = ""
    body: str = ""
    checklist: list[ChecklistItem] = []
    pinned: bool = False
    remind_at: datetime | None = None  # local time when sent without an offset
    repeat: Literal["", "daily", "weekly", "monthly"] = ""
    remind_others: list[int] = []  # user ids


class ShareOut(Schema):
    user_id: int
    name: str
    can_edit: bool


class NoteOut(Schema):
    id: UUID
    title: str
    body: str
    checklist: list[ChecklistItem]
    pinned: bool
    remind_at: datetime | None
    repeat: str
    remind_others: list[int]
    owner_id: int
    owner_name: str
    is_owner: bool
    can_edit: bool
    shares: list[ShareOut]
    attachments: int
    archived: bool
    updated_at: datetime


def _out(note, user_id: int) -> dict[str, Any]:
    ct = ContentType.objects.get_for_model(type(note))
    return {
        "id": note.id,
        "title": note.title,
        "body": note.body,
        "checklist": note.checklist,
        "pinned": note.pinned,
        "remind_at": timezone.localtime(note.remind_at) if note.remind_at else None,
        "repeat": note.repeat,
        "remind_others": [u.pk for u in note.remind_others.all()],
        "owner_id": note.owner_id,
        "owner_name": selectors.display_name(note.owner),
        "is_owner": note.owner_id == user_id,
        "can_edit": note.can_edit(user_id),
        "shares": [
            {"user_id": s.user_id, "name": selectors.display_name(s.user), "can_edit": s.can_edit}
            for s in note.shares.all()
        ],
        "attachments": Attachment.objects.filter(content_type=ct, object_id=note.pk).count(),
        "archived": note.archived_at is not None,
        "updated_at": note.updated_at,
    }


def _local(value: datetime | None) -> datetime | None:
    if value is not None and timezone.is_naive(value):
        return timezone.make_aware(value)
    return value


@router.get("/", response=list[NoteOut])
def list_notes(
    request: HttpRequest,
    scope: Literal["all", "mine", "shared"] = "all",
    q: str | None = None,
    archived: bool = False,
) -> list[dict]:
    ctx = get_ctx(request)
    notes = selectors.list_notes(ctx, scope=scope, q=q, archived=archived)
    return [_out(n, ctx.user_id) for n in notes]


@router.post("/", response={200: NoteOut, 422: dict})
def create_note(request: HttpRequest, payload: NoteIn):
    ctx = get_ctx(request)
    data = payload.dict()
    data["remind_at"] = _local(data["remind_at"])
    try:
        return _out(services.save_note(ctx, data), ctx.user_id)
    except ValueError as exc:
        return 422, {"detail": str(exc)}


class QuickIn(Schema):
    text: str


class ParsedOut(Schema):
    title: str
    remind_at: datetime | None
    repeat: str


@router.post("/quick", response={200: NoteOut, 422: dict})
def quick_add(request: HttpRequest, payload: QuickIn):
    """One line, e.g. "jutro 18:00 kupić mleko" — the time becomes a reminder."""
    ctx = get_ctx(request)
    try:
        return _out(services.quick_add(ctx, payload.text), ctx.user_id)
    except ValueError as exc:
        return 422, {"detail": str(exc)}


class BulkIn(Schema):
    ids: list[UUID]
    action: Literal["archive", "unarchive", "delete"]


# Before the "/{note_id}" routes, or "bulk" would be taken for an id (405).
@router.post("/bulk", response={200: dict, 422: dict})
def bulk(request: HttpRequest, payload: BulkIn):
    """Archive / restore / delete several of your own notes."""
    try:
        return {"count": services.bulk(get_ctx(request), payload.ids, payload.action)}
    except ValueError as exc:
        return 422, {"detail": str(exc)}


@router.get("/parse", response=ParsedOut)
def parse(request: HttpRequest, text: str) -> Any:
    """Preview what quick add will understand (no saving)."""
    p = quickadd.parse(text, timezone.localtime())
    return {"title": p.title, "remind_at": p.remind_at, "repeat": p.repeat}


class PersonOut(Schema):
    user_id: int
    name: str
    color: str


@router.get("/people", response=list[PersonOut])
def people(request: HttpRequest) -> list[dict]:
    """Family members with a login — to share with or remind."""
    return [
        {"user_id": u.pk, "name": u.person.display_name, "color": u.person.color}
        for u in selectors.family_users(get_ctx(request))
    ]


@router.get("/{note_id}", response=NoteOut)
def get_note(request: HttpRequest, note_id: UUID) -> dict:
    ctx = get_ctx(request)
    return _out(selectors.get_note(ctx, note_id), ctx.user_id)


@router.put("/{note_id}", response={200: NoteOut, 422: dict})
def update_note(request: HttpRequest, note_id: UUID, payload: NoteIn):
    ctx = get_ctx(request)
    data = payload.dict()
    data["remind_at"] = _local(data["remind_at"])
    try:
        return _out(services.save_note(ctx, data, note_id), ctx.user_id)
    except ValueError as exc:
        return 422, {"detail": str(exc)}


@router.delete("/{note_id}")
def delete_note(request: HttpRequest, note_id: UUID) -> dict[str, bool]:
    services.delete_note(get_ctx(request), note_id)
    return {"deleted": True}


class ArchiveIn(Schema):
    archived: bool = True


@router.post("/{note_id}/archive", response=NoteOut)
def archive(request: HttpRequest, note_id: UUID, payload: ArchiveIn) -> dict:
    ctx = get_ctx(request)
    return _out(services.archive(ctx, note_id, payload.archived), ctx.user_id)


class PinIn(Schema):
    pinned: bool


@router.post("/{note_id}/pin", response=NoteOut)
def pin(request: HttpRequest, note_id: UUID, payload: PinIn) -> dict:
    ctx = get_ctx(request)
    return _out(services.set_pinned(ctx, note_id, payload.pinned), ctx.user_id)


class ToggleIn(Schema):
    done: bool


@router.post("/{note_id}/checklist/{index}", response={200: NoteOut, 422: dict})
def toggle_item(request: HttpRequest, note_id: UUID, index: int, payload: ToggleIn):
    ctx = get_ctx(request)
    try:
        return _out(services.toggle_item(ctx, note_id, index, payload.done), ctx.user_id)
    except ValueError as exc:
        return 422, {"detail": str(exc)}


class ShareIn(Schema):
    user_id: int
    can_edit: bool = False


@router.put("/{note_id}/shares", response={200: NoteOut, 422: dict})
def set_shares(request: HttpRequest, note_id: UUID, payload: list[ShareIn]):
    ctx = get_ctx(request)
    try:
        return _out(services.set_shares(ctx, note_id, [s.dict() for s in payload]), ctx.user_id)
    except ValueError as exc:
        return 422, {"detail": str(exc)}
