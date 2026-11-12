from __future__ import annotations

from datetime import datetime
from uuid import UUID

from django.core import signing
from django.http import HttpRequest
from django.shortcuts import get_object_or_404
from ninja import Router, Schema


from . import actions, services
from .models import Reminder

router = Router()


class ReminderOut(Schema):
    id: UUID
    title: str
    body: str
    due_at: datetime | None
    status: str
    channels: list[str]
    link: str


@router.get("/upcoming", response=list[ReminderOut])
def upcoming(request: HttpRequest) -> list[Reminder]:
    user = request.user
    return list(
        Reminder.objects.filter(
            recipients=user,
            status__in=[Reminder.Status.SCHEDULED, Reminder.Status.SNOOZED],
            due_at__isnull=False,
        ).order_by("due_at")[:50]
    )


@router.post("/action", auth=None, response={200: dict, 400: dict})
def action(request: HttpRequest, token: str):
    """A notification button (Za 10 min / Zrobione), posted by the service
    worker. The signed token names one reminder and one action."""
    try:
        actions.apply(token)
    except (signing.BadSignature, Reminder.DoesNotExist):
        return 400, {"detail": "invalid or expired link"}
    return 200, {"ok": True}


class SnoozeIn(Schema):
    until: datetime


@router.post("/{reminder_id}/snooze")
def snooze(request: HttpRequest, reminder_id: UUID, payload: SnoozeIn) -> dict[str, bool]:
    reminder = get_object_or_404(Reminder, pk=reminder_id, recipients=request.user)
    services.snooze(reminder, payload.until)
    return {"ok": True}


@router.post("/{reminder_id}/done")
def done(request: HttpRequest, reminder_id: UUID) -> dict[str, bool]:
    reminder = get_object_or_404(Reminder, pk=reminder_id, recipients=request.user)
    services.mark_done(reminder)
    return {"ok": True}
