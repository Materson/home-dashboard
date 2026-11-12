"""Investment reads: holdings with their current value and gain, and value
series for charts. Access: finance:view, and then only your own
investments and those shared with you (anyone else's answers 404)."""

from __future__ import annotations

import bisect
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import Http404
from django.utils import timezone

from . import bonds, deposits, prices
from .models import Asset, InflationIndex, Lot

if TYPE_CHECKING:
    from apps.access.context import AccessContext

CENT = Decimal("0.01")


def require(ctx: AccessContext, level: str = "view") -> None:
    ctx.require("finance", level)


def _visible(ctx: AccessContext):
    return (
        Asset.objects.filter(Q(created_by_id=ctx.user_id) | Q(shares__user_id=ctx.user_id))
        .distinct()
        .prefetch_related("lots", "prices", "shares__user__person")
        .select_related("created_by__person")
    )


def list_assets(ctx: AccessContext, *, archived: bool = False, kind: str | None = None):
    require(ctx)
    qs = _visible(ctx).filter(archived_at__isnull=not archived)
    return qs.filter(kind=kind) if kind else qs


def get_asset(ctx: AccessContext, asset_id: UUID, level: str = "view") -> Asset:
    require(ctx, level)
    asset = _visible(ctx).filter(pk=asset_id).first()
    if asset is None:
        raise Http404
    if level != "view" and not asset.can_edit(ctx.user_id):
        raise PermissionDenied("shared with you to view only")
    return asset


def get_lot(ctx: AccessContext, lot_id: UUID, level: str = "view") -> Lot:
    lot = Lot.objects.filter(pk=lot_id).first()
    if lot is None:
        raise Http404
    lot.asset = get_asset(ctx, lot.asset_id, level)  # visible (and editable) through its asset
    return lot


def display_name(user) -> str:
    person = getattr(user, "person", None)
    return (person and person.display_name) or user.get_full_name() or user.email


def family_users(ctx: AccessContext) -> list:
    """People with a login (to share with), you excluded."""
    require(ctx)
    return list(
        get_user_model()
        .objects.filter(is_active=True, person__isnull=False, person__archived_at__isnull=True)
        .exclude(pk=ctx.user_id)
        .select_related("person")
        .order_by("person__display_name")
    )


def cpi_table() -> dict[tuple[int, int], Decimal]:
    return {(r.year, r.month): r.index for r in InflationIndex.objects.all()}


# Values are kept in PLN; these can be picked to show them in instead.
DISPLAY_CURRENCIES = ("USD", "EUR")
FX_CACHE_KEY = "investments:fx"
FX_CACHE_S = 3 * 3600


# Purchases and sales may be entered in these (kept in PLN as well).
TRADE_CURRENCIES = ("PLN", "USD", "EUR", "GBP", "CHF")
RATE_CACHE_S = 24 * 3600


def rate_before(currency: str, day: date) -> tuple[date, Decimal]:
    """NBP's rate for a purchase / sale on ``day`` and the day it's from
    (cached; ``prices.PriceError`` when NBP can't say)."""
    key = f"investments:rate:{currency}:{day.isoformat()}"
    found = cache.get(key)
    if found is None:
        found = prices.nbp_rate_before(currency, day)
        cache.set(key, found, RATE_CACHE_S)
    return found


def trade_rate(ctx: AccessContext, currency: str, day: date) -> dict:
    """The rate a purchase / sale in ``currency`` on ``day`` is converted at."""
    require(ctx)
    if currency not in TRADE_CURRENCIES or currency == "PLN":
        raise ValueError(f"currency must be one of {TRADE_CURRENCIES[1:]}")
    rate_date, rate = rate_before(currency, day)
    return {"currency": currency, "on": day, "rate_date": rate_date, "rate": rate}


