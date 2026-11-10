"""Bookmarks (owner-private templates) and debts (isolated from the ledger)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import PermissionDenied

from apps.access.context import AccessContext
from apps.finance import selectors, services
from apps.finance.models import Category, DebtEntry, Transaction

from .factories import AccessGrantFactory, GroupFactory, UserFactory

pytestmark = pytest.mark.django_db


def _finance_user(level: str = "edit"):
    user = UserFactory()
    group = GroupFactory()
    user.groups.add(group)
    AccessGrantFactory(group=group, module="finance", level=level)
    return user


@pytest.fixture
def groceries(db):
    return Category.objects.get(key="home.groceries")  # seeded by migration 0006


# ---- Bookmarks ---------------------------------------------------------


def _bookmark(ctx, category, label="Biedronka"):
    return services.create_bookmark(
        ctx, label=label, name="Zakupy Biedronka", amount=Decimal("150"), category_id=category.id
    )


def test_bookmarks_are_private_to_their_owner(groceries):
    alice = AccessContext.for_user(_finance_user())
    bob = AccessContext.for_user(_finance_user())
    bm = _bookmark(alice, groceries)

    assert list(selectors.list_bookmarks(alice)) == [bm]
    assert list(selectors.list_bookmarks(bob)) == []
    with pytest.raises(PermissionDenied):
        services.delete_bookmark(bob, bm.id)
    with pytest.raises(PermissionDenied):
        services.update_bookmark(bob, bm.id, label="hijacked")


def test_bookmark_needs_finance_edit(groceries):
    viewer = AccessContext.for_user(_finance_user(level="view"))
    with pytest.raises(PermissionDenied):
        _bookmark(viewer, groceries)


def test_bookmarks_hidden_without_finance_access(groceries):
    alice = AccessContext.for_user(_finance_user())
    _bookmark(alice, groceries)
    # Same user later loses finance access → nothing listed.
    no_access = AccessContext(user_id=alice.user_id, person_id=None, is_admin=False)
    assert list(selectors.list_bookmarks(no_access)) == []


# ---- Debts -------------------------------------------------------------


def test_debt_balance_per_counterparty():
    ctx = AccessContext.for_user(_finance_user())
    services.add_debt_entry(
        ctx,
        counterparty_name="Kasia",
        direction="gave",
        amount=Decimal("200"),
        date=date(2026, 3, 1),
    )
    services.add_debt_entry(
        ctx,
        counterparty_name="Kasia",
        direction="received",
        amount=Decimal("50"),
        date=date(2026, 3, 10),
    )
    # Names group case- and space-insensitively; here we owe them.
    services.add_debt_entry(
        ctx,
        counterparty_name="Marek",
        direction="received",
        amount=Decimal("100"),
        date=date(2026, 3, 2),
    )
    services.add_debt_entry(
        ctx,
        counterparty_name="marek ",
        direction="received",
        amount=Decimal("20"),
        date=date(2026, 3, 5),
    )

    balances = {b.counterparty_name: b.balance for b in selectors.debt_balances(ctx)}
    assert balances == {"Kasia": Decimal("150"), "Marek": Decimal("-120")}


def test_debts_never_touch_the_ledger():
    ctx = AccessContext.for_user(_finance_user())
    services.add_debt_entry(
        ctx,
        counterparty_name="Marek",
        direction="gave",
        amount=Decimal("500"),
        date=date(2026, 3, 1),
    )
    assert Transaction.objects.count() == 0
    assert selectors.monthly_totals(ctx, until=date(2026, 3, 1)) == []


def test_settle_zeroes_the_balance_but_keeps_the_person_listed():
    ctx = AccessContext.for_user(_finance_user())
    services.add_debt_entry(
        ctx,
        counterparty_name="Marek",
        direction="received",
        amount=Decimal("80"),
        date=date(2026, 3, 1),
    )
    entry = services.settle_debt(ctx, currency="PLN", on=date(2026, 4, 1), name="Marek")

    assert entry.direction == DebtEntry.Direction.GAVE  # we paid them back
    assert entry.amount == Decimal("80")
    (row,) = selectors.debt_balances(ctx)  # still listed, so they can be picked again
    assert (row.counterparty_name, row.balance, row.entries) == ("Marek", 0, 0)
    assert selectors.debt_balances(ctx, include_settled=True)[0].entries == 2
    # Nothing left to settle.
    assert services.settle_debt(ctx, currency="PLN", on=date(2026, 4, 2), name="Marek") is None


def test_debt_requires_counterparty_and_positive_amount():
    ctx = AccessContext.for_user(_finance_user())
    with pytest.raises(ValueError):
        services.add_debt_entry(ctx, direction="gave", amount=Decimal("10"), date=date(2026, 3, 1))
    with pytest.raises(ValueError):
        services.add_debt_entry(
            ctx, counterparty_name="X", direction="gave", amount=Decimal("0"), date=date(2026, 3, 1)
        )


def test_debts_need_finance_access():
    owner = AccessContext.for_user(_finance_user())
    services.add_debt_entry(
        owner,
        counterparty_name="Marek",
        direction="gave",
        amount=Decimal("10"),
        date=date(2026, 3, 1),
    )
    outsider = AccessContext.for_user(UserFactory())
    assert selectors.debt_balances(outsider) == []
    with pytest.raises(PermissionDenied):
        services.add_debt_entry(
            outsider,
            counterparty_name="Y",
            direction="gave",
            amount=Decimal("1"),
            date=date(2026, 3, 1),
        )
    viewer = AccessContext.for_user(_finance_user(level="view"))
    with pytest.raises(PermissionDenied):
        services.settle_debt(viewer, currency="PLN", on=date(2026, 3, 2), name="Marek")


# ---- HTTP layer --------------------------------------------------------


def test_bookmark_and_debt_endpoints_roundtrip(client, groceries):
    user = _finance_user()
    client.force_login(user)

    resp = client.post(
        "/api/finance/bookmarks",
        {
            "label": "Biedronka",
            "name": "Zakupy",
            "amount": "150.00",
            "category_id": str(groceries.id),
        },
        content_type="application/json",
    )
    assert resp.status_code == 200, resp.content
    assert [b["label"] for b in client.get("/api/finance/bookmarks").json()] == ["Biedronka"]

    resp = client.post(
        "/api/finance/debts/entries",
        {
            "counterparty_name": "Marek",
            "direction": "gave",
            "amount": "75.50",
            "date": "2026-03-01",
        },
        content_type="application/json",
    )
    assert resp.status_code == 200, resp.content
    balances = client.get("/api/finance/debts/balances").json()
    assert balances[0]["counterparty_name"] == "Marek"
    assert balances[0]["balance"] == "75.50"

    settle = {"name": "Marek", "currency": "PLN", "date": "2026-03-02"}
    resp = client.post("/api/finance/debts/settle", settle, content_type="application/json")
    assert resp.status_code == 200
    (row,) = client.get("/api/finance/debts/balances").json()
    assert (row["counterparty_name"], row["balance"]) == ("Marek", "0.00")
    history = client.get("/api/finance/debts/entries", {"name": "marek"}).json()
    assert history == []  # settled history hidden by default
    history = client.get(
        "/api/finance/debts/entries", {"name": "marek", "include_settled": True}
    ).json()
    assert len(history) == 2 and all(e["settled"] for e in history)
    resp = client.post("/api/finance/debts/settle", settle, content_type="application/json")
    assert resp.status_code == 204

    resp = client.post(
        "/api/finance/debts/entries",
        {"direction": "gave", "amount": "1", "date": "2026-03-01"},  # no counterparty
        content_type="application/json",
    )
    assert resp.status_code == 422


def test_after_settling_only_new_entries_are_current():
    ctx = AccessContext.for_user(_finance_user())

    def add(direction, amount, day):
        services.add_debt_entry(
            ctx,
            counterparty_name="Marek",
            direction=direction,
            amount=Decimal(amount),
            date=date(2026, 3, day),
        )

    add("gave", "100", 1)
    add("received", "40", 2)
    services.settle_debt(ctx, currency="PLN", on=date(2026, 3, 3), name="Marek")  # receives 60
    add("gave", "25", 10)  # a new loan after the settlement

    current = selectors.debt_history(ctx, name="Marek")
    assert [(e.direction, e.amount) for e in current] == [("gave", Decimal("25"))]

    everything = selectors.debt_history(ctx, name="Marek", include_settled=True)
    assert len(everything) == 4
    assert [e.settled for e in everything] == [False, True, True, True]  # newest first

    (row,) = selectors.debt_balances(ctx)
    assert (row.balance, row.entries, row.last_date) == (Decimal("25"), 1, date(2026, 3, 10))
    (row_all,) = selectors.debt_balances(ctx, include_settled=True)
    assert (row_all.balance, row_all.entries) == (Decimal("25"), 4)


def test_repayments_reaching_zero_also_close_the_period():
    """No explicit "settle" click needed — paying back in full closes it too."""
    ctx = AccessContext.for_user(_finance_user())
    for direction, amount, day in [("received", "50", 1), ("gave", "50", 5)]:
        services.add_debt_entry(
            ctx,
            counterparty_name="Ola",
            direction=direction,
            amount=Decimal(amount),
            date=date(2026, 3, day),
        )
    assert selectors.debt_history(ctx, name="Ola") == []
    (row,) = selectors.debt_balances(ctx)
    assert (row.balance, row.entries) == (0, 0)
    assert len(selectors.debt_history(ctx, name="Ola", include_settled=True)) == 2


def test_delete_counterparty_removes_all_their_entries(client):
    ctx = AccessContext.for_user(_finance_user())
    for name, direction in [("Marek", "gave"), ("marek", "received"), ("Ola", "gave")]:
        services.add_debt_entry(
            ctx,
            counterparty_name=name,
            direction=direction,
            amount=Decimal("10"),
            date=date(2026, 3, 1),
        )
    assert services.delete_counterparty(ctx, " MAREK ") == 2
    assert [b.counterparty_name for b in selectors.debt_balances(ctx)] == ["Ola"]

    viewer = AccessContext.for_user(_finance_user(level="view"))
    with pytest.raises(PermissionDenied):
        services.delete_counterparty(viewer, "Ola")

    client.force_login(_finance_user())
    resp = client.delete("/api/finance/debts/counterparty?name=Ola")
    assert resp.status_code == 200
    assert resp.json() == {"deleted": 1}
    assert selectors.debt_balances(ctx) == []
