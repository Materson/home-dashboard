"""Seed the system categories so other apps can rely on their keys right
after `migrate` (fuel needs car.fuel, etc.). Frozen copy of the list in
`seed_finance_categories`; that command stays for renames / later keys."""

from django.db import migrations

SYSTEM = [
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


def seed(apps, _schema_editor):
    Category = apps.get_model("finance", "Category")
    by_key = {}
    for key, name, kind, parent_key in SYSTEM:
        # Existing rows (e.g. from the seed command) are left untouched.
        cat, _ = Category.objects.get_or_create(
            key=key,
            defaults={
                "name": name,
                "kind": kind,
                "is_system": True,
                "parent": by_key.get(parent_key),
            },
        )
        by_key[key] = cat


class Migration(migrations.Migration):
    dependencies = [("finance", "0005_debt_counterparty_name_only")]

    # Seed data: removing it on reverse would orphan user transactions.
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
