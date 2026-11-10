"""Household: stock in batches, consuming first-to-expire, the shopping list
following the minimum, ticking off with stock, reminders, permissions."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import PermissionDenied
from django.utils import timezone

from apps.access.context import AccessContext
from apps.household import selectors, services
from apps.household.models import ShoppingEntry
from apps.reminders.models import Reminder

from .factories import AccessGrantFactory, UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def home():
    editor, viewer, outsider = UserFactory(), UserFactory(), UserFactory()
    AccessGrantFactory(user=editor, module="household", level="edit")
    AccessGrantFactory(user=viewer, module="household", level="view")
    AccessGrantFactory(user=outsider, module="finance", level="view")
    return {
        "editor": AccessContext.for_user(editor),
        "viewer": AccessContext.for_user(viewer),
        "outsider": AccessContext.for_user(outsider),
        "editor_user": editor,
    }


def item(ctx, name="Mleko", min_quantity=None, **extra):
    return services.save_item(
        ctx, {"name": name, "unit": "l", "min_quantity": min_quantity, **extra}
    )


def add(ctx, it, qty, days=None):
    expiry = timezone.localdate() + timedelta(days=days) if days is not None else None
    return services.save_batch(
        ctx, {"quantity": Decimal(qty), "expiry_date": expiry}, item_id=it.id
    )


def open_lines(it):
    return list(ShoppingEntry.objects.filter(item=it, done_at__isnull=True))


def test_stock_and_next_expiry_come_from_open_batches(home):
    ctx = home["editor"]
    milk = item(ctx)
    add(ctx, milk, 2, days=5)
    add(ctx, milk, 1, days=2)
    old = add(ctx, milk, 4, days=1)
    services.finish_batch(ctx, old.id)

    listed = selectors.get_item(ctx, milk.id)
    assert listed.stock == Decimal(3)
    assert listed.next_expiry == timezone.localdate() + timedelta(days=2)


def test_consume_takes_from_what_expires_first(home):
    ctx = home["editor"]
    milk = item(ctx)
    later = add(ctx, milk, 2, days=6)
    sooner = add(ctx, milk, 1, days=1)
    undated = add(ctx, milk, 5)

    services.consume(ctx, milk.id, Decimal("1.5"))
    sooner.refresh_from_db()
    later.refresh_from_db()
    undated.refresh_from_db()
    assert sooner.finished_on == timezone.localdate()  # emptied first
    assert later.quantity == Decimal("1.5")
    assert undated.quantity == Decimal(5)


def test_shopping_list_follows_the_minimum(home):
    ctx = home["editor"]
    milk = item(ctx, min_quantity=Decimal(2))
    [line] = open_lines(milk)  # nothing in stock yet → on the list
    assert line.auto and line.quantity == "2 l"

    add(ctx, milk, 1)
    assert len(open_lines(milk)) == 1  # still below, not added twice

    add(ctx, milk, 3)
    assert open_lines(milk) == []  # back above → the auto line goes

    services.consume(ctx, milk.id, Decimal(3))
    assert len(open_lines(milk)) == 1  # below again


def test_hand_added_line_survives_restocking(home):
    ctx = home["editor"]
    milk = item(ctx, min_quantity=Decimal(1))
    add(ctx, milk, 5)
    line = services.add_entry(ctx, name="mleko", quantity="6 l")  # matches the item by name
    assert line.item_id == milk.id and not line.auto
    add(ctx, milk, 1)
    assert open_lines(milk) == [line]


def test_ticking_an_item_adds_stock(home):
    ctx = home["editor"]
    milk = item(ctx, min_quantity=Decimal(2))
    [line] = open_lines(milk)
    expiry = timezone.localdate() + timedelta(days=7)

    services.tick(ctx, line.id, bought=Decimal(4), expiry_date=expiry)
    assert selectors.get_item(ctx, milk.id).stock == Decimal(4)
    assert open_lines(milk) == []
    # ticked lines stay visible for a while (undo), then clear
    assert line.id in {e.id for e in selectors.shopping_list(ctx)}
    services.untick(ctx, line.id)
    assert open_lines(milk)[0].id == line.id
    services.tick(ctx, line.id)
    assert services.clear_done(ctx) == 1


def test_free_text_line(home):
    ctx = home["editor"]
    line = services.add_entry(ctx, name="  Kwiaty   dla babci ")
    assert line.name == "Kwiaty dla babci" and line.item is None
    with pytest.raises(ValueError):
        services.add_entry(ctx, name="  ")


def test_expiry_reminder_and_expiring_list(home):
    ctx = home["editor"]
    milk = item(ctx)
    batch = add(ctx, milk, 1, days=5)
    reminder = Reminder.objects.get(object_id=batch.pk, status=Reminder.Status.SCHEDULED)
    assert timezone.localtime(reminder.due_at).date() == timezone.localdate() + timedelta(days=3)
    assert reminder.title == "Kończy się termin: Mleko"

    add(ctx, item(ctx, "Ser"), 1, days=-1)  # already expired
    statuses = {b.item.name: selectors.batch_status(b) for b in selectors.expiring(ctx, days=7)}
    assert statuses == {"Mleko": "ok", "Ser": "expired"}

    services.consume(ctx, milk.id, Decimal(1))
    reminder.refresh_from_db()
    assert reminder.status == Reminder.Status.CANCELLED  # used up → no reminder


def test_archived_item_leaves_the_list(home):
    ctx = home["editor"]
    milk = item(ctx, min_quantity=Decimal(1))
    services.archive_item(ctx, milk.id)
    assert open_lines(milk) == []
    assert not selectors.list_items(ctx).filter(pk=milk.pk).exists()


def test_viewer_reads_but_cannot_change(home):
    milk = item(home["editor"], min_quantity=Decimal(1))
    assert list(selectors.list_items(home["viewer"])) == [milk]
    assert len(list(selectors.shopping_list(home["viewer"]))) == 1
    with pytest.raises(PermissionDenied):
        services.consume(home["viewer"], milk.id)
    with pytest.raises(PermissionDenied):
        services.add_entry(home["viewer"], name="Chleb")


def test_no_household_grant_sees_nothing(home):
    item(home["editor"])
    with pytest.raises(PermissionDenied):
        selectors.list_items(home["outsider"])
    with pytest.raises(PermissionDenied):
        selectors.shopping_list(home["outsider"])


def test_api_round_trip(client, home):
    client.force_login(home["editor_user"])
    resp = client.post(
        "/api/household/items",
        {
            "name": "Tabletki do zmywarki",
            "category": "cleaning",
            "unit": "szt.",
            "min_quantity": 10,
        },
        content_type="application/json",
    )
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["below_min"] is True and body["stock"] == "0.00"

    resp = client.post(
        f"/api/household/items/{body['id']}/batches",
        {"quantity": "40"},
        content_type="application/json",
    )
    assert resp.status_code == 200, resp.content
    assert resp.json()["status"] == "unknown"  # no expiry date
    [listed] = client.get("/api/household/items?category=cleaning").json()
    assert listed["below_min"] is False and listed["stock"] == "40.00"
    assert client.get("/api/household/shopping").json() == []


def test_shopping_api_tick_clear_and_delete(client, home):
    """Through the URLs: "clear-done" must not be taken for a line id."""
    client.force_login(home["editor_user"])
    add = lambda name: client.post(  # noqa: E731
        "/api/household/shopping", {"name": name}, content_type="application/json"
    ).json()
    bread, eggs = add("Chleb"), add("Jajka")

    resp = client.post(
        f"/api/household/shopping/{bread['id']}/tick", {}, content_type="application/json"
    )
    assert resp.status_code == 200 and resp.json()["done_at"]
    resp = client.post("/api/household/shopping/clear-done")
    assert resp.status_code == 200, resp.content
    assert resp.json() == {"deleted": 1}

    assert client.delete(f"/api/household/shopping/{eggs['id']}").status_code == 200
    assert client.get("/api/household/shopping").json() == []
