"""Note writes. Editing needs the owner or an edit share; sharing, archiving
and deleting are the owner's. A note's reminder is (re)planned on every save;
a repeating one is rolled forward by a beat job once it has fired."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from dateutil.rrule import DAILY, MONTHLY, WEEKLY, rrule
from django.core.exceptions import PermissionDenied
from django.db.transaction import atomic
from django.utils import timezone

from apps.core import attachments
from apps.reminders import actions as reminder_actions
from apps.reminders import services as reminders

from . import quickadd
from .models import Note, NoteShare
from .selectors import _require, family_users, get_note

if TYPE_CHECKING:
    from apps.access.context import AccessContext

_FREQ = {"daily": DAILY, "weekly": WEEKLY, "monthly": MONTHLY}
MAX_CHECKLIST = 200


def _require_edit(ctx: AccessContext) -> None:
    _require(ctx)
    ctx.require("notes", "edit")


def _clean_checklist(items: list[dict]) -> list[dict]:
    out = []
    for it in (items or [])[:MAX_CHECKLIST]:
        text = " ".join(str(it.get("text", "")).split())[:300]
        if text:
            out.append({"text": text, "done": bool(it.get("done"))})
    return out


def _family_ids(ctx: AccessContext) -> set:
    return {u.pk for u in family_users(ctx)}


@atomic
def save_note(ctx: AccessContext, data: dict[str, Any], note_id: UUID | None = None) -> Note:
    _require_edit(ctx)
    note = get_note(ctx, note_id, "edit") if note_id else Note(owner_id=ctx.user_id)
    others = data.pop("remind_others", None)
    for k, v in data.items():
        setattr(note, k, v)
    note.title = " ".join(note.title.split())
    note.checklist = _clean_checklist(note.checklist)
    if not (note.title or note.body.strip() or note.checklist):
        raise ValueError("the note is empty")
    if note.remind_at:
        note.remind_at = note.remind_at.replace(second=0, microsecond=0)  # whole minutes
    else:
        note.repeat = ""
    note.save()

    if others is not None:
        allowed = _family_ids(ctx) | {note.owner_id}
        if not set(others) <= allowed:
            raise ValueError("can only remind family members")
        others = [u for u in others if u != note.owner_id]
        note.remind_others.set(others)
        # Whoever gets reminded can at least read the note.
        for uid in others:
            NoteShare.objects.get_or_create(note=note, user_id=uid)
    _plan_reminder(note)
    return get_note(ctx, note.id)


@atomic
def quick_add(ctx: AccessContext, text: str) -> Note:
    """One line → a note, with a reminder when it names a time."""
    parsed = quickadd.parse(text, timezone.localtime())
    data = {
        "title": parsed.title or " ".join(text.split()),
        "remind_at": parsed.remind_at,
        "repeat": parsed.repeat,
    }
    return save_note(ctx, data)


@atomic
def set_shares(ctx: AccessContext, note_id: UUID, shares: list[dict]) -> Note:
    """Replace who the note is shared with: [{"user_id": …, "can_edit": …}]."""
    _require_edit(ctx)
    note = get_note(ctx, note_id)
    if note.owner_id != ctx.user_id:
        raise PermissionDenied("only the owner shares a note")
    wanted = {
        s["user_id"]: bool(s.get("can_edit")) for s in shares if s["user_id"] != note.owner_id
    }
    if not set(wanted) <= _family_ids(ctx):
        raise ValueError("can only share with family members")
    note.shares.exclude(user_id__in=wanted).delete()
    for uid, can_edit in wanted.items():
        NoteShare.objects.update_or_create(note=note, user_id=uid, defaults={"can_edit": can_edit})
    # No longer shared → no longer reminded.
    note.remind_others.remove(*[u for u in note.remind_others.all() if u.pk not in wanted])
    _plan_reminder(note)
    return get_note(ctx, note.id)


def toggle_item(ctx: AccessContext, note_id: UUID, index: int, done: bool) -> Note:
    """Tick one checklist line (without resending the whole note)."""
    _require_edit(ctx)
    with atomic():
        note = get_note(ctx, note_id, "edit")
        note = Note.objects.select_for_update().get(pk=note.pk)
        if not 0 <= index < len(note.checklist):
            raise ValueError("no such checklist item")
        note.checklist[index]["done"] = done
        note.save(update_fields=["checklist", "updated_at"])
    return get_note(ctx, note_id)


def _owned(ctx: AccessContext, note_id: UUID) -> Note:
    _require_edit(ctx)
    note = get_note(ctx, note_id)
    if note.owner_id != ctx.user_id:
        raise PermissionDenied("only the owner can do this")
    return note


@atomic
def archive(ctx: AccessContext, note_id: UUID, archived: bool = True) -> Note:
    note = _owned(ctx, note_id)
    note.archived_at = timezone.now() if archived else None
    note.save(update_fields=["archived_at", "updated_at"])
    _plan_reminder(note)
    return get_note(ctx, note.id)


@atomic
def delete_note(ctx: AccessContext, note_id: UUID) -> None:
    note = _owned(ctx, note_id)
    reminders.cancel_for_target(note)
    attachments.delete_all_for(note)
    note.delete()


def set_pinned(ctx: AccessContext, note_id: UUID, pinned: bool) -> Note:
    """Pin to the top of the list (saved at once). Anyone who may edit the
    note may pin it; it doesn't count as an edit (``updated_at`` stays)."""
    _require_edit(ctx)
    note = get_note(ctx, note_id, "edit")
    note.pinned = pinned
    note.save(update_fields=["pinned"])
    return get_note(ctx, note.id)