def fx_rates(ctx: AccessContext) -> dict:
    """The latest NBP rates for showing values in USD / EUR:
    ``{"date": day, "rates": {"USD": PLN for 1 USD, ...}}``. Cached a few
    hours; raises ``prices.PriceError`` when NBP can't be reached."""
    require(ctx)
    found = cache.get(FX_CACHE_KEY)
    if found is None:
        day, rates = prices.nbp_latest()
        found = {"date": day, "rates": {c: rates[c] for c in DISPLAY_CURRENCIES if c in rates}}
        cache.set(FX_CACHE_KEY, found, FX_CACHE_S)
    return found


# ---------------- valuation ----------------


class Pricer:
    """Unit price of an asset on a day: the latest snapshot on or before it."""

    def __init__(self, asset: Asset):
        snaps = sorted(asset.prices.all(), key=lambda p: p.date)
        self.dates = [p.date for p in snaps]
        self.prices = [p.unit_price for p in snaps]

    def on(self, day: date) -> tuple[Decimal | None, date | None]:
        i = bisect.bisect_right(self.dates, day) - 1
        return (self.prices[i], self.dates[i]) if i >= 0 else (None, None)


def _active(lot: Lot, day: date) -> bool:
    return lot.bought_on <= day and (lot.sold_on is None or day < lot.sold_on)


def lot_value(asset: Asset, lot: Lot, day: date, pricer: Pricer, cpi: dict) -> tuple[Decimal, bool]:
    """Value of a lot on a day, and whether it's an estimate. Before any
    price is known the lot counts at what was paid for it."""
    if asset.kind == Asset.Kind.BOND and asset.bond_type in bonds.TYPES:
        per_bond, estimated = bonds.value_on(
            asset.bond_type,
            lot.bought_on,
            asset.bond_first_rate or Decimal(0),
            asset.bond_margin,
            cpi,
            day,
            lot.rate_overrides,
        )
        return lot.quantity * per_bond, estimated
    if asset.kind == Asset.Kind.OTHER and asset.rate is not None:
        value = deposits.value_on(
            lot.price_total,
            lot.bought_on,
            day,
            rate=asset.rate,
            compounding=asset.compounding,
            term_months=asset.term_months,
        )
        return value, False
    price, _ = pricer.on(day)
    if price is None:
        return lot.price_total, True
    return lot.quantity * price, False


@dataclass
class Summary:
    quantity: Decimal = Decimal(0)
    cost: Decimal = Decimal(0)
    value: Decimal = Decimal(0)
    gain: Decimal = Decimal(0)
    gain_pct: Decimal | None = None
    realized: Decimal = Decimal(0)  # sold lots: received - paid
    paid_out: Decimal = Decimal(0)  # bond interest already paid to the account
    price_date: date | None = None
    estimated: bool = False
    bond_periods: list[dict] = field(default_factory=list)


def summary(asset: Asset, cpi: dict, today: date | None = None) -> Summary:
    today = today or timezone.localdate()
    pricer = Pricer(asset)
    s = Summary()
    for lot in asset.lots.all():
        if lot.sold_on and lot.sold_on <= today:
            s.realized += (lot.sold_amount or Decimal(0)) - lot.price_total
            continue
        if lot.bought_on > today:
            continue
        value, estimated = lot_value(asset, lot, today, pricer, cpi)
        s.quantity += lot.quantity
        s.cost += lot.price_total
        s.value += value
        s.estimated |= estimated
        if asset.kind == Asset.Kind.BOND and asset.bond_type in bonds.TYPES:
            s.paid_out += lot.quantity * bonds.paid_out(
                asset.bond_type,
                lot.bought_on,
                asset.bond_first_rate or Decimal(0),
                asset.bond_margin,
                cpi,
                today,
                lot.rate_overrides,
            )
    s.value = s.value.quantize(CENT)
    s.gain = (s.value + s.paid_out - s.cost).quantize(CENT)
    s.gain_pct = (s.gain / s.cost * 100).quantize(Decimal("0.1")) if s.cost else None
    s.realized = s.realized.quantize(CENT)
    s.price_date = pricer.on(today)[1]
    return s


