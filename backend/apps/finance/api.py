from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID

from django.http import HttpRequest
from django.shortcuts import get_object_or_404
from ninja import Query, Router, Schema

from apps.access.context import get_ctx

from . import selectors, services
from .loans import schedule as loan_schedule
from .models import (
    Category,
    DebtEntry,
    Loan,
    RateChange,
    RecurringRule,
    Transaction,
    TransactionBookmark,
)

router = Router()

# -------------------- Schemas --------------------


class CategoryOut(Schema):
    id: UUID
    key: str
    name: str
    kind: str
    parent_id: UUID | None
    color: str
    is_system: bool


class CategoryIn(Schema):
    key: str
    name: str
    kind: str = "expense"
    parent_id: UUID | None = None
    color: str = "#868e96"


class TransactionOut(Schema):
    id: UUID
    date: date
    amount: Decimal
    currency: str
    name: str
    notes: str
    category_id: UUID
    person_id: UUID | None
    recurring_rule_id: UUID | None
    source_id: UUID | None
    related_kind: str
    related_id: UUID | None


class TransactionIn(Schema):
    date: date
    amount: Decimal
    currency: str = "PLN"
    category_id: UUID
    person_id: UUID | None = None
    name: str
    notes: str = ""
    # Optional "what it was for", e.g. related_kind="health.cabinetitem".
    related_kind: str = ""
    related_id: UUID | None = None


class TransactionEdit(TransactionIn):
    update_future: bool = False  # when the tx came from a recurring rule


class TransactionSearch(Schema):
    q: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    amount_min: Decimal | None = None
    amount_max: Decimal | None = None
    category_keys: list[str] | None = None
    person_ids: list[UUID] | None = None
    kind: str | None = None
    limit: int = 100
    offset: int = 0


class MonthlySumOut(Schema):
    year_month: str
    kind: str
    total: Decimal
    currency: str


class RecurringRuleOut(Schema):
    id: UUID
    name: str
    amount: Decimal
    currency: str
    category_id: UUID
    person_id: UUID | None
    rrule: str
    start_date: date
    end_date: date | None
    next_run_at: date
    is_active: bool


class RecurringRuleIn(Schema):
    name: str
    amount: Decimal
    currency: str = "PLN"
    category_id: UUID
    person_id: UUID | None = None
    rrule: str
    start_date: date
    end_date: date | None = None
    next_run_at: date
    is_active: bool = True


class LoanOut(Schema):
    id: UUID
    name: str
    person_id: UUID | None
    kind: str
    principal: Decimal
    currency: str
    start_date: date
    term_months: int
    base_rate: Decimal


class LoanIn(Schema):
    name: str
    person_id: UUID | None = None
    kind: str = "annuity"
    principal: Decimal
    currency: str = "PLN"
    start_date: date
    term_months: int
    base_rate: Decimal


class RateChangeIn(Schema):
    effective_from: date
    nominal_rate_p_a: Decimal


class OverpaymentIn(Schema):
    date: date
    amount: Decimal
    mode: str = "shorten_term"  # or "reduce_installment"


class InstallmentOut(Schema):
    index: int
    due_date: date
    opening_balance: Decimal
    installment: Decimal
    principal_part: Decimal
    interest_part: Decimal
    overpayment: Decimal
    closing_balance: Decimal
    nominal_rate_p_a: Decimal


class ScheduleOut(Schema):
    rows: list[InstallmentOut]
    total_installments: Decimal
    total_interest: Decimal
    total_overpayment: Decimal
    months: int


class OverpaymentComparisonOut(Schema):
    base: ScheduleOut
    with_overpayment: ScheduleOut
    saved_interest: Decimal
    months_saved: int


# -------------------- Categories --------------------


@router.get("/categories", response=list[CategoryOut])
def list_categories(request: HttpRequest) -> list[Category]:
    return list(selectors.list_categories(get_ctx(request)))


@router.post("/categories", response=CategoryOut)
def create_category(request: HttpRequest, payload: CategoryIn) -> Category:
    get_ctx(request).require("finance", "manage")
    return Category.objects.create(**payload.dict())


@router.delete("/categories/{category_id}")
def delete_category(request: HttpRequest, category_id: UUID) -> dict[str, bool]:
    get_ctx(request).require("finance", "manage")
    cat = get_object_or_404(Category, pk=category_id, is_system=False)
    cat.delete()
    return {"deleted": True}


# -------------------- Transactions --------------------


@router.get("/transactions", response=list[TransactionOut])
def list_transactions(request: HttpRequest, filters: Query[TransactionSearch]) -> list[Transaction]:
    f = selectors.TransactionFilter(
        q=filters.q,
        date_from=filters.date_from,
        date_to=filters.date_to,
        amount_min=filters.amount_min,
        amount_max=filters.amount_max,
        category_keys=filters.category_keys,
        person_ids=filters.person_ids,
        kind=filters.kind,
    )
    qs = selectors.list_transactions(get_ctx(request), f)
    return list(qs[filters.offset : filters.offset + filters.limit])


