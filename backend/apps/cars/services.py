"""Cars writes. Every record goes through ``save_record`` / ``delete_record``
so the side effects stay consistent:

1. permission check (``cars:edit``) and car visibility;
2. save;
3. mirror the cost into the finance ledger (or remove it when the cost is
   cleared) — authorized by *cars*, so finance access isn't needed;
4. re-plan reminders (oil change by km/date, inspection/insurance expiry);
5. fire distance-based reminders the new odometer value has reached.

Reminder texts are Polish — the household UI language.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import UUID

from dateutil.relativedelta import relativedelta
from django.contrib.auth import get_user_model
from django.db.transaction import atomic
from django.utils import timezone

from apps.finance import services as finance
from apps.reminders import services as reminders

from .models import Car, CarDeadline, FuelEntry, MaintenanceEvent, OilChange
from .selectors import RECORD_MODELS, current_odometer, get_car

if TYPE_CHECKING:
    from django.db import models

    from apps.access.context import AccessContext

OIL_REMIND_KM_BEFORE = 500
OIL_REMIND_DAYS_BEFORE = 7
DEADLINE_REMIND_DAYS_BEFORE = (14, 1)
REMINDER_CHANNELS = ("email", "webpush")
DEADLINE_CATEGORY = {
    CarDeadline.Kind.INSPECTION: "car.inspection",
    CarDeadline.Kind.INSURANCE: "car.insurance",
    CarDeadline.Kind.OTHER: "car.maintenance",
}
DEADLINE_LABEL = {
    CarDeadline.Kind.INSPECTION: "Przegląd techniczny",
    CarDeadline.Kind.INSURANCE: "Ubezpieczenie",
    CarDeadline.Kind.OTHER: "Termin",
}


# ---- cars --------------------------------------------------------------


def create_car(ctx: AccessContext, **fields: Any) -> Car:
    ctx.require("cars", "edit")
    return Car.objects.create(**fields)


def update_car(ctx: AccessContext, car_id: UUID, **fields: Any) -> Car:
    ctx.require("cars", "edit")
    car = get_car(ctx, car_id)
    for k, v in fields.items():
        setattr(car, k, v)
    car.save()
    return car


def set_archived(ctx: AccessContext, car_id: UUID, *, archived: bool) -> Car:
    ctx.require("cars", "edit")
    car = get_car(ctx, car_id)
    car.archived_at = timezone.now() if archived else None
    car.save(update_fields=["archived_at", "updated_at"])
    return car


# ---- records -----------------------------------------------------------


@atomic
def save_record(
    ctx: AccessContext,
    kind: str,
    car_id: UUID,
    data: dict[str, Any],
    record_id: UUID | None = None,
) -> models.Model:
    """Create (``record_id`` None) or update a record of ``kind`` for a car."""
    ctx.require("cars", "edit")
    car = get_car(ctx, car_id)
    model = RECORD_MODELS[kind]
    if record_id is None:
        record = model(car=car, created_by_id=ctx.user_id)
    else:
        record = model.objects.get(pk=record_id, car=car)
    for k, v in data.items():
        setattr(record, k, v)
    if isinstance(record, OilChange):
        _fill_oil_defaults(record, car)
    record.save()

    _sync_ledger(ctx, record, car)
    _sync_reminders(ctx, record, car)
    reminders.fire_odometer_reminders(car.id, current_odometer(car), OIL_REMIND_KM_BEFORE)
    return record


@atomic
def delete_record(ctx: AccessContext, kind: str, car_id: UUID, record_id: UUID) -> None:
    ctx.require("cars", "edit")
    car = get_car(ctx, car_id)
    record = RECORD_MODELS[kind].objects.get(pk=record_id, car=car)
    finance.delete_linked_transaction(record)
    reminders.cancel_for_target(record)
    record.delete()
    if isinstance(record, OilChange):
        _plan_oil_reminders(ctx, car)  # the previous change becomes the latest again


# ---- side effects ------------------------------------------------------


def _fill_oil_defaults(oil: OilChange, car: Car) -> None:
    """Next change due from the car's intervals unless given explicitly."""
    if oil.next_due_km is None and car.oil_interval_km:
        oil.next_due_km = oil.odometer_km + car.oil_interval_km
    if oil.next_due_date is None and car.oil_interval_months:
        oil.next_due_date = oil.date + relativedelta(months=car.oil_interval_months)


