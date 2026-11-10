"""Cars: vehicles and everything recorded about them.

The odometer is never stored as a single number — "current km" is the
highest reading across every record that carries one (fuel, service, oil
top-up, manual reading). Costs are mirrored into the finance ledger via
``finance.services.upsert_linked_transaction`` (see ``services.py``).
"""

from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db import models

from apps.core.models import TimeStamped, UUIDModel, currency_field, money_amount_field


class Car(UUIDModel, TimeStamped):
    class FuelType(models.TextChoices):
        PETROL = "petrol", "Petrol"
        DIESEL = "diesel", "Diesel"
        LPG = "lpg", "LPG"
        HYBRID = "hybrid", "Hybrid"
        ELECTRIC = "electric", "Electric"

    name = models.CharField(max_length=80, help_text="How the family calls it, e.g. 'Octavia'.")
    make = models.CharField(max_length=60, blank=True)
    model = models.CharField(max_length=60, blank=True)
    year = models.PositiveSmallIntegerField(null=True, blank=True)
    plate = models.CharField(max_length=20, blank=True)
    vin = models.CharField(max_length=17, blank=True)
    fuel_type = models.CharField(max_length=10, choices=FuelType.choices, default=FuelType.PETROL)
    owner = models.ForeignKey(
        "people.Person",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="cars",
        help_text="Used for permission scoping and as the person on cost transactions.",
    )
    initial_odometer_km = models.PositiveIntegerField(default=0)
    oil_interval_km = models.PositiveIntegerField(default=15_000)
    oil_interval_months = models.PositiveSmallIntegerField(default=12)
    notes = models.TextField(blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("archived_at", "name")

    def __str__(self) -> str:
        return self.name


class _CarRecord(UUIDModel, TimeStamped):
    """Base for everything recorded against a car."""

    car = models.ForeignKey(Car, on_delete=models.CASCADE, related_name="+")
    date = models.DateField(db_index=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        abstract = True
        ordering = ("-date", "-created_at")


class OdometerReading(_CarRecord):
    odometer_km = models.PositiveIntegerField()


class FuelEntry(_CarRecord):
    """One fill-up, recorded like the receipt.

    ``total_cost`` is what was actually paid (after discounts) and is what
    goes to the finance ledger. ``price_per_litre`` (pump price) and
    ``discount`` are optional details; the UI pre-computes
    ``litres * price_per_litre - discount`` but the paid amount wins."""

    odometer_km = models.PositiveIntegerField()
    litres = models.DecimalField(max_digits=7, decimal_places=2)
    price_per_litre = models.DecimalField(
        max_digits=7, decimal_places=3, null=True, blank=True, help_text="Pump price per litre."
    )
    discount = money_amount_field(null=True, blank=True)
    total_cost = money_amount_field(help_text="Amount actually paid, after discounts.")
    currency = currency_field()
    full_tank = models.BooleanField(default=True)
    station = models.CharField(max_length=80, blank=True)

    @property
    def effective_price_per_litre(self) -> Decimal | None:
        """What a litre really cost: paid / litres."""
        if not self.litres:
            return None
        return (self.total_cost / self.litres).quantize(Decimal("0.001"))


class MaintenanceEvent(_CarRecord):
    """Service, repair, replaced part, or just "something happened"."""

    class Kind(models.TextChoices):
        SERVICE = "service", "Service"
        PART = "part", "Part replaced"
        REPAIR = "repair", "Repair"
        ISSUE = "issue", "Issue / event"
        OTHER = "other", "Other"

    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.SERVICE)
    title = models.CharField(max_length=200)
    odometer_km = models.PositiveIntegerField(null=True, blank=True)
    cost = money_amount_field(null=True, blank=True)
    currency = currency_field()
    workshop = models.CharField(max_length=120, blank=True)


class OilChange(_CarRecord):
    odometer_km = models.PositiveIntegerField()
    oil_spec = models.CharField(max_length=80, blank=True, help_text="e.g. 5W-30 VW 504.00")
    litres = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    with_filter = models.BooleanField(default=True)
    next_due_km = models.PositiveIntegerField(null=True, blank=True)
    next_due_date = models.DateField(null=True, blank=True)
    cost = money_amount_field(null=True, blank=True)
    currency = currency_field()


class OilTopUp(_CarRecord):
    """Oil added between changes — the history shows how much the engine eats."""

    odometer_km = models.PositiveIntegerField(null=True, blank=True)
    litres = models.DecimalField(max_digits=5, decimal_places=2)


class CarDeadline(_CarRecord):
    """Something valid until a date: technical inspection, insurance, …"""

    class Kind(models.TextChoices):
        INSPECTION = "inspection", "Technical inspection"
        INSURANCE = "insurance", "Insurance"
        OTHER = "other", "Other"

    kind = models.CharField(max_length=12, choices=Kind.choices)
    valid_until = models.DateField()
    odometer_km = models.PositiveIntegerField(null=True, blank=True)
    provider = models.CharField(max_length=120, blank=True)
    cost = money_amount_field(null=True, blank=True)
    currency = currency_field()
