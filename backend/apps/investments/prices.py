"""Public price sources. Only *what* to price is sent (gold, a coin id) —
never quantities or anything about the family. Every fetch has a short
timeout and failing is fine: values can always be entered by hand.

- NBP: gold, PLN per 1 g of 1000-fineness gold, ``/api/cenyzlota/{from}/{to}``
  (≤ 93 days per query, history from 2013-01-02).
- CoinGecko (no key, IP rate-limited): ``/simple/price`` and
  ``/coins/{id}/market_chart/range`` (history limited to the last 365 days).
- GUS: monthly CPI CSV linked from the "since 1982" page (Windows-1250,
  ``;``-separated, decimal comma).
- Yahoo Finance chart data (no key; an *unofficial* interface - it may
  change or rate-limit): stocks/ETFs anywhere (SPY, CSPX.L, SXR8.DE,
  CDR.WA) and COMEX silver; converted to PLN with NBP rates (table A).
"""

from __future__ import annotations

import bisect
import csv
import io
import logging
import re
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from urllib.parse import quote

import httpx

log = logging.getLogger(__name__)

TIMEOUT = 20.0
HEADERS = {"User-Agent": "home-dashboard (self-hosted)", "Accept": "application/json"}
NBP_GOLD = "https://api.nbp.pl/api/cenyzlota/{start}/{end}/?format=json"
NBP_FIRST_DAY = date(2013, 1, 2)
NBP_MAX_DAYS = 93
COINGECKO = "https://api.coingecko.com/api/v3"
COINGECKO_HISTORY_DAYS = 364
GUS_PAGE = (
    "https://stat.gov.pl/obszary-tematyczne/ceny-handel/wskazniki-cen/"
    "wskazniki-cen-towarow-i-uslug-konsumpcyjnych-pot-inflacja-/"
    "miesieczne-wskazniki-cen-towarow-i-uslug-konsumpcyjnych-od-1982-roku/"
)
GUS_ROOT = "https://stat.gov.pl"
YOY = "Analogiczny miesiąc poprzedniego roku = 100"
NBP_FX = "https://api.nbp.pl/api/exchangerates/rates/a/{code}/{start}/{end}/?format=json"
YAHOO = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
# Yahoo's chart data is an unofficial interface; it answers browser-like clients.
YAHOO_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; home-dashboard)",
    "Accept": "application/json",
}
SILVER_SYMBOL = "SI=F"  # COMEX silver, USD per troy ounce (close to spot)
# Prices quoted in minor units: pence, cents.
MINOR_UNITS = {"GBp": "GBP", "GBX": "GBP", "ZAc": "ZAR", "ILA": "ILS"}


class PriceError(RuntimeError):
    pass


def _get(url: str, **params) -> httpx.Response:
    try:
        resp = httpx.get(
            url, params=params or None, headers=HEADERS, timeout=TIMEOUT, follow_redirects=True
        )
    except httpx.HTTPError as exc:
        raise PriceError(f"{url}: {exc}") from exc
    return resp


# ---------------- NBP gold ----------------


def nbp_gold(start: date, end: date) -> dict[date, Decimal]:
    """PLN per gram of pure gold for every day NBP published, in chunks."""
    start = max(start, NBP_FIRST_DAY)
    out: dict[date, Decimal] = {}
    while start <= end:
        chunk_end = min(end, start + timedelta(days=NBP_MAX_DAYS - 1))
        resp = _get(NBP_GOLD.format(start=start.isoformat(), end=chunk_end.isoformat()))
        if resp.status_code == 200:  # noqa: PLR2004
            out.update(parse_nbp_gold(resp.json()))
        elif resp.status_code != 404:  # 404 = no prices in that window  # noqa: PLR2004
            raise PriceError(f"NBP gold: HTTP {resp.status_code}")
        start = chunk_end + timedelta(days=1)
    return out


def parse_nbp_gold(rows: list[dict]) -> dict[date, Decimal]:
    return {date.fromisoformat(r["data"]): Decimal(str(r["cena"])) for r in rows}


# ---------------- CoinGecko ----------------


def coingecko_history(coin_id: str, start: date, end: date) -> dict[date, Decimal]:
    """Daily PLN prices (the public API only goes back 365 days)."""
    start = max(start, end - timedelta(days=COINGECKO_HISTORY_DAYS))
    ts = lambda d: int(datetime(d.year, d.month, d.day, tzinfo=UTC).timestamp())  # noqa: E731
    resp = _get(
        f"{COINGECKO}/coins/{coin_id}/market_chart/range",
        vs_currency="pln",
        to=ts(end + timedelta(days=1)),
        interval="daily",
        **{"from": ts(start)},
    )
    if resp.status_code != 200:  # noqa: PLR2004
        raise PriceError(f"CoinGecko {coin_id}: HTTP {resp.status_code}")
    return parse_coingecko_history(resp.json())


def parse_coingecko_history(body: dict) -> dict[date, Decimal]:
    out: dict[date, Decimal] = {}
    for ms, price in body.get("prices", []):
        day = datetime.fromtimestamp(ms / 1000, tz=UTC).date()
        out[day] = Decimal(str(price))
    return out


def coingecko_now(coin_ids: list[str]) -> dict[str, Decimal]:
    if not coin_ids:
        return {}
    resp = _get(
        f"{COINGECKO}/simple/price", ids=",".join(sorted(set(coin_ids))), vs_currencies="pln"
    )
    if resp.status_code != 200:  # noqa: PLR2004
        raise PriceError(f"CoinGecko price: HTTP {resp.status_code}")
    return {k: Decimal(str(v["pln"])) for k, v in resp.json().items() if "pln" in v}


