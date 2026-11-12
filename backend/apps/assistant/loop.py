# ruff: noqa: E501 — the system prompt below is prose
"""One user turn: pick the model, offer only the allowed tools, replace
private data for cloud models, run the tool loop, log what was sent, and
store the answer.

The loop is ours (not an SDK's tool runner) because it is the same for
every provider and every tool call must pass: permission (tool offered at
all) → arguments re-hydrated → the app's selector/service with the user's
AccessContext → result aliased → back to the model.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING, Any

from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.utils import timezone

from apps.people.models import Person

from . import page_context, policy
from .llm import ChatMessage, Image, LLMError, ToolResult, ToolSpec, build_adapter
from .models import Conversation, LLMCall, Message, ProviderProfile
from .privacy import Passthrough, Pseudonymizer
from .tools import REGISTRY, Tool, ToolError, ToolRun

if TYPE_CHECKING:
    from apps.access.context import AccessContext

MAX_STEPS = 8  # model calls per turn
HISTORY_TURNS = 20  # earlier messages sent along
WEEKDAYS = ("poniedziałek", "wtorek", "środa", "czwartek", "piątek", "sobota", "niedziela")

# Fixed for every conversation (cacheable): today's date and the page go in
# the user message instead.
SYSTEM = """You are the assistant of a private family home dashboard (finance, cars, health, household stock and shopping list, notes and reminders). Answer in Polish unless the user writes in another language. Be brief and concrete.

