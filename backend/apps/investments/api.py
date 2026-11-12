"""Investments REST API — thin wrappers over selectors/services."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from dateutil.relativedelta import relativedelta
from django.http import HttpRequest
from django.utils import timezone
from ninja import Router, Schema

from apps.access.context import get_ctx

from . import bonds, prices, selectors, services
from .models import Asset, InflationIndex, Lot

router = Router()

Kind = Literal["gold", "silver", "crypto", "stock", "bond", "other"]
TradeCurrency = Literal["PLN", "USD", "EUR", "GBP", "CHF"]


class AssetIn(Schema):
    name: str
    kind: Kind
    unit: Literal["oz", "g", "pcs"] = "pcs"
    symbol: str = ""
    person_id: UUID | None = None
    bond_type: str = ""
    bond_first_rate: Decimal | None = None
    bond_margin: Decimal | None = None
    rate: Decimal | None = None
    compounding: Literal["none", "monthly", "quarterly", "yearly"] = "none"
    term_months: int | None = None
    notes: str = ""


class LotOut(Schema):
    id: UUID
    bought_on: date
    quantity: Decimal
    price_total: Decimal
    sold_on: date | None
    sold_amount: Decimal | None
    price_currency: str
    price_foreign: Decimal | None
    price_rate: Decimal | None
    sold_currency: str
    sold_foreign: Decimal | None
    sold_rate: Decimal | None
    rate_overrides: dict
    notes: str


class ShareOut(Schema):
    user_id: int
    name: str
    can_edit: bool


class AssetOut(AssetIn):
    id: UUID
    archived: bool
    owner_name: str
    is_owner: bool
    can_edit: bool
    shares: list[ShareOut]
    lots: list[LotOut]
    quantity: Decimal
    cost: Decimal
    value: Decimal
    gain: Decimal
    gain_pct: Decimal | None
    realized: Decimal
    paid_out: Decimal
    price_date: date | None
    estimated: bool


def _out(asset: Asset, cpi: dict, user_id: int) -> dict[str, Any]:
    s = selectors.summary(asset, cpi)
    return {
        "owner_name": selectors.display_name(asset.created_by) if asset.created_by else "",
        "is_owner": asset.created_by_id == user_id,
        "can_edit": asset.can_edit(user_id),
        "shares": [
            {
                "user_id": sh.user_id,
                "name": selectors.display_name(sh.user),
                "can_edit": sh.can_edit,
            }
            for sh in asset.shares.all()
        ],
        **{
            f: getattr(asset, f)
            for f in ("id", "name", "kind", "unit", "symbol", "person_id", "notes")
        },
        "bond_type": asset.bond_type,
        "bond_first_rate": asset.bond_first_rate,
        "bond_margin": asset.bond_margin,
        "rate": asset.rate,
        "compounding": asset.compounding or "none",
        "term_months": asset.term_months,
        "archived": asset.archived_at is not None,
        "lots": list(asset.lots.all()),
        "quantity": s.quantity,
        "cost": s.cost,
        "value": s.value,
        "gain": s.gain,
        "gain_pct": s.gain_pct,
        "realized": s.realized,
        "paid_out": s.paid_out,
        "price_date": s.price_date,
        "estimated": s.estimated,
    }


@router.get("/assets", response=list[AssetOut])
def list_assets(request: HttpRequest, archived: bool = False) -> list[dict]:
    ctx = get_ctx(request)
    cpi = selectors.cpi_table()
    return [_out(a, cpi, ctx.user_id) for a in selectors.list_assets(ctx, archived=archived)]


@router.post("/assets", response={200: AssetOut, 422: dict})
def create_asset(request: HttpRequest, payload: AssetIn):
    ctx = get_ctx(request)
    try:
        asset = services.save_asset(ctx, payload.dict())
    except ValueError as exc:
        return 422, {"detail": str(exc)}
    return _out(selectors.get_asset(ctx, asset.id), selectors.cpi_table(), ctx.user_id)


@router.put("/assets/{asset_id}", response={200: AssetOut, 422: dict})
def update_asset(request: HttpRequest, asset_id: UUID, payload: AssetIn):
    ctx = get_ctx(request)
    try:
        services.save_asset(ctx, payload.dict(), asset_id)
    except ValueError as exc:
        return 422, {"detail": str(exc)}
    return _out(selectors.get_asset(ctx, asset_id), selectors.cpi_table(), ctx.user_id)


@router.delete("/assets/{asset_id}")
def archive_asset(request: HttpRequest, asset_id: UUID) -> dict[str, bool]:
    services.archive_asset(get_ctx(request), asset_id)
    return {"archived": True}


class ShareIn(Schema):
    user_id: int
    can_edit: bool = False


@router.put("/assets/{asset_id}/shares", response={200: AssetOut, 422: dict})
def set_shares(request: HttpRequest, asset_id: UUID, payload: list[ShareIn]):
    """Who else sees this investment (owner only)."""
    ctx = get_ctx(request)
    try:
        services.set_shares(ctx, asset_id, [p.dict() for p in payload])
    except ValueError as exc:
        return 422, {"detail": str(exc)}
    return _out(selectors.get_asset(ctx, asset_id), selectors.cpi_table(), ctx.user_id)


class PersonOut(Schema):
    user_id: int
    name: str


@router.get("/people", response=list[PersonOut])
def people(request: HttpRequest) -> list[dict]:
    """Family members with a login — to share an investment with."""
    return [
        {"user_id": u.pk, "name": selectors.display_name(u)}
        for u in selectors.family_users(get_ctx(request))
    ]


class LotIn(Schema):
    bought_on: date
    quantity: Decimal
    price_total: Decimal | None = None  # PLN (computed when paid in another currency)
    price_currency: TradeCurrency = "PLN"
    price_foreign: Decimal | None = None  # what was paid in that currency
    price_rate: Decimal | None = None  # PLN for 1 unit of it; empty = NBP's
    notes: str = ""


@router.post("/assets/{asset_id}/lots", response={200: LotOut, 422: dict})
def add_lot(request: HttpRequest, asset_id: UUID, payload: LotIn):
    try:
        return services.save_lot(get_ctx(request), payload.dict(), asset_id=asset_id)
    except ValueError as exc:
        return 422, {"detail": str(exc)}


@router.put("/lots/{lot_id}", response={200: LotOut, 422: dict})
def update_lot(request: HttpRequest, lot_id: UUID, payload: LotIn):
    try:
        return services.save_lot(get_ctx(request), payload.dict(), lot_id=lot_id)
    except ValueError as exc:
        return 422, {"detail": str(exc)}


@router.delete("/lots/{lot_id}")
def delete_lot(request: HttpRequest, lot_id: UUID) -> dict[str, bool]:
    services.delete_lot(get_ctx(request), lot_id)
    return {"deleted": True}


class SellIn(Schema):
    sold_on: date
    sold_amount: Decimal | None = None  # PLN, or:
    sold_currency: TradeCurrency = "PLN"
    sold_foreign: Decimal | None = None  # what was received in that currency
    sold_rate: Decimal | None = None  # PLN for 1 unit of it; empty = NBP's
    quantity: Decimal | None = None  # part of the purchase; empty = all of it


@router.post("/lots/{lot_id}/sell", response={200: LotOut, 422: dict})
def sell_lot(request: HttpRequest, lot_id: UUID, payload: SellIn):
    try:
        return services.sell_lot(get_ctx(request), lot_id, **payload.dict())
    except ValueError as exc:
        return 422, {"detail": str(exc)}


class SellAssetIn(Schema):
    sold_on: date
    quantity: Decimal
    sold_amount: Decimal | None = None
    sold_currency: TradeCurrency = "PLN"
    sold_foreign: Decimal | None = None
    sold_rate: Decimal | None = None


@router.post("/assets/{asset_id}/sell", response={200: list[LotOut], 422: dict})
def sell_asset(request: HttpRequest, asset_id: UUID, payload: SellAssetIn):
    """Sell part (or all) of what's held, oldest purchases first."""
    try:
        return services.sell_asset(get_ctx(request), asset_id, **payload.dict())
    except ValueError as exc:
        return 422, {"detail": str(exc)}


