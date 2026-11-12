"""Notes: privacy, sharing (view/edit), owner-only actions, reminders (to
others, repeating, Snooze/Done buttons), checklist, attachments."""

from __future__ import annotations

from datetime import timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from django.core.exceptions import PermissionDenied
from django.core.files.uploadedfile import SimpleUploadedFile
from django.http import Http404
from django.utils import timezone

from apps.access.context import AccessContext
from apps.core import attachments
from apps.notes import selectors, services
from apps.notes.models import Note
from apps.reminders.models import Reminder
from apps.reminders.tasks import dispatch_due_reminders

from .factories import AccessGrantFactory, PersonFactory, UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def fam():
    users = {}
    for name in ("mama", "tata", "zosia"):
        u = UserFactory()
        PersonFactory(display_name=name.title(), user=u)
        AccessGrantFactory(user=u, module="notes", level="edit")
        users[name] = u
    outsider = UserFactory()  # no notes grant, no person
    return {
        **{k: AccessContext.for_user(u) for k, u in users.items()},
        "users": users,
        "outsider": AccessContext.for_user(outsider),
    }


def note(ctx, **data):
    return services.save_note(ctx, {"title": "Zakupy", **data})


def pending(note_obj):
    return list(
        Reminder.objects.filter(
            object_id=note_obj.pk, status__in=[Reminder.Status.SCHEDULED, Reminder.Status.SNOOZED]
        )
    )


def test_notes_are_private_by_default(fam):
    mine = note(fam["mama"], body="tajne")
    assert list(selectors.list_notes(fam["tata"])) == []
    with pytest.raises(Http404):  # not even a hint that it exists
        selectors.get_note(fam["tata"], mine.id)
    with pytest.raises(PermissionDenied):
        selectors.list_notes(fam["outsider"])


def test_sharing_view_and_edit(fam):
    n = note(fam["mama"])
    u = fam["users"]
    services.set_shares(
        fam["mama"], n.id, [{"user_id": u["tata"].pk, "can_edit": True}, {"user_id": u["zosia"].pk}]
    )
    assert [x.id for x in selectors.list_notes(fam["zosia"], scope="shared")] == [n.id]
    assert list(selectors.list_notes(fam["zosia"], scope="mine")) == []

    services.save_note(fam["tata"], {"title": "Zakupy na sobotę"}, n.id)  # edit share
    with pytest.raises(PermissionDenied):  # view share
        services.save_note(fam["zosia"], {"title": "x"}, n.id)
    # only the owner shares, archives, deletes
    for action in (
        lambda: services.set_shares(fam["tata"], n.id, []),
        lambda: services.archive(fam["tata"], n.id),
        lambda: services.delete_note(fam["tata"], n.id),
    ):
        with pytest.raises(PermissionDenied):
            action()


def test_cannot_share_outside_the_family(fam):
    n = note(fam["mama"])
    stranger = UserFactory()
    with pytest.raises(ValueError):
        services.set_shares(fam["mama"], n.id, [{"user_id": stranger.pk}])


def test_empty_note_is_rejected(fam):
    with pytest.raises(ValueError):
        services.save_note(fam["mama"], {"title": " ", "checklist": [{"text": "  "}]})


def test_reminder_to_others_shares_the_note(fam):
    when = timezone.now() + timedelta(hours=2)
    n = note(fam["mama"], remind_at=when, remind_others=[fam["users"]["zosia"].pk])
    [r] = pending(n)
    assert set(r.recipients.all()) == {fam["users"]["mama"], fam["users"]["zosia"]}
    assert r.link == f"/notes?open={n.pk}"
    assert [a["action"] for a in r.actions] == ["snooze10", "done"]
    assert selectors.get_note(fam["zosia"], n.id)  # can read what she's reminded of

    # unsharing stops the reminders to her
    services.set_shares(fam["mama"], n.id, [])
    [r] = pending(n)
    assert list(r.recipients.all()) == [fam["users"]["mama"]]


def test_editing_the_time_replaces_the_reminder(fam):
    n = note(fam["mama"], remind_at=timezone.now() + timedelta(hours=1))
    services.save_note(fam["mama"], {"remind_at": timezone.now() + timedelta(hours=3)}, n.id)
    assert len(pending(n)) == 1
    services.archive(fam["mama"], n.id)
    assert pending(n) == []  # archived → no reminder


def test_notification_buttons_snooze_and_done(client, fam):
    n = note(fam["mama"], remind_at=timezone.now() + timedelta(minutes=1))
    [r] = pending(n)
    url = {a["action"]: a["url"] for a in r.actions}

    # The service worker posts without a session.
    token = parse_qs(urlparse(url["snooze10"]).query)["token"][0]
    assert client.post(f"/api/reminders/action?token={token}").status_code == 200
    r.refresh_from_db()
    assert r.status == Reminder.Status.SNOOZED
    assert r.due_at > timezone.now() + timedelta(minutes=9)

    # A snoozed reminder is delivered again when its new time comes.
    Reminder.objects.filter(pk=r.pk).update(due_at=timezone.now() - timedelta(seconds=1))
    assert dispatch_due_reminders() == 1

    token = parse_qs(urlparse(url["done"]).query)["token"][0]
    assert client.post(f"/api/reminders/action?token={token}").status_code == 200
    r.refresh_from_db()
    assert r.status == Reminder.Status.DONE
    assert client.post("/api/reminders/action?token=forged").status_code == 400


