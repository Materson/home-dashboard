
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("investments", "0002_seed_category_and_daily_refresh"),
    ]

    operations = [
        migrations.AddField(
            model_name="asset",
            name="compounding",
            field=models.CharField(blank=True, default="none", max_length=10),
        ),
        migrations.AddField(
            model_name="asset",
            name="rate",
            field=models.DecimalField(
                blank=True, decimal_places=3, max_digits=6, null=True
            ),
        ),
        migrations.AddField(
            model_name="asset",
            name="term_months",
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
    ]
