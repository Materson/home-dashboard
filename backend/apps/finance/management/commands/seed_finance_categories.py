"""Seed the system categories other apps reference by key.

Names are Polish (the household UI language); other apps only rely on the keys.

Idempotent — safe to re-run after adding new keys."""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.finance.models import Category

SYSTEM: list[tuple[str, str, str, str | None]] = [
    # (key, name, kind, parent_key)
    ("car", "Samochód", "expense", None),
    ("car.fuel", "Paliwo", "expense", "car"),
    ("car.maintenance", "Serwis i naprawy", "expense", "car"),
    ("car.inspection", "Przegląd techniczny", "expense", "car"),
    ("car.insurance", "Ubezpieczenie", "expense", "car"),
    ("home", "Dom", "expense", None),
    ("home.groceries", "Zakupy spożywcze", "expense", "home"),
    ("home.utilities", "Media i rachunki", "expense", "home"),
    ("home.rent", "Czynsz / rata kredytu", "expense", "home"),
    ("health", "Zdrowie", "expense", None),
    ("health.medicines", "Leki", "expense", "health"),
    ("health.appointments", "Wizyty lekarskie", "expense", "health"),
    ("income", "Przychody", "income", None),
    ("income.salary", "Wynagrodzenie", "income", "income"),
    ("income.other", "Inne przychody", "income", "income"),
    ("transfer", "Przelew", "transfer", None),
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
