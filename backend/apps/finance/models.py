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
    is_system = models.BooleanField(
        default=False, help_text="Seeded by the app; UI prevents delete."
    )

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

    # What the money was *for*, chosen by the user (e.g. a medicine from the
    # cabinet: "health.cabinetitem" + its id). Unlike ``source`` this is not
    # owned by the other app — editing/deleting stays in Finance. Plain
    # strings keep finance independent of the apps it can point at.
    related_kind = models.CharField(max_length=60, blank=True, db_index=True)
    related_id = models.UUIDField(null=True, blank=True)

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
            models.UniqueConstraint(
                fields=["loan", "effective_from"], name="finance_ratechange_unique"
            ),
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
        Transaction,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="loan_overpayment",
    )

    class Meta:
        ordering = ("date",)

    def __str__(self) -> str:
        return f"{self.loan_id} {self.date} {self.amount}"


# ---- Bookmarks ---------------------------------------------------------


class TransactionBookmark(UUIDModel, TimeStamped):
    """A user's saved template for a transaction they add often.

    Unlike ``RecurringRule`` it never creates anything on its own — the user
    picks it to get a pre-filled "add transaction" form. Private to its owner."""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="finance_bookmarks"
    )
    label = models.CharField(max_length=60, help_text="Short chip text, e.g. 'Biedronka'.")
    name = models.CharField(max_length=200)
    amount = money_amount_field()
    currency = currency_field()
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name="bookmarks")
    person = models.ForeignKey(
        "people.Person", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    notes = models.TextField(blank=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("sort_order", "label")

    def __str__(self) -> str:
        return self.label


# ---- Debts / IOUs ------------------------------------------------------


class DebtEntry(UUIDModel, TimeStamped):
    """Money that moved between the household and someone else, expected back.

    Deliberately **not** a ``Transaction``: the money is expected back, so it
    must never count as income or expense. Lending and repaying are the same
    movement (money leaves us), as are borrowing and being repaid (money comes
    in), so each entry only records the direction. A counterparty's balance is

        sum(gave) - sum(received)

    positive → they owe the household, negative → the household owes them.
    The counterparty ("who") is plain text, matched case-insensitively, so
    family members and outsiders are recorded the same way."""

    class Direction(models.TextChoices):
        GAVE = "gave", "We gave them money"
        RECEIVED = "received", "They gave us money"

    counterparty_name = models.CharField(max_length=120)
    direction = models.CharField(max_length=10, choices=Direction.choices)
    amount = money_amount_field()
    currency = currency_field()
    date = models.DateField(db_index=True)
    due_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        ordering = ("-date", "-created_at")
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(counterparty_name=""), name="finance_debt_name_required"
            ),
            models.CheckConstraint(
                condition=models.Q(amount__gt=0), name="finance_debt_amount_positive"
            ),
        ]

    @property
    def signed_amount(self) -> Decimal:
        """Effect on "they owe us": + when we gave, - when we received."""
        return self.amount if self.direction == self.Direction.GAVE else -self.amount

    def __str__(self) -> str:
        return (
            f"{self.date} {self.direction} {self.counterparty_name} {self.amount} {self.currency}"
        )
