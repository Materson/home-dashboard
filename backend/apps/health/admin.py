from __future__ import annotations

from django.contrib import admin

from .models import Appointment, Condition, DoseLog, Medication, MedicinePurchase, TestResult


@admin.register(Condition, Medication, MedicinePurchase, Appointment, TestResult)
class HealthRecordAdmin(admin.ModelAdmin):
    list_display = ("__str__", "person", "created_at")
    list_filter = ("person",)


@admin.register(DoseLog)
class DoseLogAdmin(admin.ModelAdmin):
    list_display = ("medication", "scheduled_at", "status")
    list_filter = ("status",)