@dataclass
class PeriodGain:
    gain: Decimal = Decimal(0)
    # What the gain is measured against: the value at the start, plus what
    # was paid for purchases made during the period.
    base: Decimal = Decimal(0)

    @property
    def gain_pct(self) -> Decimal | None:
        return (self.gain / self.base * 100).quantize(Decimal("0.1")) if self.base else None


def _coupons(asset: Asset, lot: Lot, cpi: dict, start: date, stop: date) -> Decimal:
    """Bond interest paid out to the account between ``start`` and ``stop``."""
    if asset.kind != Asset.Kind.BOND or asset.bond_type not in bonds.TYPES:
        return Decimal(0)
    terms = (asset.bond_type, lot.bought_on, asset.bond_first_rate or Decimal(0), asset.bond_margin)
    paid = lambda on: bonds.paid_out(*terms, cpi, on, lot.rate_overrides)  # noqa: E731
    return lot.quantity * (paid(stop) - paid(start))


def period_gain(
    asset: Asset, cpi: dict, start: date, end: date, *, open_only: bool = False
) -> PeriodGain:
    """What an asset earned between ``start`` and ``end``: per purchase, its
    value at the end (or what it was sold for) minus its value at the start
    (or what was paid, if bought later), plus bond interest paid out meanwhile.
    ``open_only`` leaves out purchases already sold."""
    pricer = Pricer(asset)
    out = PeriodGain()
    for lot in asset.lots.all():
        sold_by_end = lot.sold_on is not None and lot.sold_on <= end
        if open_only and lot.sold_on:
            continue
        if lot.bought_on > end or (lot.sold_on and lot.sold_on <= start):
            continue  # not held during the period
        if lot.bought_on < start:
            begin, _ = lot_value(asset, lot, start, pricer, cpi)
        else:
            begin = lot.price_total
        if sold_by_end:
            finish = lot.sold_amount or Decimal(0)
        else:
            finish, _ = lot_value(asset, lot, end, pricer, cpi)
        stop = lot.sold_on if sold_by_end else end
        out.gain += finish + _coupons(asset, lot, cpi, start, stop) - begin
        out.base += begin
    out.gain = out.gain.quantize(CENT)
    out.base = out.base.quantize(CENT)
    return out


def bond_schedule(asset: Asset, lot: Lot, cpi: dict) -> list[dict]:
    """A bond lot's interest periods with their rates and where each came from."""
    if asset.bond_type not in bonds.TYPES:
        return []
    return [
        {
            "number": p.number,
            "start": p.start,
            "end": p.end,
            "rate": p.rate,
            "source": p.source,
            "inflation": p.inflation,
        }
        for p in bonds.periods(
            asset.bond_type,
            lot.bought_on,
            asset.bond_first_rate or Decimal(0),
            asset.bond_margin,
            cpi,
            lot.rate_overrides,
        )
    ]


# ---------------- series for charts ----------------


def _days(start: date, end: date) -> list[date]:
    span = (end - start).days
    step = 1 if span <= 120 else 7 if span <= 3 * 366 else 30  # noqa: PLR2004
    out = [start + timedelta(days=i) for i in range(0, span + 1, step)]
    if out[-1] != end:
        out.append(end)
    return out


def series(
    assets: list[Asset],
    cpi: dict,
    *,
    start: date | None = None,
    end: date | None = None,
    open_only: bool = False,
) -> list[dict]:
    """[{date, value, cost}] summed over ``assets`` (lots held on each day;
    ``open_only`` leaves out positions already sold / closed)."""
    end = end or timezone.localdate()
    lots = [(a, lot) for a in assets for lot in a.lots.all() if not (open_only and lot.sold_on)]
    if not lots:
        return []
    start = start or min(lot.bought_on for _, lot in lots)
    pricers = {a.id: Pricer(a) for a in assets}
    out = []
    for day in _days(start, end):
        value = cost = Decimal(0)
        for asset, lot in lots:
            if _active(lot, day):
                v, _ = lot_value(asset, lot, day, pricers[asset.id], cpi)
                value += v
                cost += lot.price_total
        out.append({"date": day, "value": value.quantize(CENT), "cost": cost.quantize(CENT)})
    return out
