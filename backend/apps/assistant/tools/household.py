# ruff: noqa: E501 — tool descriptions are prose for the model
"""Household: stock and expiry, the shopping list, adding to the list."""

from __future__ import annotations

from typing import Any

from apps.household import selectors

from . import STR, ToolError, ToolRun, obj, tool


@tool(
    "household_stock",
    "Food and cleaning supplies at home: stock left, below-minimum flag, nearest expiry; plus what expires within 7 days.",
    obj({"query": {"type": "string", "description": "Optional name filter."}}),
    module="household",
    policy="household",
)
def household_stock(run: ToolRun, args: dict[str, Any]) -> Any:
    items = selectors.list_items(run.ctx, q=args.get("query") or None)
    return {
        "items": [
            {
                "name": i.name,
                "category": i.category,
                "stock": f"{i.stock.normalize():f} {i.unit}".strip(),
                "below_min": i.min_quantity is not None and i.stock < i.min_quantity,
                "next_expiry": i.next_expiry,
            }
            for i in items
        ],
        "use_first": [
            {"name": b.item.name, "expires": b.expiry_date, "status": selectors.batch_status(b)}
            for b in selectors.expiring(run.ctx, days=7)
        ],
    }


@tool(
    "shopping_list",
    "What is on the shared shopping list now (not yet bought).",
    obj({}),
    module="household",
    policy="household",
)
def shopping_list(run: ToolRun, args: dict[str, Any]) -> Any:
    return [
        {"name": e.name, "quantity": e.quantity, "added_because_low": e.auto}
        for e in selectors.shopping_list(run.ctx)
        if e.done_at is None
    ]


@tool(
    "add_to_shopping_list",
    "Add lines to the shared shopping list. Done at once (the user can undo).",
    obj(
        {
            "items": {
                "type": "array",
                "items": obj({"name": STR, "quantity": STR}, ("name",)),
                "minItems": 1,
            }
        },
        ("items",),
    ),
    module="household",
    policy="household",
    level="edit",
)
def add_to_shopping_list(run: ToolRun, args: dict[str, Any]) -> Any:
    from apps.assistant import actions  # noqa: PLC0415

    items = [
        {
            "name": str(i.get("name", "")).strip()[:120],
            "quantity": str(i.get("quantity") or "")[:40],
        }
        for i in args.get("items") or []
        if str(i.get("name", "")).strip()
    ]
    if not items:
        raise ToolError("items is empty")
    return actions.do_now(run, "household.shopping", {"items": items})
