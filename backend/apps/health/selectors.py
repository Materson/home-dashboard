"""Health reads — scoped by person and by the grant's date window."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from django.db.models import Q, QuerySet
from django.http import Http404
from django.utils import timezone

from apps.people.models import Person

from . import dosing
from .models import (
    Appointment,
    CabinetItem,
    Condition,
    DoseLog,
    Measurement,
    Medication,
    MedicinePackage,
    Symptom,
    TestResult,
)

if TYPE_CHECKING:
    from apps.access.context import AccessContext

# URL segment → (model, date lookup used for the grant's date window).
RECORDS = {
    "conditions": (Condition, "start_date"),
    "medications": (Medication, "start_date"),
    "appointments": (Appointment, "starts_at__date"),
    "results": (TestResult, "date"),
    "measurements": (Measurement, "date"),
    "symptoms": (Symptom, "observed_at__date"),
}


def list_people(ctx: AccessContext) -> QuerySet[Person]:
    """People whose health data the caller may see (a child: only themself)."""
    qs = Person.objects.filter(archived_at__isnull=True)
    return ctx.scope_by_person(module="health", qs=qs, person_field="id")


def list_records(
    ctx: AccessContext,
    kind: str,
    *,
    person_id: UUID | None = None,
    condition_id: UUID | None = None,
    cabinet_item_id: UUID | None = None,
) -> QuerySet:
    """One record type in the caller's scope; optionally for one person, one
    illness/event (visits, treatments) or one cabinet medicine (treatments)."""
    model, date_field = RECORDS[kind]
    qs = ctx.scope_by_person(
        module="health",
        qs=model.objects.select_related("person"),
        person_field="person_id",
        date_field=date_field,
    )
    if person_id:
        qs = qs.filter(person_id=person_id)
    if condition_id and hasattr(model, "condition"):
        qs = qs.filter(condition_id=condition_id)
    if cabinet_item_id and hasattr(model, "cabinet_item"):
        qs = qs.filter(cabinet_item_id=cabinet_item_id)
    return qs


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


# ---- Medicine cabinet --------------------------------------------------------

EXPIRING_SOON_DAYS = 30


def package_status(package: MedicinePackage, today: date) -> str:
    """finished | expired | soon | ok | unknown"""
    if package.finished_on:
        return "finished"
    expiry = package.effective_expiry
    if expiry is None:
        return "unknown"
    if expiry < today:
        return "expired"
    if (expiry - today).days <= EXPIRING_SOON_DAYS:
        return "soon"
    return "ok"


def list_cabinet(
    ctx: AccessContext,
    *,
    q: str | None = None,
    for_whom: str | None = None,
    include_finished: bool = False,
) -> list[CabinetItem]:
    """Household medicines (any health access may read them). ``q`` matches
    name, substance, what it's for and notes; ``for_whom="children"`` also
    includes medicines for everyone. Each item gets ``shown_packages``."""
    if not ctx.has("health", "view"):
        return []
    qs = CabinetItem.objects.prefetch_related("packages")
    if q:
        qs = qs.filter(
            Q(name__icontains=q)
            | Q(substance__icontains=q)
            | Q(indications__icontains=q)
            | Q(notes__icontains=q)
        )
    if for_whom in (CabinetItem.ForWhom.CHILDREN, CabinetItem.ForWhom.ADULTS):
        qs = qs.filter(for_whom__in=[for_whom, CabinetItem.ForWhom.EVERYONE])
    items = list(qs)
    for item in items:
        packages = list(item.packages.all())
        item.shown_packages = [p for p in packages if include_finished or not p.finished_on]
    return items


def get_cabinet_item(ctx: AccessContext, item_id: UUID) -> CabinetItem:
    if not ctx.has("health", "view"):
        raise Http404("not found")
    item = CabinetItem.objects.filter(pk=item_id).first()
    if item is None:
        raise Http404("not found")
    return item


def get_package(ctx: AccessContext, package_id: UUID) -> MedicinePackage:
    if not ctx.has("health", "view"):
        raise Http404("not found")
    package = MedicinePackage.objects.select_related("item").filter(pk=package_id).first()
    if package is None:
        raise Http404("not found")
    return package


def age_in_months(birth_date: date | None, today: date) -> int | None:
    if birth_date is None:
        return None
    months = (today.year - birth_date.year) * 12 + today.month - birth_date.month
    return months - (1 if today.day < birth_date.day else 0)


def dose_for(
    ctx: AccessContext,
    item_id: UUID,
    weight_kg: Decimal,
    *,
    person_id: UUID | None = None,
    today: date | None = None,
) -> dosing.DoseResult:
    """Dose of a cabinet medicine for a weight; with ``person_id`` (who must
    be in the caller's health scope) their age is checked too."""
    item = get_cabinet_item(ctx, item_id)
    age = None
    if person_id:
        person = list_people(ctx).filter(pk=person_id).first()
        if person is None:
            raise Http404("not found")
        age = age_in_months(person.birth_date, today or timezone.localdate())
    rule = dosing.DoseRule(
        strength_mg=item.strength_mg,
        strength_volume_ml=item.strength_volume_ml,
        dose_mg_per_kg=item.dose_mg_per_kg,
        dose_ml_per_kg=item.dose_ml_per_kg,
        dose_max_mg=item.dose_max_mg,
        daily_max_mg_per_kg=item.daily_max_mg_per_kg,
        daily_max_mg=item.daily_max_mg,
        min_interval_hours=item.min_interval_hours,
        min_age_months=item.min_age_months,
    )
    return dosing.calculate(rule, weight_kg, age_months=age)


SUGGESTION_FIELDS = ("doctor", "specialty", "place", "room", "purpose")
SUGGESTION_LIMIT = 50


def appointment_suggestions(ctx: AccessContext) -> dict:
    """Distinct earlier values per field (most recent first) from the visits
    the caller may see, plus each doctor's last specialty/place/room."""
    visits = list_records(ctx, "appointments").order_by("-starts_at").values(*SUGGESTION_FIELDS)
    out: dict = {f: [] for f in SUGGESTION_FIELDS}
    seen: dict = {f: set() for f in SUGGESTION_FIELDS}
    doctors: dict[str, dict] = {}
    for v in visits:
        for f in SUGGESTION_FIELDS:
            value = (v[f] or "").strip()
            key = value.lower()
            if value and key not in seen[f] and len(out[f]) < SUGGESTION_LIMIT:
                seen[f].add(key)
                out[f].append(value)
        name = (v["doctor"] or "").strip()
        if name and name.lower() not in doctors:  # newest visit wins
            doctors[name.lower()] = {
                f: (v[f] or "").strip() for f in ("doctor", "specialty", "place", "room")
            }
    out["doctors"] = list(doctors.values())
    return out


def cabinet_item_purchases(ctx: AccessContext, item_id: UUID) -> list:
    """Finance transactions linked to a cabinet medicine (what was paid for
    it). Needs finance access too — otherwise the list is simply empty."""
    from apps.finance import selectors as finance  # noqa: PLC0415 — finance is optional here

    get_cabinet_item(ctx, item_id)
    if not ctx.has("finance", "view"):
        return []
    return list(
        finance.list_transactions(ctx)
        .filter(related_kind=CABINET_ITEM_KIND, related_id=item_id)
        .order_by("-date")
    )


CABINET_ITEM_KIND = "health.cabinetitem"


# ---- Health profile ------------------------------------------------------------

ADULT_MONTHS = 18 * 12
BMI_BANDS = (
    (Decimal("18.5"), "underweight"),
    (Decimal("25"), "normal"),
    (Decimal("30"), "overweight"),
)


def bmi_category(bmi: Decimal, age_months: int | None) -> str:
    """Adult WHO bands. Under 18 the same number means different things by
    age and sex (percentile charts), so children get "child" — no label."""
    if age_months is None or age_months < ADULT_MONTHS:
        return "child"
    for limit, name in BMI_BANDS:
        if bmi < limit:
            return name
    return "obese"


def health_profile(ctx: AccessContext, person_id: UUID, *, today: date | None = None) -> dict:
    """One person's health at a glance: age, latest weight/height, BMI,
    measurement history, current treatments, upcoming visits, open events."""
    person = list_people(ctx).filter(pk=person_id).first()
    if person is None:
        raise Http404("not found")
    today = today or timezone.localdate()
    age = age_in_months(person.birth_date, today)
    measurements = list(list_records(ctx, "measurements", person_id=person_id).order_by("date"))
    weight = next((m for m in reversed(measurements) if m.weight_kg), None)
    height = next((m for m in reversed(measurements) if m.height_cm), None)
    bmi = None
    if weight and height:
        meters = height.height_cm / 100
        bmi = (weight.weight_kg / (meters * meters)).quantize(Decimal("0.1"))
    return {
        "person_id": person.id,
        "display_name": person.display_name,
        "birth_date": person.birth_date,
        "age_months": age,
        "weight_kg": weight.weight_kg if weight else None,
        "weight_date": weight.date if weight else None,
        "height_cm": height.height_cm if height else None,
        "height_date": height.date if height else None,
        "bmi": bmi,
        "bmi_category": bmi_category(bmi, age) if bmi else None,
        "measurements": measurements,
        "treatments": list(
            list_records(ctx, "medications", person_id=person_id)
            .filter(start_date__lte=today)
            .filter(Q(end_date__isnull=True) | Q(end_date__gte=today))
        ),
        "upcoming_visits": list(
            list_records(ctx, "appointments", person_id=person_id)
            .filter(status="planned", starts_at__gte=timezone.now())
            .order_by("starts_at")[:5]
        ),
        "open_conditions": list(
            list_records(ctx, "conditions", person_id=person_id).filter(end_date__isnull=True)
        ),
    }
