from __future__ import annotations

from django.contrib import admin

from .models import (
    Car,
    CarDeadline,
    FuelEntry,
    MaintenanceEvent,
    OdometerReading,
    OilChange,
    OilTopUp,
)


@admin.register(Car)
class CarAdmin(admin.ModelAdmin):
    list_display = ("name", "make", "model", "plate", "owner", "archived_at")
    search_fields = ("name", "make", "model", "plate", "vin")


@admin.register(FuelEntry, OdometerReading, MaintenanceEvent, OilChange, OilTopUp, CarDeadline)
class CarRecordAdmin(admin.ModelAdmin):
    list_display = ("date", "car", "__str__")
    list_filter = ("car",)
    date_hierarchy = "date"
