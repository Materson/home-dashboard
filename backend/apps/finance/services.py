"""Finance writes — only path that mutates the finance tables."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from dateutil.rrule import rrulestr
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied
from django.db import models
from django.db.transaction import atomic
from django.utils import timezone

from .models import (
    Category,
    DebtEntry,
    RecurringRule,
    Transaction,
    TransactionBookmark,
    TransactionShare,
)
from .selectors import TransactionFilter, find_category, list_debt_entries, list_transactions

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
    save_shares(tx, [(person_id, amount)] if person_id else [])
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
    """ "This and all following": the edited occurrence's name, amount,
    currency, category, notes and split go to the rule (future occurrences)
    and to the occurrences already recorded after it. Dates stay."""
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
    rule.shares = shares_json([(s.person_id, s.amount) for s in transaction.shares.all()])
    rule.save(
        update_fields=[
            "name",
            "amount",
            "currency",
            "category",
            "person",
            "notes",
            "shares",
            "updated_at",
        ]
    )
    pairs = [(s.person_id, s.amount) for s in transaction.shares.all()]
    for later in rule.instances.filter(date__gt=transaction.date).exclude(pk=transaction.pk):
        for field in ("name", "amount", "currency", "category_id", "notes"):
            setattr(later, field, getattr(transaction, field))
        later.save()
        save_shares(later, pairs)


@atomic
def update_recurring(
    ctx: AccessContext,
    rule_id: UUID,
    data: dict[str, Any],
    *,
    shares: list[dict] | None = None,
    repeat: str = "",
) -> RecurringRule:
    """Edit a repeating payment from the list: what the next occurrences
    will be (recorded ones stay). A new frequency applies from today on."""
    from . import recurring  # noqa: PLC0415

    ctx.require("finance", "edit")
    rule = RecurringRule.objects.get(pk=rule_id)
    pairs = normalize_shares(data["amount"], shares, None)
    for k, v in data.items():
        setattr(rule, k, v)
    if rule.end_date and rule.end_date < rule.start_date:
        raise ValueError("the end is before the first date")
    rule.person_id = pairs[0][0] if len(pairs) == 1 else None
    rule.shares = shares_json(pairs)
    today = timezone.localdate()
    if repeat:
        if repeat not in REPEATS:
            raise ValueError(f"repeat must be one of {sorted(REPEATS)}")
        text = repeat_rule(repeat, rule.start_date)
        if text != rule.rrule:
            # A new frequency applies from today on — nothing is back-filled.
            rule.rrule = text
            last = rule.instances.order_by("-date").values_list("date", flat=True).first()
            after = max(last or rule.start_date - timedelta(days=1), today - timedelta(days=1))
            nxt = rrulestr(text, dtstart=datetime.combine(rule.start_date, time())).after(
                datetime.combine(after, time())
            )
            if nxt is not None:
                rule.next_run_at = nxt.date()
    if rule.end_date and rule.next_run_at > rule.end_date:
        rule.is_active = False
    rule.save()
    if rule.is_active:
        recurring.advance_rule(rule, timezone.localdate())
    return rule


# ---- Categories ---------------------------------------------------------
# Two levels: main categories (e.g. Samochód) and their sub-categories
# (Paliwo, Przegląd techniczny). A transaction may sit in either.

CATEGORY_KINDS = ("expense", "income")


def _clean_name(name: str) -> str:
    name = " ".join(name.split())[:80]
    if not name:
        raise ValueError("the name is empty")
    return name


def _check_unique(
    name: str, kind: str, parent: Category | None, exclude_id: UUID | None = None
) -> None:
    """Unique among its siblings — "Inne" may sit under several main ones."""
    clash = Category.objects.filter(name__iexact=name, kind=kind, parent=parent)
    if exclude_id:
        clash = clash.exclude(pk=exclude_id)
    if clash.exists():
        raise ValueError(f"a category named {name!r} already exists there")


def _parent_for(kind: str, parent_id: UUID | None, cat: Category | None = None) -> Category | None:
    """The main category to put ``cat`` (or a new one) under, checked."""
    if not parent_id:
        return None
    parent = Category.objects.filter(pk=parent_id).first()
    if parent is None:
        raise ValueError("the main category doesn't exist")
    if parent.kind != kind:
        raise ValueError("a sub-category must be of the same kind as its main category")
    if parent.parent_id:
        raise ValueError("a sub-category can't have sub-categories of its own")
    if cat is not None:
        if parent.pk == cat.pk:
            raise ValueError("a category can't be under itself")
        if cat.children.exists():
            raise ValueError("it has sub-categories of its own, so it stays a main category")
    return parent


@atomic
def create_category(
    ctx: AccessContext,
    *,
    name: str,
    kind: str,
    color: str = "",
    parent_id: UUID | None = None,
) -> Category:
    ctx.require("finance", "edit")
    if kind not in CATEGORY_KINDS:
        raise ValueError("a category is an expense or an income one")
    name = _clean_name(name)
    parent = _parent_for(kind, parent_id)
    _check_unique(name, kind, parent)
    return Category.objects.create(
        # Random, not time-based: two made in the same millisecond must differ.
        key=f"user.{uuid4().hex[:12]}",
        name=name,
        kind=kind,
        parent=parent,
        color=color or (parent.color if parent else "#868e96"),
    )


@atomic
def update_category(
    ctx: AccessContext,
    category_id: UUID,
    *,
    name: str,
    color: str,
    parent_id: UUID | None = None,
) -> Category:
    """Rename / recolour / move under another main category (or make it a
    main one with ``parent_id=None``) — built-in categories too (their key
    stays, so cars and health keep finding them)."""
    ctx.require("finance", "edit")
    cat = Category.objects.get(pk=category_id)
    cat.name = _clean_name(name)
    cat.parent = _parent_for(cat.kind, parent_id, cat)
    _check_unique(cat.name, cat.kind, cat.parent, exclude_id=cat.id)
    cat.color = color or cat.color
    cat.save(update_fields=["name", "color", "parent", "updated_at"])
    return cat


@atomic
def merge_category(ctx: AccessContext, source_id: UUID, target_id: UUID) -> int:
    """Move everything from ``source`` into ``target`` (same kind) and delete
    ``source``; its sub-categories move under ``target``. Returns how many
    transactions moved."""
    ctx.require("finance", "edit")
    source = Category.objects.get(pk=source_id)
    target = Category.objects.get(pk=target_id)
    if source.pk == target.pk:
        raise ValueError("pick a different category")
    if source.kind != target.kind:
        raise ValueError("both categories must be of the same kind")
    if source.is_system:
        raise ValueError("a built-in category can't be merged away")
    if target.parent_id and source.children.exists():
        raise ValueError(
            "it has sub-categories, so it can only be merged into another main category"
        )
    moved = source.transactions.update(category=target)
    source.recurring_rules.update(category=target)
    source.bookmarks.update(category=target)
    source.children.update(parent=target)
    source.delete()
    return moved


@atomic
def delete_category(ctx: AccessContext, category_id: UUID) -> None:
    """Only an unused, non-built-in one without sub-categories — otherwise
    merge it into another."""
    ctx.require("finance", "edit")
    cat = Category.objects.get(pk=category_id)
    if cat.is_system:
        raise ValueError("a built-in category can't be deleted (rename it instead)")
    if cat.transactions.exists() or cat.recurring_rules.exists():
        raise ValueError("the category is in use — merge it into another one instead")
    if cat.children.exists():
        raise ValueError("it has sub-categories — move or delete them first")
    cat.delete()


# ---- Bookmarks ---------------------------------------------------------


def create_bookmark(ctx: AccessContext, **fields) -> TransactionBookmark:
    ctx.require("finance", "edit")
    fields["shares"] = shares_json(
        normalize_shares(fields["amount"], fields.get("shares"), fields.get("person_id"))
    )
    return TransactionBookmark.objects.create(owner_id=ctx.user_id, **fields)


def _own_bookmark(ctx: AccessContext, bookmark_id: UUID) -> TransactionBookmark:
    ctx.require("finance", "edit")
    bm = TransactionBookmark.objects.filter(pk=bookmark_id).first()
    if bm is None or bm.owner_id != ctx.user_id:
        raise PermissionDenied("not your bookmark")
    return bm


def update_bookmark(ctx: AccessContext, bookmark_id: UUID, **fields) -> TransactionBookmark:
    bm = _own_bookmark(ctx, bookmark_id)
    fields["shares"] = shares_json(
        normalize_shares(fields["amount"], fields.get("shares"), fields.get("person_id"))
    )
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


# ---- Shares: who a transaction was for ---------------------------------

CENT = Decimal("0.01")
REPEATS = {
    "weekly": "FREQ=WEEKLY",
    "monthly": "FREQ=MONTHLY",
    "quarterly": "FREQ=MONTHLY;INTERVAL=3",
    "yearly": "FREQ=YEARLY",
}


def equal_split(amount: Decimal, person_ids: list) -> list[tuple[Any, Decimal]]:
    """600 for 2 → 300 + 300; 100 for 3 → 33.34 + 33.33 + 33.33 (cents add up)."""
    if not person_ids:
        return []
    cents = int((amount / CENT).to_integral_value())
    base, rest = divmod(cents, len(person_ids))
    return [
        (pid, Decimal(base + (1 if i < rest else 0)) * CENT) for i, pid in enumerate(person_ids)
    ]


def normalize_shares(
    amount: Decimal, shares: list[dict] | None, person_id=None
) -> list[tuple[UUID, Decimal]]:
    """Validated (person, amount) pairs: explicit shares must name distinct,
    existing people and add up to the amount; otherwise ``person_id`` gets
    all of it; neither = shared by the household (no shares)."""
    from apps.people.models import Person  # noqa: PLC0415

    if not shares:
        return [(UUID(str(person_id)), amount)] if person_id else []
    pairs = [(UUID(str(s["person_id"])), Decimal(str(s["amount"])).quantize(CENT)) for s in shares]
    ids = [p for p, _ in pairs]
    if len(set(ids)) != len(ids):
        raise ValueError("a person appears twice in the split")
    if Person.objects.filter(pk__in=ids).count() != len(ids):
        raise ValueError("unknown person in the split")
    if any(a <= 0 for _, a in pairs):
        raise ValueError("every part of the split must be more than 0")
    if sum(a for _, a in pairs) != Decimal(amount).quantize(CENT):
        raise ValueError("the parts of the split must add up to the amount")
    return pairs


def shares_json(pairs: list[tuple[UUID, Decimal]]) -> list[dict[str, str]]:
    return [{"person_id": str(p), "amount": f"{a:.2f}"} for p, a in pairs]


def save_shares(tx: Transaction, pairs: list[tuple[UUID, Decimal]]) -> None:
    tx.shares.all().delete()
    TransactionShare.objects.bulk_create(
        TransactionShare(transaction=tx, person_id=p, amount=a) for p, a in pairs
    )
    person_id = pairs[0][0] if len(pairs) == 1 else None
    if tx.person_id != person_id:
        tx.person_id = person_id
        tx.save(update_fields=["person"])


def _next_occurrence(rrule_text: str, start: date) -> date:
    rule = rrulestr(rrule_text, dtstart=datetime.combine(start, time()))
    nxt = rule.after(datetime.combine(start, time()))
    return nxt.date() if nxt else start


def repeat_rule(kind: str, start: date) -> str:
    text = REPEATS[kind]
    # A payment on the 29th-31st would skip shorter months; it goes on the
    # last day of every month instead.
    if kind in ("monthly", "quarterly") and start.day > 28:  # noqa: PLR2004
        text += ";BYMONTHDAY=-1"
    return text


@atomic
def create_transaction(
    ctx: AccessContext,
    data: dict[str, Any],
    *,
    shares: list[dict] | None = None,
    repeat: str = "",
    repeat_until: date | None = None,
) -> Transaction:
    """A hand-entered transaction (the page form, or a confirmed assistant
    proposal), split between people, optionally repeating: then a
    RecurringRule is created too and this is its first occurrence."""
    ctx.require("finance", "edit")
    data = {"related_kind": "", "related_id": None, **data}
    check_related(data["related_kind"], data["related_id"])
    pairs = normalize_shares(data["amount"], shares, data.get("person_id"))
    data["person_id"] = pairs[0][0] if len(pairs) == 1 else None
    if repeat:
        if repeat not in REPEATS:
            raise ValueError(f"repeat must be one of {sorted(REPEATS)}")
        if repeat_until and repeat_until < data["date"]:
            raise ValueError("the repeat end is before the first date")
        text = repeat_rule(repeat, data["date"])
        data["recurring_rule"] = RecurringRule.objects.create(
            name=data["name"],
            amount=data["amount"],
            currency=data.get("currency", "PLN"),
            category_id=data["category_id"],
            person_id=data["person_id"],
            notes=data.get("notes", ""),
            rrule=text,
            start_date=data["date"],
            end_date=repeat_until,
            next_run_at=_next_occurrence(text, data["date"]),
            shares=shares_json(pairs),
        )
    tx = Transaction.objects.create(**data)
    save_shares(tx, pairs)
    if repeat:
        from . import recurring  # noqa: PLC0415

        recurring.advance_rule(data["recurring_rule"], timezone.localdate())
    return tx


@atomic
def update_transaction(
    ctx: AccessContext,
    tx_id: UUID,
    data: dict[str, Any],
    *,
    shares: list[dict] | None = None,
    update_future: bool = False,
) -> Transaction:
    ctx.require("finance", "edit")
    tx = Transaction.objects.get(pk=tx_id)
    check_related(data.get("related_kind", ""), data.get("related_id"))
    pairs = normalize_shares(data["amount"], shares, data.get("person_id"))
    for k, v in data.items():
        setattr(tx, k, v)
    tx.person_id = pairs[0][0] if len(pairs) == 1 else None
    tx.save()
    save_shares(tx, pairs)
    propagate_edit_to_rule(ctx, tx, update_future=update_future)
    return tx


def stop_recurring(ctx: AccessContext, rule_id: UUID) -> RecurringRule:
    """No more occurrences; the ones already recorded stay."""
    ctx.require("finance", "edit")
    rule = RecurringRule.objects.get(pk=rule_id)
    rule.is_active = False
    rule.save(update_fields=["is_active", "updated_at"])
    return rule


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


# -------------------- Many at once --------------------


@atomic
def bulk_update_transactions(
    ctx: AccessContext,
    f: TransactionFilter,
    *,
    ids: list[UUID] | None = None,
    person: str = "keep",
    person_id: UUID | None = None,
    category_id: UUID | None = None,
    dry_run: bool = False,
) -> dict[str, int]:
    """Set who and/or which category on every transaction the filter finds
    (of them only ``ids``, when given). ``person``: "keep", "household" (no
    one) or "person" (``person_id`` — replacing a split between people). A
    category only goes to transactions of its kind (income / expense); the
    others keep theirs and are counted in ``wrong_kind``. ``dry_run`` only
    counts."""
    from apps.people.models import Person  # noqa: PLC0415

    ctx.require("finance", "edit")
    if person not in ("keep", "household", "person"):
        raise ValueError("person must be keep, household or person")
    if person == "person" and not Person.objects.filter(pk=person_id).exists():
        raise ValueError("unknown person")
    category = Category.objects.filter(pk=category_id).first() if category_id else None
    if category_id and (category is None or category.kind not in CATEGORY_KINDS):
        raise ValueError("unknown category")
    qs = list_transactions(ctx, f).prefetch_related("shares")
    if ids is not None:
        qs = qs.filter(pk__in=ids)
    who = str(person_id) if person == "person" else None
    matched = changed = wrong_kind = 0
    for tx in qs:
        matched += 1
        dirty = False
        if category and tx.category_id != category.id:
            if tx.category.kind == category.kind:
                dirty = True
                if not dry_run:
                    tx.category = category
                    tx.save(update_fields=["category", "updated_at"])
            else:
                wrong_kind += 1
        if person != "keep":
            wanted = {(who, tx.amount)} if who else set()
            if {(str(s.person_id), s.amount) for s in tx.shares.all()} != wanted:
                dirty = True
                if not dry_run:
                    save_shares(tx, [(person_id, tx.amount)] if who else [])
        changed += dirty
    return {"matched": matched, "changed": changed, "wrong_kind": wrong_kind}


# -------------------- Import --------------------

# Colours for main categories an import creates (sub-categories take their main's).
IMPORT_COLORS = (
    "#4c6ef5",
    "#12b886",
    "#fab005",
    "#fa5252",
    "#7950f2",
    "#15aabf",
    "#fd7e14",
    "#e64980",
    "#40c057",
    "#228be6",
)
NO_CATEGORY = "Inne"


@atomic
def import_transactions(
    ctx: AccessContext,
    rows: list[dict[str, Any]],
    *,
    mapping: list[dict[str, Any]] | None = None,
    person_id: UUID | None = None,
) -> dict[str, int]:
    """Save rows read by ``importer.parse`` (and checked in the preview).
    Each row's "main > sub" category is the one ``mapping`` points it at,
    else the one of that name — created when missing (sub-categories too).
    The description (Opis) is the name, the note (Notatka) goes to the
    notes, with an amount in another currency."""
    from apps.people.models import Person  # noqa: PLC0415

    from .importer import name_and_note  # noqa: PLC0415

    ctx.require("finance", "edit")
    if person_id and not Person.objects.filter(pk=person_id).exists():
        raise ValueError("unknown person")
    targets = {
        (m["kind"], m["category"] or NO_CATEGORY, m.get("subcategory") or ""): m.get("target_id")
        for m in mapping or []
    }
    resolved: dict[tuple[str, str, str], Category] = {}
    created = 0

    def find_or_create(kind: str, name: str, parent: Category | None = None) -> Category:
        nonlocal created
        found = find_category(kind, parent.name if parent else name, name if parent else "")
        if found:
            return found
        created += 1
        color = "" if parent else IMPORT_COLORS[created % len(IMPORT_COLORS)]
        return create_category(
            ctx, name=name, kind=kind, color=color, parent_id=parent.id if parent else None
        )

    def category_for(kind: str, main: str, sub: str) -> Category:
        key = (kind, main, sub)
        if key not in resolved:
            target = targets.get(key)
            if target:
                cat = Category.objects.filter(pk=target).first()
                if cat is None or cat.kind != kind:
                    raise ValueError(f"the category chosen for {main} is not an {kind} one")
            else:
                cat = find_or_create(kind, main)
                if sub:
                    cat = find_or_create(kind, sub, cat)
            resolved[key] = cat
        return resolved[key]

    for r in rows:
        if r["kind"] not in CATEGORY_KINDS or r["amount"] <= 0:
            raise ValueError(f"line {r.get('line')}: an income or expense of more than 0")
        cat = category_for(r["kind"], r["category"] or NO_CATEGORY, r.get("subcategory") or "")
        name, note = name_and_note(r.get("description", ""), r.get("note", ""))
        name = " ".join((name or r.get("subcategory") or cat.name).split())[:200]
        extra = [note]
        if r.get("original"):
            extra.append(f"Kwota oryginalna: {r['original']}")
        create_transaction(
            ctx,
            {
                "date": r["date"],
                "amount": r["amount"],
                "currency": r.get("currency") or "PLN",
                "category_id": cat.id,
                "person_id": person_id,
                "name": name,
                "notes": "\n".join(x for x in extra if x),
            },
        )
    return {"created": len(rows), "categories": created}
