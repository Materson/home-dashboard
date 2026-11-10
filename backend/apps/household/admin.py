from __future__ import annotations

from django.contrib import admin

from .models import Batch, Item, ShoppingEntry


class BatchInline(admin.TabularInline):
    model = Batch
    extra = 0
    fields = ("quantity", "expiry_date", "added_on", "finished_on", "notes")


@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "unit", "min_quantity", "archived_at")
    list_filter = ("category",)
    search_fields = ("name",)
    inlines = (BatchInline,)


@admin.register(ShoppingEntry)
class ShoppingEntryAdmin(admin.ModelAdmin):
    list_display = ("name", "quantity", "auto", "done_at")
    list_filter = ("auto",)
