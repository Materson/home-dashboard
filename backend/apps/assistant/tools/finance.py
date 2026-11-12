# ruff: noqa: E501 — tool descriptions are prose for the model
"""Money: monthly summary, transaction search, proposing a transaction."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from django.db.models import Q
from django.utils import timezone

from apps.finance import selectors
from apps.finance.models import Category

from . import (
    DATE,
    INT,
    NUM,
    PERSON,
    STR,
    ToolError,
    ToolRun,
    arg_date,
    arg_decimal,
    money,
    obj,
    tool,
)

SEARCH_LIMIT = 50


def _month_bounds(year: int, month: int) -> tuple[date, date]:
    start = date(year, month, 1)
    end = (date(year + (month == 12), month % 12 + 1, 1)) - timedelta(days=1)  # noqa: PLR2004
    return start, end


@tool(
    "finance_summary",
    "Income and expenses of one month, total and per category.",
    obj(
        {"year": INT, "month": {"type": "integer", "minimum": 1, "maximum": 12}}, ("year", "month")
    ),
    module="finance",
    policy="finance",
)
def finance_summary(run: ToolRun, args: dict[str, Any]) -> Any:
    try:
        start, end = _month_bounds(int(args["year"]), int(args["month"]))
    except (KeyError, ValueError) as exc:
        raise ToolError("year and month are required") from exc
    rows = selectors.list_transactions(
        run.ctx, selectors.TransactionFilter(date_from=start, date_to=end)
    )
    totals: dict[str, Decimal] = defaultdict(Decimal)
    by_cat: dict[tuple, Decimal] = defaultdict(Decimal)
    for t in rows:
        totals[f"{t.category.kind}:{t.currency}"] += t.amount
        by_cat[(_path(t.category), t.category.kind, t.currency)] += t.amount
    return {
        "month": f"{start:%Y-%m}",
        "totals": {k: money(v) for k, v in totals.items()},
        "by_category": [
            {"category": name, "kind": kind, "total": money(total), "currency": cur}
            for (name, kind, cur), total in sorted(by_cat.items(), key=lambda x: -x[1])
        ],
    }


@tool(
    "finance_search",
    "Search transactions. All filters optional; dates inclusive. Returns up to 50 rows and their sum.",
    obj(
        {
            "query": {"type": "string", "description": "Text in the name or notes."},
            "date_from": DATE,
            "date_to": DATE,
            "kind": {"type": "string", "enum": ["income", "expense"]},
            "category": {
                "type": "string",
                "description": (
                    "Category name, key or main / sub path, e.g. Paliwo, car.fuel, "
                    "Samochód / Paliwo. A main category includes its sub-categories."
                ),
            },
            "min_amount": NUM,
            "max_amount": NUM,
        }
    ),
    module="finance",
    policy="finance",
)
def finance_search(run: ToolRun, args: dict[str, Any]) -> Any:
    keys = None
    if args.get("category"):
        cat = _category(args["category"])
        keys = [cat.key]
    f = selectors.TransactionFilter(
        q=args.get("query") or None,
        date_from=arg_date(args, "date_from"),
        date_to=arg_date(args, "date_to"),
        amount_min=arg_decimal(args, "min_amount"),
        amount_max=arg_decimal(args, "max_amount"),
        category_keys=keys,
        kind=args.get("kind") or None,
    )
    qs = selectors.list_transactions(run.ctx, f).order_by("-date")
    total = sum((t.amount for t in qs), Decimal(0))
    count = qs.count()
    return {
        "count": count,
        "sum": money(total),
        "rows": [
            {
                "date": t.date.isoformat(),
                "name": t.name,
                "amount": money(t.amount),
                "currency": t.currency,
                "category": _path(t.category),
                "kind": t.category.kind,
                "person": t.person.display_name if t.person else None,
            }
            for t in qs[:SEARCH_LIMIT]
        ],
        "truncated": count > SEARCH_LIMIT,
    }


def _path(cat: Category) -> str:
    """A sub-category as "Samochód / Paliwo", a main one by its name."""
    return f"{cat.parent.name} / {cat.name}" if cat.parent_id else cat.name


def _category(name: str, kind: str | None = None) -> Category:
    name = name.strip()
    qs = Category.objects.select_related("parent")
    if kind:
        qs = qs.filter(kind=kind)
    found = list(qs.filter(Q(name__iexact=name) | Q(key__iexact=name)))
    main, _, child = (part.strip() for part in name.replace("›", "/").partition("/"))  # noqa: RUF001
    if not found and child:  # "Samochód / Paliwo" (a name may hold "/" itself)
        found = list(qs.filter(name__iexact=child, parent__name__iexact=main))
    if len(found) == 1:
        return found[0]
    problem = "ambiguous" if found else "unknown"
    options = ", ".join(sorted(_path(c) for c in (found or qs)))
    raise ToolError(f"{problem} category {name!r}; choose one of: {options}")


@tool(
    "propose_transaction",
    "Propose adding an income or expense. The user sees a card and confirms it — nothing is saved until then.",
    obj(
        {
            "kind": {"type": "string", "enum": ["income", "expense"]},
            "amount": {"type": "number", "description": "Positive amount."},
            "currency": {"type": "string", "description": "Default PLN."},
            "date": DATE,
            "name": STR,
            "category": {
                "type": "string",
                "description": "Category name or main / sub path, e.g. Samochód / Paliwo.",
            },
            "person": PERSON,
            "notes": STR,
        },
        ("kind", "amount", "name", "category"),
    ),
    module="finance",
    policy="finance",
    level="edit",
)
def propose_transaction(run: ToolRun, args: dict[str, Any]) -> Any:
    from apps.assistant import actions  # noqa: PLC0415
    from apps.people.selectors import list_people  # noqa: PLC0415

    from .people import find_person  # noqa: PLC0415

    kind = args.get("kind")
    if kind not in ("income", "expense"):
        raise ToolError("kind must be income or expense")
    cat = _category(str(args.get("category", "")), kind)
    person = find_person(list_people(run.ctx), args["person"]) if args.get("person") else None
    payload = {
        "date": (arg_date(args, "date") or timezone.localdate()).isoformat(),
        "amount": money(arg_decimal(args, "amount", required=True, positive=True)),
        "currency": (args.get("currency") or "PLN").upper()[:3],
        "name": str(args.get("name", "")).strip()[:200] or cat.name,
        "category_id": str(cat.id),
        "category": _path(cat),
        "kind": kind,
        "person_id": str(person.id) if person else None,
        "person": person.display_name if person else None,
        "notes": str(args.get("notes") or "")[:1000],
    }
    return actions.propose(run, "finance.transaction", payload)
