"""Cars: ledger mirroring, reminders, odometer, permissions, HTTP."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.utils import timezone

from apps.access.context import AccessContext
from apps.cars import selectors, services
from apps.cars.models import OilChange
from apps.finance.models import Transaction
from apps.reminders.models import Reminder

from .factories import AccessGrantFactory, GroupFactory, PersonFactory, UserFactory

pytestmark = pytest.mark.django_db  # categories come from finance migration 0006


def _user(**grants):
    """User with the given module grants, e.g. _user(cars="edit")."""
    user = UserFactory()
    group = GroupFactory()
    user.groups.add(group)
    for module, level in grants.items():
        AccessGrantFactory(group=group, module=module, level=level)
    return user


@pytest.fixture
def ctx():
    return AccessContext.for_user(_user(cars="edit"))  # no finance access on purpose


@pytest.fixture
def car(ctx):
    return services.create_car(ctx, name="Octavia", initial_odometer_km=100_000)


def fuel(ctx, car, km, *, litres="40", cost="260", day=None, full=True):
    return services.save_record(
        ctx,
        "fuel",
        car.id,
        {
            "date": day or timezone.localdate(),
            "odometer_km": km,
            "litres": Decimal(litres),
            "total_cost": Decimal(cost),
            "full_tank": full,
        },
    )


# ---- ledger --------------------------------------------------------------


def test_fuel_creates_updates_and_removes_its_transaction(ctx, car):
    """Cars access alone is enough: the ledger write is authorized by cars."""
    entry = fuel(ctx, car, 100_500)
    tx = Transaction.objects.get(source_id=entry.id)
    assert (tx.category.key, tx.amount) == ("car.fuel", Decimal("260.00"))

    services.save_record(ctx, "fuel", car.id, {"total_cost": Decimal("275")}, record_id=entry.id)
    assert Transaction.objects.get(source_id=entry.id).amount == Decimal("275.00")

    services.delete_record(ctx, "fuel", car.id, entry.id)
    assert not Transaction.objects.filter(source_id=entry.id).exists()


def test_cost_is_optional_for_service_records(ctx, car):
    issue = services.save_record(
        ctx, "maintenance", car.id, {"date": date(2026, 3, 1), "kind": "issue", "title": "Stuk"}
    )
    assert not Transaction.objects.filter(source_id=issue.id).exists()

    services.save_record(ctx, "maintenance", car.id, {"cost": Decimal("400")}, record_id=issue.id)
    assert Transaction.objects.get(source_id=issue.id).category.key == "car.maintenance"

    services.save_record(ctx, "maintenance", car.id, {"cost": None}, record_id=issue.id)
    assert not Transaction.objects.filter(source_id=issue.id).exists()


def test_deadline_cost_goes_to_its_own_category(ctx, car):
    insurance = services.save_record(
        ctx,
        "deadlines",
        car.id,
        {
            "date": date(2026, 3, 1),
            "kind": "insurance",
            "valid_until": date(2027, 2, 28),
            "cost": Decimal("1800"),
        },
    )
    assert Transaction.objects.get(source_id=insurance.id).category.key == "car.insurance"


# ---- odometer & oil ------------------------------------------------------


def test_current_odometer_is_the_highest_reading_anywhere(ctx, car):
    assert selectors.current_odometer(car) == 100_000
    fuel(ctx, car, 100_800)
    services.save_record(
        ctx, "odometer", car.id, {"date": timezone.localdate(), "odometer_km": 101_200}
    )
    assert selectors.current_odometer(car) == 101_200


def test_oil_change_defaults_and_reminders(ctx, car):
    today = timezone.localdate()
    oil = services.save_record(ctx, "oil-changes", car.id, {"date": today, "odometer_km": 100_000})
    assert oil.next_due_km == 115_000  # car default interval
    assert oil.next_due_date is not None

    live = Reminder.objects.filter(object_id=oil.id, status=Reminder.Status.SCHEDULED)
    assert live.filter(due_odometer_km=115_000, due_at__isnull=True).count() == 1
    assert live.filter(due_at__isnull=False).count() == 1  # the date-based one

    # Driving to within 500 km makes the km reminder due right away.
    fuel(ctx, car, 114_600)
    assert live.filter(due_odometer_km=115_000, due_at__isnull=False).count() == 1


def test_new_oil_change_cancels_the_previous_ones_reminders(ctx, car):
    today = timezone.localdate()
    first = services.save_record(
        ctx, "oil-changes", car.id, {"date": today, "odometer_km": 100_000}
    )
    second = services.save_record(
        ctx, "oil-changes", car.id, {"date": today, "odometer_km": 114_000}
    )
    scheduled = Reminder.objects.filter(status=Reminder.Status.SCHEDULED)
    assert not scheduled.filter(object_id=first.id).exists()
    assert scheduled.filter(object_id=second.id).exists()

    # Deleting the newest brings the older one's reminders back.
    services.delete_record(ctx, "oil-changes", car.id, second.id)
    assert scheduled.filter(object_id=first.id).exists()
    assert OilChange.objects.count() == 1


def test_deadline_reminders_two_weeks_and_one_day_before(ctx, car):
    valid_until = timezone.localdate() + timedelta(days=60)
    inspection = services.save_record(
        ctx,
        "deadlines",
        car.id,
        {"date": timezone.localdate(), "kind": "inspection", "valid_until": valid_until},
    )
    days = sorted(
        r.due_at.date()
        for r in Reminder.objects.filter(object_id=inspection.id, status="scheduled")
    )
    assert days == [valid_until - timedelta(days=14), valid_until - timedelta(days=1)]


# ---- summary -------------------------------------------------------------


def test_summary_consumption_and_oil_status(ctx, car):
    start = timezone.localdate() - timedelta(days=30)
    fuel(ctx, car, 100_000, litres="40", day=start)
    fuel(ctx, car, 100_600, litres="42", day=start + timedelta(days=10))
    services.save_record(ctx, "oil-changes", car.id, {"date": start, "odometer_km": 100_000})
    s = selectors.car_summary(ctx, car.id)
    assert s.current_km == 100_600
    assert s.last_consumption == Decimal("7.00")
    assert s.oil.km_left == 14_400
    assert s.fuel_cost_month >= 0


# ---- permissions -----------------------------------------------------------


def test_cars_are_invisible_and_read_only_without_grants(ctx, car):
    outsider = AccessContext.for_user(UserFactory())
    assert list(selectors.list_cars(outsider)) == []
    with pytest.raises(Http404):
        selectors.car_summary(outsider, car.id)

    viewer = AccessContext.for_user(_user(cars="view"))
    assert list(selectors.list_cars(viewer)) == [car]
    with pytest.raises(PermissionDenied):
        fuel(viewer, car, 100_100)


def test_person_scoped_grant_sees_only_their_cars():
    kid = PersonFactory()
    user = UserFactory()
    kid.user = user
    kid.save()
    AccessGrantFactory(user=user, module="cars", level="view", subjects="self")
    admin = AccessContext.for_user(UserFactory(is_superuser=True))
    mine = services.create_car(admin, name="Mine", owner=kid)
    services.create_car(admin, name="Parents'")

    assert list(selectors.list_cars(AccessContext.for_user(user))) == [mine]


# ---- HTTP ------------------------------------------------------------------


def test_http_roundtrip(client):
    client.force_login(_user(cars="edit"))
    resp = client.post("/api/cars/", {"name": "Octavia"}, content_type="application/json")
    assert resp.status_code == 200, resp.content
    car_id = resp.json()["id"]

    resp = client.post(
        f"/api/cars/{car_id}/fuel",
        {
            "date": "2026-03-01",
            "odometer_km": 1200,
            "litres": "40.5",
            "total_cost": "263.25",
        },
        content_type="application/json",
    )
    assert resp.status_code == 200, resp.content
    assert resp.json()["effective_price_per_litre"] == "6.500"

    summary = client.get(f"/api/cars/{car_id}/summary").json()
    assert summary["current_km"] == 1200
    assert len(client.get(f"/api/cars/{car_id}/fuel").json()) == 1
    assert client.post(f"/api/cars/{car_id}/archive").json()["archived"] is True
    assert client.get("/api/cars/").json() == []


def test_fuel_discount_ledger_uses_amount_paid(ctx, car):
    """Pump price and discount are details; Finance gets what was paid."""
    entry = services.save_record(
        ctx,
        "fuel",
        car.id,
        {
            "date": timezone.localdate(),
            "odometer_km": 100_400,
            "litres": Decimal("40"),
            "price_per_litre": Decimal("6.499"),
            "discount": Decimal("12.00"),
            "total_cost": Decimal("247.96"),  # 259.96 - 12.00
        },
    )
    tx = Transaction.objects.get(source_id=entry.id)
    assert tx.amount == Decimal("247.96")
    assert "rabat 12.00" in tx.name
    assert entry.effective_price_per_litre == Decimal("6.199")
    assert selectors.car_summary(ctx, car.id).fuel_discounts_year == Decimal("12.00")


def test_odometer_history_includes_every_source(ctx, car):
    today = timezone.localdate()
    entry = fuel(ctx, car, 100_600, day=today)
    services.save_record(
        ctx, "odometer", car.id, {"date": today - timedelta(days=3), "odometer_km": 100_300}
    )
    services.save_record(
        ctx,
        "maintenance",
        car.id,
        {"date": today - timedelta(days=5), "title": "Klocki", "odometer_km": 100_200},
    )
    history = selectors.odometer_history(ctx, car.id)
    assert [(p.odometer_km, p.source) for p in history] == [
        (100_600, "fuel"),
        (100_300, "odometer"),
        (100_200, "maintenance"),
        (100_000, "initial"),
    ]
    # Live view: editing the fill-up's km changes the history, no stale copy.
    services.save_record(ctx, "fuel", car.id, {"odometer_km": 100_650}, record_id=entry.id)
    assert selectors.odometer_history(ctx, car.id)[0].odometer_km == 100_650


def test_summary_costs_for_a_chosen_month_and_its_year(ctx, car):
    for day, cost in [
        (date(2025, 12, 20), "100"),
        (date(2026, 3, 5), "200"),
        (date(2026, 4, 1), "300"),
    ]:
        fuel(ctx, car, 100_000 + day.toordinal() % 1000, cost=cost, day=day)

    march = selectors.car_summary(ctx, car.id, month=date(2026, 3, 17))
    assert march.period_month == date(2026, 3, 1)
    assert march.fuel_cost_month == Decimal("200")  # not April, not December
    assert march.costs_year == Decimal("500")  # 2026 only

    december = selectors.car_summary(ctx, car.id, month=date(2025, 12, 1))
    assert (december.fuel_cost_month, december.costs_year) == (Decimal("100"), Decimal("100"))
