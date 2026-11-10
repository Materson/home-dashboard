"""Finance read queries — every function takes an AccessContext."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from django.db.models import Q, QuerySet, Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone

from .models import Category, Loan, RecurringRule, Transaction

if TYPE_CHECKING:
    from apps.access.context import AccessContext


@dataclass(slots=True)
class TransactionFilter:
    q: str | None = None               # name/notes text
    date_from: date | None = None
    date_to: date | None = None
    amount_min: Decimal | None = None
    amount_max: Decimal | None = None
    category_keys: list[str] | None = None
    person_ids: list[UUID] | None = None
    kind: str | None = None            # 'income' | 'expense' | 'transfer'


def list_categories(ctx: AccessContext) -> QuerySet[Category]:
    if not ctx.has("finance", "view"):
        return Category.objects.none()
    return Category.objects.all().select_related("parent")


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
        qs = qs.filter(person_id__in=f.person_ids)
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
    ctx: AccessContext, *, until: date | None = None, months: int = 12
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

    qs = list_transactions(ctx, TransactionFilter(date_from=start, date_to=end))
    qs = (
        qs.annotate(month=TruncMonth("date"))
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
    return (
        ctx.scope_by_person(
            module="finance",
            qs=Loan.objects.filter(archived_at__isnull=True),
            person_field="person_id",
        )
        .prefetch_related("rate_changes", "overpayments")
    )
