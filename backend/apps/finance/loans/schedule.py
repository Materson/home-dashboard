"""Pure-Decimal loan amortization — annuity + variable rate + overpayments.

Deterministic, side-effect-free. No Django imports: safe to call from tests,
Celery tasks, the Ninja API and the AI assistant with the same semantics.

Rounding
--------
All money values are quantized to **2 decimal places** with ``ROUND_HALF_EVEN``
(banker's rounding — the standard in European banking). The last installment
absorbs any rounding residual so ``sum(principals) == principal`` exactly.

Model
-----
A loan is defined by:
  * ``principal``             – disbursed amount
  * ``start_date``            – first installment month start (installment
                                 is charged at **end** of each month)
  * ``term_months``           – number of monthly installments
  * ``rate_segments``         – list of ``(effective_from, nominal_rate_p_a)``
                                 covering the term. The first segment's
                                 ``effective_from`` must equal ``start_date``.
                                 For a **fixed-rate** loan pass a single
                                 segment.
  * ``overpayments``          – list of ``Overpayment(date, amount, mode)``
                                 where ``mode`` is ``SHORTEN_TERM`` (installment
                                 unchanged, term shrinks) or
                                 ``REDUCE_INSTALLMENT`` (term unchanged,
                                 installment drops).

The engine produces an ``AmortizationSchedule`` with one row per installment
and summary totals; ``simulate_overpayment`` returns two schedules (current
vs with-the-extra-payment) so the UI can show the saving side-by-side.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_EVEN, Decimal
from enum import Enum
from typing import Iterable

_ONE_DAY = timedelta(days=1)

TWO_DP = Decimal("0.01")
ZERO = Decimal("0")
ONE = Decimal("1")
MONTHS_PER_YEAR = Decimal("12")


class OverpaymentMode(str, Enum):
    SHORTEN_TERM = "shorten_term"
    REDUCE_INSTALLMENT = "reduce_installment"


@dataclass(frozen=True, slots=True)
class RateSegment:
    effective_from: date
    nominal_rate_p_a: Decimal  # e.g. Decimal("0.0725") for 7.25%


@dataclass(frozen=True, slots=True)
class Overpayment:
    date: date
    amount: Decimal
    mode: OverpaymentMode = OverpaymentMode.SHORTEN_TERM


@dataclass(frozen=True, slots=True)
class InstallmentRow:
    index: int
    due_date: date
    opening_balance: Decimal
    installment: Decimal       # principal + interest paid this month (not inc. overpayment)
    principal_part: Decimal
    interest_part: Decimal
    overpayment: Decimal
    closing_balance: Decimal
    nominal_rate_p_a: Decimal


@dataclass(frozen=True, slots=True)
class AmortizationSchedule:
    rows: tuple[InstallmentRow, ...]
    total_installments: Decimal
    total_interest: Decimal
    total_overpayment: Decimal
    months: int


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------


def _q(value: Decimal) -> Decimal:
    """Quantize to 2 dp using banker's rounding."""
    return value.quantize(TWO_DP, rounding=ROUND_HALF_EVEN)


def _due_date(start: date, offset_months: int) -> date:
    """Return the due date of installment ``offset_months + 1`` (0-indexed).

    Installments are due on the **last day** of each calendar month, counted
    from ``start``'s month. (``start = 2026-01-01`` → month 1 due 2026-01-31,
    month 2 due 2026-02-28, …) This keeps rate-segment boundaries and
    overpayment dates naturally aligned."""
    year = start.year + (start.month - 1 + offset_months) // 12
    month = (start.month - 1 + offset_months) % 12 + 1
    if month == 12:
        return date(year + 1, 1, 1) - _ONE_DAY
    return date(year, month + 1, 1) - _ONE_DAY


def _annuity_installment(balance: Decimal, monthly_rate: Decimal, n: int) -> Decimal:
    """Classic annuity formula.

    ``PMT = P * r * (1+r)^n / ((1+r)^n - 1)`` — for ``r == 0`` reduces to ``P/n``.
    """
    if n <= 0:
        return ZERO
    if monthly_rate == ZERO:
        return _q(balance / Decimal(n))
    factor = (ONE + monthly_rate) ** n
    return _q(balance * monthly_rate * factor / (factor - ONE))


