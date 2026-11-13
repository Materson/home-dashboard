from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from django.contrib.contenttypes.models import ContentType
from django.core import signing
from django.http import HttpRequest
from django.utils import timezone
from ninja import Router, Schema

from apps.access.context import get_ctx
from apps.core.models import Attachment

from . import doses, selectors, services
from .models import DoseLog, TestResult

router = Router()


class PersonOut(Schema):
    id: UUID
    display_name: str
    color: str  # the person's colour, as on People


@router.get("/people", response=list[PersonOut])
def list_people(request: HttpRequest) -> list[Any]:
    """People whose health the caller may see — the page's person picker."""
    return list(selectors.list_people(get_ctx(request)))


# -------------------- Records --------------------


class ConditionIn(Schema):
    person_id: UUID
    kind: Literal["illness", "injury", "chronic", "allergy", "vaccination", "other"] = "illness"
    title: str
    start_date: date
    end_date: date | None = None
    notes: str = ""


class MedicationIn(Schema):
    person_id: UUID
    name: str
    dosage: str = ""
    start_date: date
    end_date: date | None = None
    dose_times: list[str] = []  # ["08:00", "20:00"]
    reminders_enabled: bool = True
    condition_id: UUID | None = None
    # A cabinet medicine, or leave empty and type `name`: it is matched by
    # name or added to the cabinet.
    cabinet_item_id: UUID | None = None
    notes: str = ""


class AppointmentIn(Schema):
    person_id: UUID
    starts_at: datetime  # local time when sent without an offset
    doctor: str = ""
    specialty: str = ""
    place: str = ""
    room: str = ""
    purpose: str = ""
    status: Literal["planned", "done", "cancelled"] = "planned"
    cost: Decimal | None = None
    currency: str = "PLN"
    condition_id: UUID | None = None  # the illness/event this visit is about
    notes: str = ""


class SymptomIn(Schema):
    person_id: UUID
    condition_id: UUID  # always part of an illness/event
    observed_at: datetime  # local time when sent without an offset
    symptom: str
    value: str = ""
    notes: str = ""


class SymptomOut(SymptomIn):
    id: UUID

    @staticmethod
    def resolve_observed_at(obj) -> datetime:
        return timezone.localtime(obj.observed_at)


class MeasurementIn(Schema):
    person_id: UUID
    date: date
    weight_kg: Decimal | None = None
    height_cm: Decimal | None = None
    notes: str = ""


class MeasurementOut(MeasurementIn):
    id: UUID


class ResultIn(Schema):
    person_id: UUID
    date: date
    title: str
    lab: str = ""
    notes: str = ""


class ConditionOut(ConditionIn):
    id: UUID


class MedicationOut(MedicationIn):
    id: UUID
    person_name: str

    @staticmethod
    def resolve_person_name(obj) -> str:
        return obj.person.display_name


class AppointmentOut(AppointmentIn):
    id: UUID

    @staticmethod
    def resolve_starts_at(obj) -> datetime:
        return timezone.localtime(obj.starts_at)


class ResultOut(ResultIn):
    id: UUID
    attachments: int

    @staticmethod
    def resolve_attachments(obj: TestResult) -> int:
        ct = ContentType.objects.get_for_model(TestResult)
        return Attachment.objects.filter(content_type=ct, object_id=obj.pk).count()


def _register(kind: str, schema_in: type[Schema], schema_out: type[Schema]) -> None:
    """List (optionally per person) / create / update / delete for one kind."""
    slug = kind

    @router.get(f"/{kind}", response=list[schema_out], operation_id=f"health_{slug}_list")
    def list_(
        request: HttpRequest,
        person_id: UUID | None = None,
        condition_id: UUID | None = None,
        cabinet_item_id: UUID | None = None,
    ) -> list[Any]:
        return list(
            selectors.list_records(
                get_ctx(request),
                kind,
                person_id=person_id,
                condition_id=condition_id,
                cabinet_item_id=cabinet_item_id,
            )
        )

    def create(request: HttpRequest, payload: Schema):
        try:
            return services.save_record(get_ctx(request), kind, payload.dict())
        except ValueError as exc:
            return 422, {"detail": str(exc)}

    def update(request: HttpRequest, record_id: UUID, payload: Schema):
        try:
            return services.save_record(get_ctx(request), kind, payload.dict(), record_id)
        except ValueError as exc:
            return 422, {"detail": str(exc)}

    # `from __future__ import annotations` turns the hint into a string; Ninja
    # needs the real body schema class.
    create.__annotations__["payload"] = schema_in
    update.__annotations__["payload"] = schema_in
    router.post(
        f"/{kind}", response={200: schema_out, 422: dict}, operation_id=f"health_{slug}_create"
    )(create)
    router.put(
        f"/{kind}/{{record_id}}",
        response={200: schema_out, 422: dict},
        operation_id=f"health_{slug}_update",
    )(update)

    @router.delete(f"/{kind}/{{record_id}}", operation_id=f"health_{slug}_delete")
    def delete(request: HttpRequest, record_id: UUID) -> dict[str, bool]:
        services.delete_record(get_ctx(request), kind, record_id)
        return {"deleted": True}


