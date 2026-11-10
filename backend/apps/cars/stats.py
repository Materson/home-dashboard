"""Pure car statistics — no Django, so they're trivial to test and reuse
(API summary, AI assistant tools).

Fuel consumption uses the **full-to-full** method: when the tank is filled
completely, consumption since the previous full fill-up is

    litres put in after that previous full fill (including this one)
    / km driven between the two full fill-ups * 100

Partial fill-ups only add their litres to the next full one. Litres before
the very first full fill-up can't be attributed to a distance and are
ignored.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

HUNDRED = Decimal("100")


@dataclass(frozen=True, slots=True)
class Fill:
    date: date
    odometer_km: int
    litres: Decimal
    full_tank: bool


@dataclass(frozen=True, slots=True)
class ConsumptionPoint:
    date: date
    odometer_km: int
    litres_per_100km: Decimal
    distance_km: int


def consumption_series(fills: Iterable[Fill]) -> list[ConsumptionPoint]:
    """One point per full fill-up that has a previous full fill-up."""
    points: list[ConsumptionPoint] = []
    last_full_km: int | None = None
    litres_since = Decimal("0")
    for f in sorted(fills, key=lambda f: (f.odometer_km, f.date)):
        litres_since += f.litres
        if not f.full_tank:
            continue
        if last_full_km is not None and f.odometer_km > last_full_km:
            distance = f.odometer_km - last_full_km
            value = (litres_since / distance * HUNDRED).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            points.append(ConsumptionPoint(f.date, f.odometer_km, value, distance))
        last_full_km = f.odometer_km
        litres_since = Decimal("0")
    return points


def average_consumption(points: Sequence[ConsumptionPoint]) -> Decimal | None:
    """Distance-weighted average over the given points (not a mean of means)."""
    distance = sum(p.distance_km for p in points)
    if not distance:
        return None
    litres = sum(p.litres_per_100km * p.distance_km / HUNDRED for p in points)
    return (litres / distance * HUNDRED).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


@dataclass(frozen=True, slots=True)
class Reading:
    date: date
    odometer_km: int


MIN_SPAN_DAYS = 7


def average_daily_km(
    readings: Iterable[Reading], *, today: date, window_days: int = 365
) -> Decimal | None:
    """km per day between the oldest and newest reading in the window.

    ``None`` until readings span at least a week — shorter spans give wild
    estimates."""
    recent = [r for r in readings if r.date >= today - timedelta(days=window_days)]
    if len(recent) < 2:  # noqa: PLR2004
        return None
    first = min(recent, key=lambda r: (r.date, r.odometer_km))
    last = max(recent, key=lambda r: (r.date, r.odometer_km))
    days = (last.date - first.date).days
    if days < MIN_SPAN_DAYS or last.odometer_km <= first.odometer_km:
        return None
    return (Decimal(last.odometer_km - first.odometer_km) / days).quantize(Decimal("0.1"))


@dataclass(frozen=True, slots=True)
class DueStatus:
    """When something distance- and/or date-based is due next."""

    due_km: int | None
    km_left: int | None
    due_date: date | None
    # Estimated date the km limit is hit at the current driving pace.
    km_eta: date | None
    # The earlier of due_date and km_eta — "do it by".
    due_by: date | None


def due_status(
    *,
    due_km: int | None,
    due_date: date | None,
    current_km: int | None,
    daily_km: Decimal | None,
    today: date,
) -> DueStatus:
    km_left = due_km - current_km if due_km is not None and current_km is not None else None
    km_eta = None
    if km_left is not None and daily_km:
        km_eta = today + timedelta(days=max(0, int(Decimal(km_left) / daily_km)))
    candidates = [d for d in (due_date, km_eta) if d is not None]
    return DueStatus(
        due_km=due_km,
        km_left=km_left,
        due_date=due_date,
        km_eta=km_eta,
        due_by=min(candidates) if candidates else None,
    )