Rules:
- Facts about the family come only from your tools. Never invent numbers, dates or names; if a tool has no data, say so.
- People may appear as aliases like [P1]. Use them exactly as written (they are turned back into names for the user); never guess real names, addresses or identifiers.
- Each user message starts with today's date and the page the user is on, in square brackets; "this car", "her", "here" usually refer to that page.
- Changes: use the propose_* tools for money, cars and anything not the user's own; the user confirms a card — say it is waiting for confirmation, never that it is saved. add_note and add_to_shopping_list save at once (the user can undo).
- If the user attaches a receipt, odometer photo or invoice, read it and propose the matching entry; ask for missing required values instead of guessing (e.g. the odometer for a fuel entry).
- Health: give information from the family's own records and the medicine cabinet (doses from the dosing rule); remind briefly to follow the leaflet or a doctor when giving doses. Not a diagnosis.
- If a topic isn't covered by your tools, it may be switched off for this model in the privacy settings (Ustawienia → AI) or need a private conversation with the local model — say that.
- Amounts are in PLN unless stated. Dates as DD.MM.YYYY in answers."""


def available_tools(
    ctx: AccessContext, profile: ProviderProfile, policies: dict[str, str]
) -> list[Tool]:
    return [
        t
        for t in REGISTRY.values()
        if ctx.has(t.module, t.level)
        and policy.allows(policies.get(t.policy, "off"), profile.location)
    ]


def _header(page: str, ctx: AccessContext) -> str:
    now = timezone.localtime()
    where = page_context.describe(page, ctx)
    text = f"[Dziś: {WEEKDAYS[now.weekday()]} {now:%d.%m.%Y %H:%M}"
    return text + (f". Strona: {where}]" if where else "]")


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=_default)


def _default(value: Any) -> str:
    if isinstance(value, datetime):
        return (
            timezone.localtime(value).strftime("%Y-%m-%d %H:%M")
            if timezone.is_aware(value)
            else value.isoformat()
        )
    return str(value)


def run_turn(  # noqa: PLR0915 — one readable pass through the turn
    ctx: AccessContext,
    conversation: Conversation,
    user_message: Message,
    images: list[Image],
) -> Message:
    """Answer ``user_message`` (already saved). Returns the assistant message
    (``error=True`` with a readable text when something failed)."""
    settings = policy.ai_settings()
    policies = policy.policies(settings)
    try:
        profile = policy.profile_for(conversation, settings)
    except policy.NotConfigured as exc:
        return _reply(conversation, str(exc), error=True)

    if images:
        problem = _images_problem(images, profile, policies)
        if problem:
            return _reply(conversation, problem, error=True)

    tools = {t.name: t for t in available_tools(ctx, profile, policies)}
    cloud = profile.location == ProviderProfile.Location.CLOUD
    names = list(Person.objects.values_list("display_name", flat=True))
    pz = Pseudonymizer(conversation.aliases, names) if cloud else Passthrough()

    earlier = list(
        conversation.messages.filter(error=False)
        .exclude(pk=user_message.pk)
        .order_by("-created_at")[:HISTORY_TURNS]
    )[::-1]
    history = [ChatMessage(m.role, pz.hide(m.text)) for m in earlier if m.text]
    current = ChatMessage(
        "user", pz.hide(f"{_header(user_message.page, ctx)}\n\n{user_message.text}"), images
    )
    specs = [ToolSpec(t.name, t.description, t.parameters) for t in tools.values()]

    run = ToolRun(ctx=ctx, conversation=conversation)
    adapter = build_adapter(profile)
    session = adapter.start(SYSTEM, specs, [*history, current])
    sent: list[dict[str, Any]] = [{"role": m.role, "text": m.text} for m in [*history, current]]
    modules: set[str] = set()
    calls: list[LLMCall] = []
    answer = ""
    error = False

    for _ in range(MAX_STEPS):
        call = LLMCall(
            conversation=conversation,
            user_id=ctx.user_id,
            profile_name=profile.name,
            provider=profile.kind,
            model=profile.model,
            location=profile.location,
            modules=sorted(modules),
            sent=sent,
            images=len(images) if not calls else 0,
        )
        try:
            turn = session.step()
        except LLMError as exc:
            call.ok, call.error = False, exc.user_text
            call.save()
            calls.append(call)
            answer, error = exc.user_text, True
            break
        call.input_tokens, call.output_tokens = turn.input_tokens, turn.output_tokens
        call.save()
        calls.append(call)

        if not turn.tool_calls:
            answer = pz.reveal(turn.text)
            break
        results = []
        for tc in turn.tool_calls:
            result = _call_tool(tools.get(tc.name), run, pz.reveal_obj(tc.args))
            if tools.get(tc.name):
                modules.add(tools[tc.name].policy)
            content = _json(pz.hide_obj(result["value"]))
            results.append(ToolResult(tc, content, result["error"]))
        session.add_tool_results(results)
        sent = [{"role": "tool", "text": f"{r.call.name}: {r.content}"} for r in results]
    else:
        answer = "Nie udało mi się dokończyć odpowiedzi (za dużo kroków). Spróbuj zapytać prościej."
        error = True

    conversation.aliases = pz.aliases if cloud else conversation.aliases
    if not conversation.title:
        conversation.title = user_message.text[:60] or "Zdjęcie"
    conversation.save(update_fields=["aliases", "title", "updated_at"])

    reply = _reply(conversation, answer or "(brak odpowiedzi)", error=error)
    for c in calls:
        c.message = reply
        c.save(update_fields=["message"])
    for a in run.actions:
        a.message = reply
        a.save(update_fields=["message"])
    return reply


def _call_tool(tool: Tool | None, run: ToolRun, args: dict[str, Any]) -> dict[str, Any]:
    if tool is None:
        return {"value": {"error": "this tool is not available"}, "error": True}
    try:
        return {"value": tool.handler(run, args), "error": False}
    except ToolError as exc:
        return {"value": {"error": str(exc)}, "error": True}
    except (PermissionDenied, Http404):
        return {"value": {"error": "not found or not allowed for this user"}, "error": True}


def _images_problem(images: list[Image], profile: ProviderProfile, policies: dict[str, str]) -> str:
    if not profile.vision:
        return f"Model „{profile.name}” nie czyta zdjęć ani dokumentów."
    if not policy.allows(policies["documents"], profile.location):
        return (
            "Wysyłanie zdjęć i dokumentów do tego modelu jest wyłączone w ustawieniach prywatności "
            "(Ustawienia → AI → Zdjęcia i dokumenty)."
        )
    adapter = build_adapter(profile)
    bad = {i.mime for i in images} - set(adapter.supported_files)
    if bad:
        return f"Ten model nie obsługuje plików: {', '.join(sorted(bad))}."
    return ""


def _reply(conversation: Conversation, text: str, *, error: bool) -> Message:
    return Message.objects.create(
        conversation=conversation, role=Message.Role.ASSISTANT, text=text, error=error
    )
