"""Health: person scoping, ledger, appointment reminders, doses, attachments."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import PermissionDenied
from django.core.files.uploadedfile import SimpleUploadedFile
from django.http import Http404
from django.utils import timezone

from apps.access.context import AccessContext
from apps.access.models import AccessGrant
from apps.finance.models import Transaction
from apps.health import doses, selectors, services
from apps.health.models import DoseLog
from apps.reminders.models import Reminder

from .factories import AccessGrantFactory, GroupFactory, PersonFactory, UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def family():
    """A parent (health edit, everyone) and a child (health view, self only)."""
    parent_user, child_user = UserFactory(), UserFactory()
    parents = GroupFactory()
    parent_user.groups.add(parents)
    AccessGrantFactory(group=parents, module="health", level="edit")
    AccessGrantFactory(
        user=child_user, module="health", level="view", subjects=AccessGrant.Subjects.SELF
    )
    mom = PersonFactory(display_name="Mama", user=parent_user)
    kid = PersonFactory(display_name="Zosia", user=child_user)
    return {
        "parent": AccessContext.for_user(parent_user),
        "child": AccessContext.for_user(child_user),
        "mom": mom,
        "kid": kid,
    }


def condition(ctx, person, title="Angina", start=date(2026, 3, 1)):
    return services.save_record(
        ctx, "conditions", {"person_id": person.id, "title": title, "start_date": start}
    )


# ---- scoping -----------------------------------------------------------------


def test_child_sees_only_their_own_health(family):
    condition(family["parent"], family["mom"], "Migrena")
    own = condition(family["parent"], family["kid"], "Angina")

    child = family["child"]
    assert list(selectors.list_people(child)) == [family["kid"]]
    assert list(selectors.list_records(child, "conditions")) == [own]
    with pytest.raises(PermissionDenied):  # view-only
        condition(child, family["kid"], "Katar")


def test_records_cannot_be_moved_to_someone_out_of_scope(family):
    restricted_user = UserFactory()
    AccessGrantFactory(
        user=restricted_user,
        module="health",
        level="edit",
        subjects=AccessGrant.Subjects.SELECTED,
        person_ids=[str(family["kid"].id)],
    )
    ctx = AccessContext.for_user(restricted_user)
    record = condition(ctx, family["kid"])
    with pytest.raises(PermissionDenied):
        services.save_record(ctx, "conditions", {"person_id": family["mom"].id}, record.id)
    with pytest.raises(Http404):  # mom's records don't even exist for them
        selectors.get_record(ctx, "conditions", condition(family["parent"], family["mom"]).id)


def test_date_window_hides_older_history(family):
    windowed_user = UserFactory()
    AccessGrantFactory(
        user=windowed_user, module="health", level="view", data_from=date(2026, 1, 1)
    )
    condition(family["parent"], family["kid"], "Old", start=date(2025, 6, 1))
    new = condition(family["parent"], family["kid"], "New", start=date(2026, 2, 1))
    assert list(selectors.list_records(AccessContext.for_user(windowed_user), "conditions")) == [
        new
    ]


def test_medication_cannot_link_another_persons_illness(family):
    moms_illness = condition(family["parent"], family["mom"])
    with pytest.raises(ValueError):
        services.save_record(
            family["parent"],
            "medications",
            {
                "person_id": family["kid"].id,
                "name": "Ibuprofen",
                "start_date": date(2026, 3, 1),
                "condition_id": moms_illness.id,
            },
        )


# ---- ledger & appointment reminders -----------------------------------------


def test_medicine_purchase_goes_to_finance_without_finance_access(family):
    purchase = services.save_record(
        family["parent"],
        "purchases",
        {
            "person_id": family["kid"].id,
            "date": date(2026, 3, 2),
            "name": "Amoksycylina",
            "cost": Decimal("32.50"),
        },
    )
    tx = Transaction.objects.get(source_id=purchase.id)
    assert (tx.category.key, tx.amount, tx.person_id) == (
        "health.medicines",
        Decimal("32.50"),
        family["kid"].id,
    )


def test_appointment_reminders_are_generic_and_follow_status(family):
    starts = timezone.localtime() + timedelta(days=3)
    appt = services.save_record(
        family["parent"],
        "appointments",
        {"person_id": family["kid"].id, "starts_at": starts, "specialty": "Laryngolog"},
    )
    live = Reminder.objects.filter(object_id=appt.id, status=Reminder.Status.SCHEDULED)
    assert live.count() == 2
    assert all(r.sensitivity == "private" and "Laryngolog" not in r.title for r in live)

    services.save_record(family["parent"], "appointments", {"status": "cancelled"}, appt.id)
    assert live.all().count() == 0  # .all(): `live` was iterated above, so it is cached


# ---- doses -------------------------------------------------------------------


def medication(ctx, person, times=("08:00", "20:00"), start=None, end=None):
    return services.save_record(
        ctx,
        "medications",
        {
            "person_id": person.id,
            "name": "Amoksycylina",
            "dosage": "5 ml",
            "start_date": start or timezone.localdate(),
            "end_date": end,
            "dose_times": list(times),
        },
    )


def test_doses_are_planned_48h_ahead_with_action_buttons(family):
    med = medication(family["parent"], family["kid"])
    upcoming = DoseLog.objects.filter(medication=med, scheduled_at__gt=timezone.now())
    assert 3 <= upcoming.count() <= 4  # two a day within the next 48 h
    reminder = Reminder.objects.get(object_id=upcoming.first().id)
    assert reminder.title == "Pora na lek" and reminder.sensitivity == "private"
    assert [a["title"] for a in reminder.actions] == ["Wzięte", "Pominięte"]


def test_hourly_top_up_does_not_churn_reminders(family):
    med = medication(family["parent"], family["kid"])
    before = Reminder.objects.count()
    doses.plan_all()
    doses.plan_all()
    assert Reminder.objects.count() == before
    assert not Reminder.objects.filter(status=Reminder.Status.CANCELLED).exists()

    # An edit does replace the future plan.
    services.save_record(family["parent"], "medications", {"dose_times": ["12:00"]}, med.id)
    times = {
        d.scheduled_at.astimezone().strftime("%H:%M") for d in med.doses.filter(status="pending")
    }
    assert times == {"12:00"}


def test_finished_course_plans_nothing(family):
    med = medication(
        family["parent"],
        family["kid"],
        end=timezone.localdate() - timedelta(days=1),
        start=timezone.localdate() - timedelta(days=7),
    )
    assert not med.doses.exists()


def test_notification_button_marks_the_dose(client, family):
    med = medication(family["parent"], family["kid"])
    dose = med.doses.first()
    token = doses.action_token(dose, "taken")

    resp = client.post(f"/api/health/doses/action?token={token}")  # no session at all
    assert resp.status_code == 200
    dose.refresh_from_db()
    assert dose.status == "taken"
    assert not Reminder.objects.filter(object_id=dose.id, status="scheduled").exists()

    assert client.post("/api/health/doses/action?token=forged").status_code == 400


def test_child_can_confirm_only_their_own_doses(family):
    kid_dose = medication(family["parent"], family["kid"]).doses.first()
    mom_dose = medication(family["parent"], family["mom"]).doses.first()

    services.set_dose_status(family["child"], kid_dose.id, "taken")
    with pytest.raises(Http404):
        services.set_dose_status(family["child"], mom_dose.id, "taken")


def test_invalid_dose_time_is_rejected(family):
    with pytest.raises(ValueError):
        medication(family["parent"], family["kid"], times=("25:99",))


# ---- attachments -------------------------------------------------------------


def test_result_file_upload_view_and_scoping(client, family, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    result = services.save_record(
        family["parent"],
        "results",
        {"person_id": family["kid"].id, "date": date(2026, 3, 3), "title": "Morfologia"},
    )
    parent_user = family["mom"].user
    client.force_login(parent_user)

    pdf = SimpleUploadedFile("wyniki_badań.pdf", b"%PDF-1.4 test", content_type="application/pdf")
    resp = client.post(
        "/api/attachments",
        {"subject_type": "health.testresult", "subject_id": str(result.id), "file": pdf},
    )
    assert resp.status_code == 200, resp.content
    url = resp.json()["url"]

    # Production: nginx serves the file via an internal redirect.
    download = client.get(url)
    assert download.status_code == 200
    accel = download["X-Accel-Redirect"]
    assert accel.startswith("/protected-media/attachments/") and accel.isascii()
    assert "bada" not in accel  # stored under a generated name, not the original
    assert "no-store" in download["Cache-Control"]
    # Development (runserver, no nginx): Django streams it itself.
    settings.DEBUG = True
    download = client.get(url)
    assert b"".join(download.streaming_content) == b"%PDF-1.4 test"
    assert "filename*=utf-8''wyniki_bada%C5%84.pdf" in download["Content-Disposition"]
    settings.DEBUG = False

    exe = SimpleUploadedFile("virus.exe", b"MZ", content_type="application/pdf")
    resp = client.post(
        "/api/attachments",
        {"subject_type": "health.testresult", "subject_id": str(result.id), "file": exe},
    )
    assert resp.status_code == 422

    # Mom's own result is invisible to the child — the file too.
    moms = services.save_record(
        family["parent"],
        "results",
        {"person_id": family["mom"].id, "date": date(2026, 3, 3), "title": "TSH"},
    )
    resp = client.post(
        "/api/attachments",
        {
            "subject_type": "health.testresult",
            "subject_id": str(moms.id),
            "file": SimpleUploadedFile("tsh.pdf", b"%PDF", content_type="application/pdf"),
        },
    )
    moms_file = resp.json()["url"]
    client.force_login(family["kid"].user)
    assert client.get(url).status_code == 200  # their own
    assert client.get(moms_file).status_code == 403

    # Deleting the result removes its files from disk.
    stored = list(tmp_path.rglob("*.pdf"))
    services.delete_record(family["parent"], "results", result.id)
    assert len(list(tmp_path.rglob("*.pdf"))) == len(stored) - 1
