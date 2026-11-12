"""The assistant's tools — thin wrappers over each app's selectors/services,
run with the *asking user's* AccessContext (so a child never reads finance).

A tool declares:
- ``module`` + ``level``: the permission the user needs for it to be offered
- ``policy``: the privacy policy key that decides whether its results may go
  to a cloud model (Settings → AI → per-module policy)
Writes don't happen here: ``propose_*`` tools create a ``PendingAction``
the user confirms; ``add_*`` tools for your own notes / shopping lines run
at once and can be undone (see ``apps.assistant.actions``).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from apps.access.context import AccessContext
    from apps.assistant.models import Conversation, PendingAction


class ToolError(ValueError):
    """Bad arguments / nothing found — the message goes back to the model."""


@dataclass
class ToolRun:
    ctx: AccessContext
    conversation: Conversation
    actions: list[PendingAction] = field(default_factory=list)


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    module: str
    policy: str
    handler: Callable[[ToolRun, dict[str, Any]], Any]
    level: str = "view"


REGISTRY: dict[str, Tool] = {}


def tool(
    name: str,
    description: str,
    parameters: dict[str, Any],
    *,
    module: str,
    policy: str,
    level: str = "view",
) -> Callable:
    def register(fn: Callable[[ToolRun, dict[str, Any]], Any]) -> Callable:
        REGISTRY[name] = Tool(name, description, parameters, module, policy, fn, level)
        return fn

    return register


def obj(properties: dict[str, Any], required: tuple[str, ...] = ()) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": list(required),
        "additionalProperties": False,
    }


STR = {"type": "string"}
DATE = {"type": "string", "description": "YYYY-MM-DD"}
NUM = {"type": "number"}
INT = {"type": "integer"}
BOOL = {"type": "boolean"}
PERSON = {"type": "string", "description": "Person as given by family_members (alias like [P1])."}


# ---- argument helpers (tools validate their own input) ----


def arg_date(args: dict, key: str, *, required: bool = False) -> date | None:
    value = args.get(key)
    if value in (None, ""):
        if required:
            raise ToolError(f"{key} is required (YYYY-MM-DD)")
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError as exc:
        raise ToolError(f"{key} must be YYYY-MM-DD, got {value!r}") from exc


def arg_datetime(args: dict, key: str) -> datetime | None:
    value = args.get(key)
    if value in (None, ""):
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError as exc:
        raise ToolError(f"{key} must be YYYY-MM-DDTHH:MM, got {value!r}") from exc


def arg_decimal(
    args: dict, key: str, *, required: bool = False, positive: bool = False
) -> Decimal | None:
    value = args.get(key)
    if value in (None, ""):
        if required:
            raise ToolError(f"{key} is required")
        return None
    try:
        number = Decimal(str(value).replace(",", ".").replace(" ", ""))
    except InvalidOperation as exc:
        raise ToolError(f"{key} must be a number, got {value!r}") from exc
    if positive and number <= 0:
        raise ToolError(f"{key} must be greater than 0")
    return number


def money(value: Decimal | None) -> str | None:
    return None if value is None else f"{value:.2f}"


# Importing registers the tools.
from . import cars, finance, health, household, notes, people  # noqa: E402, F401
