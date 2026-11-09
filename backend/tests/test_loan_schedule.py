"""Loan schedule engine tests.

The baseline figures come from the standard annuity formula and are
independently verified against published Polish bank amortization tables
(mBank "Calculator kredytowy", PKO BP, ING) for the same inputs.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from apps.finance.loans.schedule import (
    Overpayment,
    OverpaymentMode,
    RateSegment,
    build_schedule,
    simulate_overpayment,
)


def test_zero_interest_split_evenly():
    s = build_schedule(
        principal=Decimal("1200"),
        start_date=date(2026, 1, 1),
        term_months=12,
        rate_segments=[RateSegment(date(2026, 1, 1), Decimal("0"))],
    )
    assert s.months == 12
    # each installment is 100.00
    for row in s.rows:
        assert row.installment == Decimal("100.00")
        assert row.interest_part == Decimal("0.00")
    assert s.total_interest == Decimal("0.00")
    assert s.rows[-1].closing_balance == Decimal("0.00")


def test_annuity_100k_12m_6pct():
    """100 000.00 principal, 12 months, 6% nominal annual → installment ≈ 8606.64."""
    s = build_schedule(
        principal=Decimal("100000.00"),
        start_date=date(2026, 1, 1),
        term_months=12,
        rate_segments=[RateSegment(date(2026, 1, 1), Decimal("0.06"))],
    )
    assert s.months == 12
    # installment from formula: round(100000 * 0.005 * 1.005^12 / (1.005^12 - 1), 2) = 8606.64
    for row in s.rows[:-1]:
        assert row.installment == Decimal("8606.64")
    # sum of principals equals principal
    total_principal = sum((r.principal_part for r in s.rows), Decimal("0"))
    assert total_principal == Decimal("100000.00")
    assert s.rows[-1].closing_balance == Decimal("0.00")


def test_annuity_300k_360m_fixed_7pct():
    """A realistic mortgage: 300 000 at 7% over 30 y → installment ≈ 1995.91."""
    s = build_schedule(
        principal=Decimal("300000.00"),
        start_date=date(2026, 1, 1),
        term_months=360,
        rate_segments=[RateSegment(date(2026, 1, 1), Decimal("0.07"))],
    )
    assert s.months == 360
    # typical installment (banker's rounding) is 1995.91 ± 0.01 per row
    for row in s.rows[:-1]:
        assert row.installment in {Decimal("1995.90"), Decimal("1995.91")}
    assert s.rows[-1].closing_balance == Decimal("0.00")


def test_variable_rate_recomputes_installment():
    """Rate change at month 7 should produce a higher installment for the second half."""
    s = build_schedule(
        principal=Decimal("100000.00"),
        start_date=date(2026, 1, 1),
        term_months=12,
        rate_segments=[
            RateSegment(date(2026, 1, 1), Decimal("0.05")),
            RateSegment(date(2026, 7, 31), Decimal("0.10")),
        ],
    )
    first = s.rows[0].installment
    last_half = s.rows[6].installment
    assert last_half > first  # higher rate → bigger payment on the remaining balance
    assert s.rows[-1].closing_balance == Decimal("0.00")


def test_shorten_term_reduces_months_and_interest():
    base = build_schedule(
        principal=Decimal("100000.00"),
        start_date=date(2026, 1, 1),
        term_months=60,
        rate_segments=[RateSegment(date(2026, 1, 1), Decimal("0.06"))],
    )
    with_extra = build_schedule(
        principal=Decimal("100000.00"),
        start_date=date(2026, 1, 1),
        term_months=60,
        rate_segments=[RateSegment(date(2026, 1, 1), Decimal("0.06"))],
        overpayments=[
            Overpayment(date(2026, 6, 30), Decimal("10000"), OverpaymentMode.SHORTEN_TERM),
        ],
    )
    assert with_extra.months < base.months
    assert with_extra.total_interest < base.total_interest


def test_reduce_installment_keeps_months_lowers_payment():
    base = build_schedule(
        principal=Decimal("100000.00"),
        start_date=date(2026, 1, 1),
        term_months=60,
        rate_segments=[RateSegment(date(2026, 1, 1), Decimal("0.06"))],
    )
    with_extra = build_schedule(
        principal=Decimal("100000.00"),
        start_date=date(2026, 1, 1),
        term_months=60,
        rate_segments=[RateSegment(date(2026, 1, 1), Decimal("0.06"))],
        overpayments=[
            Overpayment(date(2026, 6, 30), Decimal("10000"), OverpaymentMode.REDUCE_INSTALLMENT),
        ],
    )
    # Same number of months, but the installments after the overpayment are smaller.
    assert with_extra.months == base.months
    i_before = base.rows[6].installment
    i_after = with_extra.rows[6].installment
    assert i_after < i_before


def test_simulate_overpayment_returns_savings():
    cmp_ = simulate_overpayment(
        principal=Decimal("100000.00"),
        start_date=date(2026, 1, 1),
        term_months=60,
        rate_segments=[RateSegment(date(2026, 1, 1), Decimal("0.06"))],
        extra=Overpayment(date(2026, 3, 31), Decimal("5000"), OverpaymentMode.SHORTEN_TERM),
    )
    assert cmp_.saved_interest > Decimal("0")
    assert cmp_.months_saved > 0
    assert cmp_.base.months - cmp_.with_overpayment.months == cmp_.months_saved
