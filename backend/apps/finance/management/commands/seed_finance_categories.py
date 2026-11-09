"""Seed the system categories other apps reference by key.

Idempotent — safe to re-run after adding new keys."""
from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.finance.models import Category

SYSTEM: list[tuple[str, str, str, str | None]] = [
    # (key, name, kind, parent_key)
    ("car", "Car", "expense", None),
    ("car.fuel", "Fuel", "expense", "car"),
    ("car.maintenance", "Maintenance", "expense", "car"),
    ("car.inspection", "Technical inspection", "expense", "car"),
    ("car.insurance", "Insurance", "expense", "car"),
    ("home", "Home", "expense", None),
    ("home.groceries", "Groceries", "expense", "home"),
    ("home.utilities", "Utilities", "expense", "home"),
    ("home.rent", "Rent / mortgage", "expense", "home"),
    ("health", "Health", "expense", None),
    ("health.medicines", "Medicines", "expense", "health"),
    ("health.appointments", "Appointments", "expense", "health"),
    ("income", "Income", "income", None),
    ("income.salary", "Salary", "income", "income"),
    ("income.other", "Other income", "income", "income"),
    ("transfer", "Transfer", "transfer", None),
]


class Command(BaseCommand):
    help = "Create / update the system finance categories."

    def handle(self, *_args, **_opts) -> None:
        created_by_key: dict[str, Category] = {}
        for key, name, kind, parent_key in SYSTEM:
            parent = created_by_key.get(parent_key) if parent_key else None
            cat, created = Category.objects.get_or_create(
                key=key,
                defaults={"name": name, "kind": kind, "is_system": True, "parent": parent},
            )
            if not created:
                changed = False
                if cat.name != name:
                    cat.name = name
                    changed = True
                if cat.kind != kind:
                    cat.kind = kind
                    changed = True
                if cat.parent_id != (parent.id if parent else None):
                    cat.parent = parent
                    changed = True
                if not cat.is_system:
                    cat.is_system = True
                    changed = True
                if changed:
                    cat.save()
            created_by_key[key] = cat
            self.stdout.write(f"{'+' if created else '='} {key}")
