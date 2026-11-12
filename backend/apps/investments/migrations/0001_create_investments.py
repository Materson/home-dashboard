
import apps.core.uuid7
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("people", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Asset",
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
                    "kind",
                    models.CharField(
                        choices=[
                            ("gold", "Gold (NBP price)"),
                            ("crypto", "Cryptocurrency (CoinGecko)"),
                            ("stock", "Stock / ETF (manual value)"),
                            ("bond", "Polish treasury bond"),
                            ("other", "Other (manual value)"),
                        ],
                        max_length=10,
                    ),
                ),
                (
                    "unit",
                    models.CharField(
                        choices=[
                            ("oz", "troy ounce"),
                            ("g", "gram"),
                            ("pcs", "piece / unit"),
                        ],
                        default="pcs",
                        max_length=4,
                    ),
                ),
                ("symbol", models.CharField(blank=True, max_length=60)),
                ("bond_type", models.CharField(blank=True, max_length=3)),
                (
                    "bond_first_rate",
                    models.DecimalField(
                        blank=True, decimal_places=3, max_digits=6, null=True
                    ),
                ),
                (
                    "bond_margin",
                    models.DecimalField(
                        blank=True, decimal_places=3, max_digits=6, null=True
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
                    "person",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="people.person",
                    ),
                ),
            ],
            options={
                "ordering": ("name",),
            },
        ),
        migrations.CreateModel(
            name="InflationIndex",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("year", models.PositiveSmallIntegerField()),
                ("month", models.PositiveSmallIntegerField()),
                ("index", models.DecimalField(decimal_places=2, max_digits=6)),
                ("manual", models.BooleanField(default=False)),
            ],
            options={
                "ordering": ("year", "month"),
                "constraints": [
                    models.UniqueConstraint(
                        fields=("year", "month"), name="one_cpi_a_month"
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="Lot",
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
                ("bought_on", models.DateField(db_index=True)),
                ("quantity", models.DecimalField(decimal_places=8, max_digits=20)),
                (
                    "price_total",
                    models.DecimalField(
                        decimal_places=2,
                        help_text="What was paid for the whole lot (PLN).",
                        max_digits=12,
                    ),
                ),
                ("sold_on", models.DateField(blank=True, null=True)),
                (
                    "sold_amount",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        help_text="What it was sold for.",
                        max_digits=12,
                        null=True,
                    ),
                ),
                ("rate_overrides", models.JSONField(blank=True, default=dict)),
                ("notes", models.TextField(blank=True)),
                (
                    "asset",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="lots",
                        to="investments.asset",
                    ),
                ),
            ],
            options={
                "ordering": ("bought_on", "created_at"),
            },
        ),
        migrations.CreateModel(
            name="PriceSnapshot",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("date", models.DateField()),
                (
                    "unit_price",
                    models.DecimalField(
                        decimal_places=6, help_text="PLN per unit.", max_digits=20
                    ),
                ),
                (
                    "source",
                    models.CharField(
                        choices=[
                            ("nbp", "NBP"),
                            ("coingecko", "CoinGecko"),
                            ("manual", "Manual"),
                        ],
                        max_length=10,
                    ),
                ),
                (
                    "asset",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="prices",
                        to="investments.asset",
                    ),
                ),
            ],
            options={
                "ordering": ("date",),
                "constraints": [
                    models.UniqueConstraint(
                        fields=("asset", "date"), name="one_price_a_day"
                    )
                ],
            },
        ),
    ]
