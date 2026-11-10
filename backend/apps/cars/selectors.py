"""Cars read queries — every function takes an AccessContext.

Cars are scoped like person-owned data: a grant limited to some persons sees
only the cars those persons own."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from dateutil.relativedelta import relativedelta
from django.db.models import Max, QuerySet, Sum
from django.http import Http404
from django.utils import timezone

from . import stats
from .models import (
    Car,
    CarDeadline,
    FuelEntry,
    MaintenanceEvent,
    OdometerReading,
    OilChange,
    OilTopUp,
)

if TYPE_CHECKING:
    from apps.access.context import AccessContext

# URL segment → model, shared by selectors, services and the API.
RECORD_MODELS = {
    "odometer": OdometerReading,
    "fuel": FuelEntry,
    "maintenance": MaintenanceEvent,
    "oil-changes": OilChange,
    "oil-topups": OilTopUp,
    "deadlines": CarDeadline,
}
# Records that carry an odometer value (used for "current km").
ODOMETER_MODELS = (OdometerReading, FuelEntry, MaintenanceEvent, OilChange, OilTopUp, CarDeadline)


def list_cars(ctx: AccessContext, *, include_archived: bool = False) -> QuerySet[Car]:
    qs = ctx.scope_by_person(module="cars", qs=Car.objects.all(), person_field="owner_id")
    if not include_archived:
        qs = qs.filter(archived_at__isnull=True)
    return qs


def get_car(ctx: AccessContext, car_id: UUID) -> Car:
    """A car the caller may view (archived included); 404 otherwise, so the
    response doesn't reveal that someone else's car exists."""
    car = list_cars(ctx, include_archived=True).filter(pk=car_id).first()
    if car is None:
        raise Http404("car not found")
    return car


def list_records(ctx: AccessContext, kind: str, car_id: UUID) -> QuerySet:
    car = get_car(ctx, car_id)
    return RECORD_MODELS[kind].objects.filter(car=car)


def current_odometer(car: Car) -> int:
    best = car.initial_odometer_km
    for model in ODOMETER_MODELS:
        top = model.objects.filter(car=car).aggregate(m=Max("odometer_km"))["m"]
        if top is not None:
            best = max(best, top)
    return best


def _readings(car: Car) -> list[stats.Reading]:
    readings: list[stats.Reading] = []
    for model in ODOMETER_MODELS:
        for d, km in model.objects.filter(car=car, odometer_km__isnull=False).values_list(
            "date", "odometer_km"
        ):
            readings.append(stats.Reading(d, km))
    return readings


@dataclass(slots=True)
class OdometerPoint:
    date: date
    odometer_km: int
    source: str  # a RECORD_MODELS key, or "initial" for the car's starting value
    record_id: UUID | None


def odometer_history(ctx: AccessContext, car_id: UUID) -> list[OdometerPoint]:
    """Every odometer value the car has, from whichever entry recorded it,
    newest first. Read live from the records, so editing a fill-up updates
    the history too (nothing is copied). The car's starting value is always
    the last row, dated no later than the earliest entry."""
    car = get_car(ctx, car_id)
    points: list[OdometerPoint] = []
    for kind, model in RECORD_MODELS.items():
        for pk, d, km in model.objects.filter(car=car, odometer_km__isnull=False).values_list(
            "pk", "date", "odometer_km"
        ):
            points.append(OdometerPoint(d, km, kind, pk))
    points.sort(key=lambda p: (p.date, p.odometer_km), reverse=True)
    added_on = timezone.localtime(car.created_at).date()
    start = min([added_on, *(p.date for p in points)])
    points.append(OdometerPoint(start, car.initial_odometer_km, "initial", None))
    return points


@dataclass(slots=True)
class DeadlineStatus:
    kind: str
    valid_until: date
    days_left: int


@dataclass(slots=True)
class CarSummary:
    current_km: int
    daily_km: Decimal | None
    last_oil_change_date: date | None
    last_oil_change_km: int | None
    oil: stats.DueStatus | None
    oil_topped_up_litres: Decimal  # since the last oil change
    deadlines: list[DeadlineStatus]
    avg_consumption: Decimal | None
    last_consumption: Decimal | None
    consumption: list[stats.ConsumptionPoint] = field(default_factory=list)
    # Costs for the requested period: ``period_month`` and its whole year.
    period_month: date | None = None
    fuel_cost_month: Decimal = Decimal("0")
    fuel_discounts_year: Decimal = Decimal("0")
    costs_year: Decimal = Decimal("0")


def car_summary(
    ctx: AccessContext,
    car_id: UUID,
    *,
    today: date | None = None,
    month: date | None = None,
) -> CarSummary:
    """Current state of the car (odometer, oil, deadlines, consumption) plus
    costs for ``month`` (any day in it; default: this month) and its year."""
    car = get_car(ctx, car_id)
    today = today or timezone.localdate()
    current_km = current_odometer(car)
    daily_km = stats.average_daily_km(_readings(car), today=today)

    last_oil = OilChange.objects.filter(car=car).order_by("-odometer_km", "-date").first()
    oil = topped_up = None
    if last_oil:
        oil = stats.due_status(
            due_km=last_oil.next_due_km,
            due_date=last_oil.next_due_date,
            current_km=current_km,
            daily_km=daily_km,
            today=today,
        )
        topped_up = OilTopUp.objects.filter(car=car, date__gte=last_oil.date).aggregate(
            s=Sum("litres")
        )["s"]

    deadlines = []
    for kind in CarDeadline.Kind.values:
        latest = CarDeadline.objects.filter(car=car, kind=kind).order_by("-valid_until").first()
        if latest:
            deadlines.append(
                DeadlineStatus(kind, latest.valid_until, (latest.valid_until - today).days)
            )

    fills = [
        stats.Fill(f.date, f.odometer_km, f.litres, f.full_tank)
        for f in FuelEntry.objects.filter(car=car)
    ]
    series = stats.consumption_series(fills)
    year_ago = date(today.year - 1, today.month, 1)

    def cost(model, amount_field: str, since: date, until: date) -> Decimal:
        total = model.objects.filter(car=car, date__gte=since, date__lt=until).aggregate(
            s=Sum(amount_field)
        )["s"]
        return total or Decimal("0")

    month_start = (month or today).replace(day=1)
    month_end = month_start + relativedelta(months=1)
    year_start = month_start.replace(month=1)
    year_end = year_start + relativedelta(years=1)
    return CarSummary(
        current_km=current_km,
        daily_km=daily_km,
        last_oil_change_date=last_oil.date if last_oil else None,
        last_oil_change_km=last_oil.odometer_km if last_oil else None,
        oil=oil,
        oil_topped_up_litres=topped_up or Decimal("0"),
        deadlines=deadlines,
        avg_consumption=stats.average_consumption([p for p in series if p.date >= year_ago]),
        last_consumption=series[-1].litres_per_100km if series else None,
        consumption=series[-24:],
        period_month=month_start,
        fuel_cost_month=cost(FuelEntry, "total_cost", month_start, month_end),
        fuel_discounts_year=cost(FuelEntry, "discount", year_start, year_end),
        costs_year=sum(
            (
                cost(FuelEntry, "total_cost", year_start, year_end),
                cost(MaintenanceEvent, "cost", year_start, year_end),
                cost(OilChange, "cost", year_start, year_end),
                cost(CarDeadline, "cost", year_start, year_end),
            ),
            Decimal("0"),
        ),
    )
