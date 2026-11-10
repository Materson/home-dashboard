"""Household: what the family keeps at home (food, cleaning supplies), how
much is left, what expires, and one shared shopping list.

- ``Item``: a kind of thing ("Mleko", "Tabletki do zmywarki") with its unit
  and an optional minimum — below it, it goes on the list.
- ``Batch``: one purchase of an item — quantity left and expiry date. Using
  some lowers the quantity; using all (or throwing it away) closes it.
- ``ShoppingEntry``: a line on the shared list — free text or an item; items
  below their minimum are added automatically (``auto``).

Not person-scoped: access is the ``household`` module (view / edit).
"""

from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.core.models import Archivable, TimeStamped, UUIDModel


class Item(UUIDModel, TimeStamped, Archivable):
    class Category(models.TextChoices):
        FOOD = "food", "Food"
        CLEANING = "cleaning", "Cleaning"

    name = models.CharField(max_length=120)
    category = models.CharField(max_length=10, choices=Category.choices, default=Category.FOOD)
    unit = models.CharField(max_length=20, blank=True, default="szt.")
    min_quantity = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Below this, the item goes on the shopping list. Empty = never.",
    )
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name


class Batch(UUIDModel, TimeStamped):
    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name="batches")
    quantity = models.DecimalField(max_digits=8, decimal_places=2, help_text="How much is left.")
    expiry_date = models.DateField(null=True, blank=True)
    added_on = models.DateField()
    finished_on = models.DateField(null=True, blank=True, help_text="Used up or thrown away.")
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        # Use what expires first; batches without a date last.
        ordering = (models.F("expiry_date").asc(nulls_last=True), "added_on", "created_at")

    def __str__(self) -> str:
        return f"{self.item.name}: {self.quantity}"


class ShoppingEntry(UUIDModel, TimeStamped):
    item = models.ForeignKey(
        Item, null=True, blank=True, on_delete=models.SET_NULL, related_name="shopping_entries"
    )
    name = models.CharField(max_length=120)
    quantity = models.CharField(max_length=40, blank=True, help_text="Free text, e.g. '2 opak.'")
    auto = models.BooleanField(default=False, help_text="Added because the item ran low.")
    done_at = models.DateTimeField(null=True, blank=True, db_index=True)
    done_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ("created_at",)

    def __str__(self) -> str:
        return self.name
