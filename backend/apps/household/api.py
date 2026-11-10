"""Household REST API — thin wrappers over selectors/services."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from django.http import HttpRequest
from ninja import Router, Schema

from apps.access.context import get_ctx

from . import selectors, services

router = Router()


# -------------------- Items --------------------


class ItemIn(Schema):
    name: str
    category: Literal["food", "cleaning"] = "food"
    unit: str = "szt."
    min_quantity: Decimal | None = None
    notes: str = ""


class ItemOut(ItemIn):
    id: UUID
    stock: Decimal
    next_expiry: date | None
    below_min: bool

    @staticmethod
    def resolve_stock(obj) -> Decimal:
        return Decimal(obj.stock).quantize(Decimal("0.01"))  # SQLite returns a bare 0

    @staticmethod
    def resolve_below_min(obj) -> bool:
        return obj.min_quantity is not None and obj.stock < obj.min_quantity


class BatchIn(Schema):
    quantity: Decimal
    expiry_date: date | None = None
    added_on: date | None = None  # default: today
    finished_on: date | None = None
    notes: str = ""


class BatchOut(BatchIn):
    id: UUID
    item_id: UUID
    added_on: date
    status: str

    @staticmethod
    def resolve_status(obj) -> str:
        return selectors.batch_status(obj)


class ExpiringOut(BatchOut):
    item_name: str
    unit: str

    @staticmethod
    def resolve_item_name(obj) -> str:
        return obj.item.name

    @staticmethod
    def resolve_unit(obj) -> str:
        return obj.item.unit


class ConsumeIn(Schema):
    amount: Decimal = Decimal(1)


@router.get("/items", response=list[ItemOut])
def list_items(
    request: HttpRequest,
    q: str | None = None,
    category: str | None = None,
) -> Any:
    return selectors.list_items(get_ctx(request), q=q, category=category)


@router.post("/items", response={200: ItemOut, 422: dict})
def create_item(request: HttpRequest, payload: ItemIn):
    try:
        return services.save_item(get_ctx(request), payload.dict())
    except ValueError as exc:
        return 422, {"detail": str(exc)}


@router.put("/items/{item_id}", response={200: ItemOut, 422: dict})
def update_item(request: HttpRequest, item_id: UUID, payload: ItemIn):
    try:
        return services.save_item(get_ctx(request), payload.dict(), item_id)
    except ValueError as exc:
        return 422, {"detail": str(exc)}


@router.delete("/items/{item_id}")
def archive_item(request: HttpRequest, item_id: UUID) -> dict[str, bool]:
    services.archive_item(get_ctx(request), item_id)
    return {"archived": True}


@router.post("/items/{item_id}/consume", response={200: ItemOut, 422: dict})
def consume(request: HttpRequest, item_id: UUID, payload: ConsumeIn):
    """Use some — taken from the batch that expires first."""
    try:
        return services.consume(get_ctx(request), item_id, payload.amount)
    except ValueError as exc:
        return 422, {"detail": str(exc)}


@router.get("/items/{item_id}/batches", response=list[BatchOut])
def list_batches(request: HttpRequest, item_id: UUID, include_finished: bool = False) -> Any:
    return selectors.list_batches(get_ctx(request), item_id, include_finished=include_finished)


@router.post("/items/{item_id}/batches", response={200: BatchOut, 422: dict})
def create_batch(request: HttpRequest, item_id: UUID, payload: BatchIn):
    try:
        return services.save_batch(get_ctx(request), payload.dict(), item_id=item_id)
    except ValueError as exc:
        return 422, {"detail": str(exc)}


@router.put("/batches/{batch_id}", response={200: BatchOut, 422: dict})
def update_batch(request: HttpRequest, batch_id: UUID, payload: BatchIn):
    try:
        return services.save_batch(get_ctx(request), payload.dict(), batch_id=batch_id)
    except ValueError as exc:
        return 422, {"detail": str(exc)}


@router.post("/batches/{batch_id}/finish", response=BatchOut)
def finish_batch(request: HttpRequest, batch_id: UUID) -> Any:
    return services.finish_batch(get_ctx(request), batch_id)


@router.delete("/batches/{batch_id}")
def delete_batch(request: HttpRequest, batch_id: UUID) -> dict[str, bool]:
    services.delete_batch(get_ctx(request), batch_id)
    return {"deleted": True}


@router.get("/expiring", response=list[ExpiringOut])
def expiring(request: HttpRequest, days: int = 7) -> Any:
    """Expired, or expiring within ``days`` — use these first."""
    return selectors.expiring(get_ctx(request), days=days)


# -------------------- Shopping list --------------------


class EntryIn(Schema):
    name: str = ""
    quantity: str = ""
    item_id: UUID | None = None


class EntryOut(Schema):
    id: UUID
    name: str
    quantity: str
    item_id: UUID | None
    unit: str | None
    auto: bool
    done_at: datetime | None

    @staticmethod
    def resolve_unit(obj) -> str | None:
        return obj.item.unit if obj.item else None


class TickIn(Schema):
    bought: Decimal | None = None  # adds stock for an item
    expiry_date: date | None = None


@router.get("/shopping", response=list[EntryOut])
def shopping(request: HttpRequest) -> Any:
    return selectors.shopping_list(get_ctx(request))


@router.post("/shopping", response={200: EntryOut, 422: dict})
def add_entry(request: HttpRequest, payload: EntryIn):
    try:
        return services.add_entry(get_ctx(request), **payload.dict())
    except ValueError as exc:
        return 422, {"detail": str(exc)}


# Before the "/shopping/{entry_id}" routes, or "clear-done" is taken for an id (405).
@router.post("/shopping/clear-done")
def clear_done(request: HttpRequest) -> dict[str, int]:
    return {"deleted": services.clear_done(get_ctx(request))}


@router.put("/shopping/{entry_id}", response=EntryOut)
def update_entry(request: HttpRequest, entry_id: UUID, payload: EntryIn) -> Any:
    return services.update_entry(
        get_ctx(request), entry_id, name=payload.name, quantity=payload.quantity
    )


@router.post("/shopping/{entry_id}/tick", response={200: EntryOut, 422: dict})
def tick(request: HttpRequest, entry_id: UUID, payload: TickIn):
    try:
        return services.tick(get_ctx(request), entry_id, **payload.dict())
    except ValueError as exc:
        return 422, {"detail": str(exc)}


@router.post("/shopping/{entry_id}/untick", response=EntryOut)
def untick(request: HttpRequest, entry_id: UUID) -> Any:
    return services.untick(get_ctx(request), entry_id)


@router.delete("/shopping/{entry_id}")
def delete_entry(request: HttpRequest, entry_id: UUID) -> dict[str, bool]:
    services.delete_entry(get_ctx(request), entry_id)
    return {"deleted": True}
