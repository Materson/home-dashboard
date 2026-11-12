"""Polish retail treasury bonds — value of one bond (nominal 100 zł) on a
day. Pure Decimal maths; the rules are those on obligacjeskarbowe.pl:

- EDO (10 y), ROS (6 y), ROD (12 y): year 1 fixed; later years
  ``margin + inflation``; interest capitalised yearly
  (100 * prod(1 + r_i)).
- COI (4 y): like EDO but interest is *paid out* every year — the bond
  itself is worth 100 + this year's accrued interest.
- TOS (3 y): fixed rate, capitalised yearly.
- OTS (3 months): fixed rate, paid at the end.
- ROR (1 y) / DOR (2 y): monthly coupons at the NBP reference rate
  (+ margin); later months use an entered rate (``overrides``) or the
  last known one.
- "Inflation" is the GUS CPI y/y *announced in the month before* the
  period starts — i.e. the figure for two months before the period's first
  month. Negative inflation counts as 0.
- Within a period interest accrues by days elapsed / days in the period.
  Values are before the 19% tax and any early-redemption fee; the official
  rounding isn't published, so cents may differ slightly from the bank's.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from dateutil.relativedelta import relativedelta

NOMINAL = Decimal(100)
ZERO = Decimal(0)


@dataclass(frozen=True)
class BondType:
    months: int  # whole term
    period_months: int  # one interest period
    style: str  # "cap" capitalised, "coupon" paid out, "simple" paid at the end
    indexed: bool  # later periods follow inflation
    floating: bool = False  # later periods follow the NBP reference rate


TYPES: dict[str, BondType] = {
    "OTS": BondType(3, 3, "simple", indexed=False),
    "ROR": BondType(12, 1, "coupon", indexed=False, floating=True),
    "DOR": BondType(24, 1, "coupon", indexed=False, floating=True),
    "TOS": BondType(36, 12, "cap", indexed=False),
    "COI": BondType(48, 12, "coupon", indexed=True),
    "EDO": BondType(120, 12, "cap", indexed=True),
    "ROS": BondType(72, 12, "cap", indexed=True),
    "ROD": BondType(144, 12, "cap", indexed=True),
}


@dataclass(frozen=True)
class Period:
    number: int  # from 1
    start: date
    end: date  # exclusive
    rate: Decimal | None  # % a year; None = not known yet
    source: str  # "first" | "inflation" | "fixed" | "override" | "carried" | "unknown"
    inflation: Decimal | None = None  # the CPI y/y used (e.g. 104.1)


def cpi_month_for(period_start: date) -> tuple[int, int]:
    """The CPI month used for a period starting on ``period_start``: GUS
    announces month M's figure in M+1, and the rule takes the figure
    announced in the month before the period starts → M = start - 2."""
    ref = period_start - relativedelta(months=2)
    return ref.year, ref.month


def periods(  # noqa: PLR0917 — the bond's terms
    bond_type: str,
    bought_on: date,
    first_rate: Decimal,
    margin: Decimal | None,
    cpi: dict[tuple[int, int], Decimal],
    overrides: dict[str, str] | None = None,
) -> list[Period]:
    t = TYPES[bond_type]
    overrides = overrides or {}
    out: list[Period] = []
    last_rate = first_rate
    count = t.months // t.period_months
    for i in range(count):
        start = bought_on + relativedelta(months=i * t.period_months)
        end = bought_on + relativedelta(months=(i + 1) * t.period_months)
        number = i + 1
        inflation = None
        if str(number) in overrides:
            rate, source = Decimal(str(overrides[str(number)])), "override"
        elif i == 0:
            rate, source = first_rate, "first"
        elif t.indexed:
            inflation = cpi.get(cpi_month_for(start))
            if inflation is None:
                rate, source = None, "unknown"
            else:
                rate, source = (margin or ZERO) + max(inflation - NOMINAL, ZERO), "inflation"
        elif t.floating:
            rate, source = last_rate, "carried"
        else:
            rate, source = first_rate, "fixed"
        if rate is not None:
            last_rate = rate
        out.append(Period(number, start, end, rate, source, inflation))
    return out


def _fraction(start: date, end: date, on: date) -> Decimal:
    return Decimal((on - start).days) / Decimal((end - start).days)


def value_on(  # noqa: PLR0917 — the bond's terms
    bond_type: str,
    bought_on: date,
    first_rate: Decimal,
    margin: Decimal | None,
    cpi: dict[tuple[int, int], Decimal],
    on: date,
    overrides: dict[str, str] | None = None,
) -> tuple[Decimal, bool]:
    """Value of one bond on ``on`` (before tax/fees), and whether it's an
    estimate (a period's rate isn't known yet — the last known rate is used)."""
    if on <= bought_on:
        return NOMINAL, False
    t = TYPES[bond_type]
    ps = periods(bond_type, bought_on, first_rate, margin, cpi, overrides)
    maturity = ps[-1].end
    on = min(on, maturity)
    estimated = False
    value = NOMINAL
    known = first_rate
    for p in ps:
        rate = p.rate
        if rate is None:
            rate, estimated = known, True
        known = rate
        if on >= p.end:  # whole period done
            if t.style == "cap":
                value *= 1 + rate / 100
            elif t.style == "simple" and on == maturity:
                value += (
                    NOMINAL * rate / 100 * _fraction(p.start, p.end, p.end) * t.period_months / 12
                )
            continue
        accrued_rate = rate / 100 * _fraction(p.start, p.end, on) * t.period_months / 12
        if t.style == "cap":
            value *= 1 + accrued_rate
        else:  # coupon / simple: this period's interest on the nominal
            value = NOMINAL + NOMINAL * accrued_rate
        break
    else:
        if t.style == "coupon":
            value = NOMINAL  # the last coupon has been paid with the redemption
    return value.quantize(Decimal("0.0001")), estimated


def paid_out(  # noqa: PLR0917 — the bond's terms
    bond_type: str,
    bought_on: date,
    first_rate: Decimal,
    margin: Decimal | None,
    cpi: dict[tuple[int, int], Decimal],
    on: date,
    overrides: dict[str, str] | None = None,
) -> Decimal:
    """Interest already paid out per bond by ``on`` (COI yearly, ROR/DOR monthly)."""
    t = TYPES[bond_type]
    if t.style != "coupon":
        return ZERO
    total = ZERO
    for p in periods(bond_type, bought_on, first_rate, margin, cpi, overrides):
        if p.end <= on and p.rate is not None:
            total += NOMINAL * p.rate / 100 * t.period_months / 12
    return total.quantize(Decimal("0.01"))
