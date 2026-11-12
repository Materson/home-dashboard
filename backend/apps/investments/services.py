"""Investment writes (finance:edit) and the daily price refresh."""

from __future__ import annotations

import logging
import threading
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
from .selectors import family_users, get_asset, get_lot, require

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
    require(ctx, "edit")
    lot = get_lot(ctx, lot_id, "edit") if lot_id else Lot(asset=get_asset(ctx, asset_id, "edit"))
    for k, v in data.items():
        setattr(lot, k, v)
    if lot.quantity is None or lot.quantity <= 0:
        raise ValueError("quantity must be more than 0")
    if lot.price_total is None or lot.price_total < 0:
        raise ValueError("the price can't be negative")
    if lot.bought_on > timezone.localdate():
        raise ValueError("the purchase date is in the future")
    if lot.sold_on and lot.sold_on < lot.bought_on:
        raise ValueError("sold before it was bought")
    lot.save()
    schedule_refresh(lot.asset_id)
    return lot


@atomic
def sell_lot(
    ctx: AccessContext,
    lot_id: UUID,
    *,
    sold_on: date,
    sold_amount: Decimal,
) -> Lot:
    require(ctx, "edit")
    lot = get_lot(ctx, lot_id, "edit")
    if sold_on < lot.bought_on:
        raise ValueError("sold before it was bought")
    if sold_amount < 0:
        raise ValueError("the amount can't be negative")
    lot.sold_on, lot.sold_amount = sold_on, sold_amount
    lot.save(update_fields=["sold_on", "sold_amount", "updated_at"])
    return lot


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
