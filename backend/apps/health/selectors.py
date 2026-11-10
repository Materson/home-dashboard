"""Health reads — scoped by person and by the grant's date window."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING
from uuid import UUID

from django.db.models import QuerySet
from django.http import Http404

from apps.people.models import Person

from .models import Appointment, Condition, DoseLog, Medication, MedicinePurchase, TestResult

if TYPE_CHECKING:
    from apps.access.context import AccessContext

# URL segment → (model, date lookup used for the grant's date window).
RECORDS = {
    "conditions": (Condition, "start_date"),
    "medications": (Medication, "start_date"),
    "purchases": (MedicinePurchase, "date"),
    "appointments": (Appointment, "starts_at__date"),
    "results": (TestResult, "date"),
}


def list_people(ctx: AccessContext) -> QuerySet[Person]:
    """People whose health data the caller may see (a child: only themself)."""
    qs = Person.objects.filter(archived_at__isnull=True)
    return ctx.scope_by_person(module="health", qs=qs, person_field="id")


def list_records(ctx: AccessContext, kind: str, *, person_id: UUID | None = None) -> QuerySet:
    model, date_field = RECORDS[kind]
    qs = ctx.scope_by_person(
        module="health",
        qs=model.objects.select_related("person"),
        person_field="person_id",
        date_field=date_field,
    )
    return qs.filter(person_id=person_id) if person_id else qs


def get_record(ctx: AccessContext, kind: str, record_id: UUID):
    """404 (not 403) for records outside the caller's scope — don't reveal them."""
    record = list_records(ctx, kind).filter(pk=record_id).first()
    if record is None:
        raise Http404("not found")
    return record


def list_doses(
    ctx: AccessContext, *, day: date, person_id: UUID | None = None
) -> QuerySet[DoseLog]:
    qs = ctx.scope_by_person(
        module="health",
        qs=DoseLog.objects.select_related("medication__person"),
        person_field="medication__person_id",
        date_field="scheduled_at__date",
    ).filter(scheduled_at__date=day)
    return qs.filter(medication__person_id=person_id) if person_id else qs


def get_dose(ctx: AccessContext, dose_id: UUID) -> DoseLog:
    dose = (
        ctx.scope_by_person(
            module="health",
            qs=DoseLog.objects.select_related("medication__person"),
            person_field="medication__person_id",
        )
        .filter(pk=dose_id)
        .first()
    )
    if dose is None:
        raise Http404("not found")
    return dose


__all__ = ["RECORDS", "Medication", "get_dose", "get_record", "list_doses", "list_people"]
