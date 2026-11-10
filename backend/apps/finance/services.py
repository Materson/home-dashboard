"""Finance writes — only path that mutates the finance tables."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied
from django.db import models
from django.db.transaction import atomic

from .models import Category, DebtEntry, Transaction, TransactionBookmark
from .selectors import list_debt_entries

if TYPE_CHECKING:
    from apps.access.context import AccessContext


@atomic
def upsert_linked_transaction(
    ctx: AccessContext,
    *,
    source_obj: models.Model,
    category_key: str,
    amount: Decimal,
    currency: str,
    occurred_on: date,
    name: str,
    person_id=None,
    notes: str = "",
    authorized_by: str = "finance",
) -> Transaction:
    """Create or update the single Transaction linked to ``source_obj``.

    The pair ``(source_type, source_id)`` is unique (see Transaction.Meta),
    so another app can call this every time it saves — fuel entry edits
    update the ledger row, deletes cascade via a separate hook.

    ``authorized_by`` is the module whose *edit* permission covers the write.
    Other apps pass their own module ("cars"): the ledger row is a side
    effect of recording fuel, so a user who may edit cars but not see
    finance can still log a fill-up.
    """
    ctx.require(authorized_by, "edit")

    try:
        category = Category.objects.get(key=category_key)
    except ObjectDoesNotExist as exc:
        raise ValueError(
            f"unknown category key {category_key!r} — run seed_finance_categories"
        ) from exc

    ct = ContentType.objects.get_for_model(type(source_obj))
    oid = source_obj.pk

    defaults = {
        "date": occurred_on,
        "amount": amount,
        "currency": currency,
        "category": category,
        "person_id": person_id,
        "name": name,
        "notes": notes,
    }
    tx, _created = Transaction.objects.update_or_create(
        source_type=ct,
        source_id=oid,
        defaults=defaults,
    )
    return tx


def delete_linked_transaction(source_obj: models.Model) -> None:
    """Remove the ledger row tied to ``source_obj`` (if any)."""
    ct = ContentType.objects.get_for_model(type(source_obj))
    Transaction.objects.filter(source_type=ct, source_id=source_obj.pk).delete()


@atomic
def propagate_edit_to_rule(
    ctx: AccessContext,
    transaction: Transaction,
    *,
    update_future: bool,
) -> None:
    """When a user edits a recurring-rule-materialized Transaction and the UI
    asks "apply to future occurrences?", this is what runs on yes.

    It copies the edited transaction's ``name / amount / currency / category /
    person / notes`` back onto the rule, so the next auto-materialized
    transactions inherit them."""
    if not update_future:
        return
    rule = transaction.recurring_rule
    if rule is None:
        return
    ctx.require("finance", "edit")
    rule.name = transaction.name
    rule.amount = transaction.amount
    rule.currency = transaction.currency
    rule.category = transaction.category
    rule.person_id = transaction.person_id
    rule.notes = transaction.notes
    rule.save(
        update_fields=["name", "amount", "currency", "category", "person", "notes", "updated_at"]
    )


# ---- Bookmarks ---------------------------------------------------------


def create_bookmark(ctx: AccessContext, **fields) -> TransactionBookmark:
    ctx.require("finance", "edit")
    return TransactionBookmark.objects.create(owner_id=ctx.user_id, **fields)


def _own_bookmark(ctx: AccessContext, bookmark_id: UUID) -> TransactionBookmark:
    ctx.require("finance", "edit")
    bm = TransactionBookmark.objects.filter(pk=bookmark_id).first()
    if bm is None or bm.owner_id != ctx.user_id:
        raise PermissionDenied("not your bookmark")
    return bm


def update_bookmark(ctx: AccessContext, bookmark_id: UUID, **fields) -> TransactionBookmark:
    bm = _own_bookmark(ctx, bookmark_id)
    for k, v in fields.items():
        setattr(bm, k, v)
    bm.save()
    return bm


def delete_bookmark(ctx: AccessContext, bookmark_id: UUID) -> None:
    _own_bookmark(ctx, bookmark_id).delete()


# ---- Debts -------------------------------------------------------------


def add_debt_entry(ctx: AccessContext, **fields) -> DebtEntry:
    ctx.require("finance", "edit")
    fields["counterparty_name"] = (fields.get("counterparty_name") or "").strip()
    if not fields["counterparty_name"]:
        raise ValueError("who is required")
    if Decimal(fields["amount"]) <= 0:
        raise ValueError("amount must be positive")
    return DebtEntry.objects.create(created_by_id=ctx.user_id, **fields)


def delete_debt_entry(ctx: AccessContext, entry_id: UUID) -> None:
    ctx.require("finance", "edit")
    DebtEntry.objects.filter(pk=entry_id).delete()


def delete_counterparty(ctx: AccessContext, name: str) -> int:
    """Remove a person from the debts list: every entry recorded for them
    (any spelling, any currency). Returns how many entries were deleted."""
    ctx.require("finance", "edit")
    deleted, _ = DebtEntry.objects.filter(counterparty_name__iexact=name.strip()).delete()
    return deleted


@atomic
def settle_debt(ctx: AccessContext, *, name: str, currency: str, on: date) -> DebtEntry | None:
    """Record the repayment that brings ``name``'s balance to zero.

    Returns ``None`` when there is nothing outstanding."""
    ctx.require("finance", "edit")
    entries = list_debt_entries(ctx, name=name).filter(currency=currency)
    balance = sum((e.signed_amount for e in entries), Decimal("0"))
    if balance == 0:
        return None
    # They owe us -> they pay us back (we receive); we owe them -> we give.
    direction = DebtEntry.Direction.RECEIVED if balance > 0 else DebtEntry.Direction.GAVE
    return add_debt_entry(
        ctx,
        counterparty_name=name,
        direction=direction,
        amount=abs(balance),
        currency=currency,
        date=on,
        notes="Rozliczenie",  # household language is Polish (see seed_finance_categories)
    )


def check_related(kind: str, related_id: UUID | None) -> None:
    """A transaction may point at a record in another app ("app.model" + id)
    only if that record exists and its model is registered with an access
    module; otherwise the link is rejected (ValueError → 422)."""
    if not kind and related_id is None:
        return
    from apps.core.attachments import AttachmentError, resolve_subject  # noqa: PLC0415

    if not kind or related_id is None:
        raise ValueError("related_kind and related_id go together")
    try:
        resolve_subject(kind, related_id)
    except AttachmentError as exc:
        raise ValueError(f"unknown related record {kind}") from exc
