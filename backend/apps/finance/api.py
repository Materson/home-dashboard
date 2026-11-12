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
    used: int  # transactions in it


class CategoryIn(Schema):
    name: str
    kind: Literal["expense", "income"] = "expense"
    color: str = "#868e96"


class CategoryEdit(Schema):
    name: str
    color: str = ""


class ShareSchema(Schema):
    person_id: UUID
    amount: Decimal


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
    shares: list[ShareSchema]

    @staticmethod
    def resolve_shares(obj) -> list[dict]:
        return [{"person_id": s.person_id, "amount": s.amount} for s in obj.shares.all()]


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
    # Who it was for; empty = the household. Must add up to the amount.
    shares: list[ShareSchema] = []
    # Repeat from this date (new transactions only).
    repeat: Literal["", "weekly", "monthly", "quarterly", "yearly"] = ""
    repeat_until: date | None = None


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
    shares: list[ShareSchema]
    notes: str


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
    shares: list[ShareSchema] = []


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


def _with_usage(cat: Category) -> Category:
    cat.used = cat.transactions.count()
    return cat


@router.post("/categories", response={200: CategoryOut, 422: dict})
def create_category(request: HttpRequest, payload: CategoryIn):
    try:
        return _with_usage(services.create_category(get_ctx(request), **payload.dict()))
    except ValueError as exc:
        return 422, {"detail": str(exc)}


@router.put("/categories/{category_id}", response={200: CategoryOut, 422: dict})
def update_category(request: HttpRequest, category_id: UUID, payload: CategoryEdit):
    get_object_or_404(Category, pk=category_id)
    try:
        return _with_usage(
            services.update_category(get_ctx(request), category_id, **payload.dict())
        )
    except ValueError as exc:
        return 422, {"detail": str(exc)}


class MergeIn(Schema):
    into: UUID


@router.post("/categories/{category_id}/merge", response={200: dict, 422: dict})
def merge_category(request: HttpRequest, category_id: UUID, payload: MergeIn):
    """Move everything into another category of the same kind, then remove this one."""
    get_object_or_404(Category, pk=category_id)
    get_object_or_404(Category, pk=payload.into)
    try:
        return {"moved": services.merge_category(get_ctx(request), category_id, payload.into)}
    except ValueError as exc:
        return 422, {"detail": str(exc)}


@router.delete("/categories/{category_id}", response={200: dict, 422: dict})
def delete_category(request: HttpRequest, category_id: UUID):
    get_object_or_404(Category, pk=category_id)
    try:
        services.delete_category(get_ctx(request), category_id)
    except ValueError as exc:
        return 422, {"detail": str(exc)}
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
    data = payload.dict()
    shares = data.pop("shares")
    repeat, until = data.pop("repeat"), data.pop("repeat_until")
    try:
        return services.create_transaction(
            get_ctx(request), data, shares=shares, repeat=repeat, repeat_until=until
        )
    except ValueError as exc:
        return 422, {"detail": str(exc)}


@router.put("/transactions/{tx_id}", response={200: TransactionOut, 422: dict})
def update_transaction(request: HttpRequest, tx_id: UUID, payload: TransactionEdit):
    data = payload.dict(exclude={"update_future", "repeat", "repeat_until"})
    shares = data.pop("shares")
    get_object_or_404(Transaction, pk=tx_id)
    try:
        return services.update_transaction(
            get_ctx(request), tx_id, data, shares=shares, update_future=payload.update_future
        )
    except ValueError as exc:
        return 422, {"detail": str(exc)}


@router.delete("/transactions/{tx_id}")
def delete_transaction(request: HttpRequest, tx_id: UUID) -> dict[str, bool]:
    get_ctx(request).require("finance", "edit")
    get_object_or_404(Transaction, pk=tx_id).delete()
    return {"deleted": True}


@router.get("/monthly-totals", response=list[MonthlySumOut])
def monthly_totals(
    request: HttpRequest, until: date | None = None, months: int = 12, person: str | None = None
) -> list[selectors.MonthlySum]:
    """Chart data: the ``months`` months ending with ``until``'s month;
    ``person`` = one person's parts, or "shared" for unsplit spending."""
    return selectors.monthly_totals(get_ctx(request), until=until, months=months, person=person)


class SliceOut(Schema):
    key: str
    label: str
    color: str
    total: Decimal


@router.get("/category-totals", response=list[SliceOut])
def category_totals(  # noqa: PLR0917 — query parameters
    request: HttpRequest,
    date_from: date,
    date_to: date,
    kind: Literal["income", "expense"] = "expense",
    person: str | None = None,
    currency: str = "PLN",
) -> list[selectors.Slice]:
    """Pie chart data: totals per category, biggest first."""
    return selectors.category_totals(
        get_ctx(request),
        date_from=date_from,
        date_to=date_to,
        kind=kind,
        person=person,
        currency=currency,
    )


@router.get("/person-totals", response=list[SliceOut])
def person_totals(
    request: HttpRequest,
    date_from: date,
    date_to: date,
    kind: Literal["income", "expense"] = "expense",
    currency: str = "PLN",
) -> list[selectors.Slice]:
    """Pie chart data: who the money was for ("shared" = the household)."""
    return selectors.person_totals(
        get_ctx(request), date_from=date_from, date_to=date_to, kind=kind, currency=currency
    )


# -------------------- Recurring --------------------


@router.get("/recurring", response=list[RecurringRuleOut])
def list_recurring(request: HttpRequest) -> list[RecurringRule]:
    return list(selectors.list_recurring(get_ctx(request)))


@router.post("/recurring", response={200: RecurringRuleOut, 422: dict})
def create_recurring(request: HttpRequest, payload: RecurringRuleIn):
    get_ctx(request).require("finance", "edit")
    data = payload.dict()
    try:
        pairs = services.normalize_shares(data["amount"], data.pop("shares"), data.get("person_id"))
    except ValueError as exc:
        return 422, {"detail": str(exc)}
    data["person_id"] = pairs[0][0] if len(pairs) == 1 else None
    return RecurringRule.objects.create(**data, shares=services.shares_json(pairs))


class RecurringEditIn(Schema):
    name: str
    amount: Decimal
    currency: str = "PLN"
    category_id: UUID
    notes: str = ""
    end_date: date | None = None
    shares: list[ShareSchema] = []
    repeat: Literal["", "weekly", "monthly", "quarterly", "yearly"] = ""


@router.put("/recurring/{rule_id}", response={200: RecurringRuleOut, 422: dict})
def update_recurring(request: HttpRequest, rule_id: UUID, payload: RecurringEditIn):
    """Change what the next occurrences will be (recorded ones stay)."""
    get_object_or_404(RecurringRule, pk=rule_id)
    data = payload.dict()
    shares, repeat = data.pop("shares"), data.pop("repeat")
    try:
        return services.update_recurring(
            get_ctx(request), rule_id, data, shares=shares, repeat=repeat
        )
    except ValueError as exc:
        return 422, {"detail": str(exc)}


@router.post("/recurring/{rule_id}/stop", response=RecurringRuleOut)
def stop_recurring(request: HttpRequest, rule_id: UUID) -> RecurringRule:
    """Stop repeating; what was already recorded stays."""
    return services.stop_recurring(get_ctx(request), rule_id)


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
    shares: list[ShareSchema]


class BookmarkIn(Schema):
    label: str
    name: str
    amount: Decimal
    currency: str = "PLN"
    category_id: UUID
    person_id: UUID | None = None
    notes: str = ""
    sort_order: int = 0
    shares: list[ShareSchema] = []


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
