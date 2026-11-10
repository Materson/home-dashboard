from __future__ import annotations

from datetime import date
from decimal import Decimal

from apps.cars.stats import (
    ConsumptionPoint,
    Fill,
    Reading,
    average_consumption,
    average_daily_km,
    consumption_series,
    due_status,
)


def fill(day, km, litres, full=True):
    return Fill(date(2026, 3, day), km, Decimal(litres), full)


def test_full_to_full_consumption():
    series = consumption_series(
        [
            fill(1, 10_000, "40"),  # baseline full tank
            fill(8, 10_600, "42"),  # 42 l / 600 km = 7.00
        ]
    )
    assert [(p.odometer_km, p.litres_per_100km) for p in series] == [(10_600, Decimal("7.00"))]


def test_partial_fills_count_towards_next_full_one():
    series = consumption_series(
        [
            fill(1, 10_000, "40"),
            fill(4, 10_300, "15", full=False),
            fill(8, 10_700, "20"),  # (15 + 20) l / 700 km = 5.00
        ]
    )
    assert series[0].litres_per_100km == Decimal("5.00")
    assert series[0].distance_km == 700


def test_litres_before_first_full_fill_are_ignored():
    series = consumption_series(
        [
            fill(1, 9_800, "30", full=False),
            fill(2, 10_000, "40"),
            fill(8, 10_500, "35"),  # 35 l / 500 km = 7.00
        ]
    )
    assert [p.litres_per_100km for p in series] == [Decimal("7.00")]


def test_fills_entered_out_of_order_are_sorted_by_odometer():
    series = consumption_series([fill(8, 10_600, "42"), fill(1, 10_000, "40")])
    assert series[0].litres_per_100km == Decimal("7.00")


def test_average_is_distance_weighted():
    points = [
        ConsumptionPoint(date(2026, 3, 1), 1_000, Decimal("10"), 100),  # 10 l
        ConsumptionPoint(date(2026, 3, 9), 1_900, Decimal("5"), 900),  # 45 l
    ]
    # 55 l / 1000 km, not the plain mean (7.5)
    assert average_consumption(points) == Decimal("5.50")
    assert average_consumption([]) is None


def test_average_daily_km_needs_a_week_of_data():
    today = date(2026, 3, 31)
    assert (
        average_daily_km([Reading(date(2026, 3, 28), 100), Reading(today, 400)], today=today)
        is None
    )
    readings = [Reading(date(2026, 3, 1), 10_000), Reading(date(2026, 3, 31), 11_500)]
    assert average_daily_km(readings, today=today) == Decimal("50.0")


def test_due_status_uses_earlier_of_date_and_km_eta():
    today = date(2026, 3, 1)
    s = due_status(
        due_km=25_000,
        due_date=date(2026, 12, 1),
        current_km=24_000,
        daily_km=Decimal("50"),
        today=today,
    )
    assert s.km_left == 1_000
    assert s.km_eta == date(2026, 3, 21)  # 1000 km / 50 per day
    assert s.due_by == date(2026, 3, 21)

    overdue = due_status(
        due_km=25_000, due_date=None, current_km=25_300, daily_km=None, today=today
    )
    assert overdue.km_left == -300
    assert overdue.due_by is None
