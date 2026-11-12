"""Investment writes (finance:edit) and the daily price refresh."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import UUID

from django.core.exceptions import PermissionDenied
from django.db import connection, transaction
from django.db.transaction import atomic
from django.utils import timezone

from . import bonds, deposits, prices
from .models import TROY_OUNCE_G, Asset, AssetShare, InflationIndex, Lot, PriceSnapshot
from .selectors import (
    TRADE_CURRENCIES,
    family_users,
    get_asset,
    get_lot,
    rate_before,
    require,
)

if TYPE_CHECKING:
    from apps.access.context import AccessContext

log = logging.getLogger(__name__)


# ---------------- assets ----------------


@atomic
def save_asset(ctx: AccessContext, data: dict[str, Any], asset_id: UUID | None = None) -> Asset:
    require(ctx, "edit")
    asset = get_asset(ctx, asset_id, "edit") if asset_id else Asset(created_by_id=ctx.user_id)
    for k, v in data.items():
        setattr(asset, k, v)
    _clean_asset(asset)
    asset.save()
    if asset_id:
        schedule_refresh(asset.id)
    return asset


def _clean_asset(asset: Asset) -> None:
    """Kind-specific checks and normalising (raises ValueError)."""
    asset.name = " ".join(asset.name.split())
    if not asset.name:
        raise ValueError("name is required")
    if asset.kind == Asset.Kind.CRYPTO and not asset.symbol.strip():
        raise ValueError("a cryptocurrency needs its CoinGecko id (e.g. bitcoin)")
    metals = (Asset.Kind.GOLD, Asset.Kind.SILVER)
    if asset.kind in metals and asset.unit not in (Asset.Unit.OZ, Asset.Unit.G):
        raise ValueError("precious metals are counted in troy ounces or grams")
    if asset.kind == Asset.Kind.BOND:
        if asset.bond_type not in bonds.TYPES:
            raise ValueError(f"bond type must be one of {sorted(bonds.TYPES)}")
        if asset.bond_first_rate is None:
            raise ValueError("the first period's rate is required")
        t = bonds.TYPES[asset.bond_type]
        if (t.indexed or asset.bond_type == "DOR") and asset.bond_margin is None:
            raise ValueError("this bond needs its margin")
        asset.unit = Asset.Unit.PIECE
    if asset.kind == Asset.Kind.OTHER and asset.rate is not None:
        if asset.rate < 0:
            raise ValueError("the interest rate can't be negative")
        if asset.compounding not in deposits.COMPOUNDING:
            raise ValueError(f"compounding must be one of {deposits.COMPOUNDING}")
    else:
        asset.rate, asset.compounding, asset.term_months = None, "none", None
    symbol = asset.symbol.strip()
    asset.symbol = symbol.lower() if asset.kind == Asset.Kind.CRYPTO else symbol.upper()


@atomic
def archive_asset(ctx: AccessContext, asset_id: UUID) -> None:
    _owned(ctx, asset_id).archive()


def _owned(ctx: AccessContext, asset_id: UUID) -> Asset:
    asset = get_asset(ctx, asset_id, "edit")
    if asset.created_by_id != ctx.user_id:
        raise PermissionDenied("only the owner can do this")
    return asset


@atomic
def set_shares(ctx: AccessContext, asset_id: UUID, shares: list[dict]) -> Asset:
    """Who else sees this investment: [{"user_id": …, "can_edit": …}] (owner only)."""
    asset = _owned(ctx, asset_id)
    wanted = {s["user_id"]: bool(s.get("can_edit")) for s in shares if s["user_id"] != ctx.user_id}
    if not set(wanted) <= {u.pk for u in family_users(ctx)}:
        raise ValueError("can only share with family members")
    asset.shares.exclude(user_id__in=wanted).delete()
    for uid, can_edit in wanted.items():
        AssetShare.objects.update_or_create(
            asset=asset, user_id=uid, defaults={"can_edit": can_edit}
        )
    return asset


# ---------------- lots ----------------


@atomic
def save_lot(
    ctx: AccessContext,
    data: dict[str, Any],
    *,
    asset_id: UUID | None = None,
    lot_id: UUID | None = None,
) -> Lot:
    """A purchase. Paid in another currency: ``price_currency`` with
    ``price_foreign`` (and ``price_rate``, else NBP's) — kept in PLN too."""
    require(ctx, "edit")
    lot = get_lot(ctx, lot_id, "edit") if lot_id else Lot(asset=get_asset(ctx, asset_id, "edit"))
    for k, v in data.items():
        setattr(lot, k, v)
    if lot.quantity is None or lot.quantity <= 0:
        raise ValueError("quantity must be more than 0")
    if lot.bought_on > timezone.localdate():
        raise ValueError("the purchase date is in the future")
    if lot.price_currency == "PLN":
        lot.price_foreign = lot.price_rate = None
    else:
        lot.price_total, lot.price_rate = _to_pln(
            lot.price_currency, lot.price_foreign, lot.price_rate, lot.bought_on
        )
    if lot.price_total is None or lot.price_total < 0:
        raise ValueError("the price can't be negative")
    if lot.sold_on and lot.sold_on < lot.bought_on:
        raise ValueError("sold before it was bought")
    lot.save()
    schedule_refresh(lot.asset_id)
    return lot


CENT = Decimal("0.01")


def _to_pln(
    currency: str, amount: Decimal | None, rate: Decimal | None, day: date
) -> tuple[Decimal, Decimal]:
    """PLN for ``amount`` in ``currency``, and the rate used: the one given
    (e.g. the broker's), else NBP's from the last working day before ``day``
    (as Polish tax rules count a foreign-currency purchase or sale)."""
    if currency not in TRADE_CURRENCIES or currency == "PLN":
        raise ValueError(f"currency must be one of {TRADE_CURRENCIES}")
    if amount is None or amount < 0:
        raise ValueError("the amount can't be negative")
    if rate is None:
        try:
            rate = rate_before(currency, day)[1]
        except prices.PriceError as exc:
            raise ValueError("NBP rate unavailable — enter the rate yourself") from exc
    if rate <= 0:
        raise ValueError("the rate must be more than 0")
    return (amount * rate).quantize(CENT), rate


def _check_sale(asset: Asset, sold_on: date, quantity: Decimal) -> None:
    if sold_on > timezone.localdate():
        raise ValueError("the sale date is in the future")
    if quantity <= 0:
        raise ValueError("quantity must be more than 0")
    if asset.kind == Asset.Kind.BOND and quantity != quantity.to_integral_value():
        raise ValueError("bonds are sold whole")


@dataclass
class _Received:
    """What a sale brought: PLN, and the foreign amount and rate if any."""

    pln: Decimal
    currency: str = "PLN"
    foreign: Decimal | None = None
    rate: Decimal | None = None

    @classmethod
    def of(cls, sold_on: date, money: dict[str, Any]) -> _Received:
        currency = money.get("sold_currency") or "PLN"
        if currency == "PLN":
            amount = money.get("sold_amount")
            if amount is None or amount < 0:
                raise ValueError("the amount can't be negative")
            return cls(amount)
        foreign = money.get("sold_foreign")
        pln, rate = _to_pln(currency, foreign, money.get("sold_rate"), sold_on)
        return cls(pln, currency, foreign, rate)

    def share(self, part: Decimal, whole: Decimal) -> _Received:
        """This sale's part for ``part`` of ``whole`` sold."""
        cut = lambda v: None if v is None else (v * part / whole).quantize(CENT)  # noqa: E731
        return _Received(cut(self.pln), self.currency, cut(self.foreign), self.rate)

    def minus(self, other: _Received) -> _Received:
        rest = None if self.foreign is None else self.foreign - other.foreign
        return _Received(self.pln - other.pln, self.currency, rest, self.rate)


def _split(lot: Lot, quantity: Decimal) -> Lot:
    """Cut ``quantity`` off an open purchase into its own lot — bought the
    same day, with its share of the price (the rest stays with ``lot``)."""
    share = (lot.price_total * quantity / lot.quantity).quantize(CENT)
    foreign = None
    if lot.price_foreign is not None:
        foreign = (lot.price_foreign * quantity / lot.quantity).quantize(CENT)
    part = Lot.objects.create(
        asset=lot.asset,
        bought_on=lot.bought_on,
        quantity=quantity,
        price_total=share,
        price_currency=lot.price_currency,
        price_foreign=foreign,
        price_rate=lot.price_rate,
        rate_overrides=dict(lot.rate_overrides),
        notes=lot.notes,
    )
    lot.quantity -= quantity
    lot.price_total -= share
    if foreign is not None:
        lot.price_foreign -= foreign
    lot.save(update_fields=["quantity", "price_total", "price_foreign", "updated_at"])
    return part


def _mark_sold(lot: Lot, sold_on: date, received: _Received) -> Lot:
    lot.sold_on, lot.sold_amount = sold_on, received.pln
    lot.sold_currency, lot.sold_foreign, lot.sold_rate = (
        received.currency,
        received.foreign,
        received.rate,
    )
    lot.save(
        update_fields=[
            "sold_on",
            "sold_amount",
            "sold_currency",
            "sold_foreign",
            "sold_rate",
            "updated_at",
        ]
    )
    return lot


@atomic
def sell_lot(
    ctx: AccessContext,
    lot_id: UUID,
    *,
    sold_on: date,
    quantity: Decimal | None = None,
    **money: Any,
) -> Lot:
    """Sell a purchase: all of it, or ``quantity`` of it (that part becomes
    its own lot with its share of the price). ``money``: ``sold_amount`` in
    PLN, or ``sold_currency`` + ``sold_foreign`` (+ ``sold_rate``). Returns
    the sold lot."""
    require(ctx, "edit")
    lot = get_lot(ctx, lot_id, "edit")
    quantity = lot.quantity if quantity is None else quantity
    _check_sale(lot.asset, sold_on, quantity)
    if sold_on < lot.bought_on:
        raise ValueError("sold before it was bought")
    if quantity > lot.quantity:
        raise ValueError("can't sell more than this purchase holds")
    received = _Received.of(sold_on, money)
    if quantity < lot.quantity:
        if lot.sold_on:
            raise ValueError("this purchase is already sold")
        lot = _split(lot, quantity)
    return _mark_sold(lot, sold_on, received)


@atomic
def sell_asset(
    ctx: AccessContext,
    asset_id: UUID,
    *,
    sold_on: date,
    quantity: Decimal,
    **money: Any,
) -> list[Lot]:
    """Sell ``quantity`` of what's held on ``sold_on``, the oldest purchases
    first (FIFO — as the tax office counts it). The last purchase touched is
    split; what was received is shared out by quantity. Returns the sold lots."""
    require(ctx, "edit")
    asset = get_asset(ctx, asset_id, "edit")
    _check_sale(asset, sold_on, quantity)
    held = sorted(
        (lot for lot in asset.lots.all() if lot.sold_on is None and lot.bought_on <= sold_on),
        key=lambda lot: (lot.bought_on, lot.created_at),
    )
    if quantity > sum((lot.quantity for lot in held), Decimal(0)):
        raise ValueError("can't sell more than was held that day")
    received = _Received.of(sold_on, money)
    sold: list[Lot] = []
    left, rest = quantity, received
    for lot in held:
        if not left:
            break
        lot.asset = asset
        take = min(lot.quantity, left)
        got = rest if take == left else received.share(take, quantity)
        part = _split(lot, take) if take < lot.quantity else lot
        sold.append(_mark_sold(part, sold_on, got))
        left -= take
        rest = rest.minus(got)
    return sold


def delete_lot(ctx: AccessContext, lot_id: UUID) -> None:
    require(ctx, "edit")
    get_lot(ctx, lot_id, "edit").delete()


@atomic
def set_rate_override(ctx: AccessContext, lot_id: UUID, period: int, rate: Decimal | None) -> Lot:
    """A bond period's rate as the bank shows it (None = back to computed)."""
    require(ctx, "edit")
    lot = get_lot(ctx, lot_id, "edit")
    overrides = dict(lot.rate_overrides)
    if rate is None:
        overrides.pop(str(period), None)
    else:
        if rate < 0:
            raise ValueError("the rate can't be negative")
        overrides[str(period)] = str(rate)
    lot.rate_overrides = overrides
    lot.save(update_fields=["rate_overrides", "updated_at"])
    return lot


# ---------------- values ----------------


@atomic
def set_value(
    ctx: AccessContext,
    asset_id: UUID,
    *,
    on: date,
    unit_price: Decimal | None = None,
    total: Decimal | None = None,
) -> PriceSnapshot:
    """A value entered by hand — per unit, or for everything held that day."""
    require(ctx, "edit")
    asset = get_asset(ctx, asset_id, "edit")
    if asset.kind == Asset.Kind.BOND:
        raise ValueError("bond values are computed — correct a period's rate instead")
    if unit_price is None:
        held = sum(
            (
                lot.quantity
                for lot in asset.lots.all()
                if lot.bought_on <= on and (not lot.sold_on or on < lot.sold_on)
            ),
            Decimal(0),
        )
        if total is None or not held:
            raise ValueError("give the unit price, or the total for what was held that day")
        unit_price = total / held
    if unit_price < 0:
        raise ValueError("the price can't be negative")
    snap, _ = PriceSnapshot.objects.update_or_create(
        asset=asset,
        date=on,
        defaults={"unit_price": unit_price.quantize(Decimal("0.000001")), "source": "manual"},
    )
    return snap


@atomic
def add_inflation(ctx: AccessContext, year: int, month: int, index: Decimal) -> InflationIndex:
    """CPI y/y entered by hand when GUS can't be downloaded."""
    require(ctx, "edit")
    if not (1 <= month <= 12 and 80 <= index <= 200):  # noqa: PLR2004
        raise ValueError("month 1-12 and an index like 104.1 (= 4.1% inflation)")
    row, _ = InflationIndex.objects.update_or_create(
        year=year, month=month, defaults={"index": index, "manual": True}
    )
    return row


# ---------------- refresh (background) ----------------


def schedule_refresh(asset_id: UUID) -> None:
    """Fetch the asset's price history right after the save is committed, in
    a short background thread — no task queue needed (queueing would block
    the request when the broker is down). The daily job catches up anyway."""

    def run() -> None:
        try:
            asset = Asset.objects.filter(pk=asset_id).first()
            if asset is not None:
                refresh_asset_prices(asset)
                if asset.kind == Asset.Kind.BOND and not InflationIndex.objects.exists():
                    refresh_inflation()
        except prices.PriceError as exc:
            log.warning("price refresh for %s failed: %s", asset_id, exc)
        except Exception:
            log.exception("price refresh for %s crashed", asset_id)
        finally:
            connection.close()  # this thread's own DB connection

    transaction.on_commit(lambda: threading.Thread(target=run, name="prices", daemon=True).start())


def refresh_now(ctx: AccessContext) -> dict[str, int]:
    """ "Pobierz notowania": the daily refresh, on demand (takes a few seconds)."""
    require(ctx, "edit")
    return refresh_all()


def _upsert(
    asset: Asset, found: dict[date, Decimal], source: str, factor: Decimal = Decimal(1)
) -> int:
    manual = set(asset.prices.filter(source="manual").values_list("date", flat=True))
    n = 0
    for day, price in found.items():
        if day in manual:  # a hand-entered value wins
            continue
        PriceSnapshot.objects.update_or_create(
            asset=asset,
            date=day,
            defaults={
                "unit_price": (price * factor).quantize(Decimal("0.000001")),
                "source": source,
            },
        )
        n += 1
    return n


OUNCE = Decimal(TROY_OUNCE_G)


def _gold(asset: Asset, start: date, today: date) -> tuple[dict[date, Decimal], str, Decimal]:
    """NBP: PLN per gram of pure gold."""
    factor = OUNCE if asset.unit == Asset.Unit.OZ else Decimal(1)
    return prices.nbp_gold(start, today), "nbp", factor


def _silver(asset: Asset, start: date, today: date) -> tuple[dict[date, Decimal], str, Decimal]:
    """Yahoo: COMEX silver, USD per troy ounce."""
    currency, found = prices.yahoo_history(prices.SILVER_SYMBOL, start, today)
    factor = Decimal(1) if asset.unit == Asset.Unit.OZ else 1 / OUNCE
    return prices.to_pln(found, currency), "yahoo", factor


def _stock(asset: Asset, start: date, today: date) -> tuple[dict[date, Decimal], str, Decimal]:
    currency, found = prices.yahoo_history(asset.symbol, start, today)
    return prices.to_pln(found, currency), "yahoo", Decimal(1)


def _crypto(asset: Asset, start: date, today: date) -> tuple[dict[date, Decimal], str, Decimal]:
    found = prices.coingecko_history(asset.symbol, start, today)
    now = prices.coingecko_now([asset.symbol]).get(asset.symbol)
    if now is not None:
        found[today] = now
    return found, "coingecko", Decimal(1)


# kind -> (needs a symbol, fetcher)
FETCHERS = {
    Asset.Kind.GOLD: (False, _gold),
    Asset.Kind.SILVER: (False, _silver),
    Asset.Kind.STOCK: (True, _stock),
    Asset.Kind.CRYPTO: (True, _crypto),
}


def refresh_asset_prices(asset: Asset, today: date | None = None) -> int:
    """Download missing daily prices since the first purchase (gold, silver,
    stocks/ETFs with a symbol, crypto). Hand-entered values are kept."""
    today = today or timezone.localdate()
    needs_symbol, fetch = FETCHERS.get(asset.kind, (False, None))
    first = asset.lots.order_by("bought_on").values_list("bought_on", flat=True).first()
    if fetch is None or first is None or asset.archived_at or (needs_symbol and not asset.symbol):
        return 0
    last = (
        asset.prices.exclude(source="manual")
        .order_by("-date")
        .values_list("date", flat=True)
        .first()
    )
    start = min(max(first, last + timedelta(days=1)) if last else first, today)
    found, source, factor = fetch(asset, start, today)
    return _upsert(asset, found, source, factor)


def refresh_inflation() -> int:
    """Official GUS figures (they replace hand-entered ones)."""
    rows = prices.gus_cpi()
    for (year, month), index in rows.items():
        InflationIndex.objects.update_or_create(
            year=year, month=month, defaults={"index": index, "manual": False}
        )
    return len(rows)


def refresh_all() -> dict[str, int]:
    out = {"prices": 0, "inflation": 0, "errors": 0}
    for asset in Asset.objects.filter(
        archived_at__isnull=True, kind__in=["gold", "silver", "crypto", "stock"]
    ):
        try:
            out["prices"] += refresh_asset_prices(asset)
        except prices.PriceError as exc:
            out["errors"] += 1
            log.warning("price refresh failed for %s: %s", asset.name, exc)
    if Asset.objects.filter(archived_at__isnull=True, kind="bond").exists():
        try:
            out["inflation"] = refresh_inflation()
        except prices.PriceError as exc:
            out["errors"] += 1
            log.warning("GUS inflation download failed: %s", exc)
    return out
