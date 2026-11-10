"""Finance tests: upsert idempotency, recurring materialization, permission scoping."""
from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from django.core.exceptions import PermissionDenied

from apps.access.context import AccessContext
from apps.finance import recurring, selectors, services
from apps.finance.models import Category, RecurringRule, Transaction

from .factories import AccessGrantFactory, GroupFactory, PersonFactory, UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def _system_categories(db):
    """Minimal seed — what the seed_finance_categories command would create."""
    car = Category.objects.create(key="car", name="Car", kind="expense", is_system=True)
    fuel = Category.objects.create(
        key="car.fuel", name="Fuel", kind="expense", parent=car, is_system=True
    )
    salary = Category.objects.create(
        key="income.salary", name="Salary", kind="income", is_system=True
    )
    return {"car.fuel": fuel, "income.salary": salary}


@pytest.fixture
def _parent_user(db):
    user = UserFactory()
    group = GroupFactory()
    user.groups.add(group)
    AccessGrantFactory(group=group, module="finance", level="edit")
    return user


def test_upsert_linked_transaction_is_idempotent(_system_categories, _parent_user):
    """Re-saving the source should update the same Transaction row, not create a second."""
    ctx = AccessContext.for_user(_parent_user)
    # Any model works as a "source"; use Person for simplicity.
    source = PersonFactory()

    first = services.upsert_linked_transaction(
        ctx,
        source_obj=source,
        category_key="car.fuel",
        amount=Decimal("180.00"),
        currency="PLN",
        occurred_on=date(2026, 3, 1),
        name="Tank Orlen",
    )
    second = services.upsert_linked_transaction(
        ctx,
        source_obj=source,
        category_key="car.fuel",
        amount=Decimal("200.00"),  # price edited
        currency="PLN",
        occurred_on=date(2026, 3, 1),
        name="Tank Orlen",
    )
    assert first.id == second.id
    assert Transaction.objects.count() == 1
    assert Transaction.objects.get().amount == Decimal("200.00")


def test_upsert_requires_edit_permission(_system_categories):
    user = UserFactory()  # no grants → deny-all
    ctx = AccessContext.for_user(user)
    source = PersonFactory()
    with pytest.raises(PermissionDenied):
        services.upsert_linked_transaction(
            ctx,
            source_obj=source,
            category_key="car.fuel",
            amount=Decimal("10"),
            currency="PLN",
            occurred_on=date(2026, 3, 1),
            name="x",
        )


def test_search_filter_narrows_results(_system_categories, _parent_user):
    cat_fuel = _system_categories["car.fuel"]
    cat_salary = _system_categories["income.salary"]
    Transaction.objects.create(
        date=date(2026, 1, 15), amount=Decimal("100"), currency="PLN",
        category=cat_fuel, name="January fuel",
    )
    Transaction.objects.create(
        date=date(2026, 2, 15), amount=Decimal("200"), currency="PLN",
        category=cat_fuel, name="February fuel",
    )
    Transaction.objects.create(
        date=date(2026, 2, 28), amount=Decimal("8000"), currency="PLN",
        category=cat_salary, name="Salary",
    )

    ctx = AccessContext.for_user(_parent_user)
    f = selectors.TransactionFilter(date_from=date(2026, 2, 1), kind="expense")
    found = list(selectors.list_transactions(ctx, f))
    assert {t.name for t in found} == {"February fuel"}


def test_materialize_due_creates_txs_and_advances_cursor(_system_categories, _parent_user):
    cat = _system_categories["income.salary"]
    today = date(2026, 3, 15)
    rule = RecurringRule.objects.create(
        name="Salary",
        amount=Decimal("8000"),
        currency="PLN",
        category=cat,
        rrule="FREQ=MONTHLY;BYMONTHDAY=1",
        start_date=date(2026, 1, 1),
        next_run_at=date(2026, 1, 1),
    )
    # "Today" is March 15 — Jan, Feb and Mar occurrences should be materialized.
    created = recurring.materialize_due(
        now=datetime(today.year, today.month, today.day, 12, tzinfo=UTC)
    )
    assert created == 3
    rule.refresh_from_db()
    assert rule.next_run_at == date(2026, 4, 1)
    txs = list(Transaction.objects.filter(recurring_rule=rule).order_by("date"))
    assert [t.date for t in txs] == [date(2026, 1, 1), date(2026, 2, 1), date(2026, 3, 1)]


def test_propagate_edit_to_rule_copies_edited_fields(_system_categories, _parent_user):
    cat = _system_categories["income.salary"]
    rule = RecurringRule.objects.create(
        name="Salary",
        amount=Decimal("8000"),
        currency="PLN",
        category=cat,
        rrule="FREQ=MONTHLY;BYMONTHDAY=1",
        start_date=date(2026, 1, 1),
        next_run_at=date(2026, 1, 1),
    )
    tx = Transaction.objects.create(
        date=date(2026, 1, 1),
        amount=Decimal("8000"),
        currency="PLN",
        category=cat,
        name="Salary",
        recurring_rule=rule,
    )
    # User edits — new amount + name.
    tx.amount = Decimal("9000")
    tx.name = "Salary (raise)"
    tx.save()

    ctx = AccessContext.for_user(_parent_user)
    services.propagate_edit_to_rule(ctx, tx, update_future=True)

    rule.refresh_from_db()
    assert rule.amount == Decimal("9000")
    assert rule.name == "Salary (raise)"


def test_monthly_totals_window_ends_at_until_month(_system_categories, _parent_user):
    """Regression: the chart window must follow the picked month, not be all-time."""
    fuel = _system_categories["car.fuel"]
    for d, amount in [
        (date(2025, 12, 31), "50"),  # just outside a 3-month window ending March 2026
        (date(2026, 1, 1), "100"),
        (date(2026, 3, 31), "300"),
        (date(2026, 4, 1), "999"),  # after the window
    ]:
        Transaction.objects.create(
            date=d, amount=Decimal(amount), currency="PLN", category=fuel, name="fuel"
        )

    ctx = AccessContext.for_user(_parent_user)
    rows = selectors.monthly_totals(ctx, until=date(2026, 3, 15), months=3)

    assert {(r.year_month, r.total) for r in rows} == {
        ("2026-01", Decimal("100.00")),
        ("2026-03", Decimal("300.00")),
    }


def test_monthly_totals_empty_without_finance_grant(_system_categories):
    Transaction.objects.create(
        date=date(2026, 3, 1),
        amount=Decimal("10"),
        currency="PLN",
        category=_system_categories["car.fuel"],
        name="x",
    )
    ctx = AccessContext.for_user(UserFactory())  # no grants
    assert selectors.monthly_totals(ctx, until=date(2026, 3, 1)) == []