def _ledger_entry(record: models.Model, car: Car) -> tuple[str, Decimal, str] | None:
    """(category key, amount, transaction name) or None when there's no cost."""
    if isinstance(record, FuelEntry):
        rabat = f", rabat {record.discount}" if record.discount else ""
        return "car.fuel", record.total_cost, f"Paliwo — {car.name} ({record.litres} l{rabat})"
    if isinstance(record, MaintenanceEvent) and record.cost:
        return "car.maintenance", record.cost, f"{car.name}: {record.title}"
    if isinstance(record, OilChange) and record.cost:
        return "car.maintenance", record.cost, f"Wymiana oleju — {car.name}"
    if isinstance(record, CarDeadline) and record.cost:
        label = DEADLINE_LABEL[CarDeadline.Kind(record.kind)]
        return (
            DEADLINE_CATEGORY[CarDeadline.Kind(record.kind)],
            record.cost,
            f"{label} — {car.name}",
        )
    return None


def _sync_ledger(ctx: AccessContext, record: models.Model, car: Car) -> None:
    entry = _ledger_entry(record, car)
    if entry is None:
        finance.delete_linked_transaction(record)  # cost cleared on edit
        return
    category_key, amount, name = entry
    finance.upsert_linked_transaction(
        ctx,
        source_obj=record,
        category_key=category_key,
        amount=amount,
        currency=record.currency,
        occurred_on=record.date,
        name=name,
        person_id=car.owner_id,
        notes=record.notes,
        authorized_by="cars",
    )


def _sync_reminders(ctx: AccessContext, record: models.Model, car: Car) -> None:
    if isinstance(record, OilChange):
        _plan_oil_reminders(ctx, car)
    elif isinstance(record, CarDeadline):
        _plan_deadline_reminders(ctx, record, car)


def _recipients(ctx: AccessContext) -> list:
    return list(get_user_model().objects.filter(pk=ctx.user_id)) if ctx.user_id else []


def _morning(day: date) -> datetime:
    """09:00 local on ``day``, but never in the past (then: right away)."""
    when = timezone.make_aware(datetime.combine(day, time(9)))
    return max(when, timezone.now())


def _plan_oil_reminders(ctx: AccessContext, car: Car) -> None:
    """Only the latest oil change has live reminders."""
    changes = list(OilChange.objects.filter(car=car).order_by("-odometer_km", "-date"))
    for change in changes:
        reminders.cancel_for_target(change)
    recipients = _recipients(ctx)
    if not changes or not recipients:
        return
    latest = changes[0]
    due = " / ".join(
        part
        for part in (
            f"przy {latest.next_due_km} km" if latest.next_due_km else "",
            f"do {latest.next_due_date:%d.%m.%Y}" if latest.next_due_date else "",
        )
        if part
    )
    common = {
        "title": f"Wymiana oleju — {car.name}",
        "body": f"Następna wymiana oleju: {due}.",
        "target": latest,
        "recipients": recipients,
        "channels": REMINDER_CHANNELS,
    }
    if latest.next_due_km:
        reminders.schedule(ctx, **common, due_odometer_km=latest.next_due_km, car_id=car.id)
    if latest.next_due_date and latest.next_due_date >= timezone.localdate():
        reminders.schedule(
            ctx,
            **common,
            due_at=_morning(latest.next_due_date - timedelta(days=OIL_REMIND_DAYS_BEFORE)),
        )


def _plan_deadline_reminders(ctx: AccessContext, deadline: CarDeadline, car: Car) -> None:
    reminders.cancel_for_target(deadline)
    recipients = _recipients(ctx)
    if not recipients or deadline.valid_until < timezone.localdate():
        return
    label = DEADLINE_LABEL[CarDeadline.Kind(deadline.kind)]
    for days in DEADLINE_REMIND_DAYS_BEFORE:
        remind_on = deadline.valid_until - timedelta(days=days)
        if remind_on < timezone.localdate():
            continue  # that heads-up moment has already passed
        reminders.schedule(
            ctx,
            title=f"{label} — {car.name}",
            body=f"{label} ważne do {deadline.valid_until:%d.%m.%Y}.",
            target=deadline,
            recipients=recipients,
            channels=REMINDER_CHANNELS,
            due_at=_morning(remind_on),
        )
