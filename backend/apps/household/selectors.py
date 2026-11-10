"""Household reads. Anyone with household:view sees everything here — the
module isn't per person."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from django.core.exceptions import PermissionDenied
from django.db.models import DecimalField, Min, Q, QuerySet, Sum, Value
from django.db.models.functions import Coalesce
from django.http import Http404
from django.utils import timezone

from .models import Batch, Item, ShoppingEntry

if TYPE_CHECKING:
    from apps.access.context import AccessContext

EXPIRY_SOON_DAYS = 3
_OPEN = Q(batches__finished_on__isnull=True)


def _require_view(ctx: AccessContext) -> None:
    if not ctx.has("household", "view"):
        raise PermissionDenied("household:view denied")


def _with_stock(qs: QuerySet[Item]) -> QuerySet[Item]:
    """Adds ``stock`` (what's left in open batches) and ``next_expiry``."""
    return qs.annotate(
        stock=Coalesce(
            Sum("batches__quantity", filter=_OPEN),
            Value(Decimal(0)),
            output_field=DecimalField(max_digits=10, decimal_places=2),
        ),
        next_expiry=Min("batches__expiry_date", filter=_OPEN),
    )


def list_items(
    ctx: AccessContext,
    *,
    q: str | None = None,
    category: str | None = None,
) -> QuerySet[Item]:
    _require_view(ctx)
    qs = Item.objects.filter(archived_at__isnull=True)
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(notes__icontains=q))
    if category:
        qs = qs.filter(category=category)
    return _with_stock(qs).order_by("name")


def get_item(ctx: AccessContext, item_id: UUID) -> Item:
    _require_view(ctx)
    item = _with_stock(Item.objects.filter(pk=item_id, archived_at__isnull=True)).first()
    if item is None:
        raise Http404
    return item


def stock_of(item: Item) -> Decimal:
    return item.batches.filter(finished_on__isnull=True).aggregate(s=Sum("quantity"))[
        "s"
    ] or Decimal(0)


def is_below_min(item: Item, stock: Decimal | None = None) -> bool:
    if item.min_quantity is None or item.archived_at:
        return False
    return (stock_of(item) if stock is None else stock) < item.min_quantity


def list_batches(ctx: AccessContext, item_id: UUID, *, include_finished: bool = False):
    item = get_item(ctx, item_id)
    qs = item.batches.all()
    return qs if include_finished else qs.filter(finished_on__isnull=True)


def get_batch(ctx: AccessContext, batch_id: UUID) -> Batch:
    _require_view(ctx)
    batch = Batch.objects.select_related("item").filter(pk=batch_id).first()
    if batch is None or batch.item.archived_at:
        raise Http404
    return batch


def batch_status(batch: Batch, today: date | None = None) -> str:
    """expired / soon (within EXPIRY_SOON_DAYS) / ok / unknown (no date) / finished."""
    if batch.finished_on:
        return "finished"
    if batch.expiry_date is None:
        return "unknown"
    today = today or timezone.localdate()
    if batch.expiry_date < today:
        return "expired"
    if batch.expiry_date <= today + timedelta(days=EXPIRY_SOON_DAYS):
        return "soon"
    return "ok"


def expiring(ctx: AccessContext, *, days: int = 7) -> QuerySet[Batch]:
    """Open batches that are expired or expire within ``days`` — oldest first."""
    _require_view(ctx)
    until = timezone.localdate() + timedelta(days=days)
    return Batch.objects.select_related("item").filter(
        finished_on__isnull=True,
        expiry_date__lte=until,
        item__archived_at__isnull=True,
    )


def shopping_list(ctx: AccessContext) -> QuerySet[ShoppingEntry]:
    """What's still to buy, plus what was ticked off in the last 12 hours
    (so a mis-tap in the shop can be undone)."""
    _require_view(ctx)
    since = timezone.now() - timedelta(hours=12)
    return ShoppingEntry.objects.select_related("item").filter(
        Q(done_at__isnull=True) | Q(done_at__gte=since)
    )


def get_entry(ctx: AccessContext, entry_id: UUID) -> ShoppingEntry:
    _require_view(ctx)
    entry = ShoppingEntry.objects.select_related("item").filter(pk=entry_id).first()
    if entry is None:
        raise Http404
    return entry
