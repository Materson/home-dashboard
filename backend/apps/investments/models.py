"""Investments: what the family holds and what it's worth over time.

- ``Asset``: one kind of holding — a gold coin type, a cryptocurrency, a
  stock/ETF, a treasury bond series, or anything else valued by hand.
- ``Lot``: one purchase of it — date, quantity (fractions allowed: 0.1 oz,
  0.05 BTC, 30 bonds) and what was paid; optionally sold later. Amounts are
  in PLN; one paid / received in another currency also keeps that amount and
  the rate it was converted at.
- ``PriceSnapshot``: the price of one unit of an asset on a day (NBP gold,
  CoinGecko crypto, or entered by hand). Bonds aren't priced — their value
  is computed from the bond's rules and ``InflationIndex`` (see ``bonds``).
- ``InflationIndex``: GUS monthly CPI, same month of previous year = 100.

Access: the ``finance`` module (a child without finance sees none of it),
and then each investment is private to the one who added it unless shared
(``AssetShare``: view or edit) — like notes.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.core.models import Archivable, TimeStamped, UUIDModel, money_amount_field

TROY_OUNCE_G = "31.1034768"


class Asset(UUIDModel, TimeStamped, Archivable):
    class Kind(models.TextChoices):
        GOLD = "gold", "Gold (NBP price)"
        SILVER = "silver", "Silver (COMEX price via Yahoo)"
        CRYPTO = "crypto", "Cryptocurrency (CoinGecko)"
        STOCK = "stock", "Stock / ETF (Yahoo Finance; manual without a symbol)"
        BOND = "bond", "Polish treasury bond"
        OTHER = "other", "Other (manual value)"

    class Unit(models.TextChoices):
        OZ = "oz", "troy ounce"
        G = "g", "gram"
        PIECE = "pcs", "piece / unit"

    name = models.CharField(max_length=120)
    kind = models.CharField(max_length=10, choices=Kind.choices)
    # Gold: fine-gold weight unit; crypto/stock/other: units held.
    unit = models.CharField(max_length=4, choices=Unit.choices, default=Unit.PIECE)
    # Crypto: CoinGecko id ("bitcoin"); stock/ETF: Yahoo symbol ("CSPX.L").
    symbol = models.CharField(max_length=60, blank=True)
    person = models.ForeignKey(
        "people.Person", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    # Bonds: series type (EDO, COI, ROS, ROD, TOS, OTS, ROR, DOR), the first
    # period's rate and the margin over inflation / the NBP rate (in %).
    bond_type = models.CharField(max_length=3, blank=True)
    bond_first_rate = models.DecimalField(max_digits=6, decimal_places=3, null=True, blank=True)
    bond_margin = models.DecimalField(max_digits=6, decimal_places=3, null=True, blank=True)
    # "Other" with interest (a deposit, a savings account): % a year, how
    # often interest is added, and the term (empty = open-ended).
    rate = models.DecimalField(max_digits=6, decimal_places=3, null=True, blank=True)
    compounding = models.CharField(max_length=10, blank=True, default="none")
    term_months = models.PositiveSmallIntegerField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name

    # The owner is ``created_by``; others see it only when it's shared with them.
    def share_for(self, user_id) -> AssetShare | None:
        return next((s for s in self.shares.all() if s.user_id == user_id), None)

    def can_view(self, user_id) -> bool:
        return self.created_by_id == user_id or self.share_for(user_id) is not None

    def can_edit(self, user_id) -> bool:
        share = self.share_for(user_id)
        return self.created_by_id == user_id or bool(share and share.can_edit)


class AssetShare(models.Model):
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name="shares")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    can_edit = models.BooleanField(default=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["asset", "user"], name="one_asset_share")]

    def __str__(self) -> str:
        return f"{self.asset_id} -> {self.user_id}"


class Lot(UUIDModel, TimeStamped):
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name="lots")
    bought_on = models.DateField(db_index=True)
    quantity = models.DecimalField(max_digits=20, decimal_places=8)
    price_total = money_amount_field(help_text="What was paid for the whole lot (PLN).")
    sold_on = models.DateField(null=True, blank=True)
    sold_amount = money_amount_field(null=True, blank=True, help_text="What it was sold for.")
    # Paid / received in another currency: that amount and the PLN rate used
    # (NBP's from the last working day before, or the broker's own).
    price_currency = models.CharField(max_length=3, default="PLN")
    price_foreign = money_amount_field(null=True, blank=True)
    price_rate = models.DecimalField(max_digits=12, decimal_places=6, null=True, blank=True)
    sold_currency = models.CharField(max_length=3, default="PLN")
    sold_foreign = money_amount_field(null=True, blank=True)
    sold_rate = models.DecimalField(max_digits=12, decimal_places=6, null=True, blank=True)
    # Bonds: a period's rate as the bank shows it, if it differs from ours
    # ({"2": "6.10"} = the 2nd year). Periods count from 1.
    rate_overrides = models.JSONField(default=dict, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ("bought_on", "created_at")

    def __str__(self) -> str:
        return f"{self.asset.name}: {self.quantity} @ {self.bought_on}"


class PriceSnapshot(models.Model):
    class Source(models.TextChoices):
        NBP = "nbp", "NBP"
        COINGECKO = "coingecko", "CoinGecko"
        YAHOO = "yahoo", "Yahoo Finance"
        MANUAL = "manual", "Manual"

    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name="prices")
    date = models.DateField()
    unit_price = models.DecimalField(max_digits=20, decimal_places=6, help_text="PLN per unit.")
    source = models.CharField(max_length=10, choices=Source.choices)

    class Meta:
        ordering = ("date",)
        constraints = [models.UniqueConstraint(fields=["asset", "date"], name="one_price_a_day")]

    def __str__(self) -> str:
        return f"{self.asset_id} {self.date}: {self.unit_price}"


class InflationIndex(models.Model):
    """GUS CPI, same month of the previous year = 100 (e.g. 104.1 = 4.1%)."""

    year = models.PositiveSmallIntegerField()
    month = models.PositiveSmallIntegerField()
    index = models.DecimalField(max_digits=6, decimal_places=2)
    manual = models.BooleanField(default=False)

    class Meta:
        ordering = ("year", "month")
        constraints = [models.UniqueConstraint(fields=["year", "month"], name="one_cpi_a_month")]

    def __str__(self) -> str:
        return f"{self.year}-{self.month:02d}: {self.index}"
