
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("investments", "0003_add_deposit_interest"),
    ]

    operations = [
        migrations.AlterField(
            model_name="asset",
            name="kind",
            field=models.CharField(
                choices=[
                    ("gold", "Gold (NBP price)"),
                    ("silver", "Silver (COMEX price via Yahoo)"),
                    ("crypto", "Cryptocurrency (CoinGecko)"),
                    ("stock", "Stock / ETF (Yahoo Finance; manual without a symbol)"),
                    ("bond", "Polish treasury bond"),
                    ("other", "Other (manual value)"),
                ],
                max_length=10,
            ),
        ),
        migrations.AlterField(
            model_name="pricesnapshot",
            name="source",
            field=models.CharField(
                choices=[
                    ("nbp", "NBP"),
                    ("coingecko", "CoinGecko"),
                    ("yahoo", "Yahoo Finance"),
                    ("manual", "Manual"),
                ],
                max_length=10,
            ),
        ),
    ]
