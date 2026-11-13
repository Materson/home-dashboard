"""Finance read queries — every function takes an AccessContext."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import UUID

from django.db.models import Count, F, Q, QuerySet, Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone

from .models import (
    Category,
    DebtEntry,
    Loan,
    RecurringRule,
    Transaction,
    TransactionBookmark,
    TransactionShare,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from apps.access.context import AccessContext


@dataclass(slots=True)
class TransactionFilter:
    q: str | None = None  # name/notes text
    date_from: date | None = None
    date_to: date | None = None
    amount_min: Decimal | None = None
    amount_max: Decimal | None = None
    category_keys: list[str] | None = None
    person_ids: list[UUID] | None = None
    kind: str | None = None  # 'income' | 'expense' | 'transfer'


def list_categories(ctx: AccessContext) -> QuerySet[Category]:
    """With ``used`` = how many transactions are in each."""
    if not ctx.has("finance", "view"):
        return Category.objects.none()
    return Category.objects.select_related("parent").annotate(used=Count("transactions"))


def list_transactions(
    ctx: AccessContext, f: TransactionFilter | None = None
) -> QuerySet[Transaction]:
    qs = ctx.scope_by_person(
        module="finance",
        qs=Transaction.objects.all(),
        person_field="person_id",
        date_field="date",
    ).select_related("category__parent", "person")
    if not f:
        return qs
    if f.q:
        qs = qs.filter(Q(name__icontains=f.q) | Q(notes__icontains=f.q))
    if f.date_from:
        qs = qs.filter(date__gte=f.date_from)
    if f.date_to:
        qs = qs.filter(date__lte=f.date_to)
    if f.amount_min is not None:
        qs = qs.filter(amount__gte=f.amount_min)
    if f.amount_max is not None:
        qs = qs.filter(amount__lte=f.amount_max)
    if f.category_keys:
        # A main category brings its sub-categories along.
        qs = qs.filter(
            Q(category__key__in=f.category_keys) | Q(category__parent__key__in=f.category_keys)
        )
    if f.person_ids:
        # A split counts for each person in it.
        qs = qs.filter(
            Q(person_id__in=f.person_ids) | Q(shares__person_id__in=f.person_ids)
        ).distinct()
    if f.kind:
        qs = qs.filter(category__kind=f.kind)
    return qs


@dataclass(slots=True)
class MonthlySum:
    year_month: str
    kind: str
    total: Decimal
    currency: str

    def __post_init__(self) -> None:
        self.total = Decimal(self.total).quantize(Decimal("0.01"))  # SQLite sums drop the cents


MAX_CHART_MONTHS = 36
SHARED = "shared"  # person filter: the household's (not split to anyone)


@dataclass(slots=True)
class ChartFilter:
    """What the charts count, beside the period: transactions whose name or
    notes hold any of ``terms``, amounts and categories as on the list. With
    ``persons`` (people's ids and/or "shared") only those people's parts
    count — and, for "shared", the household's unsplit transactions."""

    terms: list[str] | None = None
    amount_min: Decimal | None = None
    amount_max: Decimal | None = None
    category_keys: list[str] | None = None
    persons: list[str] | None = None

    @property
    def words(self) -> list[str]:
        return [w.strip() for w in self.terms or [] if w.strip()]


def _has_words(words: list[str]) -> Q:
    q = Q()
    for word in words:
        q |= Q(name__icontains=word) | Q(notes__icontains=word)
    return q


def _chart_base(
    ctx: AccessContext, f: ChartFilter, *, date_from: date, date_to: date, kind: str | None = None
) -> QuerySet[Transaction]:
    qs = list_transactions(
        ctx,
        TransactionFilter(
            date_from=date_from,
            date_to=date_to,
            amount_min=f.amount_min,
            amount_max=f.amount_max,
            category_keys=f.category_keys,
            kind=kind,
        ),
    )
    return qs.filter(_has_words(f.words)) if f.words else qs


def _is_uuid(value: str) -> bool:
    try:
        UUID(value)
    except ValueError:
        return False
    return True


def _person_ids(persons: list[str]) -> list[UUID]:
    """The people among ``persons`` ("shared" and junk left out)."""
    return [UUID(p) for p in persons if p != SHARED and _is_uuid(p)]


def _by_month_and_kind(prefix: str) -> dict[str, Any]:
    return {"month": TruncMonth(f"{prefix}date"), "kind": F(f"{prefix}category__kind")}


def _sums(
    base: QuerySet[Transaction],
    persons: list[str] | None,
    group: Callable[[str], dict[str, Any]],
) -> dict[tuple[Any, ...], Decimal]:
    """``base``'s totals per ``group`` (name -> expression, for a lookup
    prefix: "" on transactions, "transaction__" on their shares): whole
    amounts, or with ``persons`` those people's parts (plus the unsplit
    transactions for "shared")."""
    out: dict[tuple[Any, ...], Decimal] = {}

    def add(qs: QuerySet[Any], prefix: str) -> None:
        exprs = {f"g_{name}": expr for name, expr in group(prefix).items()}
        rows = qs.annotate(**exprs).values(*exprs).annotate(total=Sum("amount")).order_by()
        for row in rows:
            key = tuple(row[name] for name in exprs)
            out[key] = out.get(key, Decimal(0)) + row["total"]

    if not persons:
        add(base, "")
        return out
    if ids := _person_ids(persons):
        add(
            TransactionShare.objects.filter(transaction__in=base, person_id__in=ids),
            "transaction__",
        )
    if SHARED in persons:
        add(base.filter(shares__isnull=True), "")
    return out


def _window(until: date | None, months: int) -> tuple[date, date]:
    """First and last day of the ``months`` calendar months ending with
    ``until``'s month (default: the current one)."""
    months = max(1, min(months, MAX_CHART_MONTHS))
    until = until or timezone.localdate()
    # A running month index (year * 12 + month0) needs no year special-casing.
    until_idx = until.year * 12 + until.month - 1
    return _month_start(until_idx - (months - 1)), _month_start(until_idx + 1) - timedelta(days=1)


def monthly_totals(
    ctx: AccessContext,
    *,
    until: date | None = None,
    months: int = 12,
    person: str | None = None,
    f: ChartFilter | None = None,
) -> list[MonthlySum]:
    """Totals grouped by (month, category.kind, currency) for the ``months``
    calendar months ending with ``until``'s month (default: the current one);
    ``person`` = one person's parts, or "shared" (as ``f.persons``)."""
    if not ctx.has("finance", "view"):
        return []
    f = f or ChartFilter()
    start, end = _window(until, months)
    base = _chart_base(ctx, f, date_from=start, date_to=end)

    def group(prefix: str) -> dict[str, Any]:
        return {**_by_month_and_kind(prefix), "currency": F(f"{prefix}currency")}

    sums = _sums(base, f.persons or ([person] if person else None), group)
    return [
        MonthlySum(month.strftime("%Y-%m"), kind, total, currency)
        for (month, kind, currency), total in sorted(sums.items())
    ]


@dataclass(slots=True)
class SeriesPoint:
    key: str  # a category's id, a person's id / "shared", or a search word
    year_month: str
    kind: str
    total: Decimal

    def __post_init__(self) -> None:
        self.total = Decimal(self.total).quantize(Decimal("0.01"))


def monthly_series(
    ctx: AccessContext,
    *,
    by: str,
    until: date | None = None,
    months: int = 12,
    f: ChartFilter | None = None,
    currency: str = "PLN",
) -> list[SeriesPoint]:
    """The line chart split into lines to compare, each with its monthly
    totals per kind: ``by`` "category" (the filter's — a main one with its
    sub-categories — else every main category), "person" (the filter's,
    else everyone with a part and the household's unsplit ones) or "term"
    (each search word)."""
    if not ctx.has("finance", "view"):
        return []
    f = f or ChartFilter()
    start, end = _window(until, months)
    base = _chart_base(ctx, f, date_from=start, date_to=end).filter(currency=currency)
    lines: dict[str, dict[tuple[Any, ...], Decimal]] = {}
    if by == "category" and f.category_keys:
        found = dict(Category.objects.filter(key__in=f.category_keys).values_list("key", "id"))
        for key in f.category_keys:
            if key in found:
                inside = base.filter(Q(category__key=key) | Q(category__parent__key=key))
                lines[str(found[key])] = _sums(inside, f.persons, _by_month_and_kind)
    elif by == "category":

        def per_category(prefix: str) -> dict[str, Any]:
            return {"category": F(f"{prefix}category_id"), **_by_month_and_kind(prefix)}

        sums = _sums(base, f.persons, per_category)
        parents = dict(
            Category.objects.filter(pk__in={c for c, _, _ in sums}).values_list("id", "parent_id")
        )
        for (cid, month, kind), total in sums.items():
            line = lines.setdefault(str(parents[cid] or cid), {})
            line[month, kind] = line.get((month, kind), Decimal(0)) + total
    elif by == "person":
        persons = f.persons or [
            *(
                str(pid)
                for pid in TransactionShare.objects.filter(transaction__in=base)
                .order_by()
                .values_list("person_id", flat=True)
                .distinct()
            ),
            SHARED,
        ]
        for p in persons:
            lines[p] = _sums(base, [p], _by_month_and_kind)
    elif by == "term":
        for word in f.words:
            lines[word] = _sums(base.filter(_has_words([word])), f.persons, _by_month_and_kind)
    else:
        raise ValueError(f"Unknown split: {by}")
    return [
        SeriesPoint(key, month.strftime("%Y-%m"), kind, total)
        for key, sums_ in lines.items()
        for (month, kind), total in sorted(sums_.items())
        if total
    ]


@dataclass(slots=True)
class Slice:
    key: str
    label: str
    color: str
    total: Decimal

    def __post_init__(self) -> None:
        self.total = Decimal(self.total).quantize(Decimal("0.01"))  # SQLite sums drop the cents


def category_totals(
    ctx: AccessContext,
    *,
    date_from: date,
    date_to: date,
    kind: str,
    person: str | None = None,
    currency: str = "PLN",
    parent: UUID | None = None,
    f: ChartFilter | None = None,
) -> list[Slice]:
    """Per main category (sub-categories added into it), biggest first — the
    whole amount, or one person's part (``person`` = id) or only unsplit
    household spending (``"shared"``); ``f`` narrows it (its ``persons`` as
    ``person``). With categories picked in ``f``: per picked category, each
    transaction under the most specific one it's in (a picked sub-category
    stays itself). With ``parent``: inside that one main category, per
    sub-category (what was booked straight into the main one keeps its key)."""
    f = f or ChartFilter()
    base = _chart_base(ctx, f, date_from=date_from, date_to=date_to, kind=kind).filter(
        currency=currency
    )
    if parent:
        base = base.filter(Q(category_id=parent) | Q(category__parent_id=parent))
    sums = _sums(
        base,
        f.persons or ([person] if person else None),
        lambda prefix: {"category": F(f"{prefix}category_id")},
    )
    cats = Category.objects.select_related("parent").in_bulk([cid for (cid,) in sums])
    picked = set(f.category_keys or [])
    totals: dict[Category, Decimal] = {}
    for (cid,), total in sums.items():
        cat = cats[cid]
        own = parent or cat.parent is None or cat.key in picked
        shown = cat if own else cat.parent
        totals[shown] = totals.get(shown, Decimal(0)) + total
    out = [Slice(str(c.id), c.name, c.color, total) for c, total in totals.items()]
    return sorted(out, key=lambda s: -s.total)


def person_totals(
    ctx: AccessContext,
    *,
    date_from: date,
    date_to: date,
    kind: str,
    currency: str = "PLN",
    f: ChartFilter | None = None,
) -> list[Slice]:
    """Who the money was for: each person's parts, plus the household's
    unsplit share under ``"shared"`` — only those in ``f.persons`` when set."""
    from apps.people.models import Person  # noqa: PLC0415

    f = f or ChartFilter()
    base = _chart_base(ctx, f, date_from=date_from, date_to=date_to, kind=kind).filter(
        currency=currency
    )
    shares = TransactionShare.objects.filter(transaction__in=base)
    if f.persons:
        shares = shares.filter(person_id__in=_person_ids(f.persons))
    rows = list(shares.values("person_id").annotate(total=Sum("amount")).order_by())
    people = {p.id: p for p in Person.objects.filter(pk__in=[r["person_id"] for r in rows])}
    out = [
        Slice(
            str(r["person_id"]),
            people[r["person_id"]].display_name,
            people[r["person_id"]].color,
            r["total"],
        )
        for r in rows
    ]
    if not f.persons or SHARED in f.persons:
        shared = base.filter(shares__isnull=True).aggregate(s=Sum("amount"))["s"]
        if shared:
            out.append(Slice(SHARED, "", "#868e96", shared))
    return sorted(out, key=lambda s: -s.total)


def _month_start(month_idx: int) -> date:
    """First day of the month for a running index ``year * 12 + month0``."""
    year, month0 = divmod(month_idx, 12)
    return date(year, month0 + 1, 1)


def list_recurring(ctx: AccessContext) -> QuerySet[RecurringRule]:
    return ctx.scope_by_person(
        module="finance",
        qs=RecurringRule.objects.all(),
        person_field="person_id",
    ).select_related("category__parent", "person")


def list_loans(ctx: AccessContext) -> QuerySet[Loan]:
    return ctx.scope_by_person(
        module="finance",
        qs=Loan.objects.filter(archived_at__isnull=True),
        person_field="person_id",
    ).prefetch_related("rate_changes", "overpayments")


# ---- Bookmarks ---------------------------------------------------------


def list_bookmarks(ctx: AccessContext) -> QuerySet[TransactionBookmark]:
    """The caller's own bookmarks — never anyone else's."""
    if not ctx.has("finance", "view") or ctx.user_id is None:
        return TransactionBookmark.objects.none()
    return TransactionBookmark.objects.filter(owner_id=ctx.user_id).select_related("category")


# ---- Debts -------------------------------------------------------------


@dataclass(slots=True)
class DebtBalance:
    counterparty_name: str
    currency: str
    balance: Decimal  # > 0 they owe us, < 0 we owe them
    entries: int  # in the shown period (current only, unless include_settled)
    last_date: date


def _name_key(name: str) -> str:
    """Case/space-insensitive identity: "Kasia", "kasia " and "KASIA" match."""
    return name.strip().lower()


def list_debt_entries(ctx: AccessContext, *, name: str | None = None) -> QuerySet[DebtEntry]:
    if not ctx.has("finance", "view"):
        return DebtEntry.objects.none()
    qs = DebtEntry.objects.all()
    if name:
        qs = qs.filter(counterparty_name__iexact=name.strip())
    return qs


def _grouped_with_settled_flag(entries: list[DebtEntry]) -> dict[tuple, list[DebtEntry]]:
    """Group entries per counterparty+currency, oldest first, and set
    ``e.settled`` on every entry up to the last moment the running balance
    hit zero - that part of the history is closed (settled or repaid)."""
    groups: dict[tuple, list[DebtEntry]] = {}
    for e in sorted(entries, key=lambda e: (e.date, e.created_at)):
        groups.setdefault((_name_key(e.counterparty_name), e.currency), []).append(e)
    for group in groups.values():
        running, last_zero = Decimal("0"), -1
        for i, e in enumerate(group):
            running += e.signed_amount
            if running == 0:
                last_zero = i
        for i, e in enumerate(group):
            e.settled = i <= last_zero
    return groups


def debt_history(
    ctx: AccessContext, *, name: str, include_settled: bool = False
) -> list[DebtEntry]:
    """One counterparty's entries, newest first. Settled history is left out
    unless ``include_settled``; each entry carries a ``settled`` flag."""
    groups = _grouped_with_settled_flag(list(list_debt_entries(ctx, name=name)))
    entries = [e for g in groups.values() for e in g if include_settled or not e.settled]
    return sorted(entries, key=lambda e: (e.date, e.created_at), reverse=True)


def debt_balances(ctx: AccessContext, *, include_settled: bool = False) -> list[DebtBalance]:
    """One row per (counterparty, currency) for everyone ever recorded -
    settled ones included (balance 0) so they stay pickable.
    ``include_settled`` only decides whether ``entries`` counts the closed
    history too. Open balances first (largest first), then settled by name."""
    rows: list[DebtBalance] = []
    for group in _grouped_with_settled_flag(list(list_debt_entries(ctx))).values():
        shown = group if include_settled else [e for e in group if not e.settled]
        rows.append(
            DebtBalance(
                counterparty_name=group[0].counterparty_name.strip(),  # first spelling stays
                currency=group[0].currency,
                balance=sum((e.signed_amount for e in group), Decimal("0")),
                entries=len(shown),
                last_date=group[-1].date,
            )
        )
    return sorted(
        rows, key=lambda r: (r.balance == 0, -abs(r.balance), _name_key(r.counterparty_name))
    )


# -------------------- Import --------------------


def _same(a: str, b: str) -> bool:
    return " ".join(a.split()).lower() == " ".join(b.split()).lower()


def find_category(
    kind: str, main: str, sub: str = "", categories: list[Category] | None = None
) -> Category | None:
    """The category at "main" (a main one) or "main > sub", by name, any case."""
    for c in categories if categories is not None else Category.objects.select_related("parent"):
        if c.kind != kind:
            continue
        if sub and c.parent and _same(c.parent.name, main) and _same(c.name, sub):
            return c
        if not sub and c.parent is None and _same(c.name, main):
            return c
    return None


def import_preview(ctx: AccessContext, raw: bytes, filename: str = "") -> dict[str, Any]:
    """What importing a file would do: its rows (each marked ``duplicate`` when
    a transaction of that day, amount, kind and name is already here), the
    category paths in it with the existing category each matches (none: it
    will be created) and the lines skipped. Raises ``importer.ImportProblem``."""
    from . import importer  # noqa: PLC0415

    ctx.require("finance", "edit")  # only to import
    rows, skipped = importer.parse(raw, filename)
    categories = list(Category.objects.select_related("parent").exclude(kind="transfer"))
    paths = Counter((r.kind, r.category, r.subcategory) for r in rows)
    seen: set[tuple] = set()
    if rows:
        here = list_transactions(
            ctx,
            TransactionFilter(
                date_from=min(r.date for r in rows), date_to=max(r.date for r in rows)
            ),
        ).values_list("date", "amount", "category__kind", "name")
        seen = {(d, a, k, " ".join(n.split()).lower()) for d, a, k, n in here}

    def duplicate(r: Any) -> bool:
        name = " ".join(importer.name_and_note(r.description, r.note)[0].split()).lower()
        return bool(name) and (r.date, r.amount, r.kind, name) in seen

    return {
        "rows": [{**asdict(r), "duplicate": duplicate(r)} for r in rows],
        "categories": [
            {
                "kind": kind,
                "category": main,
                "subcategory": sub,
                "count": n,
                "match_id": getattr(find_category(kind, main, sub, categories), "id", None),
            }
            for (kind, main, sub), n in sorted(paths.items())
        ],
        "skipped": [asdict(s) for s in skipped],
    }
