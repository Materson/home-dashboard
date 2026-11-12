"""Investments: bond maths, price parsers (shapes as the live sources return
them), valuation, manual values, selling, Finance link, permissions.
Network calls are replaced with fakes."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.utils import timezone

from apps.access.context import AccessContext
from apps.investments import bonds, prices, selectors, services
from apps.investments.models import InflationIndex, PriceSnapshot

from .factories import AccessGrantFactory, PersonFactory, UserFactory

pytestmark = pytest.mark.django_db
D = Decimal


# ---------------- bonds ----------------


def test_cpi_month_is_the_one_announced_the_month_before():
    # A period starting in November uses the September figure (announced in October).
    assert bonds.cpi_month_for(date(2026, 11, 1)) == (2026, 9)
    assert bonds.cpi_month_for(date(2026, 1, 15)) == (2025, 11)


def test_edo_capitalises_yearly_with_inflation_plus_margin():
    cpi = {(2025, 9): D("102.9")}
    bought = date(2024, 11, 1)
    one_year, est = bonds.value_on("EDO", bought, D("6.80"), D("2.00"), cpi, date(2025, 11, 1))
    assert one_year == D("106.8000") and not est
    ps = bonds.periods("EDO", bought, D("6.80"), D("2.00"), cpi)
    assert (ps[1].rate, ps[1].source, ps[1].inflation) == (D("4.90"), "inflation", D("102.9"))
    two_years, _ = bonds.value_on(
        "EDO", bought, D("6.80"), D("2.00"), cpi | {(2026, 9): D("104.1")}, date(2026, 11, 1)
    )
    assert two_years == (D("106.80") * D("1.049")).quantize(D("0.0001"))
    halfway, _ = bonds.value_on("EDO", bought, D("6.80"), D("2.00"), cpi, date(2025, 5, 3))
    assert D("103.3") < halfway < D("103.5")  # ~half of 6.80 %


def test_deflation_counts_as_zero_and_unknown_cpi_is_an_estimate():
    ps = bonds.periods("ROS", date(2020, 3, 1), D("1.70"), D("2.00"), {(2021, 1): D("99.5")})
    assert ps[1].rate == D("2.00")  # margin only
    _, estimated = bonds.value_on(
        "ROS", date(2020, 3, 1), D("1.70"), D("2.00"), {}, date(2021, 6, 1)
    )
    assert estimated  # year 2's CPI unknown → last known rate used


def test_coi_pays_interest_out_every_year():
    cpi = {(2025, 9): D("102.9")}
    bought = date(2024, 11, 1)
    value, _ = bonds.value_on("COI", bought, D("6.55"), D("1.50"), cpi, date(2025, 11, 1))
    assert value == D("100.0000")  # year 1 interest was paid out
    assert bonds.paid_out("COI", bought, D("6.55"), D("1.50"), cpi, date(2025, 11, 1)) == D("6.55")
    mid, _ = bonds.value_on("COI", bought, D("6.55"), D("1.50"), cpi, date(2026, 5, 2))
    assert D("102") < mid < D("102.3")  # 4.40 % for ~half a year


def test_fixed_and_short_bonds():
    tos, _ = bonds.value_on("TOS", date(2023, 1, 10), D("4.40"), None, {}, date(2026, 1, 10))
    assert tos == (D(100) * D("1.044") ** 3).quantize(D("0.0001"))
    ots, _ = bonds.value_on("OTS", date(2026, 1, 1), D("2.00"), None, {}, date(2026, 4, 1))
    assert ots == D("100.5000")
    ror, _ = bonds.value_on("ROR", date(2026, 1, 1), D("4.00"), None, {}, date(2026, 6, 16))
    assert D("100.1") < ror < D("100.2")  # half a month of 4 % a year


# ---------------- parsers (shapes of the live responses) ----------------


def test_parse_nbp_gold():
    rows = [{"data": "2026-11-10", "cena": 516.29}, {"data": "2026-11-12", "cena": 513.76}]
    assert prices.parse_nbp_gold(rows) == {
        date(2026, 11, 10): D("516.29"),
        date(2026, 11, 12): D("513.76"),
    }


def test_parse_coingecko_history():
    body = {
        "prices": [[1791072000000, 330135.26943], [1791158400000, 337019.44]],
        "market_caps": [],
    }
    out = prices.parse_coingecko_history(body)
    assert list(out.values()) == [D("330135.26943"), D("337019.44")]


def test_parse_gus_cpi_csv_in_windows_1250():
    name = "Wskaźnik cen towarów i usług konsumpcyjnych;Polska"
    yoy = "Analogiczny miesiąc poprzedniego roku = 100"
    text = (
        "Nazwa zmiennej;Jednostka terytorialna;Sposób prezentacji;Rok;Miesiąc;Wartość;Flaga;;\n"
        f"{name};{yoy};2026;9;104,1;;;\n"
        f"{name};{yoy};2026;10;;;;\n"  # announced later: empty for now
        f"{name};Poprzedni miesiąc = 100;2026;9;100,1;;;\n"  # another series
    )
    assert prices.parse_gus_cpi(text.encode("cp1250")) == {(2026, 9): D("104.1")}


# ---------------- services ----------------


@pytest.fixture
def fin():
    editor, spouse, viewer, outsider = UserFactory(), UserFactory(), UserFactory(), UserFactory()
    AccessGrantFactory(user=editor, module="finance", level="edit")
    AccessGrantFactory(user=spouse, module="finance", level="edit")
    AccessGrantFactory(user=viewer, module="finance", level="view")
    AccessGrantFactory(user=outsider, module="health", level="view")
    for user, name in ((editor, "Mateusz"), (spouse, "Ola"), (viewer, "Zosia")):
        PersonFactory(display_name=name, user=user)
    return {
        "ctx": AccessContext.for_user(editor),
        "spouse": AccessContext.for_user(spouse),
        "viewer": AccessContext.for_user(viewer),
        "outsider": AccessContext.for_user(outsider),
        "user": editor,
        "spouse_user": spouse,
        "viewer_user": viewer,
    }


def asset(fin, **data):
    return services.save_asset(fin["ctx"], {"name": "x", "kind": "other", **data})


def lot(fin, a, qty, paid, on, **kw):
    return services.save_lot(
        fin["ctx"],
        {"bought_on": on, "quantity": D(qty), "price_total": D(paid)},
        asset_id=a.id,
        **kw,
    )


def test_gold_in_ounces_is_priced_from_nbp_per_gram(fin, monkeypatch):
    coin = asset(fin, name="Krugerrand 1/10 oz", kind="gold", unit="oz")
    today = timezone.localdate()
    lot(fin, coin, "0.1", "1500", today - timedelta(days=3))
    monkeypatch.setattr(
        prices, "nbp_gold", lambda start, end: {today - timedelta(days=1): D("500")}
    )
    services.refresh_asset_prices(coin, today)
    s = selectors.summary(selectors.get_asset(fin["ctx"], coin.id), {})
    assert s.value == (D("0.1") * D("500") * D("31.1034768")).quantize(D("0.01"))  # 1555.17
    assert s.gain == s.value - D("1500")


def test_crypto_fraction_and_series_before_the_first_price(fin, monkeypatch):
    btc = asset(fin, name="Bitcoin", kind="crypto", symbol="Bitcoin ")
    assert btc.symbol == "bitcoin"
    today = timezone.localdate()
    lot(fin, btc, "0.05", "14000", today - timedelta(days=10))
    monkeypatch.setattr(
        prices, "coingecko_history", lambda c, s, e: {today - timedelta(days=5): D("300000")}
    )
    monkeypatch.setattr(prices, "coingecko_now", lambda ids: {"bitcoin": D("320000")})
    services.refresh_asset_prices(btc, today)
    loaded = selectors.get_asset(fin["ctx"], btc.id)
    assert selectors.summary(loaded, {}).value == D("16000.00")
    points = selectors.series([loaded], {})
    assert points[0]["value"] == D("14000.00")  # before any price: what was paid
    assert points[-1] == {"date": today, "value": D("16000.00"), "cost": D("14000.00")}


def test_manual_value_wins_over_downloaded_and_sold_lots_count_as_realized(fin, monkeypatch):
    etf = asset(fin, name="ETF", kind="stock", symbol="SPY")
    today = timezone.localdate()
    first = lot(fin, etf, "10", "1000", today - timedelta(days=30))
    lot(fin, etf, "5", "600", today - timedelta(days=20))
    services.set_value(fin["ctx"], etf.id, on=today, total=D("1800"))  # 15 units → 120 each
    services.sell_lot(
        fin["ctx"], first.id, sold_on=today - timedelta(days=1), sold_amount=D("1150")
    )
    s = selectors.summary(selectors.get_asset(fin["ctx"], etf.id), {})
    assert (s.quantity, s.cost, s.value, s.realized) == (D("5"), D("600"), D("600.00"), D("150.00"))
    with pytest.raises(ValueError):
        services.set_value(
            fin["ctx"],
            asset(fin, kind="bond", bond_type="TOS", bond_first_rate=D("4.4")).id,
            on=today,
            unit_price=D("1"),
        )


def test_bond_lot_value_and_rate_override(fin):
    edo = asset(
        fin,
        name="EDO1134",
        kind="bond",
        bond_type="EDO",
        bond_first_rate=D("6.80"),
        bond_margin=D("2.00"),
    )
    InflationIndex.objects.create(year=2025, month=9, index=D("102.9"))
    held = lot(fin, edo, "30", "3000", date(2024, 11, 1))
    loaded = selectors.get_asset(fin["ctx"], edo.id)
    periods = selectors.bond_schedule(loaded, held, selectors.cpi_table())
    assert periods[1]["rate"] == D("4.90")
    services.set_rate_override(fin["ctx"], held.id, 2, D("5.10"))
    held.refresh_from_db()
    assert selectors.bond_schedule(loaded, held, selectors.cpi_table())[1]["source"] == "override"
    with pytest.raises(ValueError, match="margin"):
        asset(fin, kind="bond", bond_type="COI", bond_first_rate=D("6"))


def test_refresh_survives_a_failing_source(fin, monkeypatch):
    coin = asset(fin, name="Coin", kind="gold", unit="g")
    lot(fin, coin, "1", "500", timezone.localdate() - timedelta(days=2))
    services.set_value(fin["ctx"], coin.id, on=timezone.localdate(), unit_price=D("510"))

    def boom(start, end):
        raise prices.PriceError("down")

    monkeypatch.setattr(prices, "nbp_gold", boom)
    assert services.refresh_all()["errors"] == 1
    monkeypatch.setattr(prices, "nbp_gold", lambda s, e: {timezone.localdate(): D("400")})
    services.refresh_all()
    assert PriceSnapshot.objects.get(asset=coin, date=timezone.localdate()).unit_price == D(
        "510"
    )  # manual kept


def test_inflation_by_hand_then_official(fin, monkeypatch):
    services.add_inflation(fin["ctx"], 2026, 10, D("104.3"))
    with pytest.raises(ValueError):
        services.add_inflation(fin["ctx"], 2026, 13, D("104"))
    monkeypatch.setattr(prices, "gus_cpi", lambda: {(2026, 10): D("104.2")})
    services.refresh_inflation()
    row = InflationIndex.objects.get(year=2026, month=10)
    assert (row.index, row.manual) == (D("104.2"), False)


def test_investments_are_private_unless_shared(fin):
    gold = asset(fin, name="Złoto", kind="gold", unit="g")
    buy = {"bought_on": date(2026, 1, 1), "quantity": D(1), "price_total": D(1)}
    # Another parent with finance access doesn't see it at all.
    assert list(selectors.list_assets(fin["spouse"])) == []
    with pytest.raises(Http404):
        selectors.get_asset(fin["spouse"], gold.id)

    services.set_shares(
        fin["ctx"],
        gold.id,
        [{"user_id": fin["spouse_user"].pk, "can_edit": True}, {"user_id": fin["viewer_user"].pk}],
    )
    assert [a.name for a in selectors.list_assets(fin["spouse"])] == ["Złoto"]
    services.save_lot(fin["spouse"], buy, asset_id=gold.id)  # edit share: may add a purchase
    with pytest.raises(PermissionDenied):  # view share: may not
        services.save_lot(fin["viewer"], buy, asset_id=gold.id)
    # sharing and removing stay with the owner
    for action in (
        lambda: services.set_shares(fin["spouse"], gold.id, []),
        lambda: services.archive_asset(fin["spouse"], gold.id),
    ):
        with pytest.raises(PermissionDenied):
            action()
    with pytest.raises(ValueError, match="family"):
        services.set_shares(fin["ctx"], gold.id, [{"user_id": UserFactory().pk}])
    with pytest.raises(PermissionDenied):  # no finance access at all
        selectors.list_assets(fin["outsider"])


def test_shared_with_me_is_marked_in_the_api(client, fin):
    gold = asset(fin, name="Złoto", kind="gold", unit="g")
    services.set_shares(fin["ctx"], gold.id, [{"user_id": fin["spouse_user"].pk}])
    client.force_login(fin["spouse_user"])
    [row] = client.get("/api/investments/assets").json()
    assert (row["is_owner"], row["can_edit"], row["owner_name"]) == (False, False, "Mateusz")
    names = {p["name"] for p in client.get("/api/investments/people").json()}
    assert names == {"Mateusz", "Zosia"}


def test_api_portfolio(client, fin):
    client.force_login(fin["user"])
    resp = client.post(
        "/api/investments/assets",
        {"name": "Obligacje TOS", "kind": "bond", "bond_type": "TOS", "bond_first_rate": "4.40"},
        content_type="application/json",
    )
    assert resp.status_code == 200, resp.content
    asset_id = resp.json()["id"]
    resp = client.post(
        f"/api/investments/assets/{asset_id}/lots",
        {
            "bought_on": str(timezone.localdate() - timedelta(days=365)),
            "quantity": "10",
            "price_total": "1000",
        },
        content_type="application/json",
    )
    assert resp.status_code == 200, resp.content
    body = client.get("/api/investments/portfolio").json()
    assert Decimal(body["value"]) > Decimal("1040") and Decimal(body["cost"]) == Decimal("1000")
    assert set(body["by_kind"]) == {"bond"} and body["series"]
    assert client.get(f"/api/investments/assets/{asset_id}/series").status_code == 200
    bad = client.post(
        "/api/investments/assets", {"name": "x", "kind": "crypto"}, content_type="application/json"
    )
    assert bad.status_code == 422


# ---------------- deposits ("other" with interest) ----------------


def test_deposit_simple_interest_stops_at_the_end_of_the_term():
    from apps.investments.deposits import value_on  # noqa: PLC0415

    start = date(2026, 1, 1)
    half = value_on(D("10000"), start, date(2026, 7, 2), rate=D("6"), term_months=6)
    assert half == (D("10000") * (1 + D("0.06") * D(181) / 365)).quantize(D("0.01"))  # 6 months
    later = value_on(D("10000"), start, date(2027, 1, 1), rate=D("6"), term_months=6)
    assert later == half  # nothing after the term


def test_deposit_monthly_compounding():
    from apps.investments.deposits import value_on  # noqa: PLC0415

    year = value_on(
        D("1000"), date(2026, 1, 1), date(2027, 1, 1), rate=D("12"), compounding="monthly"
    )
    assert year == (D("1000") * D("1.01") ** 12).quantize(D("0.01"))  # 1126.83


def test_other_with_interest_is_valued_from_the_rate(fin):
    savings = asset(fin, name="Lokata", rate=D("5"), compounding="none", term_months=12)
    today = timezone.localdate()
    lot(fin, savings, "1", "10000", today - timedelta(days=73))
    s = selectors.summary(selectors.get_asset(fin["ctx"], savings.id), {})
    assert s.value == (D("10000") * (1 + D("0.05") * D(73) / 365)).quantize(D("0.01"))  # +100
    with pytest.raises(ValueError, match="negative"):
        asset(fin, name="x", rate=D("-1"))
    plain = asset(fin, name="Srebro", kind="gold", unit="g", rate=D("5"))
    assert plain.rate is None  # interest only for "other"


def test_saving_a_purchase_doesnt_wait_for_prices(
    fin, monkeypatch, django_capture_on_commit_callbacks
):
    """The price download runs after the commit in a thread — the request
    never waits for a task queue (which hung when Redis was down)."""
    started, refreshed = [], []

    class InlineThread:
        def __init__(self, target, **kw):
            self.target = target

        def start(self):
            started.append(True)
            self.target()

    monkeypatch.setattr(services.threading, "Thread", InlineThread)
    monkeypatch.setattr(
        services, "connection", type("C", (), {"close": staticmethod(lambda: None)})
    )
    monkeypatch.setattr(services, "refresh_asset_prices", lambda a: refreshed.append(a.name) or 0)
    coin = asset(fin, name="Coin", kind="gold", unit="g")
    with django_capture_on_commit_callbacks(execute=True):
        lot(fin, coin, "1", "500", date(2020, 5, 4))
    assert started and refreshed == ["Coin"]


def test_portfolio_filters_by_kind_and_dates(client, fin):
    client.force_login(fin["user"])
    gold = asset(fin, name="Złoto", kind="gold", unit="g")
    lot(fin, gold, "10", "3000", date(2025, 1, 10))
    savings = asset(fin, name="Lokata", rate=D("5"))
    lot(fin, savings, "1", "10000", date(2025, 6, 1))
    only_other = client.get("/api/investments/portfolio", {"kind": "other"}).json()
    assert set(only_other["by_kind"]) == {"other"} and Decimal(only_other["cost"]) == D("10000")
    ranged = client.get(
        "/api/investments/portfolio", {"date_from": "2025-02-01", "date_to": "2025-03-01"}
    ).json()
    assert (
        ranged["series"][0]["date"] == "2025-02-01" and ranged["series"][-1]["date"] == "2025-03-01"
    )
    assert all(Decimal(p["cost"]) == D("3000") for p in ranged["series"])  # before the deposit


def test_closed_positions_can_be_left_out_of_the_chart(fin):
    etf = asset(fin, name="ETF", kind="stock")
    today = timezone.localdate()
    old = lot(fin, etf, "1", "100", today - timedelta(days=20))
    lot(fin, etf, "1", "200", today - timedelta(days=10))
    services.sell_lot(fin["ctx"], old.id, sold_on=today - timedelta(days=5), sold_amount=D("120"))
    loaded = [selectors.get_asset(fin["ctx"], etf.id)]
    everything = selectors.series(loaded, {})
    assert everything[0]["cost"] == D("100.00")  # the sold lot, while it was held
    open_only = selectors.series(loaded, {}, open_only=True)
    assert open_only[0]["date"] == today - timedelta(days=10)
    assert {p["cost"] for p in open_only} == {D("200.00")}


# ---------------- Yahoo (stocks, ETFs, silver) ----------------


def _yahoo(currency, closes, stamps=(1794470400, 1794556800), offset=0):
    return {
        "chart": {
            "result": [
                {
                    "meta": {"currency": currency, "gmtoffset": offset},
                    "timestamp": list(stamps),
                    "indicators": {"quote": [{"close": list(closes)}]},
                }
            ]
        }
    }


def test_parse_yahoo_pence_and_gaps():
    currency, found = prices.parse_yahoo(_yahoo("GBp", [10826.0, None]))
    assert currency == "GBP" and list(found.values()) == [
        D("108.26")
    ]  # pence → pounds, gap skipped
    with pytest.raises(prices.PriceError, match="delisted"):
        prices.parse_yahoo(
            {"chart": {"result": None, "error": {"description": "symbol may be delisted"}}}
        )


def test_to_pln_uses_the_last_published_rate(monkeypatch):
    fri, sat = date(2026, 11, 6), date(2026, 11, 7)
    monkeypatch.setattr(prices, "nbp_fx", lambda code, s, e: {fri: D("4.00")})
    assert prices.to_pln({fri: D("10"), sat: D("11")}, "USD") == {fri: D("40.00"), sat: D("44.00")}
    assert prices.to_pln({fri: D("10")}, "PLN") == {fri: D("10")}


def test_stock_and_silver_are_priced_from_yahoo(fin, monkeypatch):
    today = timezone.localdate()
    etf = asset(fin, name="S&P 500", kind="stock", symbol=" cspx.l ")
    assert etf.symbol == "CSPX.L"
    silver = asset(fin, name="Srebro", kind="silver", unit="g")
    lot(fin, etf, "2", "6000", today - timedelta(days=5))
    lot(fin, silver, "31.1034768", "6000", today - timedelta(days=5))
    calls = []

    def fake(symbol, start, end):
        calls.append(symbol)
        return "USD", {today: D("800") if symbol == "CSPX.L" else D("50")}

    monkeypatch.setattr(prices, "yahoo_history", fake)
    monkeypatch.setattr(prices, "nbp_fx", lambda code, s, e: {today: D("4")})
    services.refresh_asset_prices(etf, today)
    services.refresh_asset_prices(silver, today)
    assert calls == ["CSPX.L", prices.SILVER_SYMBOL]
    assert selectors.summary(selectors.get_asset(fin["ctx"], etf.id), {}).value == D("6400.00")
    # one troy ounce of silver at 50 USD x 4 PLN
    assert selectors.summary(selectors.get_asset(fin["ctx"], silver.id), {}).value == D("200.00")


def test_parse_nbp_table():
    day, rates = prices.parse_nbp_table(
        [
            {
                "table": "A",
                "effectiveDate": "2026-11-12",
                "rates": [{"code": "USD", "mid": 3.6512}, {"code": "EUR", "mid": 4.2511}],
            }
        ]
    )
    assert (day, rates["USD"], rates["EUR"]) == (date(2026, 11, 12), D("3.6512"), D("4.2511"))
    with pytest.raises(prices.PriceError):
        prices.parse_nbp_table([])


def test_fx_rates_for_showing_values_in_usd_or_eur(client, fin, monkeypatch):
    from django.core.cache import cache  # noqa: PLC0415

    cache.delete(selectors.FX_CACHE_KEY)
    calls = []

    def latest():
        calls.append(1)
        return date(2026, 11, 12), {"USD": D("3.65"), "EUR": D("4.25"), "CHF": D("4.6")}

    monkeypatch.setattr(prices, "nbp_latest", latest)
    client.force_login(fin["viewer_user"])
    body = client.get("/api/investments/fx").json()
    assert body == {"date": "2026-11-12", "rates": {"USD": "3.65", "EUR": "4.25"}}
    client.get("/api/investments/fx")
    assert len(calls) == 1  # cached
    with pytest.raises(PermissionDenied):  # no finance, no rates
        selectors.fx_rates(fin["outsider"])

    cache.delete(selectors.FX_CACHE_KEY)

    def down():
        raise prices.PriceError("NBP down")

    monkeypatch.setattr(prices, "nbp_latest", down)
    assert client.get("/api/investments/fx").status_code == 422
    cache.delete(selectors.FX_CACHE_KEY)


def test_selling_part_of_a_purchase_splits_it(fin):
    today = timezone.localdate()
    btc = asset(fin, name="BTC", kind="crypto", symbol="bitcoin")
    bought = lot(fin, btc, "0.3", "30000", today - timedelta(days=100))
    sold = services.sell_lot(
        fin["ctx"], bought.id, sold_on=today, sold_amount=D("15000"), quantity=D("0.1")
    )
    bought.refresh_from_db()
    assert (sold.quantity, sold.price_total, sold.sold_amount) == (D("0.1"), D("10000"), D("15000"))
    assert (sold.bought_on, sold.sold_on) == (bought.bought_on, today)
    assert (bought.quantity, bought.price_total, bought.sold_on) == (D("0.2"), D("20000"), None)
    s = selectors.summary(selectors.get_asset(fin["ctx"], btc.id), {})
    assert (s.quantity, s.cost, s.realized) == (D("0.2"), D("20000"), D("5000"))

    # all of what's left: no split; more than held, or a sold lot's part: refused
    with pytest.raises(ValueError, match="more than"):
        services.sell_lot(fin["ctx"], bought.id, sold_on=today, sold_amount=D("1"), quantity=D("1"))
    with pytest.raises(ValueError, match="already sold"):
        services.sell_lot(
            fin["ctx"], sold.id, sold_on=today, sold_amount=D("1"), quantity=D("0.05")
        )
    with pytest.raises(ValueError, match="future"):
        services.sell_lot(
            fin["ctx"], bought.id, sold_on=today + timedelta(days=1), sold_amount=D("1")
        )
    whole = services.sell_lot(fin["ctx"], bought.id, sold_on=today, sold_amount=D("31000"))
    assert whole.id == bought.id and btc.lots.count() == 2
    with pytest.raises(PermissionDenied):  # view-only: no selling
        services.sell_lot(fin["viewer"], bought.id, sold_on=today, sold_amount=D("1"))


def test_selling_part_of_a_holding_takes_the_oldest_purchases_first(fin):
    today = timezone.localdate()
    gold = asset(fin, name="Krugerrand", kind="gold", unit="oz")
    first = lot(fin, gold, "2", "16000", today - timedelta(days=300))
    second = lot(fin, gold, "3", "30000", today - timedelta(days=100))
    sold = services.sell_asset(
        fin["ctx"], gold.id, sold_on=today, quantity=D("3"), sold_amount=D("33333.33")
    )
    # all of the first purchase, 1 oz split off the second; the money shared by ounces
    assert [(x.quantity, x.price_total, x.sold_amount) for x in sold] == [
        (D("2"), D("16000"), D("22222.22")),
        (D("1"), D("10000"), D("11111.11")),
    ]
    assert sold[0].id == first.id
    second.refresh_from_db()
    assert (second.quantity, second.price_total, second.sold_on) == (D("2"), D("20000"), None)
    with pytest.raises(ValueError, match="more than"):
        services.sell_asset(
            fin["ctx"], gold.id, sold_on=today, quantity=D("2.5"), sold_amount=D("1")
        )
    with pytest.raises(Http404):  # someone else's investment
        services.sell_asset(
            fin["spouse"], gold.id, sold_on=today, quantity=D("1"), sold_amount=D("1")
        )


def test_bonds_are_sold_whole_and_the_api_sells_part(client, fin):
    today = timezone.localdate()
    tos = asset(fin, name="TOS", kind="bond", bond_type="TOS", bond_first_rate=D("4.40"))
    bonds_lot = lot(fin, tos, "10", "1000", today - timedelta(days=30))
    with pytest.raises(ValueError, match="whole"):
        services.sell_lot(
            fin["ctx"], bonds_lot.id, sold_on=today, sold_amount=D("1"), quantity=D("2.5")
        )
    client.force_login(fin["user"])
    resp = client.post(
        f"/api/investments/lots/{bonds_lot.id}/sell",
        {"sold_on": str(today), "sold_amount": "401.20", "quantity": "4"},
        content_type="application/json",
    )
    assert resp.status_code == 200, resp.content
    assert (D(resp.json()["quantity"]), D(resp.json()["price_total"])) == (D("4"), D("400"))
    resp = client.post(
        f"/api/investments/assets/{tos.id}/sell",
        {"sold_on": str(today), "sold_amount": "100", "quantity": "7"},
        content_type="application/json",
    )
    assert resp.status_code == 422  # only 6 left
    resp = client.post(
        f"/api/investments/assets/{tos.id}/sell",
        {"sold_on": str(today), "sold_amount": "601.80", "quantity": "6"},
        content_type="application/json",
    )
    assert resp.status_code == 200 and [D(x["quantity"]) for x in resp.json()] == [D("6")]


def test_purchases_and_sales_in_another_currency(client, fin, monkeypatch):
    from django.core.cache import cache  # noqa: PLC0415

    cache.clear()
    today = timezone.localdate()
    day = today - timedelta(days=30)
    # NBP has a rate for the day itself, but a purchase uses the one before.
    rates = {day - timedelta(days=3): D("3.90"), day - timedelta(days=1): D("4.00"), day: D("9")}
    asked = []

    def nbp_fx(code, start, end):
        asked.append(code)
        return {d: r for d, r in rates.items() if start <= d <= end}

    monkeypatch.setattr(prices, "nbp_fx", nbp_fx)
    etf = asset(fin, name="S&P 500", kind="stock")
    bought = services.save_lot(
        fin["ctx"],
        {"bought_on": day, "quantity": D("2"), "price_currency": "USD", "price_foreign": D("1000")},
        asset_id=etf.id,
    )
    assert (bought.price_total, bought.price_rate, asked) == (D("4000.00"), D("4.00"), ["USD"])
    # the broker's own rate wins; back to PLN drops the foreign amount
    own = services.save_lot(
        fin["ctx"],
        {
            "bought_on": day,
            "quantity": D("1"),
            "price_currency": "EUR",
            "price_foreign": D("100"),
            "price_rate": D("4.3"),
        },
        asset_id=etf.id,
    )
    assert own.price_total == D("430.00")
    pln = services.save_lot(
        fin["ctx"], {"price_currency": "PLN", "price_total": D("420")}, lot_id=own.id
    )
    assert (pln.price_total, pln.price_foreign, pln.price_rate) == (D("420"), None, None)

    # sell 1 of the 2 for 600 USD at 4.10: split with half the dollars
    sold = services.sell_lot(
        fin["ctx"],
        bought.id,
        sold_on=today,
        quantity=D("1"),
        sold_currency="USD",
        sold_foreign=D("600"),
        sold_rate=D("4.10"),
    )
    assert (sold.sold_amount, sold.sold_foreign, sold.sold_rate) == (
        D("2460.00"),
        D("600"),
        D("4.10"),
    )
    assert (sold.price_total, sold.price_foreign, sold.price_currency) == (
        D("2000.00"),
        D("500.00"),
        "USD",
    )
    bought.refresh_from_db()
    assert (bought.price_total, bought.price_foreign) == (D("2000.00"), D("500.00"))

    # FIFO across two purchases: dollars and zlotys shared by quantity
    parts = services.sell_asset(
        fin["ctx"],
        etf.id,
        sold_on=today,
        quantity=D("2"),
        sold_currency="USD",
        sold_foreign=D("1000.01"),
        sold_rate=D("4"),
    )
    assert [(p.sold_foreign, p.sold_amount) for p in parts] == [
        (D("500.00"), D("2000.02")),  # 500.005 rounds half-even
        (D("500.01"), D("2000.02")),  # the last part gets the rest: nothing lost
    ]

    # NBP unreachable and no rate given: ask for one
    monkeypatch.setattr(prices, "nbp_fx", lambda *a: {})
    with pytest.raises(ValueError, match="enter the rate"):
        services.save_lot(
            fin["ctx"],
            {
                "bought_on": day - timedelta(days=100),
                "quantity": D("1"),
                "price_currency": "GBP",
                "price_foreign": D("10"),
            },
            asset_id=etf.id,
        )
    cache.clear()


def test_fx_rate_endpoint_for_the_purchase_form(client, fin, monkeypatch):
    from django.core.cache import cache  # noqa: PLC0415

    cache.clear()
    day = date(2026, 11, 9)  # a Monday: the rate is Friday's
    monkeypatch.setattr(prices, "nbp_fx", lambda code, s, e: {date(2026, 11, 6): D("3.97")})
    client.force_login(fin["viewer_user"])
    body = client.get(f"/api/investments/fx-rate?currency=EUR&on={day}").json()
    assert body == {
        "currency": "EUR",
        "on": "2026-11-09",
        "rate_date": "2026-11-06",
        "rate": "3.97",
    }
    assert client.get(f"/api/investments/fx-rate?currency=JPY&on={day}").status_code == 422
    with pytest.raises(PermissionDenied):
        selectors.trade_rate(fin["outsider"], "EUR", day)
    cache.clear()


def test_gain_in_a_period(client, fin):
    gold = asset(fin, name="Złoto", kind="gold", unit="g")
    for day, price in (
        (date(2025, 1, 10), "300"),
        (date(2025, 6, 1), "350"),
        (date(2026, 1, 1), "400"),
    ):
        PriceSnapshot.objects.create(asset=gold, date=day, unit_price=D(price), source="manual")
    lot(fin, gold, "10", "3000", date(2025, 1, 10))  # held: 3500 at the start -> 4000
    lot(fin, gold, "5", "1800", date(2025, 9, 1))  # bought during it: 1800 -> 2000
    sold = lot(fin, gold, "2", "600", date(2025, 2, 1))  # 700 at the start, sold for 760
    services.sell_lot(fin["ctx"], sold.id, sold_on=date(2025, 10, 1), sold_amount=D("760"))
    gone = lot(fin, gold, "1", "300", date(2025, 1, 10))  # sold before: not counted
    services.sell_lot(fin["ctx"], gone.id, sold_on=date(2025, 3, 1), sold_amount=D("320"))

    g = selectors.get_asset(fin["ctx"], gold.id)
    period = selectors.period_gain(g, {}, date(2025, 6, 1), date(2026, 1, 1))
    assert (period.gain, period.base, period.gain_pct) == (D("760"), D("6000"), D("12.7"))
    still_held = selectors.period_gain(g, {}, date(2025, 6, 1), date(2026, 1, 1), open_only=True)
    assert (still_held.gain, still_held.base) == (D("700"), D("5300"))

    client.force_login(fin["user"])
    body = client.get("/api/investments/portfolio?date_from=2025-06-01&date_to=2026-01-01").json()
    assert (body["period"]["gain"], body["period"]["start"]) == ("760.00", "2025-06-01")
    assert body["period"]["assets"][str(gold.id)] == {"gain": "760.00", "gain_pct": "12.7"}
    assert client.get("/api/investments/portfolio").json()["period"] is None  # "all": lifetime


def test_period_gain_counts_bond_interest_paid_out(fin):
    coi = asset(
        fin,
        name="COI",
        kind="bond",
        bond_type="COI",
        bond_first_rate=D("5.00"),
        bond_margin=D("1.50"),
    )
    lot(fin, coi, "10", "1000", date(2025, 1, 15))  # 5% for the first year: 50 zł on 15.01.2026
    a = selectors.get_asset(fin["ctx"], coi.id)
    [held] = a.lots.all()
    start, end = date(2025, 6, 1), date(2026, 3, 1)
    pricer = selectors.Pricer(a)
    moved = (
        selectors.lot_value(a, held, end, pricer, {})[0]
        - selectors.lot_value(a, held, start, pricer, {})[0]
    )
    assert selectors.period_gain(a, {}, start, end).gain == (moved + D("50")).quantize(D("0.01"))
