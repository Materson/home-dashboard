"""Health writes. One save/delete path for every record type:

permission (``health:edit`` on the record's person, after the person is set,
so a record can't be moved to someone the caller may not edit) → save →
costs to Finance (medicine purchases, appointment fees) → reminders
(appointments) / dose planning (medications).

Marking a dose taken only needs ``health:view`` on that person — a child
with read access to their own health can still confirm their own doses.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import TYPE_CHECKING, Any
from uuid import UUID

from django.db import models
from django.db.transaction import atomic
from django.utils import timezone

from apps.core import attachments
from apps.finance import services as finance
from apps.reminders import services as reminders

from . import doses
from .models import Appointment, Condition, DoseLog, Medication, MedicinePurchase
from .selectors import RECORDS, get_dose, get_record

if TYPE_CHECKING:
    from apps.access.context import AccessContext

APPOINTMENT_REMIND_EVENING_BEFORE = time(18, 0)
APPOINTMENT_REMIND_BEFORE = timedelta(hours=2)


@atomic
def save_record(
    ctx: AccessContext, kind: str, data: dict[str, Any], record_id: UUID | None = None
) -> models.Model:
    model, _ = RECORDS[kind]
    record = get_record(ctx, kind, record_id) if record_id else model(created_by_id=ctx.user_id)
    for k, v in data.items():
        setattr(record, k, v)
    if isinstance(record, Appointment) and timezone.is_naive(record.starts_at):
        record.starts_at = timezone.make_aware(record.starts_at)  # local time from the form
    ctx.require("health", "edit", record)  # after setting the person
    _validate(record)
    record.save()

    if isinstance(record, MedicinePurchase):
        _sync_ledger(ctx, record, "health.medicines", f"Leki — {record.name}", record.date)
    elif isinstance(record, Appointment):
        what = record.specialty or record.doctor or "wizyta"
        _sync_ledger(
            ctx,
            record,
            "health.appointments",
            f"Wizyta — {what}",
            timezone.localdate(record.starts_at),
        )
        _plan_appointment_reminders(record)
    elif isinstance(record, Medication):
        doses.plan_doses(record, replace=True)
    return record


@atomic
def delete_record(ctx: AccessContext, kind: str, record_id: UUID) -> None:
    record = get_record(ctx, kind, record_id)
    ctx.require("health", "edit", record)
    finance.delete_linked_transaction(record)
    reminders.cancel_for_target(record)
    if isinstance(record, Medication):
        for dose in record.doses.all():
            reminders.cancel_for_target(dose)
    attachments.delete_all_for(record)
    record.delete()


def set_dose_status(ctx: AccessContext, dose_id: UUID, status: str) -> DoseLog:
    dose = get_dose(ctx, dose_id)
    ctx.require("health", "view", dose)
    return doses.set_status(dose, status)


# ---- helpers ---------------------------------------------------------------


def _validate(record: models.Model) -> None:
    if isinstance(record, Medication):
        record.dose_times = [t.strftime("%H:%M") for t in doses.parse_times(record.dose_times)]
        if record.end_date and record.end_date < record.start_date:
            raise ValueError("end date is before start date")
        if (
            record.condition_id
            and not Condition.objects.filter(
                pk=record.condition_id, person_id=record.person_id
            ).exists()
        ):
            raise ValueError("the illness belongs to someone else")
    if isinstance(record, Condition) and record.end_date and record.end_date < record.start_date:
        raise ValueError("end date is before start date")


def _sync_ledger(ctx: AccessContext, record, category_key: str, name: str, on) -> None:
    if not getattr(record, "cost", None):
        finance.delete_linked_transaction(record)
        return
    finance.upsert_linked_transaction(
        ctx,
        source_obj=record,
        category_key=category_key,
        amount=record.cost,
        currency=record.currency,
        occurred_on=on,
        name=name,
        person_id=record.person_id,
        authorized_by="health",
    )


def _recipients(record) -> list:
    users = {u for u in (record.created_by, getattr(record.person, "user", None)) if u}
    return [u for u in users if u.is_active]


def _plan_appointment_reminders(appt: Appointment) -> None:
    reminders.cancel_for_target(appt)
    now = timezone.now()
    recipients = _recipients(appt)
    if appt.status != Appointment.Status.PLANNED or appt.starts_at <= now or not recipients:
        return
    local_day = timezone.localdate(appt.starts_at)
    evening_before = timezone.make_aware(
        datetime.combine(local_day - timedelta(days=1), APPOINTMENT_REMIND_EVENING_BEFORE)
    )
    for when, title in (
        (evening_before, "Jutro wizyta lekarska"),
        (appt.starts_at - APPOINTMENT_REMIND_BEFORE, "Wizyta lekarska za 2 godziny"),
    ):
        if when <= now:
            continue
        reminders.schedule(
            None,
            title=title,  # generic — details stay in the app
            body="Otwórz panel, aby zobaczyć szczegóły.",
            target=appt,
            recipients=recipients,
            channels=("webpush", "email"),
            due_at=when,
            sensitivity="private",
        )