def _rate_for_month(due_date: date, segments: tuple[RateSegment, ...]) -> Decimal:
    """Return the nominal annual rate in effect on ``due_date``.

    Segments are sorted by ``effective_from``; the latest segment whose
    ``effective_from <= due_date`` wins."""
    rate = segments[0].nominal_rate_p_a
    for seg in segments:
        if seg.effective_from <= due_date:
            rate = seg.nominal_rate_p_a
        else:
            break
    return rate


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_schedule(
    *,
    principal: Decimal,
    start_date: date,
    term_months: int,
    rate_segments: Iterable[RateSegment],
    overpayments: Iterable[Overpayment] = (),
) -> AmortizationSchedule:
    """Build an amortization schedule for an annuity loan with variable rates
    and optional overpayments."""
    segments = tuple(sorted(rate_segments, key=lambda s: s.effective_from))
    if not segments:
        raise ValueError("at least one rate segment is required")
    if segments[0].effective_from > start_date:
        raise ValueError("first rate segment must cover start_date")

    # Overpayments attribute to the installment whose window they land in:
    # a payment on D is applied with the first due date >= D (within term).
    remaining_ops = sorted(overpayments, key=lambda o: o.date)

    balance = _q(principal)
    rows: list[InstallmentRow] = []

    # Current annuity installment; recomputed whenever the rate changes or
    # a REDUCE_INSTALLMENT overpayment lands. Starts from the opening segment.
    remaining_months = term_months
    current_rate = segments[0].nominal_rate_p_a
    current_installment = _annuity_installment(
        balance, current_rate / MONTHS_PER_YEAR, remaining_months
    )

    for i in range(1, term_months + 1):
        due_date = _due_date(start_date, i - 1)
        prev_rate = current_rate
        current_rate = _rate_for_month(due_date, segments)
        if current_rate != prev_rate:
            current_installment = _annuity_installment(
                balance, current_rate / MONTHS_PER_YEAR, remaining_months
            )

        monthly_rate = current_rate / MONTHS_PER_YEAR
        interest = _q(balance * monthly_rate)

        # Last scheduled installment: pay off the whole balance.
        if remaining_months == 1:
            principal_part = balance
            installment = _q(principal_part + interest)
        else:
            installment = current_installment
            principal_part = _q(installment - interest)
            # safety: never over-pay the principal
            if principal_part > balance:
                principal_part = balance
                installment = _q(principal_part + interest)

        opening = balance
        balance = _q(balance - principal_part)
        remaining_months -= 1

        # Overpayments with date <= this due_date (and not yet applied) are
        # applied *after* the regular installment this month.
        overpay_total = ZERO
        while remaining_ops and remaining_ops[0].date <= due_date and balance > ZERO:
            op = remaining_ops.pop(0)
            take = min(op.amount, balance)
            overpay_total += take
            balance = _q(balance - take)
            if op.mode == OverpaymentMode.REDUCE_INSTALLMENT and balance > ZERO and remaining_months > 0:
                current_installment = _annuity_installment(
                    balance, monthly_rate, remaining_months
                )
            # SHORTEN_TERM: keep installment, the loop will naturally exit
            # early when balance hits zero.

        rows.append(
            InstallmentRow(
                index=i,
                due_date=due_date,
                opening_balance=opening,
                installment=installment,
                principal_part=principal_part,
                interest_part=interest,
                overpayment=overpay_total,
                closing_balance=balance,
                nominal_rate_p_a=current_rate,
            )
        )

        if balance <= ZERO:
            break

    total_installments = _q(sum((r.installment for r in rows), ZERO))
    total_interest = _q(sum((r.interest_part for r in rows), ZERO))
    total_overpayment = _q(sum((r.overpayment for r in rows), ZERO))

    return AmortizationSchedule(
        rows=tuple(rows),
        total_installments=total_installments,
        total_interest=total_interest,
        total_overpayment=total_overpayment,
        months=len(rows),
    )


@dataclass(frozen=True, slots=True)
class OverpaymentComparison:
    base: AmortizationSchedule
    with_overpayment: AmortizationSchedule
    saved_interest: Decimal
    months_saved: int


def simulate_overpayment(
    *,
    principal: Decimal,
    start_date: date,
    term_months: int,
    rate_segments: Iterable[RateSegment],
    existing_overpayments: Iterable[Overpayment] = (),
    extra: Overpayment,
) -> OverpaymentComparison:
    """Compute the baseline schedule and the one with ``extra`` applied,
    returning the interest saving and months saved."""
    rate_segments = tuple(rate_segments)
    existing_overpayments = tuple(existing_overpayments)

    base = build_schedule(
        principal=principal,
        start_date=start_date,
        term_months=term_months,
        rate_segments=rate_segments,
        overpayments=existing_overpayments,
    )
    bumped = build_schedule(
        principal=principal,
        start_date=start_date,
        term_months=term_months,
        rate_segments=rate_segments,
        overpayments=(*existing_overpayments, extra),
    )
    return OverpaymentComparison(
        base=base,
        with_overpayment=bumped,
        saved_interest=_q(base.total_interest - bumped.total_interest),
        months_saved=base.months - bumped.months,
    )


__all__ = [
    "AmortizationSchedule",
    "InstallmentRow",
    "Overpayment",
    "OverpaymentComparison",
    "OverpaymentMode",
    "RateSegment",
    "build_schedule",
    "simulate_overpayment",
]
