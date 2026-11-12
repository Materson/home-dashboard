""" "Where am I" for the chat button: the page path → a short Polish
description added to the user's message (not to the system prompt, which
stays fixed so it can be cached). Names in it are aliased like the rest."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING
from uuid import UUID

from apps.people.models import Person

if TYPE_CHECKING:
    from apps.access.context import AccessContext

_STATIC = {
    "/": "Przegląd",
    "/finance": "Finanse — transakcje",
    "/finance/loans": "Finanse — kredyty",
    "/finance/debts": "Finanse — długi",
    "/cars": "Samochody",
    "/health": "Zdrowie — wybór osoby",
    "/health/cabinet": "Apteczka (leki w domu)",
    "/household": "Dom — lista zakupów i zapasy",
    "/notes": "Notatki",
    "/people": "Osoby",
    "/assistant": "Asystent",
}
_PERSON_PAGES = (
    (re.compile(r"^/health/([0-9a-f-]{36})$"), "Zdrowie osoby {name}", "health"),
    (re.compile(r"^/people/([0-9a-f-]{36})$"), "Profil osoby {name}", "people"),
)


def describe(path: str, ctx: AccessContext) -> str:
    path = (path or "").split("?")[0].rstrip("/") or "/"
    if path in _STATIC:
        return _STATIC[path]
    for pattern, text, module in _PERSON_PAGES:
        if m := pattern.match(path):
            person = Person.objects.filter(pk=UUID(m.group(1))).first()
            # Only name someone the user may see in that module.
            allowed = ctx.scope_by_person(
                module=module, qs=Person.objects.filter(pk=UUID(m.group(1))), person_field="id"
            ).exists()
            if person and allowed:
                return text.format(name=person.display_name)
    return ""
