"""Changes the assistant makes: proposals the user confirms, and small own
additions done at once with Undo.

Every kind has ``execute`` (calls the app's own service with the user's
AccessContext, so permissions are checked again at confirm time) and
``undo``. Payloads hold real values (never aliases) plus display fields.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import UUID

from django.core.exceptions import ObjectDoesNotExist, PermissionDenied
from django.db.transaction import atomic
from django.http import Http404

from .models import Conversation, PendingAction

if TYPE_CHECKING:
    from apps.access.context import AccessContext

    from .tools import ToolRun


@dataclass(frozen=True)
class Kind:
    execute: Callable[[AccessContext, dict[str, Any]], list[dict[str, str]]]
    undo: Callable[[AccessContext, list[dict[str, str]]], None]


# ---- finance ----


def _tx_execute(ctx: AccessContext, p: dict[str, Any]) -> list[dict[str, str]]:
    from apps.finance import services  # noqa: PLC0415

    tx = services.create_transaction(
        ctx,
        {
            "date": date.fromisoformat(p["date"]),
            "amount": Decimal(p["amount"]),
            "currency": p["currency"],
            "category_id": UUID(p["category_id"]),
            "person_id": UUID(p["person_id"]) if p.get("person_id") else None,
            "name": p["name"],
            "notes": p.get("notes", ""),
        },
    )
    return [{"type": "finance.transaction", "id": str(tx.id)}]


def _tx_undo(ctx: AccessContext, result: list[dict[str, str]]) -> None:
    from apps.finance.models import Transaction  # noqa: PLC0415

    ctx.require("finance", "edit")
    Transaction.objects.filter(pk__in=[r["id"] for r in result]).delete()


# ---- cars ----


def _car_execute(kind: str) -> Callable:
    def execute(ctx: AccessContext, p: dict[str, Any]) -> list[dict[str, str]]:
        from apps.cars import services  # noqa: PLC0415

        data: dict[str, Any] = {
            "date": date.fromisoformat(p["date"]),
            "odometer_km": int(p["odometer_km"]),
        }
        if kind == "fuel":
            data |= {
                "litres": Decimal(p["litres"]),
                "total_cost": Decimal(p["total_cost"]),
                "price_per_litre": Decimal(p["price_per_litre"])
                if p.get("price_per_litre")
                else None,
                "full_tank": bool(p.get("full_tank", True)),
                "station": p.get("station", ""),
            }
        record = services.save_record(ctx, kind, UUID(p["car_id"]), data)
        return [{"type": f"cars.{kind}", "id": str(record.id), "car_id": p["car_id"]}]

    return execute


def _car_undo(kind: str) -> Callable:
    def undo(ctx: AccessContext, result: list[dict[str, str]]) -> None:
        from apps.cars import services  # noqa: PLC0415

        for r in result:
            services.delete_record(ctx, kind, UUID(r["car_id"]), UUID(r["id"]))

    return undo


# ---- household ----


def _shop_execute(ctx: AccessContext, p: dict[str, Any]) -> list[dict[str, str]]:
    from apps.household import services  # noqa: PLC0415

    return [
        {
            "type": "household.shopping",
            "id": str(services.add_entry(ctx, name=i["name"], quantity=i["quantity"]).id),
        }
        for i in p["items"]
    ]


def _shop_undo(ctx: AccessContext, result: list[dict[str, str]]) -> None:
    from apps.household import services  # noqa: PLC0415
    from apps.household.models import ShoppingEntry  # noqa: PLC0415

    for r in result:
        if ShoppingEntry.objects.filter(pk=r["id"]).exists():
            services.delete_entry(ctx, UUID(r["id"]))


# ---- notes ----


def _note_execute(ctx: AccessContext, p: dict[str, Any]) -> list[dict[str, str]]:
    from apps.notes import services  # noqa: PLC0415

    note = services.save_note(
        ctx,
        {
            "title": p["title"],
            "body": p.get("body", ""),
            "checklist": [{"text": t, "done": False} for t in p.get("checklist", [])],
            "remind_at": datetime.fromisoformat(p["remind_at"]) if p.get("remind_at") else None,
            "repeat": p.get("repeat", ""),
        },
    )
    return [{"type": "notes.note", "id": str(note.id)}]


def _note_undo(ctx: AccessContext, result: list[dict[str, str]]) -> None:
    from apps.notes import services  # noqa: PLC0415

    for r in result:
        services.delete_note(ctx, UUID(r["id"]))


# ---- health (always confirmed; the health services do the rest) ----


def _uuid(value: str | None) -> UUID | None:
    return UUID(value) if value else None


def _local(value: str) -> datetime:
    return datetime.fromisoformat(value)  # naive local; save_record makes it aware


def _health_save(ctx: AccessContext, kind: str, data: dict[str, Any]) -> dict[str, str]:
    from apps.health import services  # noqa: PLC0415

    record = services.save_record(ctx, kind, data)
    return {"type": f"health.{kind}", "id": str(record.id)}


def _symptom_data(p: dict[str, Any], row: dict[str, Any], condition_id: UUID) -> dict[str, Any]:
    return {
        "person_id": UUID(p["person_id"]),
        "condition_id": condition_id,
        "observed_at": _local(row["when"]),
        "symptom": row["symptom"],
        "value": row.get("reading", ""),
        "notes": row.get("notes", ""),
    }


def _hs_symptom(ctx: AccessContext, p: dict[str, Any]) -> list[dict[str, str]]:
    return [_health_save(ctx, "symptoms", _symptom_data(p, p, UUID(p["condition_id"])))]


def _hs_event(ctx: AccessContext, p: dict[str, Any]) -> list[dict[str, str]]:
    event = _health_save(
        ctx,
        "conditions",
        {
            "person_id": UUID(p["person_id"]),
            "kind": p["kind"],
            "title": p["title"],
            "start_date": date.fromisoformat(p["start_date"]),
            "notes": p.get("notes", ""),
        },
    )
    # Symptoms go with the event (deleting the event removes them too).
    for row in p.get("symptoms", []):
        _health_save(ctx, "symptoms", _symptom_data(p, row, UUID(event["id"])))
    return [event]


def _hs_measurement(ctx: AccessContext, p: dict[str, Any]) -> list[dict[str, str]]:
    return [
        _health_save(
            ctx,
            "measurements",
            {
                "person_id": UUID(p["person_id"]),
                "date": date.fromisoformat(p["date"]),
                "weight_kg": Decimal(p["weight_kg"]) if p.get("weight_kg") else None,
                "height_cm": Decimal(p["height_cm"]) if p.get("height_cm") else None,
            },
        )
    ]


def _hs_visit(ctx: AccessContext, p: dict[str, Any]) -> list[dict[str, str]]:
    return [
        _health_save(
            ctx,
            "appointments",
            {
                "person_id": UUID(p["person_id"]),
                "starts_at": _local(p["starts_at"]),
                **{
                    k: p.get(k, "")
                    for k in ("doctor", "specialty", "place", "room", "purpose", "notes")
                },
                "status": "planned",
                "cost": Decimal(p["cost"]) if p.get("cost") else None,
                "currency": p.get("currency", "PLN"),
                "condition_id": _uuid(p.get("condition_id")),
            },
        )
    ]


def _hs_treatment(ctx: AccessContext, p: dict[str, Any]) -> list[dict[str, str]]:
    return [
        _health_save(
            ctx,
            "medications",
            {
                "person_id": UUID(p["person_id"]),
                "name": p["medicine"],
                "dosage": p.get("dosage", ""),
                "dose_times": p.get("dose_times", []),
                "reminders_enabled": bool(p.get("reminders")),
                "start_date": date.fromisoformat(p["start_date"]),
                "end_date": date.fromisoformat(p["end_date"]) if p.get("end_date") else None,
                "condition_id": _uuid(p.get("condition_id")),
                "notes": p.get("notes", ""),
            },
        )
    ]


def _hs_result(ctx: AccessContext, p: dict[str, Any]) -> list[dict[str, str]]:
    from django.core.files.base import ContentFile  # noqa: PLC0415

    from apps.core import attachments  # noqa: PLC0415
    from apps.core.models import Attachment  # noqa: PLC0415
    from apps.health.models import TestResult  # noqa: PLC0415

    saved = _health_save(
        ctx,
        "results",
        {
            "person_id": UUID(p["person_id"]),
            "date": date.fromisoformat(p["date"]),
            "title": p["title"],
            "lab": p.get("lab", ""),
            "notes": p.get("notes", ""),
        },
    )
    result = TestResult.objects.get(pk=saved["id"])
    # A copy of each chat file, now governed by the result's health rules.
    for f in p.get("files", []):
        source = Attachment.objects.get(pk=f["id"])
        with source.file.open("rb") as fh:
            attachments.upload(ctx, result, ContentFile(fh.read(), name=source.original_name))
    return [saved]


def _health_undo(ctx: AccessContext, result: list[dict[str, str]]) -> None:
    from apps.health import services  # noqa: PLC0415

    for r in result:
        services.delete_record(ctx, r["type"].split(".", 1)[1], UUID(r["id"]))


KINDS: dict[str, Kind] = {
    "finance.transaction": Kind(_tx_execute, _tx_undo),
    "cars.fuel": Kind(_car_execute("fuel"), _car_undo("fuel")),
    "cars.odometer": Kind(_car_execute("odometer"), _car_undo("odometer")),
    "household.shopping": Kind(_shop_execute, _shop_undo),
    "notes.note": Kind(_note_execute, _note_undo),
    "health.symptom": Kind(_hs_symptom, _health_undo),
    "health.event": Kind(_hs_event, _health_undo),
    "health.measurement": Kind(_hs_measurement, _health_undo),
    "health.visit": Kind(_hs_visit, _health_undo),
    "health.treatment": Kind(_hs_treatment, _health_undo),
    "health.result": Kind(_hs_result, _health_undo),
}


# ---- used by tools ----


def propose(run: ToolRun, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    action = PendingAction.objects.create(conversation=run.conversation, kind=kind, payload=payload)
    run.actions.append(action)
    return {
        "status": "proposed",
        "shown_to_user": payload,
        "next": (
            "Shown to the user to confirm; not saved yet. Reply with an empty message, or "
            "one short sentence only for what it doesn't show (an assumption, a question)."
        ),
    }


def do_now(run: ToolRun, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    action = PendingAction.objects.create(
        conversation=run.conversation, kind=kind, payload=payload, auto=True
    )
    run.actions.append(action)
    _run(run.ctx, action)
    if action.status == PendingAction.Status.FAILED:
        return {"status": "failed", "error": action.error}
    return {
        "status": "done",
        "saved": payload,
        "next": (
            "Saved and shown to the user (with undo). Reply with an empty message, or one "
            "short sentence only for what it doesn't show."
        ),
    }


def _run(ctx: AccessContext, action: PendingAction) -> None:
    try:
        with atomic():
            action.result = KINDS[action.kind].execute(ctx, action.payload)
            action.status = PendingAction.Status.DONE
    except (PermissionDenied, ObjectDoesNotExist, Http404, ValueError, KeyError) as exc:
        action.status = PendingAction.Status.FAILED
        action.error = str(exc) or exc.__class__.__name__
    action.save(update_fields=["result", "status", "error", "updated_at"])


# ---- user decisions ----


def _own(ctx: AccessContext, action_id: UUID) -> PendingAction:
    action = PendingAction.objects.select_related("conversation").filter(pk=action_id).first()
    if action is None or action.conversation.owner_id != ctx.user_id:
        raise PermissionDenied("not your conversation")
    return action


def confirm(ctx: AccessContext, action_id: UUID) -> PendingAction:
    action = _own(ctx, action_id)
    if action.status != PendingAction.Status.PROPOSED:
        raise ValueError(f"already {action.status}")
    _run(ctx, action)
    return action


def cancel(ctx: AccessContext, action_id: UUID) -> PendingAction:
    action = _own(ctx, action_id)
    if action.status != PendingAction.Status.PROPOSED:
        raise ValueError(f"already {action.status}")
    action.status = PendingAction.Status.CANCELLED
    action.save(update_fields=["status", "updated_at"])
    return action


@atomic
def undo(ctx: AccessContext, action_id: UUID) -> PendingAction:
    action = _own(ctx, action_id)
    if action.status != PendingAction.Status.DONE:
        raise ValueError("only something done can be undone")
    KINDS[action.kind].undo(ctx, action.result)
    action.status = PendingAction.Status.UNDONE
    action.save(update_fields=["status", "updated_at"])
    return action


__all__ = ["KINDS", "Conversation", "cancel", "confirm", "do_now", "propose", "undo"]