class PeriodOut(Schema):
    number: int
    start: date
    end: date
    rate: Decimal | None
    source: str
    inflation: Decimal | None


@router.get("/lots/{lot_id}/periods", response=list[PeriodOut])
def lot_periods(request: HttpRequest, lot_id: UUID) -> list[dict]:
    """A bond lot's interest periods: rate and where it came from."""
    lot: Lot = selectors.get_lot(get_ctx(request), lot_id)
    return selectors.bond_schedule(lot.asset, lot, selectors.cpi_table())


class RateIn(Schema):
    rate: Decimal | None  # None = back to the computed rate


@router.put("/lots/{lot_id}/periods/{period}", response={200: LotOut, 422: dict})
def override_rate(request: HttpRequest, lot_id: UUID, period: int, payload: RateIn):
    try:
        return services.set_rate_override(get_ctx(request), lot_id, period, payload.rate)
    except ValueError as exc:
        return 422, {"detail": str(exc)}


class ValueIn(Schema):
    on: date
    unit_price: Decimal | None = None
    total: Decimal | None = None


@router.post("/assets/{asset_id}/values", response={200: dict, 422: dict})
def set_value(request: HttpRequest, asset_id: UUID, payload: ValueIn):
    """A value entered by hand (stocks, other) — per unit or in total."""
    try:
        snap = services.set_value(get_ctx(request), asset_id, **payload.dict())
    except ValueError as exc:
        return 422, {"detail": str(exc)}
    return {"date": snap.date, "unit_price": snap.unit_price}


class PointOut(Schema):
    date: date
    value: Decimal
    cost: Decimal


def _start(months: int | None) -> date | None:
    return timezone.localdate() - relativedelta(months=months) if months else None