def test_repeating_note_rolls_to_the_next_time(fam):
    first = (timezone.now() + timedelta(minutes=30)).replace(second=0, microsecond=0)
    n = note(fam["mama"], remind_at=first, repeat="weekly")
    assert len(pending(n)) == 1

    later = first + timedelta(minutes=1)
    services.roll_forward(n, later)  # what the beat job does after it fired
    n.refresh_from_db()
    assert n.remind_at == first + timedelta(days=7)
    assert len(pending(n)) == 2  # the fired one (maybe snoozed) is left alone


def test_quick_add_understands_the_time(fam):
    n = services.quick_add(fam["mama"], "jutro 18:00 kupić mleko")
    assert n.title == "Kupić mleko"
    local = timezone.localtime(n.remind_at)
    assert (local.date(), local.hour) == (timezone.localdate() + timedelta(days=1), 18)
    assert len(pending(n)) == 1
    plain = services.quick_add(fam["mama"], "zadzwonić do babci")
    assert plain.title == "Zadzwonić do babci" and plain.remind_at is None


def test_checklist_toggle_needs_edit(fam):
    n = note(fam["mama"], checklist=[{"text": "Mleko"}, {"text": "  "}, {"text": "Chleb"}])
    assert [i["text"] for i in n.checklist] == ["Mleko", "Chleb"]  # blanks dropped
    services.set_shares(fam["mama"], n.id, [{"user_id": fam["users"]["zosia"].pk}])
    with pytest.raises(PermissionDenied):
        services.toggle_item(fam["zosia"], n.id, 0, True)
    n = services.toggle_item(fam["mama"], n.id, 1, True)
    assert n.checklist[1]["done"] is True
    with pytest.raises(ValueError):
        services.toggle_item(fam["mama"], n.id, 5, True)


def test_attachments_follow_the_note(fam, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    n = note(fam["mama"])
    photo = SimpleUploadedFile("paragon.jpg", b"\xff\xd8\xff", content_type="image/jpeg")
    attachments.upload(fam["mama"], n, photo)
    with pytest.raises(PermissionDenied):
        attachments.list_for(fam["tata"], n)  # not shared
    services.set_shares(fam["mama"], n.id, [{"user_id": fam["users"]["tata"].pk}])
    n = Note.objects.get(pk=n.pk)  # as a request loads it (fresh shares)
    assert len(attachments.list_for(fam["tata"], n)) == 1
    with pytest.raises(PermissionDenied):
        attachments.upload(fam["tata"], n, photo)  # view share can't add


def test_api_quick_add_and_parse(client, fam):
    client.force_login(fam["users"]["mama"])
    preview = client.get("/api/notes/parse", {"text": "za 40 min ciasto"}).json()
    assert preview["title"] == "Ciasto" and preview["remind_at"]
    resp = client.post(
        "/api/notes/quick", {"text": "za 40 min ciasto"}, content_type="application/json"
    )
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["is_owner"] and body["can_edit"] and body["remind_at"]
    people = client.get("/api/notes/people").json()
    assert {p["name"] for p in people} == {"Tata", "Zosia"}


def test_pin_is_saved_at_once_without_counting_as_an_edit(fam):
    n = note(fam["mama"])
    before = n.updated_at
    pinned = services.set_pinned(fam["mama"], n.id, True)
    assert pinned.pinned and pinned.updated_at == before
    services.set_shares(fam["mama"], n.id, [{"user_id": fam["users"]["zosia"].pk}])
    with pytest.raises(PermissionDenied):  # view share can't pin
        services.set_pinned(fam["zosia"], n.id, False)


def test_bulk_archive_restore_and_delete_own_notes(fam):
    a = note(fam["mama"], remind_at=timezone.now() + timedelta(hours=1))
    b = note(fam["mama"])
    assert services.bulk(fam["mama"], [a.id, b.id, a.id], "archive") == 2
    assert list(selectors.list_notes(fam["mama"])) == []
    assert pending(a) == []  # archived → its reminder is cancelled
    assert services.bulk(fam["mama"], [a.id], "unarchive") == 1
    assert len(pending(a)) == 1
    assert services.bulk(fam["mama"], [a.id, b.id], "delete") == 2
    assert not Note.objects.filter(pk__in=[a.pk, b.pk]).exists()


def test_bulk_is_all_or_nothing_for_notes_that_are_not_yours(fam):
    mine = note(fam["mama"])
    theirs = note(fam["tata"])
    services.set_shares(
        fam["tata"], theirs.id, [{"user_id": fam["users"]["mama"].pk, "can_edit": True}]
    )
    with pytest.raises(PermissionDenied):  # even an edit share isn't ownership
        services.bulk(fam["mama"], [mine.id, theirs.id], "delete")
    assert Note.objects.filter(pk__in=[mine.pk, theirs.pk]).count() == 2


def test_api_bulk_and_pin_routes(client, fam):
    """Through the URLs: "bulk" must not be taken for a note id."""
    client.force_login(fam["users"]["mama"])
    n = note(fam["mama"])
    resp = client.post(f"/api/notes/{n.id}/pin", {"pinned": True}, content_type="application/json")
    assert resp.status_code == 200 and resp.json()["pinned"] is True
    resp = client.post(
        "/api/notes/bulk",
        {"ids": [str(n.id)], "action": "archive"},
        content_type="application/json",
    )
    assert resp.status_code == 200, resp.content
    assert resp.json() == {"count": 1}
    resp = client.post(
        "/api/notes/bulk", {"ids": [], "action": "burn"}, content_type="application/json"
    )
    assert resp.status_code == 422
