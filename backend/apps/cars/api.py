from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from django.http import HttpRequest
from ninja import Router, Schema

from apps.access.context import get_ctx

from . import selectors, services
from .models import Car

router = Router()


# -------------------- Cars --------------------


class CarIn(Schema):
    name: str
    make: str = ""
    model: str = ""
    year: int | None = None
    plate: str = ""
    vin: str = ""
    fuel_type: Literal["petrol", "diesel", "lpg", "hybrid", "electric"] = "petrol"
    owner_id: UUID | None = None
    initial_odometer_km: int = 0
    oil_interval_km: int = 15_000
    oil_interval_months: int = 12
    notes: str = ""


class CarOut(CarIn):
    id: UUID
    archived: bool

    @staticmethod
    def resolve_archived(obj: Car) -> bool:
        return obj.archived_at is not None


@router.get("/", response=list[CarOut])
def list_cars(request: HttpRequest, include_archived: bool = False) -> list[Car]:
    return list(selectors.list_cars(get_ctx(request), include_archived=include_archived))


@router.post("/", response=CarOut)
def create_car(request: HttpRequest, payload: CarIn) -> Car:
    return services.create_car(get_ctx(request), **payload.dict())


@router.put("/{car_id}", response=CarOut)
def update_car(request: HttpRequest, car_id: UUID, payload: CarIn) -> Car:
    return services.update_car(get_ctx(request), car_id, **payload.dict())


@router.post("/{car_id}/archive", response=CarOut)
def archive_car(request: HttpRequest, car_id: UUID) -> Car:
    return services.set_archived(get_ctx(request), car_id, archived=True)


@router.post("/{car_id}/unarchive", response=CarOut)
def unarchive_car(request: HttpRequest, car_id: UUID) -> Car:
    return services.set_archived(get_ctx(request), car_id, archived=False)


# -------------------- Summary --------------------


class DueOut(Schema):
    due_km: int | None
    km_left: int | None
    due_date: date | None
    km_eta: date | None
    due_by: date | None


class DeadlineStatusOut(Schema):
    kind: str
    valid_until: date
    days_left: int


class ConsumptionPointOut(Schema):
    date: date
    odometer_km: int
    litres_per_100km: Decimal
    distance_km: int


class SummaryOut(Schema):
    current_km: int
    daily_km: Decimal | None
    last_oil_change_date: date | None
    last_oil_change_km: int | None
    oil: DueOut | None
    oil_topped_up_litres: Decimal
    deadlines: list[DeadlineStatusOut]
    avg_consumption: Decimal | None
    last_consumption: Decimal | None
    consumption: list[ConsumptionPointOut]
    period_month: date
    fuel_cost_month: Decimal
    fuel_discounts_year: Decimal
    costs_year: Decimal


@router.get("/{car_id}/summary", response=SummaryOut)
def car_summary(
    request: HttpRequest, car_id: UUID, month: date | None = None
) -> selectors.CarSummary:
    """``month``: any day of the month whose costs to show (default: now)."""
    return selectors.car_summary(get_ctx(request), car_id, month=month)


class OdometerPointOut(Schema):
    date: date
    odometer_km: int
    source: str
    record_id: UUID | None


@router.get("/{car_id}/odometer-history", response=list[OdometerPointOut])
def odometer_history(request: HttpRequest, car_id: UUID) -> list[selectors.OdometerPoint]:
    """All odometer values from every entry (fuel, service, …), newest first."""
    return selectors.odometer_history(get_ctx(request), car_id)


# -------------------- Records --------------------


class OdometerIn(Schema):
    date: date
    odometer_km: int
    notes: str = ""


class FuelIn(Schema):
    date: date
    odometer_km: int
    litres: Decimal
    price_per_litre: Decimal | None = None  # pump price
    discount: Decimal | None = None
    total_cost: Decimal  # actually paid — goes to Finance
    currency: str = "PLN"
    full_tank: bool = True
    station: str = ""
    notes: str = ""


class MaintenanceIn(Schema):
    date: date
    kind: Literal["service", "part", "repair", "issue", "other"] = "service"
    title: str
    odometer_km: int | None = None
    cost: Decimal | None = None
    currency: str = "PLN"
    workshop: str = ""
    notes: str = ""


class OilChangeIn(Schema):
    date: date
    odometer_km: int
    oil_spec: str = ""
    litres: Decimal | None = None
    with_filter: bool = True
    # Left empty → computed from the car's oil interval.
    next_due_km: int | None = None
    next_due_date: date | None = None
    cost: Decimal | None = None
    currency: str = "PLN"
    notes: str = ""


class OilTopUpIn(Schema):
    date: date
    odometer_km: int | None = None
    litres: Decimal
    notes: str = ""


class DeadlineIn(Schema):
    date: date
    kind: Literal["inspection", "insurance", "other"]
    valid_until: date
    odometer_km: int | None = None
    provider: str = ""
    cost: Decimal | None = None
    currency: str = "PLN"
    notes: str = ""


class OdometerOut(OdometerIn):
    id: UUID


class FuelOut(FuelIn):
    id: UUID
    effective_price_per_litre: Decimal | None


class MaintenanceOut(MaintenanceIn):
    id: UUID


class OilChangeOut(OilChangeIn):
    id: UUID


class OilTopUpOut(OilTopUpIn):
    id: UUID


class DeadlineOut(DeadlineIn):
    id: UUID


def _register(kind: str, schema_in: type[Schema], schema_out: type[Schema]) -> None:
    """List / create / update / delete routes for one record type."""
    slug = kind.replace("-", "_")

    @router.get(f"/{{car_id}}/{kind}", response=list[schema_out], operation_id=f"cars_{slug}_list")
    def list_(request: HttpRequest, car_id: UUID) -> list[Any]:
        return list(selectors.list_records(get_ctx(request), kind, car_id))

    def create(request: HttpRequest, car_id: UUID, payload: Schema) -> Any:
        return services.save_record(get_ctx(request), kind, car_id, payload.dict())

    def update(request: HttpRequest, car_id: UUID, record_id: UUID, payload: Schema) -> Any:
        return services.save_record(get_ctx(request), kind, car_id, payload.dict(), record_id)

    # With `from __future__ import annotations` the hint above is just the
    # string "Schema"; Ninja reads the body schema from the real class, so set
    # it explicitly before registering the routes.
    create.__annotations__["payload"] = schema_in
    update.__annotations__["payload"] = schema_in
    router.post(f"/{{car_id}}/{kind}", response=schema_out, operation_id=f"cars_{slug}_create")(
        create
    )
    router.put(
        f"/{{car_id}}/{kind}/{{record_id}}",
        response=schema_out,
        operation_id=f"cars_{slug}_update",
    )(update)

    @router.delete(f"/{{car_id}}/{kind}/{{record_id}}", operation_id=f"cars_{slug}_delete")
    def delete(request: HttpRequest, car_id: UUID, record_id: UUID) -> dict[str, bool]:
        services.delete_record(get_ctx(request), kind, car_id, record_id)
        return {"deleted": True}


for _kind, _in, _out in (
    ("odometer", OdometerIn, OdometerOut),
    ("fuel", FuelIn, FuelOut),
    ("maintenance", MaintenanceIn, MaintenanceOut),
    ("oil-changes", OilChangeIn, OilChangeOut),
    ("oil-topups", OilTopUpIn, OilTopUpOut),
    ("deadlines", DeadlineIn, DeadlineOut),
):
    _register(_kind, _in, _out)