@router.post("/transactions", response={200: TransactionOut, 422: dict})
def create_transaction(request: HttpRequest, payload: TransactionIn):
    ctx = get_ctx(request)
    ctx.require("finance", "edit")
    data = payload.dict()
    try:
        services.check_related(data["related_kind"], data["related_id"])
    except ValueError as exc:
        return 422, {"detail": str(exc)}
    return Transaction.objects.create(**data)


@router.put("/transactions/{tx_id}", response={200: TransactionOut, 422: dict})
def update_transaction(request: HttpRequest, tx_id: UUID, payload: TransactionEdit):
    ctx = get_ctx(request)
    ctx.require("finance", "edit")
    tx = get_object_or_404(Transaction, pk=tx_id)
    data = payload.dict(exclude={"update_future"})
    try:
        services.check_related(data["related_kind"], data["related_id"])
    except ValueError as exc:
        return 422, {"detail": str(exc)}
    for k, v in data.items():
        setattr(tx, k, v)
    tx.save()
    services.propagate_edit_to_rule(ctx, tx, update_future=payload.update_future)
    return tx


@router.delete("/transactions/{tx_id}")
def delete_transaction(request: HttpRequest, tx_id: UUID) -> dict[str, bool]:
    get_ctx(request).require("finance", "edit")
    get_object_or_404(Transaction, pk=tx_id).delete()
    return {"deleted": True}


@router.get("/monthly-totals", response=list[MonthlySumOut])
def monthly_totals(
    request: HttpRequest, until: date | None = None, months: int = 12
) -> list[selectors.MonthlySum]:
    """Chart data: the ``months`` months ending with ``until``'s month."""
    return selectors.monthly_totals(get_ctx(request), until=until, months=months)


# -------------------- Recurring --------------------


@router.get("/recurring", response=list[RecurringRuleOut])
def list_recurring(request: HttpRequest) -> list[RecurringRule]:
    return list(selectors.list_recurring(get_ctx(request)))


@router.post("/recurring", response=RecurringRuleOut)
def create_recurring(request: HttpRequest, payload: RecurringRuleIn) -> RecurringRule:
    get_ctx(request).require("finance", "edit")
    return RecurringRule.objects.create(**payload.dict())


@router.delete("/recurring/{rule_id}")
def delete_recurring(request: HttpRequest, rule_id: UUID) -> dict[str, bool]:
    get_ctx(request).require("finance", "edit")
    get_object_or_404(RecurringRule, pk=rule_id).delete()
    return {"deleted": True}


# -------------------- Loans --------------------


@router.get("/loans", response=list[LoanOut])
def list_loans(request: HttpRequest) -> list[Loan]:
    return list(selectors.list_loans(get_ctx(request)))


@router.post("/loans", response=LoanOut)
def create_loan(request: HttpRequest, payload: LoanIn) -> Loan:
    ctx = get_ctx(request)
    ctx.require("finance", "edit")
    loan = Loan.objects.create(**payload.dict())
    # Seed the first rate segment so the schedule is immediately computable.
    RateChange.objects.create(
        loan=loan, effective_from=loan.start_date, nominal_rate_p_a=loan.base_rate
    )
    return loan


@router.get("/loans/{loan_id}/schedule", response=ScheduleOut)
def loan_schedule_now(request: HttpRequest, loan_id: UUID) -> ScheduleOut:
    ctx = get_ctx(request)
    ctx.require("finance", "view")
    loan = get_object_or_404(Loan, pk=loan_id)
    return _build_schedule_response(loan)


class SimulateIn(Schema):
    extra: OverpaymentIn


@router.post("/loans/{loan_id}/simulate", response=OverpaymentComparisonOut)
def simulate_loan(
    request: HttpRequest, loan_id: UUID, payload: SimulateIn
) -> OverpaymentComparisonOut:
    ctx = get_ctx(request)
    ctx.require("finance", "view")
    loan = get_object_or_404(Loan, pk=loan_id)

    segments = _loan_rate_segments(loan)
    existing = [
        loan_schedule.Overpayment(op.date, op.amount, loan_schedule.OverpaymentMode(op.mode))
        for op in loan.overpayments.all()
    ]
    extra = loan_schedule.Overpayment(
        payload.extra.date,
        payload.extra.amount,
        loan_schedule.OverpaymentMode(payload.extra.mode),
    )
    cmp_ = loan_schedule.simulate_overpayment(
        principal=loan.principal,
        start_date=loan.start_date,
        term_months=loan.term_months,
        rate_segments=segments,
        existing_overpayments=existing,
        extra=extra,
    )
    return OverpaymentComparisonOut(
        base=_schedule_to_out(cmp_.base),
        with_overpayment=_schedule_to_out(cmp_.with_overpayment),
        saved_interest=cmp_.saved_interest,
        months_saved=cmp_.months_saved,
    )


# -------------------- helpers --------------------


def _loan_rate_segments(loan: Loan) -> list[loan_schedule.RateSegment]:
    rows = list(loan.rate_changes.all().order_by("effective_from"))
    if not rows:
        return [loan_schedule.RateSegment(loan.start_date, loan.base_rate)]
    return [loan_schedule.RateSegment(r.effective_from, r.nominal_rate_p_a) for r in rows]


