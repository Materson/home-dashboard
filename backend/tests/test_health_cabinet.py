"""Medicine cabinet: real expiry after opening, search, reminders, access."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from django.core.exceptions import PermissionDenied
from django.utils import timezone

from apps.access.context import AccessContext
from apps.access.models import AccessGrant
from apps.health import selectors, services
from apps.health.models import MedicinePackage
from apps.reminders.models import Reminder

from .factories import AccessGrantFactory, UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def parent():
    user = UserFactory()
    AccessGrantFactory(user=user, module="health", level="edit")
    return AccessContext.for_user(user)


def item(ctx, **fields):
    data = {"name": "Nurofen dla dzieci", "substance": "ibuprofen", **fields}
    return services.save_cabinet_item(ctx, data)


def test_real_expiry_is_the_earlier_of_printed_and_after_opening():
    box = MedicinePackage(expiry_date=date(2027, 6, 30))
    assert box.effective_expiry == date(2027, 6, 30)
    box.opened_on, box.days_after_opening = date(2026, 3, 1), 28
    assert box.effective_expiry == date(2026, 3, 29)  # eye drops: 28 days once opened
    box.opened_on = date(2027, 6, 20)
    assert box.effective_expiry == date(2027, 6, 30)  # printed date still wins
    assert MedicinePackage().effective_expiry is None


def test_status_and_opening_moves_the_reminder(parent):
    today = timezone.localdate()
    syrup = item(parent, form="syrup")
    box = services.save_package(
        parent, {"expiry_date": today + timedelta(days=300)}, item_id=syrup.id
    )
    assert selectors.package_status(box, today) == "ok"
    (first,) = Reminder.objects.filter(object_id=box.id, status="scheduled")
    assert first.due_at.date() == today + timedelta(days=293)

    services.save_package(parent, {"opened_on": today, "days_after_opening": 14}, package_id=box.id)
    box.refresh_from_db()
    assert box.effective_expiry == today + timedelta(days=14)
    assert selectors.package_status(box, today) == "soon"
    (second,) = Reminder.objects.filter(object_id=box.id, status="scheduled")
    assert second.due_at.date() == today + timedelta(days=7)
    assert "Nurofen" in second.title

    # Used up: no more reminders, hidden unless asked for.
    services.save_package(parent, {"finished_on": today}, package_id=box.id)
    assert not Reminder.objects.filter(object_id=box.id, status="scheduled").exists()
    (listed,) = selectors.list_cabinet(parent)
    assert listed.shown_packages == []
    (listed,) = selectors.list_cabinet(parent, include_finished=True)
    assert [p.id for p in listed.shown_packages] == [box.id]


def test_expired_box_gets_no_reminder(parent):
    box = services.save_package(
        parent, {"expiry_date": timezone.localdate() - timedelta(days=1)}, item_id=item(parent).id
    )
    assert selectors.package_status(box, timezone.localdate()) == "expired"
    assert not Reminder.objects.filter(object_id=box.id).exists()


def test_search_by_what_it_is_for_and_for_whom(parent):
    item(parent, name="Nurofen dla dzieci", indications="gorączka, ból", for_whom="children")
    item(parent, name="Ketonal", indications="ból zęba", for_whom="adults")
    item(parent, name="Rutinoscorbin", indications="przeziębienie", for_whom="everyone")

    names = lambda **kw: sorted(i.name for i in selectors.list_cabinet(parent, **kw))  # noqa: E731
    assert names(q="gorącz") == ["Nurofen dla dzieci"]
    assert names(q="ból") == ["Ketonal", "Nurofen dla dzieci"]
    assert names(for_whom="children") == ["Nurofen dla dzieci", "Rutinoscorbin"]


def test_opened_after_printed_expiry_is_rejected(parent):
    with pytest.raises(ValueError):
        services.save_package(
            parent,
            {"expiry_date": date(2026, 1, 1), "opened_on": date(2026, 2, 1)},
            item_id=item(parent).id,
        )


def test_children_can_read_the_cabinet_but_not_change_it(parent):
    item(parent)
    child_user = UserFactory()
    AccessGrantFactory(
        user=child_user, module="health", level="view", subjects=AccessGrant.Subjects.SELF
    )
    child = AccessContext.for_user(child_user)
    assert len(selectors.list_cabinet(child)) == 1
    with pytest.raises(PermissionDenied):
        item(child, name="Cokolwiek")

    assert selectors.list_cabinet(AccessContext.for_user(UserFactory())) == []


def test_http_list_includes_boxes_and_status(client, parent):
    syrup = item(parent)
    services.save_package(
        parent, {"expiry_date": timezone.localdate() + timedelta(days=10)}, item_id=syrup.id
    )
    client.force_login(UserFactory(is_superuser=True))
    (row,) = client.get("/api/health/cabinet?q=ibuprofen").json()
    assert row["packages"][0]["status"] == "soon"
    assert row["packages"][0]["effective_expiry"]
