# ruff: noqa: E501 — tool descriptions are prose for the model
"""Notes and reminders (local-only by default): search, my upcoming
reminders, add a note / reminder for myself."""

from __future__ import annotations

from typing import Any

from django.utils import timezone

from apps.notes import selectors
from apps.reminders.models import Reminder

from . import STR, ToolError, ToolRun, arg_datetime, obj, tool

LIMIT = 30


@tool(
    "notes_search",
    "Search my notes and the ones shared with me (title, text, checklist).",
    obj({"query": {"type": "string", "description": "Optional text to look for."}}),
    module="notes",
    policy="notes",
)
def notes_search(run: ToolRun, args: dict[str, Any]) -> Any:
    notes = selectors.list_notes(run.ctx, q=args.get("query") or None)[:LIMIT]
    return [
        {
            "title": n.title,
            "text": n.body[:400],
            "checklist": [f"[{'x' if i['done'] else ' '}] {i['text']}" for i in n.checklist][:20],
            "reminder": timezone.localtime(n.remind_at).strftime("%Y-%m-%d %H:%M")
            if n.remind_at
            else None,
            "repeat": n.repeat or None,
            "mine": n.owner_id == run.ctx.user_id,
        }
        for n in notes
    ]


@tool(
    "my_reminders",
    "My upcoming reminders (notes, visits, doses, expiries…), soonest first.",
    obj({}),
    module="notes",
    policy="notes",
)
def my_reminders(run: ToolRun, args: dict[str, Any]) -> Any:
    rows = Reminder.objects.filter(
        recipients__id=run.ctx.user_id,
        status__in=[Reminder.Status.SCHEDULED, Reminder.Status.SNOOZED],
        due_at__isnull=False,
    ).order_by("due_at")[:LIMIT]
    return [
        {"when": timezone.localtime(r.due_at).strftime("%Y-%m-%d %H:%M"), "title": r.title}
        for r in rows
    ]


@tool(
    "add_note",
    "Add a note for me, optionally with a checklist and a reminder (once or repeating). Done at once (the user can undo).",
    obj(
        {
            "title": STR,
            "body": STR,
            "checklist": {"type": "array", "items": {"type": "string"}},
            "remind_at": {"type": "string", "description": "Local time YYYY-MM-DDTHH:MM."},
            "repeat": {"type": "string", "enum": ["", "daily", "weekly", "monthly"]},
        },
        ("title",),
    ),
    module="notes",
    policy="notes",
    level="edit",
)
def add_note(run: ToolRun, args: dict[str, Any]) -> Any:
    from apps.assistant import actions  # noqa: PLC0415

    title = str(args.get("title") or "").strip()[:200]
    if not title:
        raise ToolError("title is required")
    when = arg_datetime(args, "remind_at")
    if when and timezone.is_naive(when):
        when = timezone.make_aware(when)
    payload = {
        "title": title,
        "body": str(args.get("body") or "")[:5000],
        "checklist": [str(x)[:300] for x in args.get("checklist") or [] if str(x).strip()],
        "remind_at": when.isoformat() if when else None,
        "repeat": (args.get("repeat") or "") if when else "",
    }
    return actions.do_now(run, "notes.note", payload)