@router.get("/assets/{asset_id}/series", response=list[PointOut])
def asset_series(request: HttpRequest, asset_id: UUID, months: int | None = None) -> list[dict]:
    asset = selectors.get_asset(get_ctx(request), asset_id)
    return selectors.series([asset], selectors.cpi_table(), start=_start(months))


class GainOut(Schema):
    gain: Decimal
    gain_pct: Decimal | None


class PeriodOut(GainOut):
    """What was earned between ``start`` and ``end`` (in total and per asset id)."""

    start: date
    end: date
    assets: dict[str, GainOut]


class PortfolioOut(Schema):
    value: Decimal
    cost: Decimal
    gain: Decimal
    paid_out: Decimal
    realized: Decimal
    by_kind: dict[str, Decimal]
    series: list[PointOut]
    period: PeriodOut | None  # only when a range is chosen


@router.get("/portfolio", response=PortfolioOut)
def portfolio(  # noqa: PLR0917 — query parameters
    request: HttpRequest,
    months: int | None = None,
    kind: Kind | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    open_only: bool = False,
) -> dict[str, Any]:
    """Everything held (or one kind): totals, value per kind, and the value
    over time — the last ``months``, or ``date_from``..``date_to`` (and then
    also what was earned in that period)."""
    assets = list(selectors.list_assets(get_ctx(request), kind=kind))
    cpi = selectors.cpi_table()
    start = date_from or _start(months)
    by_kind: dict[str, Decimal] = defaultdict(Decimal)
    totals = defaultdict(Decimal)
    for a in assets:
        s = selectors.summary(a, cpi)
        by_kind[a.kind] += s.value
        for k in ("value", "cost", "gain", "paid_out", "realized"):
            totals[k] += getattr(s, k)
    return {
        **{k: totals[k] for k in ("value", "cost", "gain", "paid_out", "realized")},
        "by_kind": dict(by_kind),
        "series": selectors.series(assets, cpi, start=start, end=date_to, open_only=open_only),
        "period": _period(assets, cpi, start, date_to, open_only=open_only) if start else None,
    }


def _period(
    assets: list[Asset], cpi: dict, start: date, end: date | None, *, open_only: bool
) -> dict[str, Any]:
    end = end or timezone.localdate()
    total = selectors.PeriodGain()
    per_asset = {}
    for a in assets:
        g = selectors.period_gain(a, cpi, start, end, open_only=open_only)
        per_asset[str(a.id)] = {"gain": g.gain, "gain_pct": g.gain_pct}
        total.gain += g.gain
        total.base += g.base
    return {
        "start": start,
        "end": end,
        "gain": total.gain,
        "gain_pct": total.gain_pct,
        "assets": per_asset,
    }


class FxOut(Schema):
    date: date
    rates: dict[str, Decimal]


@router.get("/fx", response={200: FxOut, 422: dict})
def fx(request: HttpRequest):
    """NBP rates (PLN for 1 USD / EUR) to show the values in another currency."""
    try:
        return selectors.fx_rates(get_ctx(request))
    except prices.PriceError:
        return 422, {"detail": "NBP rates unavailable"}


class TradeRateOut(Schema):
    currency: str
    on: date
    rate_date: date
    rate: Decimal


@router.get("/fx-rate", response={200: TradeRateOut, 422: dict})
def fx_rate(request: HttpRequest, currency: TradeCurrency, on: date):
    """The NBP rate a purchase / sale in ``currency`` on ``on`` is converted
    at: the last working day's before it."""
    try:
        return selectors.trade_rate(get_ctx(request), currency, on)
    except (ValueError, prices.PriceError):
        return 422, {"detail": "NBP rate unavailable"}


@router.post("/refresh", response=dict)
def refresh(request: HttpRequest) -> dict[str, int]:
    """Download prices and inflation now (normally done every evening)."""
    return services.refresh_now(get_ctx(request))


class InflationOut(Schema):
    year: int
    month: int
    index: Decimal
    manual: bool


@router.get("/inflation", response=list[InflationOut])
def inflation(request: HttpRequest, last: int = 24) -> list[InflationIndex]:
    selectors.require(get_ctx(request))
    return list(InflationIndex.objects.order_by("-year", "-month")[:last])


class InflationIn(Schema):
    year: int
    month: int
    index: Decimal


@router.post("/inflation", response={200: InflationOut, 422: dict})
def add_inflation(request: HttpRequest, payload: InflationIn):
    try:
        return services.add_inflation(get_ctx(request), **payload.dict())
    except ValueError as exc:
        return 422, {"detail": str(exc)}


class BondTypeOut(Schema):
    code: str
    months: int
    indexed: bool
    floating: bool
    capitalised: bool


@router.get("/bond-types", response=list[BondTypeOut])
def bond_types(request: HttpRequest) -> list[dict]:
    return [
        {
            "code": code,
            "months": t.months,
            "indexed": t.indexed,
            "floating": t.floating,
            "capitalised": t.style == "cap",
        }
        for code, t in bonds.TYPES.items()
    ]
