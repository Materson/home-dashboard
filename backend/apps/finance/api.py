from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from django.http import HttpRequest
from django.shortcuts import get_object_or_404
from ninja import Query, Router, Schema

from apps.access.context import get_ctx

from . import selectors, services
from .loans import schedule as loan_schedule
from .models import Category, Loan, RateChange, RecurringRule, Transaction

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


class TransactionIn(Schema):
    date: date
    amount: Decimal
    currency: str = "PLN"
    category_id: UUID
    person_id: UUID | None = None
    name: str
    notes: str = ""


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


@router.post("/transactions", response=TransactionOut)
def create_transaction(request: HttpRequest, payload: TransactionIn) -> Transaction:
    get_ctx(request).require("finance", "edit")
    return Transaction.objects.create(**payload.dict())


@router.put("/transactions/{tx_id}", response=TransactionOut)
def update_transaction(request: HttpRequest, tx_id: UUID, payload: TransactionEdit) -> Transaction:
    ctx = get_ctx(request)
    ctx.require("finance", "edit")
    tx = get_object_or_404(Transaction, pk=tx_id)
    data = payload.dict(exclude={"update_future"})
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
        loan_schedule.Overpayment(
            op.date, op.amount, loan_schedule.OverpaymentMode(op.mode)
        )
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
