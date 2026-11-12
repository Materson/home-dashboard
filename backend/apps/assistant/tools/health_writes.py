# ruff: noqa: E501 — tool descriptions are prose for the model
"""Health changes — always proposals the user confirms (never done at once).

Each checks up front that the user may *edit* that person's health (a child:
only themself), so the model gets a clear error instead of a card that would
fail on Confirm. Confirming runs ``apps.health.services.save_record`` with
the user's AccessContext — the same rules as the health pages (visit and
dose reminders, cabinet linking, same-person illness check).
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.utils import timezone

from apps.health import selectors
from apps.health.doses import parse_times
from apps.people.models import Person

from . import (
    DATE,
    NUM,
    PERSON,
    STR,
    ToolError,
    ToolRun,
    arg_date,
    arg_datetime,
    arg_decimal,
    money,
    obj,
    tool,
)
from .people import find_person

WHEN = {"type": "string", "description": "Local time YYYY-MM-DDTHH:MM."}
EVENT = {
    "type": "string",
    "description": "Title of the person's illness/event it belongs to (default: the only ongoing one).",
}
KINDS = ["illness", "injury", "chronic", "allergy", "vaccination", "other"]


def _editable_person(run: ToolRun, name: str) -> Person:
    person = find_person(selectors.list_people(run.ctx), name)
    allowed = run.ctx.scope_by_person(
        module="health", qs=Person.objects.filter(pk=person.pk), person_field="id", level="edit"
    ).exists()
    if not allowed or not run.ctx.has("health", "edit"):
        raise ToolError(f"you may not change {person.display_name}'s health records")
    return person


def _event(run: ToolRun, person: Person, title: str | None, *, required: bool):
    events = selectors.list_records(run.ctx, "conditions", person_id=person.id)
    if title:
        wanted = title.strip().lower()
        hits = [e for e in events if e.title.lower() == wanted] or [
            e for e in events if wanted in e.title.lower()
        ]
        if not hits:
            raise ToolError(f"no illness/event {title!r} for this person")
        return sorted(hits, key=lambda e: (e.end_date is not None, -e.start_date.toordinal()))[0]
    ongoing = list(events.filter(end_date__isnull=True))
    if len(ongoing) == 1:
        return ongoing[0]
    if not required:
        return None
    if not ongoing:
        raise ToolError(
            "no ongoing illness/event — use propose_health_event (it can include the symptoms)"
        )
    raise ToolError(f"which illness/event? ongoing: {', '.join(e.title for e in ongoing)}")


def _when(args: dict, key: str, *, default_now: bool) -> str:
    value = arg_datetime(args, key)
    if value is None:
        if not default_now:
            raise ToolError(f"{key} is required (YYYY-MM-DDTHH:MM)")
        value = timezone.localtime().replace(tzinfo=None)
    if timezone.is_aware(value):
        value = timezone.localtime(value).replace(tzinfo=None)
    return value.replace(second=0, microsecond=0).isoformat(timespec="minutes")


def _symptom_rows(items: list[dict] | None) -> list[dict[str, str]]:
    rows = []
    for item in items or []:
        text = " ".join(str(item.get("symptom", "")).split())[:80]
        if text:
            rows.append(
                {
                    "symptom": text,
                    "reading": str(item.get("reading") or "")[:40],
                    "when": _when(item, "when", default_now=True),
                }
            )
    return rows


SYMPTOM_ITEM = obj(
    {"symptom": STR, "reading": {"type": "string", "description": "e.g. 38,5 °C"}, "when": WHEN},
    ("symptom",),
)


@tool(
    "propose_symptom",
    "Propose recording a symptom (with an optional reading like '38,5 °C') on a person's ongoing illness/event. Needs confirmation.",
    obj(
        {
            "person": PERSON,
            "symptom": STR,
            "reading": {"type": "string", "description": "e.g. 38,5 °C, 3 times at night"},
            "when": WHEN,
            "event": EVENT,
            "notes": STR,
        },
        ("person", "symptom"),
    ),
    module="health",
    policy="health",
    level="edit",
)
def propose_symptom(run: ToolRun, args: dict[str, Any]) -> Any:
    from apps.assistant import actions  # noqa: PLC0415

    person = _editable_person(run, args.get("person", ""))
    event = _event(run, person, args.get("event"), required=True)
    [row] = _symptom_rows([args]) or [None]
    if row is None:
        raise ToolError("symptom is required")
    payload = {
        "person_id": str(person.id),
        "person": person.display_name,
        "condition_id": str(event.id),
        "event": event.title,
        **row,
        "notes": str(args.get("notes") or "")[:1000],
    }
    return actions.propose(run, "health.symptom", payload)


@tool(
    "propose_health_event",
    "Propose a new illness/injury/allergy/vaccination for a person, optionally with its first symptoms. Needs confirmation.",
    obj(
        {
            "person": PERSON,
            "title": {"type": "string", "description": "e.g. Angina, Grypa"},
            "kind": {"type": "string", "enum": KINDS},
            "start_date": DATE,
            "notes": STR,
            "symptoms": {"type": "array", "items": SYMPTOM_ITEM},
        },
        ("person", "title"),
    ),
    module="health",
    policy="health",
    level="edit",
)
def propose_health_event(run: ToolRun, args: dict[str, Any]) -> Any:
    from apps.assistant import actions  # noqa: PLC0415

    person = _editable_person(run, args.get("person", ""))
    title = " ".join(str(args.get("title", "")).split())[:200]
    if not title:
        raise ToolError("title is required")
    kind = args.get("kind") or "illness"
    if kind not in KINDS:
        raise ToolError(f"kind must be one of {KINDS}")
    payload = {
        "person_id": str(person.id),
        "person": person.display_name,
        "title": title,
        "kind": kind,
        "start_date": (arg_date(args, "start_date") or timezone.localdate()).isoformat(),
        "notes": str(args.get("notes") or "")[:2000],
        "symptoms": _symptom_rows(args.get("symptoms")),
    }
    return actions.propose(run, "health.event", payload)


@tool(
    "propose_measurement",
    "Propose recording a person's weight and/or height (used for BMI and doses). Needs confirmation.",
    obj({"person": PERSON, "date": DATE, "weight_kg": NUM, "height_cm": NUM}, ("person",)),
    module="health",
    policy="health",
    level="edit",
)
def propose_measurement(run: ToolRun, args: dict[str, Any]) -> Any:
    from apps.assistant import actions  # noqa: PLC0415

    person = _editable_person(run, args.get("person", ""))
    weight = arg_decimal(args, "weight_kg", positive=True)
    height = arg_decimal(args, "height_cm", positive=True)
    if weight is None and height is None:
        raise ToolError("give weight_kg and/or height_cm")
    payload = {
        "person_id": str(person.id),
        "person": person.display_name,
        "date": (arg_date(args, "date") or timezone.localdate()).isoformat(),
        "weight_kg": str(weight) if weight is not None else None,
        "height_cm": str(height) if height is not None else None,
    }
    return actions.propose(run, "health.measurement", payload)


@tool(
    "propose_visit",
    "Propose a doctor's visit (reminders the evening before and 2 h before are set when saved). Needs confirmation.",
    obj(
        {
            "person": PERSON,
            "starts_at": WHEN,
            "doctor": STR,
            "specialty": STR,
            "place": STR,
            "room": STR,
            "purpose": STR,
            "event": EVENT,
            "cost": NUM,
            "notes": STR,
        },
        ("person", "starts_at"),
    ),
    module="health",
    policy="health",
    level="edit",
)
def propose_visit(run: ToolRun, args: dict[str, Any]) -> Any:
    from apps.assistant import actions  # noqa: PLC0415

    person = _editable_person(run, args.get("person", ""))
    event = _event(run, person, args.get("event"), required=False) if args.get("event") else None
    payload = {
        "person_id": str(person.id),
        "person": person.display_name,
        "starts_at": _when(args, "starts_at", default_now=False),
        **{
            k: str(args.get(k) or "")[:120]
            for k in ("doctor", "specialty", "place", "room", "purpose")
        },
        "condition_id": str(event.id) if event else None,
        "event": event.title if event else None,
        "cost": money(arg_decimal(args, "cost", positive=True)),
        "currency": "PLN",
        "notes": str(args.get("notes") or "")[:1000],
    }
    return actions.propose(run, "health.visit", payload)


@tool(
    "propose_treatment",
    "Propose a course of a medicine for a person: dosage, dose times (each gets a reminder) and how long. The medicine is matched to the cabinet or added to it. Needs confirmation.",
    obj(
        {
            "person": PERSON,
            "medicine": STR,
            "dosage": {"type": "string", "description": "e.g. 5 ml, 1 tabletka"},
            "dose_times": {"type": "array", "items": {"type": "string", "description": "HH:MM"}},
            "start_date": DATE,
            "days": {"type": "integer", "minimum": 1},
            "end_date": DATE,
            "event": EVENT,
            "reminders": {"type": "boolean", "description": "Dose reminders (default true)."},
            "notes": STR,
        },
        ("person", "medicine"),
    ),
    module="health",
    policy="health",
    level="edit",
)
def propose_treatment(run: ToolRun, args: dict[str, Any]) -> Any:
    from apps.assistant import actions  # noqa: PLC0415

    person = _editable_person(run, args.get("person", ""))
    medicine = " ".join(str(args.get("medicine", "")).split())[:120]
    if not medicine:
        raise ToolError("medicine is required")
    try:
        times = [t.strftime("%H:%M") for t in parse_times(args.get("dose_times") or [])]
    except ValueError as exc:
        raise ToolError(str(exc)) from exc
    start = arg_date(args, "start_date") or timezone.localdate()
    end = arg_date(args, "end_date")
    if end is None and args.get("days"):
        end = start + timedelta(days=int(args["days"]) - 1)
    if end and end < start:
        raise ToolError("end_date is before start_date")
    event = _event(run, person, args.get("event"), required=False)
    payload = {
        "person_id": str(person.id),
        "person": person.display_name,
        "medicine": medicine,
        "dosage": str(args.get("dosage") or "")[:120],
        "dose_times": times,
        "start_date": start.isoformat(),
        "end_date": end.isoformat() if end else None,
        "reminders": bool(args.get("reminders", True)) and bool(times),
        "condition_id": str(event.id) if event else None,
        "event": event.title if event else None,
        "notes": str(args.get("notes") or "")[:1000],
    }
    return actions.propose(run, "health.treatment", payload)


@tool(
    "propose_lab_result",
    "Propose saving a lab/test result for a person; the photo/PDF attached to the user's current message is attached to it. Needs confirmation.",
    obj(
        {
            "person": PERSON,
            "title": {"type": "string", "description": "e.g. Morfologia"},
            "date": DATE,
            "lab": STR,
            "notes": STR,
        },
        ("person", "title"),
    ),
    module="health",
    policy="health",
    level="edit",
)
def propose_lab_result(run: ToolRun, args: dict[str, Any]) -> Any:
    from django.contrib.contenttypes.models import ContentType  # noqa: PLC0415

    from apps.assistant import actions  # noqa: PLC0415
    from apps.assistant.models import Message  # noqa: PLC0415
    from apps.core.models import Attachment  # noqa: PLC0415

    person = _editable_person(run, args.get("person", ""))
    title = " ".join(str(args.get("title", "")).split())[:200]
    if not title:
        raise ToolError("title is required")
    files = []
    if run.message is not None:
        ct = ContentType.objects.get_for_model(Message)
        files = [
            {"id": str(a.id), "name": a.original_name}
            for a in Attachment.objects.filter(content_type=ct, object_id=run.message.pk)
        ]
    if not files:
        raise ToolError(
            "no file attached to this message — ask the user to attach the result (photo or PDF)"
        )
    payload = {
        "person_id": str(person.id),
        "person": person.display_name,
        "title": title,
        "date": (arg_date(args, "date") or timezone.localdate()).isoformat(),
        "lab": str(args.get("lab") or "")[:120],
        "notes": str(args.get("notes") or "")[:2000],
        "files": files,
    }
    return actions.propose(run, "health.result", payload)
