"""Interest on a deposit / savings account ("Inne" with a rate): the value
of what was paid in, on a day. Before the 19% tax on interest.

- ``none``: simple interest, paid at the end of the term (a typical lokata)
- ``monthly`` / ``quarterly`` / ``yearly``: interest added to the balance
  every period; within a period it accrues by days elapsed / days in it.
With ``term_months`` the money stops growing at the end of the term.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from dateutil.relativedelta import relativedelta

STEP_MONTHS = {"monthly": 1, "quarterly": 3, "yearly": 12}
COMPOUNDING = ("none", *STEP_MONTHS)


def value_on(
    principal: Decimal,
    start: date,
    on: date,
    *,
    rate: Decimal,
    compounding: str = "none",
    term_months: int | None = None,
) -> Decimal:
    if term_months:
        on = min(on, start + relativedelta(months=term_months))
    if on <= start:
        return principal
    r = rate / 100
    if compounding not in STEP_MONTHS:
        return (principal * (1 + r * Decimal((on - start).days) / 365)).quantize(Decimal("0.01"))
    step = STEP_MONTHS[compounding]
    value = principal
    period_start = start
    while (period_end := period_start + relativedelta(months=step)) <= on:
        value *= 1 + r * step / 12
        period_start = period_end
    elapsed = Decimal((on - period_start).days) / Decimal((period_end - period_start).days)
    value *= 1 + r * step / 12 * elapsed
    return value.quantize(Decimal("0.01"))
