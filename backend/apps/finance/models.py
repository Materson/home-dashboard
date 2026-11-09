"""Finance models.

Design notes
------------
* **Money** is split into ``amount`` (``DECIMAL(12,2)``) + ``currency`` on every
  monetary row. No floats, ever.
* **Category** is a tree with a parent FK and a ``key`` slug. Seeded system
  categories (``car.fuel``, ``car.maintenance``, ``health.medicines``, …) are
  flagged so that *other apps* can look them up by key without caring about
  the user's localized name — e.g. ``upsert_linked_transaction`` passes
  ``category_key="car.fuel"``.
* **Transaction** carries an optional *generic* FK (``source_type``,
  ``source_id``) that points at the originating record in another app
  (``FuelEntry``, ``MaintenanceEvent``, ``MedicationPurchase``, …). The pair
  ``(source_type, source_id)`` is unique so the `upsert_linked_transaction`
  helper is idempotent.
* **RecurringRule** stores an iCalendar ``RRULE`` string (parsed by
  ``dateutil.rrule``). The Celery task materializes transactions up to
  ``next_run_at`` and advances the cursor; user-edited values can be
  propagated back to the rule so future occurrences inherit them.
* **Loan** / **RateChange** / **Overpayment** feed the pure-Decimal schedule
  engine in ``loans/schedule.py``. ``RateChange`` rows become the engine's
  ``RateSegment`` list; the row with ``effective_from == loan.start_date``
  is the "base" segment.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models

from apps.core.models import TimeStamped, UUIDModel, currency_field, money_amount_field


class Category(UUIDModel, TimeStamped):
    """Hierarchical income/expense category."""

    class Kind(models.TextChoices):
        EXPENSE = "expense", "Expense"
        INCOME = "income", "Income"
        TRANSFER = "transfer", "Transfer"

    key = models.CharField(max_length=60, unique=True, help_text="Stable slug (e.g. car.fuel).")
    name = models.CharField(max_length=80)
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.EXPENSE)
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="children"
    )
    color = models.CharField(max_length=7, default="#868e96")
    is_system = models.BooleanField(default=False, help_text="Seeded by the app; UI prevents delete.")

    class Meta:
        ordering = ("name",)

    def __str__(self) -> str:
        return f"{self.name} ({self.key})"


class Transaction(UUIDModel, TimeStamped):
    """A single income/expense/transfer entry.

    One row = one money movement. Attach notes and (via ``apps.core.Attachment``)
    receipts; link to the originating record in another app via
    ``source_type`` + ``source_id``."""

    date = models.DateField(db_index=True)
    amount = money_amount_field()
    currency = currency_field()
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="transactions")
    person = models.ForeignKey(
        "people.Person",
        on_delete=models.PROTECT,
        related_name="finance_transactions",
        null=True,
        blank=True,
        help_text="Who the money moved for (budget scope). Blank = household.",
    )
    name = models.CharField(max_length=200)
    notes = models.TextField(blank=True)

    # Optional link to the record in another app that produced this transaction.
    source_type = models.ForeignKey(
        ContentType, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    source_id = models.UUIDField(null=True, blank=True)
    source = GenericForeignKey("source_type", "source_id")

    # When a RecurringRule materializes a transaction we keep the back-link so
    # "apply to future occurrences too" can update the rule's amount/name.
    recurring_rule = models.ForeignKey(
        "finance.RecurringRule",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="instances",
    )

    class Meta:
        ordering = ("-date", "-created_at")
        indexes = [
            models.Index(fields=["date", "category"]),
            models.Index(fields=["date", "person"]),
        ]
        constraints = [
            # One linked transaction per source record.
            models.UniqueConstraint(
                fields=["source_type", "source_id"],
                name="finance_tx_unique_source",
                condition=models.Q(source_id__isnull=False),
            ),
        ]

    def __str__(self) -> str:
        return f"{self.date} {self.name} {self.amount} {self.currency}"


class RecurringRule(UUIDModel, TimeStamped):
    """A recurring income/expense template (rent, salary, Netflix)."""

    name = models.CharField(max_length=200)
    amount = money_amount_field()
    currency = currency_field()
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="recurring_rules")
    person = models.ForeignKey(
        "people.Person",
        on_delete=models.PROTECT,
        related_name="finance_recurring_rules",
        null=True,
        blank=True,
    )
    notes = models.TextField(blank=True)

    rrule = models.TextField(
        help_text="iCalendar RRULE string, e.g. FREQ=MONTHLY;BYMONTHDAY=1",
    )
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    # Cursor: the next occurrence we have NOT yet materialized.
    next_run_at = models.DateField(db_index=True)

    is_active = models.BooleanField(default=True)

    def __str__(self) -> str:
        return f"{self.name} ({self.rrule})"


# ---- Loan --------------------------------------------------------------


class Loan(UUIDModel, TimeStamped):
    """An annuity loan, optionally with variable rate and overpayments."""

    class Kind(models.TextChoices):
        ANNUITY = "annuity", "Annuity"
        DECREASING = "decreasing", "Decreasing"  # reserved for future

    name = models.CharField(max_length=200)
    person = models.ForeignKey(
        "people.Person",
        on_delete=models.PROTECT,
        related_name="loans",
        null=True,
        blank=True,
    )
    kind = models.CharField(max_length=12, choices=Kind.choices, default=Kind.ANNUITY)
    principal = money_amount_field()
    currency = currency_field()
    start_date = models.DateField()
    term_months = models.PositiveIntegerField()
    base_rate = models.DecimalField(
        max_digits=6, decimal_places=4, help_text="Nominal annual rate at start (e.g. 0.0725)."
    )
    notes = models.TextField(blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return self.name


class RateChange(models.Model):
    """A variable-rate boundary — rate X takes effect from ``effective_from``."""

    loan = models.ForeignKey(Loan, on_delete=models.CASCADE, related_name="rate_changes")
    effective_from = models.DateField()
    nominal_rate_p_a = models.DecimalField(max_digits=6, decimal_places=4)

    class Meta:
        ordering = ("effective_from",)
        constraints = [
            models.UniqueConstraint(fields=["loan", "effective_from"], name="finance_ratechange_unique"),
        ]

    def __str__(self) -> str:
        return f"{self.loan_id} @ {self.effective_from} → {self.nominal_rate_p_a}"


class Overpayment(models.Model):
    class Mode(models.TextChoices):
        SHORTEN_TERM = "shorten_term", "Shorten term"
        REDUCE_INSTALLMENT = "reduce_installment", "Reduce installment"

    loan = models.ForeignKey(Loan, on_delete=models.CASCADE, related_name="overpayments")
    date = models.DateField()
    amount = money_amount_field()
    mode = models.CharField(max_length=20, choices=Mode.choices, default=Mode.SHORTEN_TERM)
    notes = models.TextField(blank=True)
    # Linked Transaction on the finance ledger (optional — the overpayment is
    # usually already captured as a Transaction).
    transaction = models.ForeignKey(
        Transaction, null=True, blank=True, on_delete=models.SET_NULL, related_name="loan_overpayment"
    )

    class Meta:
        ordering = ("date",)

    def __str__(self) -> str:
        return f"{self.loan_id} {self.date} {self.amount}"
