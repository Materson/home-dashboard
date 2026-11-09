"""Finance read queries — every function takes an AccessContext."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from django.db.models import Q, QuerySet, Sum

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


def list_categories(ctx: "AccessContext") -> QuerySet[Category]:
    if not ctx.has("finance", "view"):
        return Category.objects.none()
    return Category.objects.all().select_related("parent")


def list_transactions(ctx: "AccessContext", f: TransactionFilter | None = None) -> QuerySet[Transaction]:
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


def monthly_totals(ctx: "AccessContext", months: int = 12) -> list[MonthlySum]:
    """Totals grouped by (month, category.kind, currency) — fuel for the chart tiles."""
    from django.db.models.functions import TruncMonth

    if not ctx.has("finance", "view"):
        return []
    qs = list_transactions(ctx)
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


def list_recurring(ctx: "AccessContext") -> QuerySet[RecurringRule]:
    return ctx.scope_by_person(
        module="finance",
        qs=RecurringRule.objects.all(),
        person_field="person_id",
    ).select_related("category", "person")


def list_loans(ctx: "AccessContext") -> QuerySet[Loan]:
    return (
        ctx.scope_by_person(
            module="finance", qs=Loan.objects.filter(archived_at__isnull=True), person_field="person_id"
        )
        .prefetch_related("rate_changes", "overpayments")
    )