# ---------------- NBP exchange rates ----------------


def nbp_fx(code: str, start: date, end: date) -> dict[date, Decimal]:
    """Average NBP rate (table A): PLN for 1 unit of ``code``, per published day."""
    out: dict[date, Decimal] = {}
    while start <= end:
        chunk_end = min(end, start + timedelta(days=NBP_MAX_DAYS - 1))
        url = NBP_FX.format(code=code.lower(), start=start.isoformat(), end=chunk_end.isoformat())
        resp = _get(url)
        if resp.status_code == 200:  # noqa: PLR2004
            out.update(parse_nbp_fx(resp.json()))
        elif resp.status_code != 404:  # noqa: PLR2004
            raise PriceError(f"NBP {code}: HTTP {resp.status_code}")
        start = chunk_end + timedelta(days=1)
    return out


def parse_nbp_fx(body: dict) -> dict[date, Decimal]:
    return {
        date.fromisoformat(r["effectiveDate"]): Decimal(str(r["mid"]))
        for r in body.get("rates", [])
    }


def to_pln(found: dict[date, Decimal], currency: str) -> dict[date, Decimal]:
    """Convert daily prices to PLN at each day's NBP rate (the last one
    published on or before that day - no rates on weekends/holidays)."""
    if currency == "PLN" or not found:
        return found
    days = sorted(found)
    rates = nbp_fx(currency, days[0] - timedelta(days=10), days[-1])
    rate_days = sorted(rates)
    out = {}
    for day in days:
        i = bisect.bisect_right(rate_days, day) - 1
        if i >= 0:
            out[day] = found[day] * rates[rate_days[i]]
    return out


# ---------------- Yahoo Finance (stocks, ETFs, silver) ----------------


def _unix(d: date) -> int:
    return int(datetime(d.year, d.month, d.day, tzinfo=UTC).timestamp())


def yahoo_history(symbol: str, start: date, end: date) -> tuple[str, dict[date, Decimal]]:
    """Daily closes and their currency (pence etc. already turned into pounds)."""
    try:
        resp = httpx.get(
            YAHOO.format(symbol=quote(symbol, safe="")),
            params={
                "period1": _unix(start),
                "period2": _unix(end + timedelta(days=1)),
                "interval": "1d",
            },
            headers=YAHOO_HEADERS,
            timeout=TIMEOUT,
            follow_redirects=True,
        )
    except httpx.HTTPError as exc:
        raise PriceError(f"Yahoo {symbol}: {exc}") from exc
    if resp.status_code == 404:  # noqa: PLR2004
        raise PriceError(f"Yahoo: unknown symbol {symbol!r}")
    if resp.status_code != 200:  # noqa: PLR2004
        raise PriceError(f"Yahoo {symbol}: HTTP {resp.status_code}")
    return parse_yahoo(resp.json())


def parse_yahoo(body: dict) -> tuple[str, dict[date, Decimal]]:
    chart = body.get("chart") or {}
    results = chart.get("result") or []
    if not results:
        detail = (chart.get("error") or {}).get("description") or "no data"
        raise PriceError(f"Yahoo: {detail}")
    r = results[0]
    meta = r.get("meta") or {}
    currency = meta.get("currency") or "USD"
    offset = int(meta.get("gmtoffset") or 0)
    closes = ((r.get("indicators") or {}).get("quote") or [{}])[0].get("close") or []
    divisor = Decimal(100) if currency in MINOR_UNITS else Decimal(1)
    currency = MINOR_UNITS.get(currency, currency)
    out: dict[date, Decimal] = {}
    for stamp, close in zip(r.get("timestamp") or [], closes, strict=False):
        if close is None:
            continue
        day = datetime.fromtimestamp(stamp + offset, tz=UTC).date()  # the exchange's day
        out[day] = Decimal(str(close)) / divisor
    return currency, out


# ---------------- GUS CPI ----------------


def gus_cpi() -> dict[tuple[int, int], Decimal]:
    """Monthly CPI y/y from the GUS CSV (the file's link is read from the page)."""
    page = _get(GUS_PAGE)
    if page.status_code != 200:  # noqa: PLR2004
        raise PriceError(f"GUS page: HTTP {page.status_code}")
    match = re.search(r'href="([^"]+\.csv)"', page.text)
    if not match:
        raise PriceError("GUS page: no CSV link")
    url = match.group(1)
    resp = _get(url if url.startswith("http") else GUS_ROOT + url)
    if resp.status_code != 200:  # noqa: PLR2004
        raise PriceError(f"GUS CSV: HTTP {resp.status_code}")
    return parse_gus_cpi(resp.content)


def parse_gus_cpi(raw: bytes) -> dict[tuple[int, int], Decimal]:
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp1250")
    out: dict[tuple[int, int], Decimal] = {}
    reader = csv.reader(io.StringIO(text), delimiter=";")
    next(reader, None)  # header
    for row in reader:
        if len(row) < 6 or row[2].strip() != YOY or not row[5].strip():  # noqa: PLR2004
            continue
        try:
            out[(int(row[3]), int(row[4]))] = Decimal(row[5].strip().replace(",", "."))
        except (ValueError, InvalidOperation):
            continue
    return out
