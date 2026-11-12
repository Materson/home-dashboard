from __future__ import annotations

from django.contrib import admin

from .models import Asset, AssetShare, InflationIndex, Lot, PriceSnapshot


class LotInline(admin.TabularInline):
    model = Lot
    extra = 0


class ShareInline(admin.TabularInline):
    model = AssetShare
    extra = 0


@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "unit", "symbol", "bond_type", "archived_at")
    list_filter = ("kind",)
    inlines = (LotInline, ShareInline)


@admin.register(PriceSnapshot)
class PriceSnapshotAdmin(admin.ModelAdmin):
    list_display = ("asset", "date", "unit_price", "source")
    list_filter = ("source", "asset")


@admin.register(InflationIndex)
class InflationIndexAdmin(admin.ModelAdmin):
    list_display = ("year", "month", "index", "manual")
