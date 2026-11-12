# ruff: noqa: E501 — tool descriptions are prose for the model
"""Who is in the family — names (aliased for cloud models) and ages only;
never birth dates or anything identifying."""

from __future__ import annotations

from typing import Any

from django.utils import timezone

from apps.health.selectors import age_in_months
from apps.people.models import Person
from apps.people.selectors import list_people

from . import ToolError, ToolRun, obj, tool


def age_text(months: int | None) -> str | None:
    if months is None:
        return None
    return f"{months} mies." if months < 24 else f"{months // 12} lat"  # noqa: PLR2004


def find_person(queryset, name: str) -> Person:
    """Resolve the name the model passed (already re-hydrated from its alias)."""
    name = (name or "").strip().lower()
    if not name:
        raise ToolError("person is required")
    people = list(queryset)
    for p in people:
        if p.display_name.lower() == name:
            return p
    matches = [p for p in people if p.display_name.lower().split()[0] == name.split()[0]]
    if len(matches) == 1:
        return matches[0]
    raise ToolError("unknown person — call family_members for the list")


@tool(
    "family_members",
    "List the family members you may see: name (an alias) and age. Use these names when a tool asks for a person.",
    obj({}),
    module="people",
    policy="people",
)
def family_members(run: ToolRun, args: dict[str, Any]) -> Any:
    today = timezone.localdate()
    return [
        {"name": p.display_name, "age": age_text(age_in_months(p.birth_date, today))}
        for p in list_people(run.ctx)
    ]
