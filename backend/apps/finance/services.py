"""Finance writes — only path that mutates the finance tables."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ObjectDoesNotExist
from django.db import models
from django.db.transaction import atomic

from .models import Category, Transaction

if TYPE_CHECKING:
    from apps.access.context import AccessContext


@atomic
def upsert_linked_transaction(
    ctx: "AccessContext",
    *,
    source_obj: models.Model,
    category_key: str,
    amount: Decimal,
    currency: str,
    occurred_on: date,
    name: str,
    person_id=None,
    notes: str = "",
) -> Transaction:
    """Create or update the single Transaction linked to ``source_obj``.

    The pair ``(source_type, source_id)`` is unique (see Transaction.Meta),
    so another app can call this every time it saves — fuel entry edits
    update the ledger row, deletes cascade via a separate hook.
    """
    ctx.require("finance", "edit")

    try:
        category = Category.objects.get(key=category_key)
    except ObjectDoesNotExist as exc:
        raise ValueError(f"unknown category key {category_key!r} — run seed_finance_categories") from exc

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
    ctx: "AccessContext",
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
    rule.save(update_fields=["name", "amount", "currency", "category", "person", "notes", "updated_at"])