BULK_ACTIONS = ("archive", "unarchive", "delete")


@atomic
def bulk(ctx: AccessContext, note_ids: list[UUID], action: str) -> int:
    """Archive / restore / delete several of *your own* notes at once —
    all or nothing (one note that isn't yours stops the whole batch)."""
    if action not in BULK_ACTIONS:
        raise ValueError(f"unknown action {action!r}")
    notes = [_owned(ctx, nid) for nid in dict.fromkeys(note_ids)]
    for note in notes:
        if action == "delete":
            reminders.cancel_for_target(note)
            attachments.delete_all_for(note)
            note.delete()
        else:
            note.archived_at = timezone.now() if action == "archive" else None
            note.save(update_fields=["archived_at", "updated_at"])
            _plan_reminder(note)
    return len(notes)


# -------------------- Reminders --------------------


def _recipients(note: Note) -> list:
    users = [note.owner, *note.remind_others.all()]
    return [u for u in users if u.is_active]


def _summary(note: Note) -> str:
    if note.body.strip():
        return note.body.strip()[:200]
    open_items = [i["text"] for i in note.checklist if not i["done"]]
    return ", ".join(open_items)[:200]


def _schedule(note: Note, when: datetime) -> None:
    reminder = reminders.schedule(
        None,  # the note's rules were checked when it was saved
        title=note.title or "Przypomnienie",
        body=_summary(note),
        target=note,
        recipients=_recipients(note),
        channels=("webpush",),
        due_at=when,
        link=f"/notes?open={note.pk}",
    )
    reminder_actions.add_buttons(reminder)


def _plan_reminder(note: Note) -> None:
    """Replace the note's pending reminder with one for ``remind_at``."""
    reminders.cancel_for_target(note)
    if note.archived_at or not note.remind_at:
        return
    if note.remind_at > timezone.now():
        _schedule(note, note.remind_at)
    elif note.repeat:
        roll_forward(note)


def next_occurrence(note: Note, after: datetime) -> datetime | None:
    if not note.repeat or not note.remind_at:
        return None
    start = timezone.localtime(note.remind_at).replace(tzinfo=None)
    local_after = timezone.localtime(after).replace(tzinfo=None)
    nxt = rrule(_FREQ[note.repeat], dtstart=start).after(local_after)
    return timezone.make_aware(nxt) if nxt else None


def roll_forward(note: Note, now: datetime | None = None) -> None:
    """A repeating note whose time has passed moves to its next time, with a
    new reminder (the fired one — maybe snoozed — is left alone)."""
    now = now or timezone.now()
    nxt = next_occurrence(note, now)
    if nxt is None:
        return
    note.remind_at = nxt
    note.save(update_fields=["remind_at"])
    _schedule(note, nxt)


def roll_due_repeats() -> int:
    """Beat job (every few minutes)."""
    now = timezone.now()
    due = (
        Note.objects.filter(archived_at__isnull=True, remind_at__lte=now)
        .exclude(repeat="")
        .select_related("owner")
    )
    count = 0
    for note in due:
        roll_forward(note, now)
        count += 1
    return count