for _kind, _in, _out in (
    ("conditions", ConditionIn, ConditionOut),
    ("medications", MedicationIn, MedicationOut),
    ("appointments", AppointmentIn, AppointmentOut),
    ("results", ResultIn, ResultOut),
    ("measurements", MeasurementIn, MeasurementOut),
    ("symptoms", SymptomIn, SymptomOut),
):
    _register(_kind, _in, _out)


# -------------------- Doses --------------------


class DoseOut(Schema):
    id: UUID
    scheduled_at: datetime
    status: str
    medication_id: UUID
    medication_name: str
    dosage: str
    person_id: UUID
    person_name: str

    @staticmethod
    def resolve_scheduled_at(obj: DoseLog) -> datetime:
        return timezone.localtime(obj.scheduled_at)

    @staticmethod
    def resolve_medication_name(obj: DoseLog) -> str:
        return obj.medication.name

    @staticmethod
    def resolve_dosage(obj: DoseLog) -> str:
        return obj.medication.dosage

    @staticmethod
    def resolve_person_id(obj: DoseLog) -> UUID:
        return obj.medication.person_id

    @staticmethod
    def resolve_person_name(obj: DoseLog) -> str:
        return obj.medication.person.display_name


class DoseStatusIn(Schema):
    status: Literal["taken", "skipped", "pending"]


@router.get("/doses", response=list[DoseOut])
def list_doses(
    request: HttpRequest, day: date | None = None, person_id: UUID | None = None
) -> list[DoseLog]:
    """Doses for one day (default today), earliest first."""
    return list(
        selectors.list_doses(get_ctx(request), day=day or timezone.localdate(), person_id=person_id)
    )


@router.post("/doses/action", auth=None, response={200: dict, 400: dict})
def dose_action(request: HttpRequest, token: str):
    """Notification button ("Wzięte"/"Pominięte"). No session or CSRF token
    is available in the service worker, so the signed token *is* the
    authorization: it names one dose and one status and expires."""
    try:
        dose_id, status = doses.read_action_token(token)
    except signing.BadSignature:
        return 400, {"detail": "invalid or expired link"}
    dose = DoseLog.objects.filter(pk=dose_id).first()
    if dose is None:
        return 400, {"detail": "dose no longer exists"}
    doses.set_status(dose, status)
    return 200, {"ok": True}


@router.post("/doses/{dose_id}", response=DoseOut)
def set_dose_status(request: HttpRequest, dose_id: UUID, payload: DoseStatusIn) -> DoseLog:
    return services.set_dose_status(get_ctx(request), dose_id, payload.status)


# -------------------- Medicine cabinet --------------------


class PackageIn(Schema):
    expiry_date: date | None = None
    opened_on: date | None = None
    days_after_opening: int | None = None
    location: str = ""
    notes: str = ""
    finished_on: date | None = None


class PackageOut(PackageIn):
    id: UUID
    effective_expiry: date | None
    status: str  # finished | expired | soon | ok | unknown

    @staticmethod
    def resolve_status(obj) -> str:
        return selectors.package_status(obj, timezone.localdate())


class CabinetItemIn(Schema):
    name: str
    substance: str = ""
    form: Literal[
        "tablets", "syrup", "drops", "spray", "ointment", "sachet", "suppository", "other"
    ] = "tablets"
    indications: str = ""
    for_whom: Literal["everyone", "adults", "children"] = "everyone"
    min_age_months: int | None = None
    dosage_notes: str = ""
    notes: str = ""
    # Dosing by weight (all optional) — see apps/health/dosing.py.
    strength_mg: Decimal | None = None
    strength_volume_ml: Decimal | None = None
    dose_mg_per_kg: Decimal | None = None
    dose_ml_per_kg: Decimal | None = None
    dose_max_mg: Decimal | None = None
    daily_max_mg_per_kg: Decimal | None = None
    daily_max_mg: Decimal | None = None
    min_interval_hours: int | None = None


class CabinetItemOut(CabinetItemIn):
    id: UUID
    packages: list[PackageOut]

    @staticmethod
    def resolve_packages(obj) -> list:
        return getattr(obj, "shown_packages", None) or list(obj.packages.filter(finished_on=None))


