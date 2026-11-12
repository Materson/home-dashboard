"""Who a transaction was for: splits between people (also on repeating
payments and bookmarks), repeat from the form, per-person and per-category
chart totals."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from dateutil.relativedelta import relativedelta
from django.core.exceptions import PermissionDenied
from django.utils import timezone

from apps.access.context import AccessContext
from apps.finance import recurring, selectors, services
from apps.finance.models import Category, RecurringRule, Transaction

from .factories import AccessGrantFactory, PersonFactory, UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def fam():
    user = UserFactory()
    AccessGrantFactory(user=user, module="finance", level="edit")
    return {
        "ctx": AccessContext.for_user(user),
        "wife": PersonFactory(display_name="Ola"),
        "kid": PersonFactory(display_name="Zosia"),
        "insurance": Category.objects.filter(kind="expense").first(),
        "salary": Category.objects.get(key="income.salary"),
    }


def tx(fam, amount, *, shares=None, person=None, category=None, on=date(2026, 3, 10), **kw):
    data = {
        "date": on,
        "amount": Decimal(amount),
        "currency": "PLN",
        "category_id": (category or fam["insurance"]).id,
        "name": "Ubezpieczenie",
        "person_id": person.id if person else None,
    }
    return services.create_transaction(fam["ctx"], data, shares=shares, **kw)


def split(*parts):
    return [{"person_id": p.id, "amount": a} for p, a in parts]


def test_equal_split_keeps_every_cent():
    assert [a for _, a in services.equal_split(Decimal("100"), ["a", "b", "c"])] == [
        Decimal("33.34"),
        Decimal("33.33"),
        Decimal("33.33"),
    ]


def test_split_between_two_people(fam):
    t = tx(fam, "600", shares=split((fam["wife"], "400"), (fam["kid"], "200")))
    assert {(s.person_id, s.amount) for s in t.shares.all()} == {
        (fam["wife"].id, Decimal("400.00")),
        (fam["kid"].id, Decimal("200.00")),
    }
    assert t.person_id is None  # several people → not one "for whom"


def test_single_person_mirrors_the_old_field(fam):
    t = tx(fam, "80", person=fam["wife"])
    assert t.person_id == fam["wife"].id
    assert [(s.person_id, s.amount) for s in t.shares.all()] == [(fam["wife"].id, Decimal("80"))]


@pytest.mark.parametrize(
    "parts, message",
    [
        ((("wife", "400"), ("kid", "100")), "add up"),
        ((("wife", "600"), ("wife", "0")), "twice"),
        ((("wife", "700"), ("kid", "-100")), "more than 0"),
    ],
)
def test_bad_splits_are_rejected(fam, parts, message):
    with pytest.raises(ValueError, match=message):
        tx(fam, "600", shares=split(*[(fam[p], a) for p, a in parts]))
    assert not Transaction.objects.exists()


def test_repeat_keeps_the_split_and_follows_the_end_of_month(fam):
    first = tx(
        fam,
        "600",
        shares=split((fam["wife"], "300"), (fam["kid"], "300")),
        repeat="monthly",
        on=date(2026, 1, 31),
        repeat_until=date(2026, 3, 31),
    )
    rule = first.recurring_rule
    assert len(rule.shares) == 2
    later = Transaction.objects.filter(recurring_rule=rule).exclude(pk=first.pk).order_by("date")
    # filled in at once (the start is in the past); the 31st follows month ends
    assert [t.date for t in later] == [date(2026, 2, 28), date(2026, 3, 31)]
    assert all(t.shares.count() == 2 for t in later)
    rule.refresh_from_db()
    assert not rule.is_active  # past its end


def test_past_start_fills_every_occurrence_up_to_today(fam):
    today = timezone.localdate()
    start = (today - relativedelta(months=3)).replace(day=min(today.day, 28))
    first = tx(fam, "50", person=fam["kid"], repeat="monthly", on=start)
    dates = sorted(
        Transaction.objects.filter(recurring_rule=first.recurring_rule).values_list(
            "date", flat=True
        )
    )
    assert dates == [
        start + relativedelta(months=i)
        for i in range(4)
        if start + relativedelta(months=i) <= today
    ]
    rule = RecurringRule.objects.get()
    assert rule.next_run_at > today

    recurring.materialize_due(now=_noon(today))  # the night job adds nothing twice
    assert Transaction.objects.count() == len(dates)


def test_future_start_waits_for_its_date(fam):
    start = timezone.localdate() + timedelta(days=10)
    tx(fam, "50", repeat="weekly", on=start)
    assert Transaction.objects.count() == 1
    assert RecurringRule.objects.get().next_run_at == start + timedelta(days=7)


def _series(fam, months=4):
    today = timezone.localdate()
    start = (today - relativedelta(months=months)).replace(day=min(today.day, 28))
    tx(fam, "100", person=fam["wife"], repeat="monthly", on=start)
    return list(Transaction.objects.order_by("date"))


def _edit(fam, t, amount, *, future):
    data = {
        "date": t.date,
        "amount": Decimal(amount),
        "currency": "PLN",
        "category_id": fam["insurance"].id,
        "name": "Ubezpieczenie",
        "person_id": None,
    }
    services.update_transaction(
        fam["ctx"], t.id, data, shares=split((fam["wife"], amount)), update_future=future
    )


def test_edit_only_this_occurrence(fam):
    series = _series(fam)
    _edit(fam, series[2], "120", future=False)
    amounts = [t.amount for t in Transaction.objects.order_by("date")]
    assert amounts == [
        Decimal("100"),
        Decimal("100"),
        Decimal("120"),
        Decimal("100"),
        Decimal("100"),
    ]
    assert RecurringRule.objects.get().amount == Decimal("100")


def test_edit_this_and_all_following(fam):
    series = _series(fam)
    _edit(fam, series[2], "120", future=True)
    amounts = [t.amount for t in Transaction.objects.order_by("date")]
    assert amounts == [
        Decimal("100"),
        Decimal("100"),
        Decimal("120"),
        Decimal("120"),
        Decimal("120"),
    ]
    assert RecurringRule.objects.get().amount == Decimal("120")
    later = Transaction.objects.order_by("date")[4]
    assert [(s.person_id, s.amount) for s in later.shares.all()] == [
        (fam["wife"].id, Decimal("120"))
    ]


def test_edit_the_repeating_payment_from_the_list(fam):
    series = _series(fam, months=2)
    rule = RecurringRule.objects.get()
    services.update_recurring(
        fam["ctx"],
        rule.id,
        {
            "name": "Ubezpieczenie OC",
            "amount": Decimal("90"),
            "currency": "PLN",
            "category_id": fam["insurance"].id,
            "notes": "",
            "end_date": None,
        },
        shares=split((fam["wife"], "45"), (fam["kid"], "45")),
        repeat="weekly",
    )
    rule.refresh_from_db()
    assert (rule.name, rule.amount, rule.rrule, len(rule.shares)) == (
        "Ubezpieczenie OC",
        Decimal("90"),
        "FREQ=WEEKLY",
        2,
    )
    assert rule.next_run_at > timezone.localdate()
    recorded = list(Transaction.objects.order_by("date"))
    assert len(recorded) <= len(series) + 1  # weekly from today on - no back-fill
    kept = [t.amount for t in recorded[: len(series)]]
    assert kept == [Decimal("100")] * len(series)  # recorded ones stay
    assert all(t.amount == Decimal("90") and t.shares.count() == 2 for t in recorded[len(series) :])
    with pytest.raises(ValueError, match="end"):
        services.update_recurring(
            fam["ctx"],
            rule.id,
            {
                "name": "x",
                "amount": Decimal("90"),
                "currency": "PLN",
                "category_id": fam["insurance"].id,
                "notes": "",
                "end_date": rule.start_date - timedelta(days=1),
            },
        )


def test_editing_with_apply_to_future_copies_the_split(fam):
    first = tx(fam, "100", person=fam["wife"], repeat="monthly")
    data = {
        "date": first.date,
        "amount": Decimal("120"),
        "currency": "PLN",
        "category_id": fam["insurance"].id,
        "name": "Ubezpieczenie",
        "person_id": None,
    }
    services.update_transaction(
        fam["ctx"],
        first.id,
        data,
        shares=split((fam["wife"], "60"), (fam["kid"], "60")),
        update_future=True,
    )
    rule = RecurringRule.objects.get()
    assert rule.amount == Decimal("120") and len(rule.shares) == 2 and rule.person_id is None


def test_bookmark_keeps_the_split(fam):
    bm = services.create_bookmark(
        fam["ctx"],
        label="Ubezp.",
        name="Ubezpieczenie",
        amount=Decimal("600"),
        category_id=fam["insurance"].id,
        shares=split((fam["wife"], "300"), (fam["kid"], "300")),
    )
    assert [s["amount"] for s in bm.shares] == ["300.00", "300.00"]


def test_chart_totals_per_person_and_category(fam):
    tx(fam, "600", shares=split((fam["wife"], "400"), (fam["kid"], "200")))
    tx(fam, "50", person=fam["kid"])
    tx(fam, "100")  # household, not split
    tx(fam, "5000", category=fam["salary"])  # income

    period = {"date_from": date(2026, 3, 1), "date_to": date(2026, 3, 31)}
    people = selectors.person_totals(fam["ctx"], kind="expense", **period)
    assert {(s.key, s.total) for s in people} == {
        (str(fam["wife"].id), Decimal("400")),
        (str(fam["kid"].id), Decimal("250")),
        ("shared", Decimal("100")),
    }
    kid = selectors.category_totals(fam["ctx"], kind="expense", person=str(fam["kid"].id), **period)
    assert [s.total for s in kid] == [Decimal("250")]
    shared = selectors.category_totals(fam["ctx"], kind="expense", person="shared", **period)
    assert [s.total for s in shared] == [Decimal("100")]
    income = selectors.category_totals(fam["ctx"], kind="income", **period)
    # Wynagrodzenie is a sub-category: the pie shows its main one
    assert [(s.label, s.total) for s in income] == [(fam["salary"].parent.name, Decimal("5000"))]

    months = selectors.monthly_totals(
        fam["ctx"], until=date(2026, 3, 31), months=1, person=str(fam["wife"].id)
    )
    assert [(m.kind, m.total) for m in months] == [("expense", Decimal("400"))]
    found = selectors.list_transactions(
        fam["ctx"], selectors.TransactionFilter(person_ids=[fam["kid"].id])
    )
    assert found.count() == 2  # the split one counts for her too


def test_api_create_with_split_and_repeat(client, fam):
    client.force_login(UserFactory(is_superuser=True))
    body = {
        "date": "2026-03-10",
        "amount": "600",
        "category_id": str(fam["insurance"].id),
        "name": "Ubezpieczenie",
        "shares": [
            {"person_id": str(fam["wife"].id), "amount": "400"},
            {"person_id": str(fam["kid"].id), "amount": "100"},
        ],
        "repeat": "yearly",
    }
    resp = client.post("/api/finance/transactions", body, content_type="application/json")
    assert resp.status_code == 422 and "add up" in resp.json()["detail"]
    body["shares"][1]["amount"] = "200"
    resp = client.post("/api/finance/transactions", body, content_type="application/json")
    assert resp.status_code == 200, resp.content
    assert len(resp.json()["shares"]) == 2
    [rule] = client.get("/api/finance/recurring").json()
    assert rule["next_run_at"] == "2027-03-10" and len(rule["shares"]) == 2
    resp = client.get(
        "/api/finance/person-totals", {"date_from": "2026-03-01", "date_to": "2026-03-31"}
    )
    assert {r["total"] for r in resp.json()} == {"400.00", "200.00"}


def _noon(day: date):
    from datetime import datetime, time  # noqa: PLC0415

    from django.utils import timezone  # noqa: PLC0415

    return timezone.make_aware(datetime.combine(day, time(12)))


# ---------------- categories ----------------


def test_category_editor(fam):
    ctx = fam["ctx"]
    pets = services.create_category(ctx, name="  Zwierzęta ", kind="expense", color="#ff0000")
    assert pets.name == "Zwierzęta" and pets.key.startswith("user.")
    with pytest.raises(ValueError, match="already exists"):
        services.create_category(ctx, name="zwierzęta", kind="expense")
    services.update_category(ctx, pets.id, name="Zwierzaki", color="#00ff00")
    builtin = Category.objects.get(key="income.salary")
    services.update_category(ctx, builtin.id, name="Pensja", color="")
    assert Category.objects.get(key="income.salary").name == "Pensja"  # key stays

    tx(fam, "40", category=pets)
    with pytest.raises(ValueError, match="merge"):
        services.delete_category(ctx, pets.id)
    with pytest.raises(ValueError, match="same kind"):
        services.merge_category(ctx, pets.id, builtin.id)
    assert services.merge_category(ctx, pets.id, fam["insurance"].id) == 1
    assert not Category.objects.filter(pk=pets.pk).exists()
    with pytest.raises(ValueError, match="built-in"):
        services.delete_category(ctx, builtin.id)


def test_category_api_lists_usage(client, fam):
    client.force_login(UserFactory(is_superuser=True))
    tx(fam, "40")
    rows = {c["id"]: c for c in client.get("/api/finance/categories").json()}
    assert rows[str(fam["insurance"].id)]["used"] == 1
    resp = client.post(
        "/api/finance/categories", {"name": "Hobby"}, content_type="application/json"
    )
    assert resp.status_code == 200 and resp.json()["used"] == 0
    assert client.delete(f"/api/finance/categories/{resp.json()['id']}").json() == {"deleted": True}


# ---------------- sub-categories ----------------


def test_sub_categories(fam):
    ctx = fam["ctx"]
    car = Category.objects.get(key="car")
    fuel = Category.objects.get(key="car.fuel")
    pets = services.create_category(ctx, name="Zwierzęta", kind="expense", color="#ff0000")
    food = services.create_category(ctx, name="Karma", kind="expense", parent_id=pets.id)
    assert food.parent == pets and food.color == "#ff0000"  # the main one's colour
    # "Inne" may sit under two main categories, but not twice under one
    services.create_category(ctx, name="Inne", kind="expense", parent_id=pets.id)
    services.create_category(ctx, name="Inne", kind="expense", parent_id=car.id)
    with pytest.raises(ValueError, match="already exists"):
        services.create_category(ctx, name="inne", kind="expense", parent_id=car.id)
    for parent, message in ((fam["salary"].parent, "same kind"), (food, "of its own")):
        with pytest.raises(ValueError, match=message):
            services.create_category(ctx, name="X", kind="expense", parent_id=parent.id)

    # move: a built-in one under another main category; two levels, no loops
    services.update_category(ctx, fuel.id, name=fuel.name, color="", parent_id=pets.id)
    assert Category.objects.get(key="car.fuel").parent == pets
    with pytest.raises(ValueError, match="under itself"):
        services.update_category(ctx, pets.id, name="Zwierzęta", color="", parent_id=pets.id)
    with pytest.raises(ValueError, match="stays a main category"):
        services.update_category(ctx, pets.id, name="Zwierzęta", color="", parent_id=car.id)
    services.update_category(ctx, food.id, name="Karma", color="", parent_id=None)
    assert Category.objects.get(pk=food.pk).parent is None

    # a main one with sub-categories: not deleted, merged only into a main one
    with pytest.raises(ValueError, match="move or delete"):
        services.delete_category(ctx, pets.id)
    maintenance = Category.objects.get(key="car.maintenance")
    with pytest.raises(ValueError, match="another main category"):
        services.merge_category(ctx, pets.id, maintenance.id)
    services.merge_category(ctx, pets.id, car.id)
    assert Category.objects.get(key="car.fuel").parent == car  # came along


def test_only_finance_editors_arrange_categories(fam):
    viewer = UserFactory()
    AccessGrantFactory(user=viewer, module="finance", level="view")
    ctx = AccessContext.for_user(viewer)
    car = Category.objects.get(key="car")
    with pytest.raises(PermissionDenied):
        services.create_category(ctx, name="Myjnia", kind="expense", parent_id=car.id)
    fuel = Category.objects.get(key="car.fuel")
    with pytest.raises(PermissionDenied):
        services.update_category(ctx, fuel.id, name="Paliwo", color="", parent_id=None)
    assert Category.objects.get(key="car.fuel").parent == car


def test_charts_and_filter_take_sub_categories_along(fam):
    car = Category.objects.get(key="car")
    fuel = Category.objects.get(key="car.fuel")
    inspection = Category.objects.get(key="car.inspection")
    tx(fam, "200", category=fuel)
    tx(fam, "100", category=fuel, person=fam["kid"])
    tx(fam, "150", category=inspection)
    tx(fam, "50", category=car)  # straight into the main one
    period = {"date_from": date(2026, 3, 1), "date_to": date(2026, 3, 31)}

    [main] = selectors.category_totals(fam["ctx"], kind="expense", **period)
    assert (main.key, main.label, main.total) == (str(car.id), car.name, Decimal("500"))
    inside = selectors.category_totals(fam["ctx"], kind="expense", parent=car.id, **period)
    assert [(s.label, s.total) for s in inside] == [
        (fuel.name, Decimal("300")),
        (inspection.name, Decimal("150")),
        (car.name, Decimal("50")),
    ]
    kid = selectors.category_totals(
        fam["ctx"], kind="expense", parent=car.id, person=str(fam["kid"].id), **period
    )
    assert [(s.label, s.total) for s in kid] == [(fuel.name, Decimal("100"))]

    def count(*keys):
        f = selectors.TransactionFilter(category_keys=list(keys))
        return selectors.list_transactions(fam["ctx"], f).count()

    assert (count("car"), count("car.fuel"), count("car.inspection", "car.fuel")) == (4, 2, 3)


def test_sub_category_api(client, fam):
    client.force_login(UserFactory(is_superuser=True))
    car = Category.objects.get(key="car")
    resp = client.post(
        "/api/finance/categories",
        {"name": "Myjnia", "parent_id": str(car.id)},
        content_type="application/json",
    )
    assert resp.status_code == 200 and resp.json()["parent_id"] == str(car.id)
    wash = resp.json()["id"]
    resp = client.put(
        f"/api/finance/categories/{car.id}",
        {"name": car.name, "parent_id": str(Category.objects.get(key="home").id)},
        content_type="application/json",
    )
    assert resp.status_code == 422 and "main category" in resp.json()["detail"]
    tx(fam, "30", category=Category.objects.get(pk=wash))
    rows = client.get(
        "/api/finance/category-totals",
        {"date_from": "2026-03-01", "date_to": "2026-03-31", "parent": str(car.id)},
    ).json()
    assert [(r["label"], r["total"]) for r in rows] == [("Myjnia", "30.00")]
