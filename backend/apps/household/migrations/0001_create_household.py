
import apps.core.uuid7
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Item",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=apps.core.uuid7.uuid7,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "archived_at",
                    models.DateTimeField(blank=True, db_index=True, null=True),
                ),
                ("name", models.CharField(max_length=120)),
                (
                    "category",
                    models.CharField(
                        choices=[("food", "Food"), ("cleaning", "Cleaning")],
                        default="food",
                        max_length=10,
                    ),
                ),
                (
                    "location",
                    models.CharField(
                        blank=True, help_text="e.g. lodówka, spiżarnia", max_length=60
                    ),
                ),
                ("unit", models.CharField(blank=True, default="szt.", max_length=20)),
                (
                    "min_quantity",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        help_text="Below this, the item goes on the shopping list. Empty = never.",
                        max_digits=8,
                        null=True,
                    ),
                ),
                ("notes", models.TextField(blank=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ("name",),
            },
        ),
        migrations.CreateModel(
            name="Batch",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=apps.core.uuid7.uuid7,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "quantity",
                    models.DecimalField(
                        decimal_places=2, help_text="How much is left.", max_digits=8
                    ),
                ),
                ("expiry_date", models.DateField(blank=True, null=True)),
                ("added_on", models.DateField()),
                (
                    "finished_on",
                    models.DateField(
                        blank=True, help_text="Used up or thrown away.", null=True
                    ),
                ),
                ("notes", models.TextField(blank=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "item",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="batches",
                        to="household.item",
                    ),
                ),
            ],
            options={
                "ordering": (
                    models.OrderBy(models.F("expiry_date"), nulls_last=True),
                    "added_on",
                    "created_at",
                ),
            },
        ),
        migrations.CreateModel(
            name="ShoppingEntry",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=apps.core.uuid7.uuid7,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=120)),
                (
                    "quantity",
                    models.CharField(
                        blank=True, help_text="Free text, e.g. '2 opak.'", max_length=40
                    ),
                ),
                (
                    "auto",
                    models.BooleanField(
                        default=False, help_text="Added because the item ran low."
                    ),
                ),
                ("done_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "done_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "item",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="shopping_entries",
                        to="household.item",
                    ),
                ),
            ],
            options={
                "ordering": ("created_at",),
            },
        ),
    ]
