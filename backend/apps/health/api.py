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
    doctor: str = ""
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
    notes: str = ""


class PurchaseIn(Schema):
    person_id: UUID
    date: date
    name: str
    medication_id: UUID | None = None
    cost: Decimal
    currency: str = "PLN"
    pharmacy: str = ""
    notes: str = ""


class AppointmentIn(Schema):
    person_id: UUID
    starts_at: datetime  # local time when sent without an offset
    doctor: str = ""
    specialty: str = ""
    place: str = ""
    purpose: str = ""
    status: Literal["planned", "done", "cancelled"] = "planned"
    cost: Decimal | None = None
    currency: str = "PLN"
    notes: str = ""


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


class PurchaseOut(PurchaseIn):
    id: UUID


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
    def list_(request: HttpRequest, person_id: UUID | None = None) -> list[Any]:
        return list(selectors.list_records(get_ctx(request), kind, person_id=person_id))

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
    ("purchases", PurchaseIn, PurchaseOut),
    ("appointments", AppointmentIn, AppointmentOut),
    ("results", ResultIn, ResultOut),
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
