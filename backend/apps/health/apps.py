from __future__ import annotations

from django.apps import AppConfig


class HealthConfig(AppConfig):
    name = "apps.health"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        # Lets core (attachments, media) find the access module for these.
        from apps.access.permissions import register_module_for  # noqa: PLC0415

        from . import models  # noqa: PLC0415

        for model in (
            models.Condition,
            models.Medication,
            models.Appointment,
            models.TestResult,
            models.CabinetItem,
            models.Measurement,
            models.MedicinePackage,
        ):
            register_module_for(model, "health")
