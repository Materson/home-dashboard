"""Assistant health changes: always proposals, person-scoped, and confirmed
through the health services (reminders, cabinet, files)."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from apps.access.context import AccessContext
from apps.access.models import AccessGrant
from apps.assistant import actions, llm, services
from apps.assistant.llm import ToolCall, Turn
from apps.assistant.models import AISettings, PendingAction, ProviderProfile
from apps.core.models import Attachment
from apps.health import services as health
from apps.health.models import (
    Appointment,
    Condition,
    DoseLog,
    Measurement,
    Medication,
    Symptom,
    TestResult,
)
from apps.reminders.models import Reminder

from .factories import AccessGrantFactory, PersonFactory, UserFactory
from .test_assistant import FakeAdapter

pytestmark = pytest.mark.django_db


@pytest.fixture
def home(monkeypatch):
    parent, child = UserFactory(), UserFactory()
    AccessGrantFactory(user=parent, module="health", level="edit")
    AccessGrantFactory(user=parent, module="assistant", level="edit")
    AccessGrantFactory(user=child, module="assistant", level="edit")
    AccessGrantFactory(
        user=child, module="health", level="edit", subjects=AccessGrant.Subjects.SELF
    )
    mama = PersonFactory(display_name="Mama", user=parent)
    zosia = PersonFactory(display_name="Zosia", user=child, birth_date=date(2022, 3, 1))
    local = ProviderProfile.objects.create(
        name="Ollama", kind="ollama", model="llama", location="local", base_url="http://pc/v1"
    )
    AISettings.objects.create(pk=1, chat_profile=local, local_profile=local)
    return {
        "parent": AccessContext.for_user(parent),
        "child": AccessContext.for_user(child),
        "mama": mama,
        "zosia": zosia,
        "monkeypatch": monkeypatch,
    }


def run(home, ctx, calls, files=None):
    """One turn where the model makes ``calls``; returns (actions, tool results)."""
    fake = FakeAdapter(
        Turn(
            text="",
            tool_calls=[ToolCall(str(i), name, args) for i, (name, args) in enumerate(calls)],
        ),
        Turn(text="Czeka na potwierdzenie.", tool_calls=[]),
    )
    fake.supported_files = frozenset({"image/jpeg", "image/png", "application/pdf"})
    home["monkeypatch"].setattr(llm, "TEST_ADAPTER", fake)
    conv = services.create_conversation(ctx)
    _, answer = services.send_message(ctx, conv.id, text="pytanie", files=files)
    return list(answer.actions.all()), fake.sessions[0].results[0]


def test_symptom_goes_to_the_ongoing_illness_after_confirm(home):
    flu = health.save_record(
        home["parent"],
        "conditions",
        {"person_id": home["zosia"].id, "title": "Grypa", "start_date": timezone.localdate()},
    )
    args = {
        "person": "Zosia",
        "symptom": "gorączka",
        "reading": "38,5 °C",
        "when": "2026-11-12T21:00",
    }
    [action], _ = run(home, home["parent"], [("propose_symptom", args)])
    assert action.status == PendingAction.Status.PROPOSED
    assert action.payload["event"] == "Grypa"
    assert not Symptom.objects.exists()  # nothing until confirmed

    actions.confirm(home["parent"], action.id)
    s = Symptom.objects.get()
    assert (s.condition_id, s.value) == (flu.id, "38,5 °C")
    assert timezone.localtime(s.observed_at).hour == 21
    actions.undo(home["parent"], action.id)
    assert not Symptom.objects.exists()


def test_symptom_without_an_ongoing_illness_asks_for_an_event(home):
    found, results = run(
        home, home["parent"], [("propose_symptom", {"person": "Zosia", "symptom": "kaszel"})]
    )
    assert not found
    assert results[0].is_error and "propose_health_event" in results[0].content


def test_new_event_with_symptoms(home):
    args = {
        "person": "Zosia",
        "title": "Angina",
        "symptoms": [{"symptom": "ból gardła"}, {"symptom": "gorączka", "reading": "39"}],
    }
    [action], _ = run(home, home["parent"], [("propose_health_event", args)])
    actions.confirm(home["parent"], action.id)
    event = Condition.objects.get(title="Angina")
    symptoms = sorted(event.symptom_log.values_list("symptom", flat=True))
    assert symptoms == ["ból gardła", "gorączka"]
    actions.undo(home["parent"], action.id)
    assert not Condition.objects.exists() and not Symptom.objects.exists()


def test_child_may_only_change_their_own_health(home):
    _, results = run(
        home, home["child"], [("propose_measurement", {"person": "Mama", "weight_kg": 70})]
    )
    # Mama's health isn't even visible to the child → no card, an error for the model.
    assert results[0].is_error and not PendingAction.objects.exists()
    [own], _ = run(
        home, home["child"], [("propose_measurement", {"person": "Zosia", "weight_kg": "18,2"})]
    )
    actions.confirm(home["child"], own.id)
    assert Measurement.objects.get().weight_kg == Decimal("18.2")


def test_visit_gets_its_reminders(home):
    when = (timezone.localtime() + timedelta(days=3)).replace(hour=16, minute=30)
    args = {
        "person": "Zosia",
        "starts_at": when.strftime("%Y-%m-%dT%H:%M"),
        "specialty": "Pediatra",
    }
    [action], _ = run(home, home["parent"], [("propose_visit", args)])
    actions.confirm(home["parent"], action.id)
    visit = Appointment.objects.get()
    assert Reminder.objects.filter(object_id=visit.pk, status="scheduled").count() == 2
    actions.undo(home["parent"], action.id)
    assert not Appointment.objects.exists()
    assert not Reminder.objects.filter(object_id=visit.pk, status="scheduled").exists()


def test_treatment_plans_doses_and_links_the_cabinet(home):
    args = {
        "person": "Zosia",
        "medicine": "Amoksycylina",
        "dosage": "5 ml",
        "dose_times": ["8", "20:00"],
        "days": 7,
    }
    [action], _ = run(home, home["parent"], [("propose_treatment", args)])
    assert action.payload["dose_times"] == ["08:00", "20:00"]
    assert action.payload["end_date"] == (timezone.localdate() + timedelta(days=6)).isoformat()
    actions.confirm(home["parent"], action.id)
    med = Medication.objects.get()
    assert med.cabinet_item is not None
    assert DoseLog.objects.filter(medication=med).exists()
    actions.undo(home["parent"], action.id)
    assert not Medication.objects.exists() and not DoseLog.objects.exists()


def test_lab_result_takes_the_attached_file(home, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    args = {"person": "Zosia", "title": "Morfologia", "lab": "Diagnostyka"}
    _, results = run(home, home["parent"], [("propose_lab_result", args)])
    assert results[0].is_error and "attach" in results[0].content  # no file in the message

    pdf = SimpleUploadedFile("wyniki.pdf", b"%PDF-1.4 test", content_type="application/pdf")
    [action], _ = run(home, home["parent"], [("propose_lab_result", args)], files=[pdf])
    assert action.payload["files"][0]["name"] == "wyniki.pdf"
    actions.confirm(home["parent"], action.id)
    result = TestResult.objects.get()
    copy = Attachment.objects.get(object_id=result.pk)
    assert copy.original_name == "wyniki.pdf"
    with copy.file.open("rb") as fh:  # closed before undo deletes it (Windows)
        assert fh.read() == b"%PDF-1.4 test"
    actions.undo(home["parent"], action.id)
    assert not TestResult.objects.exists()
    assert not Attachment.objects.filter(object_id=result.pk).exists()


def test_health_writes_are_never_offered_to_a_cloud_model_by_default(home):
    from apps.assistant.loop import available_tools  # noqa: PLC0415
    from apps.assistant.policy import policies  # noqa: PLC0415

    cloud = ProviderProfile.objects.create(
        name="C", kind="anthropic", model="claude-opus-5-5", api_key="k"
    )
    names = {t.name for t in available_tools(home["parent"], cloud, policies())}
    assert not names & {"propose_symptom", "propose_treatment", "propose_lab_result"}
