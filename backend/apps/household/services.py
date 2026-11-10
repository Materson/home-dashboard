"""Household writes (household:edit). Every stock change re-checks the item
against its minimum, so the shopping list follows the pantry by itself."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import UUID

from django.contrib.auth import get_user_model
from django.db.transaction import atomic
from django.utils import timezone

from apps.reminders import services as reminders

from .models import Batch, Item, ShoppingEntry
from .selectors import get_batch, get_entry, get_item, is_below_min, stock_of

if TYPE_CHECKING:
    from apps.access.context import AccessContext

EXPIRY_REMIND_DAYS_BEFORE = 2


# -------------------- Items --------------------


@atomic
def save_item(ctx: AccessContext, data: dict[str, Any], item_id: UUID | None = None) -> Item:
    ctx.require("household", "edit")
    item = get_item(ctx, item_id) if item_id else Item(created_by_id=ctx.user_id)
    for k, v in data.items():
        setattr(item, k, v)
    item.name = " ".join(item.name.split())
    if not item.name:
        raise ValueError("name is empty")
    if item.min_quantity is not None and item.min_quantity < 0:
        raise ValueError("minimum can't be negative")
    item.save()
    item.shopping_entries.filter(done_at__isnull=True, auto=True).update(name=item.name)
    sync_shopping(ctx, item)
    return get_item(ctx, item.id)  # with stock annotations


@atomic
def archive_item(ctx: AccessContext, item_id: UUID) -> None:
    """Hide an item for good (history stays); its open list lines go too."""
    ctx.require("household", "edit")
    item = get_item(ctx, item_id)
    for batch in item.batches.filter(finished_on__isnull=True):
        reminders.cancel_for_target(batch)
    item.shopping_entries.filter(done_at__isnull=True).delete()
    item.archive()


# -------------------- Batches --------------------


@atomic
def save_batch(
    ctx: AccessContext,
    data: dict[str, Any],
    *,
    item_id: UUID | None = None,
    batch_id: UUID | None = None,
) -> Batch:
    """Add a purchase to ``item_id`` or update batch ``batch_id``."""
    ctx.require("household", "edit")
    if batch_id:
        batch = get_batch(ctx, batch_id)
    else:
        batch = Batch(
            item=get_item(ctx, item_id),
            created_by_id=ctx.user_id,
            added_on=timezone.localdate(),
        )
    for k, v in data.items():
        if v is not None or k != "added_on":
            setattr(batch, k, v)
    if batch.quantity is None or batch.quantity < 0:
        raise ValueError("quantity can't be negative")
    if batch.quantity == 0 and not batch.finished_on:
        batch.finished_on = timezone.localdate()  # nothing left = used up
    batch.save()
    _plan_expiry_reminder(ctx, batch)
    sync_shopping(ctx, batch.item)
    return batch


@atomic
def delete_batch(ctx: AccessContext, batch_id: UUID) -> None:
    ctx.require("household", "edit")
    batch = get_batch(ctx, batch_id)
    item = batch.item
    reminders.cancel_for_target(batch)
    batch.delete()
    sync_shopping(ctx, item)


@atomic
def finish_batch(ctx: AccessContext, batch_id: UUID) -> Batch:
    """Used up or thrown away (e.g. expired)."""
    ctx.require("household", "edit")
    batch = get_batch(ctx, batch_id)
    _close(batch)
    sync_shopping(ctx, batch.item)
    return batch


@atomic
def consume(ctx: AccessContext, item_id: UUID, amount: Decimal = Decimal(1)) -> Item:
    """Use ``amount`` of an item, from the batch that expires first onwards."""
    ctx.require("household", "edit")
    if amount <= 0:
        raise ValueError("amount must be positive")
    item = get_item(ctx, item_id)
    left = amount
    for batch in item.batches.select_for_update().filter(finished_on__isnull=True):
        if left <= 0:
            break
        take = min(batch.quantity, left)
        batch.quantity -= take
        left -= take
        if batch.quantity <= 0:
            _close(batch)
        else:
            batch.save(update_fields=["quantity", "updated_at"])
    sync_shopping(ctx, item)
    return get_item(ctx, item.id)


def _close(batch: Batch) -> None:
    """Closed batches don't count as stock; a thrown-away one keeps what was
    left in it, for the record."""
    batch.finished_on = batch.finished_on or timezone.localdate()
    batch.save(update_fields=["quantity", "finished_on", "updated_at"])
    reminders.cancel_for_target(batch)


def _plan_expiry_reminder(ctx: AccessContext, batch: Batch) -> None:
    reminders.cancel_for_target(batch)
    today = timezone.localdate()
    expiry = batch.expiry_date
    if batch.finished_on or expiry is None or expiry < today or not ctx.user_id:
        return
    remind_on = max(today, expiry - timedelta(days=EXPIRY_REMIND_DAYS_BEFORE))
    when = max(timezone.make_aware(datetime.combine(remind_on, time(9))), timezone.now())
    reminders.schedule(
        ctx,
        title=f"Kończy się termin: {batch.item.name}",
        body=f"Ważne do {expiry:%d.%m.%Y}.",
        target=batch,
        recipients=list(get_user_model().objects.filter(pk=ctx.user_id)),
        channels=("webpush",),
        due_at=when,
    )


# -------------------- Shopping list --------------------


def sync_shopping(ctx: AccessContext, item: Item) -> None:
    """Below its minimum → make sure the item is on the list (once);
    back above → drop the line that was added automatically."""
    open_lines = item.shopping_entries.filter(done_at__isnull=True)
    stock = stock_of(item)
    if is_below_min(item, stock):
        if not open_lines.exists():
            missing = item.min_quantity - stock
            ShoppingEntry.objects.create(
                item=item,
                name=item.name,
                quantity=f"{_fmt(missing)} {item.unit}".strip(),
                auto=True,
                created_by_id=ctx.user_id,
            )
    else:
        open_lines.filter(auto=True).delete()


def _fmt(value: Decimal) -> str:
    """2.50 → "2,5"; 3.00 → "3"."""
    text = f"{value.normalize():f}"
    return text.replace(".", ",")


@atomic
def add_entry(
    ctx: AccessContext, *, name: str, quantity: str = "", item_id: UUID | None = None
) -> ShoppingEntry:
    """A line on the list. A name that matches an item links to it, so
    ticking it off can add the stock."""
    ctx.require("household", "edit")
    name = " ".join(name.split())
    item = get_item(ctx, item_id) if item_id else None
    if item is None and name:
        item = Item.objects.filter(archived_at__isnull=True, name__iexact=name).first()
    if not name and item:
        name = item.name
    if not name:
        raise ValueError("name is empty")
    if item and item.shopping_entries.filter(done_at__isnull=True).exists():
        line = item.shopping_entries.filter(done_at__isnull=True).first()
        if quantity:
            line.quantity, line.auto = quantity, False
            line.save(update_fields=["quantity", "auto", "updated_at"])
        return line
    return ShoppingEntry.objects.create(
        item=item, name=name, quantity=quantity, created_by_id=ctx.user_id
    )


@atomic
def update_entry(ctx: AccessContext, entry_id: UUID, *, name: str, quantity: str) -> ShoppingEntry:
    ctx.require("household", "edit")
    entry = get_entry(ctx, entry_id)
    entry.name = " ".join(name.split()) or entry.name
    entry.quantity = quantity
    entry.auto = False  # edited by hand: keep it even if stock recovers
    entry.save()
    return entry


@atomic
def tick(
    ctx: AccessContext,
    entry_id: UUID,
    *,
    bought: Decimal | None = None,
    expiry_date: date | None = None,
) -> ShoppingEntry:
    """Bought. For an item, ``bought`` adds that much stock as a new batch."""
    ctx.require("household", "edit")
    entry = get_entry(ctx, entry_id)
    entry.done_at = timezone.now()
    entry.done_by_id = ctx.user_id
    entry.save(update_fields=["done_at", "done_by", "updated_at"])
    if entry.item and bought:
        save_batch(ctx, {"quantity": bought, "expiry_date": expiry_date}, item_id=entry.item_id)
    return entry


@atomic
def untick(ctx: AccessContext, entry_id: UUID) -> ShoppingEntry:
    ctx.require("household", "edit")
    entry = get_entry(ctx, entry_id)
    entry.done_at = None
    entry.done_by = None
    entry.save(update_fields=["done_at", "done_by", "updated_at"])
    return entry


def delete_entry(ctx: AccessContext, entry_id: UUID) -> None:
    ctx.require("household", "edit")
    get_entry(ctx, entry_id).delete()


def clear_done(ctx: AccessContext) -> int:
    ctx.require("household", "edit")
    deleted, _ = ShoppingEntry.objects.filter(done_at__isnull=False).delete()
    return deleted