def _build_schedule_response(loan: Loan) -> ScheduleOut:
    sched = loan_schedule.build_schedule(
        principal=loan.principal,
        start_date=loan.start_date,
        term_months=loan.term_months,
        rate_segments=_loan_rate_segments(loan),
        overpayments=[
            loan_schedule.Overpayment(op.date, op.amount, loan_schedule.OverpaymentMode(op.mode))
            for op in loan.overpayments.all()
        ],
    )
    return _schedule_to_out(sched)


def _schedule_to_out(s: loan_schedule.AmortizationSchedule) -> ScheduleOut:
    return ScheduleOut(
        rows=[
            InstallmentOut(
                index=r.index,
                due_date=r.due_date,
                opening_balance=r.opening_balance,
                installment=r.installment,
                principal_part=r.principal_part,
                interest_part=r.interest_part,
                overpayment=r.overpayment,
                closing_balance=r.closing_balance,
                nominal_rate_p_a=r.nominal_rate_p_a,
            )
            for r in s.rows
        ],
        total_installments=s.total_installments,
        total_interest=s.total_interest,
        total_overpayment=s.total_overpayment,
        months=s.months,
    )


# -------------------- Bookmarks --------------------


class BookmarkOut(Schema):
    id: UUID
    label: str
    name: str
    amount: Decimal
    currency: str
    category_id: UUID
    person_id: UUID | None
    notes: str
    sort_order: int


class BookmarkIn(Schema):
    label: str
    name: str
    amount: Decimal
    currency: str = "PLN"
    category_id: UUID
    person_id: UUID | None = None
    notes: str = ""
    sort_order: int = 0


@router.get("/bookmarks", response=list[BookmarkOut])
def list_bookmarks(request: HttpRequest) -> list[TransactionBookmark]:
    return list(selectors.list_bookmarks(get_ctx(request)))


@router.post("/bookmarks", response=BookmarkOut)
def create_bookmark(request: HttpRequest, payload: BookmarkIn) -> TransactionBookmark:
    return services.create_bookmark(get_ctx(request), **payload.dict())


@router.put("/bookmarks/{bookmark_id}", response=BookmarkOut)
def update_bookmark(
    request: HttpRequest, bookmark_id: UUID, payload: BookmarkIn
) -> TransactionBookmark:
    return services.update_bookmark(get_ctx(request), bookmark_id, **payload.dict())


@router.delete("/bookmarks/{bookmark_id}")
def delete_bookmark(request: HttpRequest, bookmark_id: UUID) -> dict[str, bool]:
    services.delete_bookmark(get_ctx(request), bookmark_id)
    return {"deleted": True}


# -------------------- Debts --------------------


class DebtEntryOut(Schema):
    id: UUID
    counterparty_name: str
    direction: str
    amount: Decimal
    currency: str
    date: date
    due_date: date | None
    notes: str
    settled: bool = False  # part of a closed (balance reached zero) period


class DebtEntryIn(Schema):
    counterparty_name: str
    direction: Literal["gave", "received"]
    amount: Decimal
    currency: str = "PLN"
    date: date
    due_date: date | None = None
    notes: str = ""


class DebtBalanceOut(Schema):
    counterparty_name: str
    currency: str
    balance: Decimal
    entries: int
    last_date: date


class DebtEntriesQuery(Schema):
    name: str
    include_settled: bool = False


class SettleIn(Schema):
    name: str
    currency: str = "PLN"
    date: date


@router.get("/debts/balances", response=list[DebtBalanceOut])
def debt_balances(
    request: HttpRequest, include_settled: bool = False
) -> list[selectors.DebtBalance]:
    return selectors.debt_balances(get_ctx(request), include_settled=include_settled)


@router.get("/debts/entries", response=list[DebtEntryOut])
def list_debt_entries(request: HttpRequest, q: Query[DebtEntriesQuery]) -> list[DebtEntry]:
    return selectors.debt_history(get_ctx(request), name=q.name, include_settled=q.include_settled)


@router.post("/debts/entries", response={200: DebtEntryOut, 422: dict})
def add_debt_entry(request: HttpRequest, payload: DebtEntryIn):
    try:
        return services.add_debt_entry(get_ctx(request), **payload.dict())
    except ValueError as exc:
        return 422, {"detail": str(exc)}


@router.delete("/debts/entries/{entry_id}")
def delete_debt_entry(request: HttpRequest, entry_id: UUID) -> dict[str, bool]:
    services.delete_debt_entry(get_ctx(request), entry_id)
    return {"deleted": True}


@router.delete("/debts/counterparty")
def delete_counterparty(request: HttpRequest, name: str) -> dict[str, int]:
    """Remove a person and their whole history from the debts list."""
    return {"deleted": services.delete_counterparty(get_ctx(request), name)}


@router.post("/debts/settle", response={200: DebtEntryOut, 204: None})
def settle_debt(request: HttpRequest, payload: SettleIn):
    entry = services.settle_debt(
        get_ctx(request), name=payload.name, currency=payload.currency, on=payload.date
    )
    return entry if entry is not None else (204, None)
