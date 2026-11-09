"""Reminder service layer. The only way other apps create reminders."""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Sequence

from dateutil.rrule import rrulestr
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.transaction import atomic
from django.utils import timezone

from .models import Reminder

if TYPE_CHECKING:
    from apps.access.context import AccessContext
    from apps.accounts.models import User


@atomic
def schedule(
    ctx: "AccessContext",
    *,
    title: str,
    body: str = "",
    target: models.Model | None = None,
    recipients: Sequence["User"],
    channels: Sequence[str],
    due_at: datetime | None = None,
    due_odometer_km: int | None = None,
    car_id: str | None = None,
    sensitivity: str = "normal",
    recurrence: str | None = None,  # RFC-5545 RRULE string
) -> Reminder:
    """Create a Reminder (and its next occurrences if ``recurrence`` is set)."""
    if not any([due_at, due_odometer_km]):
        raise ValueError("either due_at or due_odometer_km is required")
    if due_odometer_km and not car_id:
        raise ValueError("car_id is required with due_odometer_km")

    ct = ContentType.objects.get_for_model(type(target)) if target else None
    oid = getattr(target, "pk", None)

    reminder = Reminder.objects.create(
        title=title,
        body=body,
        content_type=ct,
        object_id=oid,
        due_at=due_at,
        due_odometer_km=due_odometer_km,
        car_id=car_id,
        channels=list(channels),
        sensitivity=sensitivity,
    )
    reminder.recipients.set(recipients)

    if recurrence and due_at:
        # Materialize the next three occurrences; beat will top them up.
        rule = rrulestr(recurrence, dtstart=due_at)
        for occurrence in list(rule)[1:4]:
            Reminder.objects.create(
                title=title,
                body=body,
                content_type=ct,
                object_id=oid,
                due_at=occurrence,
                channels=list(channels),
                sensitivity=sensitivity,
            ).recipients.set(recipients)
    return reminder


def mark_sent(reminder: Reminder) -> None:
    reminder.status = Reminder.Status.SENT
    reminder.sent_at = timezone.now()
    reminder.save(update_fields=["status", "sent_at"])


def snooze(reminder: Reminder, until: datetime) -> None:
    reminder.status = Reminder.Status.SNOOZED
    reminder.snoozed_until = until
    reminder.due_at = until
    reminder.save(update_fields=["status", "snoozed_until", "due_at"])


def mark_done(reminder: Reminder) -> None:
    reminder.status = Reminder.Status.DONE
    reminder.done_at = timezone.now()
    reminder.save(update_fields=["status", "done_at"])
