"""Finance read queries — every function takes an AccessContext."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from django.db.models import Count, Q, QuerySet, Sum
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
    ).select_related("category", "person")
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
        qs = qs.filter(category__key__in=f.category_keys)
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


MAX_CHART_MONTHS = 36


def monthly_totals(
    ctx: AccessContext, *, until: date | None = None, months: int = 12, person: str | None = None
) -> list[MonthlySum]:
    """Totals grouped by (month, category.kind, currency) for the ``months``
    calendar months ending with ``until``'s month (default: the current one)."""
    if not ctx.has("finance", "view"):
        return []
    months = max(1, min(months, MAX_CHART_MONTHS))
    until = until or timezone.localdate()
    # Work on a running month index (year * 12 + month0) so year boundaries
    # need no special-casing.
    until_idx = until.year * 12 + until.month - 1
    start = _month_start(until_idx - (months - 1))
    end = _month_start(until_idx + 1) - timedelta(days=1)

    base = list_transactions(ctx, TransactionFilter(date_from=start, date_to=end))
    if person and person != SHARED:
        # Only this person's part of each transaction.
        qs = (
            TransactionShare.objects.filter(transaction__in=base, person_id=person)
            .annotate(month=TruncMonth("transaction__date"))
            .values("month", "transaction__category__kind", "transaction__currency")
            .annotate(total=Sum("amount"))
            .order_by("month")
        )
        return [
            MonthlySum(
                year_month=row["month"].strftime("%Y-%m"),
                kind=row["transaction__category__kind"],
                total=row["total"],
                currency=row["transaction__currency"],
            )
            for row in qs
        ]
    if person == SHARED:
        base = base.filter(shares__isnull=True)
    qs = (
        base.annotate(month=TruncMonth("date"))
        .values("month", "category__kind", "currency")
        .annotate(total=Sum("amount"))
        .order_by("month")
    )
    out: list[MonthlySum] = []
    for row in qs:
        out.append(
            MonthlySum(
                year_month=row["month"].strftime("%Y-%m"),
                kind=row["category__kind"],
                total=row["total"],
                currency=row["currency"],
            )
        )
    return out


SHARED = "shared"  # person filter: the household's (not split to anyone)


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
) -> list[Slice]:
    """Per category, biggest first — the whole amount, or one person's part
    (``person`` = id) or only unsplit household spending (``"shared"``)."""
    base = list_transactions(
        ctx, TransactionFilter(date_from=date_from, date_to=date_to, kind=kind)
    ).filter(currency=currency)
    if person and person != SHARED:
        rows = (
            TransactionShare.objects.filter(transaction__in=base, person_id=person)
            .values(
                "transaction__category_id",
                "transaction__category__name",
                "transaction__category__color",
            )
            .annotate(total=Sum("amount"))
        )
        fields = (
            "transaction__category_id",
            "transaction__category__name",
            "transaction__category__color",
        )
    else:
        if person == SHARED:
            base = base.filter(shares__isnull=True)
        rows = base.values("category_id", "category__name", "category__color").annotate(
            total=Sum("amount")
        )
        fields = ("category_id", "category__name", "category__color")
    out = [Slice(str(r[fields[0]]), r[fields[1]], r[fields[2]], r["total"]) for r in rows]
    return sorted(out, key=lambda s: -s.total)


def person_totals(
    ctx: AccessContext, *, date_from: date, date_to: date, kind: str, currency: str = "PLN"
) -> list[Slice]:
    """Who the money was for: each person's parts, plus the household's
    unsplit share under ``"shared"``."""
    from apps.people.models import Person  # noqa: PLC0415

    base = list_transactions(
        ctx, TransactionFilter(date_from=date_from, date_to=date_to, kind=kind)
    ).filter(currency=currency)
    rows = (
        TransactionShare.objects.filter(transaction__in=base)
        .values("person_id")
        .annotate(total=Sum("amount"))
    )
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
    ).select_related("category", "person")


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