@router.get("/cabinet", response=list[CabinetItemOut])
def list_cabinet(
    request: HttpRequest,
    q: str | None = None,
    for_whom: str | None = None,
    include_finished: bool = False,
) -> list[Any]:
    """Home medicines: search name/substance/what it's for; for_whom=children
    also lists medicines for everyone."""
    return selectors.list_cabinet(
        get_ctx(request), q=q, for_whom=for_whom, include_finished=include_finished
    )


@router.post("/cabinet", response=CabinetItemOut)
def create_cabinet_item(request: HttpRequest, payload: CabinetItemIn) -> Any:
    return services.save_cabinet_item(get_ctx(request), payload.dict())


@router.put("/cabinet/{item_id}", response=CabinetItemOut)
def update_cabinet_item(request: HttpRequest, item_id: UUID, payload: CabinetItemIn) -> Any:
    return services.save_cabinet_item(get_ctx(request), payload.dict(), item_id)


@router.delete("/cabinet/{item_id}")
def delete_cabinet_item(request: HttpRequest, item_id: UUID) -> dict[str, bool]:
    services.delete_cabinet_item(get_ctx(request), item_id)
    return {"deleted": True}


@router.post("/cabinet/{item_id}/packages", response={200: PackageOut, 422: dict})
def create_package(request: HttpRequest, item_id: UUID, payload: PackageIn):
    try:
        return services.save_package(get_ctx(request), payload.dict(), item_id=item_id)
    except ValueError as exc:
        return 422, {"detail": str(exc)}


@router.put("/cabinet/packages/{package_id}", response={200: PackageOut, 422: dict})
def update_package(request: HttpRequest, package_id: UUID, payload: PackageIn):
    try:
        return services.save_package(get_ctx(request), payload.dict(), package_id=package_id)
    except ValueError as exc:
        return 422, {"detail": str(exc)}


@router.delete("/cabinet/packages/{package_id}")
def delete_package(request: HttpRequest, package_id: UUID) -> dict[str, bool]:
    services.delete_package(get_ctx(request), package_id)
    return {"deleted": True}


class DoseOut(Schema):
    weight_kg: Decimal
    single_mg: Decimal | None
    single_ml: Decimal | None
    single_units: Decimal | None
    daily_max_mg: Decimal | None
    daily_max_ml: Decimal | None
    max_doses_per_day: int | None
    min_interval_hours: int | None
    warnings: list[str]


@router.get("/cabinet/{item_id}/dose", response=DoseOut)
def cabinet_dose(
    request: HttpRequest, item_id: UUID, weight_kg: Decimal, person_id: UUID | None = None
) -> Any:
    """Weight-based dose; pass person_id to also check their age."""
    return selectors.dose_for(get_ctx(request), item_id, weight_kg, person_id=person_id)


class DoctorProfileOut(Schema):
    doctor: str
    specialty: str
    place: str
    room: str


class AppointmentSuggestionsOut(Schema):
    doctor: list[str]
    specialty: list[str]
    place: list[str]
    room: list[str]
    purpose: list[str]
    doctors: list[DoctorProfileOut]


@router.get("/appointment-suggestions", response=AppointmentSuggestionsOut)
def appointment_suggestions(request: HttpRequest) -> Any:
    """Values used in earlier visits, most recent first, for the form's
    pickers; ``doctors`` maps a doctor to where you last saw them."""
    return selectors.appointment_suggestions(get_ctx(request))


class CabinetPurchaseOut(Schema):
    id: UUID
    date: date
    name: str
    amount: Decimal
    currency: str


@router.get("/cabinet/{item_id}/purchases", response=list[CabinetPurchaseOut])
def cabinet_item_purchases(request: HttpRequest, item_id: UUID) -> list[Any]:
    """Finance transactions linked to this medicine (needs finance access)."""
    return selectors.cabinet_item_purchases(get_ctx(request), item_id)


class ProfileOut(Schema):
    person_id: UUID
    display_name: str
    birth_date: date | None
    age_months: int | None
    weight_kg: Decimal | None
    weight_date: date | None
    height_cm: Decimal | None
    height_date: date | None
    bmi: Decimal | None
    bmi_category: str | None  # underweight | normal | overweight | obese | child
    measurements: list[MeasurementOut]
    treatments: list[MedicationOut]
    upcoming_visits: list[AppointmentOut]
    open_conditions: list[ConditionOut]


@router.get("/people/{person_id}/profile", response=ProfileOut)
def health_profile(request: HttpRequest, person_id: UUID) -> Any:
    """A person's health at a glance (BMI, trend, current treatments …)."""
    return selectors.health_profile(get_ctx(request), person_id)
