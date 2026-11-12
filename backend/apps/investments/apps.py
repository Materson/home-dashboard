from __future__ import annotations

from django.apps import AppConfig


class InvestmentsConfig(AppConfig):
    name = "apps.investments"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        # Investment records belong to the finance module (permissions; a
        # Finance transaction linked to a lot earlier stays editable).
        from apps.access.permissions import register_module_for  # noqa: PLC0415

        from .models import Asset, Lot  # noqa: PLC0415

        register_module_for(Asset, "finance")
        register_module_for(Lot, "finance")
