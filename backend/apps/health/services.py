"""Health writes. One save/delete path for every record type:

permission (``health:edit`` on the record's person, after the person is set,
so a record can't be moved to someone the caller may not edit) → save →
costs to Finance (appointment fees) → reminders
(appointments) / dose planning (medications).

Marking a dose taken only needs ``health:view`` on that person — a child
with read access to their own health can still confirm their own doses.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import TYPE_CHECKING, Any
from uuid import UUID

from django.contrib.auth import get_user_model
from django.db import models
from django.db.transaction import atomic
from django.utils import timezone

from apps.core import attachments
from apps.finance import services as finance
from apps.reminders import services as reminders

from . import doses
from .models import (
    Appointment,
    CabinetItem,
    Condition,
    DoseLog,
    Medication,
    MedicinePackage,
    Symptom,
)
from .selectors import RECORDS, get_cabinet_item, get_dose, get_package, get_record

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
    if isinstance(record, Symptom) and timezone.is_naive(record.observed_at):
        record.observed_at = timezone.make_aware(record.observed_at)
    ctx.require("health", "edit", record)  # after setting the person
    if isinstance(record, Medication):
        _link_cabinet_item(ctx, record)
    _validate(record)
    record.save()

    if isinstance(record, Appointment):
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
    _check_same_person_condition(record)
    if isinstance(record, Medication):
        record.dose_times = [t.strftime("%H:%M") for t in doses.parse_times(record.dose_times)]
        if record.end_date and record.end_date < record.start_date:
            raise ValueError("end date is before start date")
    if isinstance(record, Condition) and record.end_date and record.end_date < record.start_date:
        raise ValueError("end date is before start date")
    if isinstance(record, Symptom):
        record.symptom = " ".join(record.symptom.split())
        if not record.symptom:
            raise ValueError("symptom is empty")


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


# ---- Medicine cabinet --------------------------------------------------------

EXPIRY_REMIND_DAYS_BEFORE = 7


def save_cabinet_item(
    ctx: AccessContext, data: dict[str, Any], item_id: UUID | None = None
) -> CabinetItem:
    ctx.require("health", "edit")
    item = get_cabinet_item(ctx, item_id) if item_id else CabinetItem(created_by_id=ctx.user_id)
    for k, v in data.items():
        setattr(item, k, v)
    item.save()
    return item


@atomic
def delete_cabinet_item(ctx: AccessContext, item_id: UUID) -> None:
    ctx.require("health", "edit")
    item = get_cabinet_item(ctx, item_id)
    for package in item.packages.all():
        reminders.cancel_for_target(package)
    item.delete()


@atomic
def save_package(
    ctx: AccessContext,
    data: dict[str, Any],
    *,
    item_id: UUID | None = None,
    package_id: UUID | None = None,
) -> MedicinePackage:
    """Create a box for ``item_id`` or update box ``package_id``; re-plans
    its expiry reminder (opening a box usually brings the expiry forward)."""
    ctx.require("health", "edit")
    if package_id:
        package = get_package(ctx, package_id)
    else:
        package = MedicinePackage(item=get_cabinet_item(ctx, item_id), created_by_id=ctx.user_id)
    for k, v in data.items():
        setattr(package, k, v)
    if package.opened_on and package.expiry_date and package.opened_on > package.expiry_date:
        raise ValueError("opened after the printed expiry date")
    package.save()
    _plan_expiry_reminder(ctx, package)
    return package


def delete_package(ctx: AccessContext, package_id: UUID) -> None:
    ctx.require("health", "edit")
    package = get_package(ctx, package_id)
    reminders.cancel_for_target(package)
    package.delete()


def _plan_expiry_reminder(ctx: AccessContext, package: MedicinePackage) -> None:
    reminders.cancel_for_target(package)
    expiry = package.effective_expiry
    today = timezone.localdate()
    if package.finished_on or expiry is None or expiry < today or not ctx.user_id:
        return
    remind_on = max(today, expiry - timedelta(days=EXPIRY_REMIND_DAYS_BEFORE))
    when = max(timezone.make_aware(datetime.combine(remind_on, time(9))), timezone.now())
    reminders.schedule(
        ctx,
        # Household cabinet, not someone's diagnosis: the name is fine here.
        title=f"Lek traci ważność: {package.item.name}",
        body=f"Opakowanie jest ważne do {expiry:%d.%m.%Y}.",
        target=package,
        recipients=list(get_user_model().objects.filter(pk=ctx.user_id)),
        channels=("webpush", "email"),
        due_at=when,
    )


def _check_same_person_condition(record: models.Model) -> None:
    """Visits, treatments and symptoms may only point at the same person's illness."""
    condition_id = getattr(record, "condition_id", None)
    if (
        condition_id
        and not Condition.objects.filter(pk=condition_id, person_id=record.person_id).exists()
    ):
        raise ValueError("the illness belongs to someone else")


def _link_cabinet_item(ctx: AccessContext, med: Medication) -> None:
    """Every treatment uses a medicine from the cabinet: an explicit
    ``cabinet_item`` wins (its name is mirrored), otherwise the typed name is
    matched case-insensitively, and a new medicine is added to the cabinet."""
    if med.cabinet_item_id:
        med.name = get_cabinet_item(ctx, med.cabinet_item_id).name
        return
    name = (med.name or "").strip()
    if not name:
        raise ValueError("medicine name is required")
    item = CabinetItem.objects.filter(name__iexact=name).first() or CabinetItem.objects.create(
        name=name, created_by_id=ctx.user_id
    )
    med.cabinet_item = item
    med.name = item.name
