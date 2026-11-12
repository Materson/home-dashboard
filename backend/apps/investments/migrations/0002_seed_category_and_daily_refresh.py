"""The "Inwestycje" finance category (a transfer — buying an investment
isn't spending) and the daily price / inflation refresh job (after NBP
publishes the day's gold price)."""

from django.db import migrations

NAME = "investments: refresh prices and inflation"
CATEGORY = "transfer.investments"


def forward(apps, _schema_editor):
    Category = apps.get_model("finance", "Category")
    Category.objects.get_or_create(
        key=CATEGORY,
        defaults={"name": "Inwestycje", "kind": "transfer", "is_system": True, "color": "#fab005"},
    )
    CrontabSchedule = apps.get_model("django_celery_beat", "CrontabSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    evening, _ = CrontabSchedule.objects.get_or_create(
        minute="30",
        hour="19",
        day_of_week="*",
        day_of_month="*",
        month_of_year="*",
        timezone="Europe/Warsaw",
    )
    PeriodicTask.objects.update_or_create(
        name=NAME,
        defaults={
            "task": "apps.investments.tasks.refresh_investments",
            "crontab": evening,
            "interval": None,
            "enabled": True,
        },
    )


def backward(apps, _schema_editor):
    apps.get_model("django_celery_beat", "PeriodicTask").objects.filter(name=NAME).delete()
    Category = apps.get_model("finance", "Category")
    Transaction = apps.get_model("finance", "Transaction")
    if not Transaction.objects.filter(category__key=CATEGORY).exists():
        Category.objects.filter(key=CATEGORY).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("investments", "0001_create_investments"),
        ("finance", "0009_add_transaction_shares"),
        ("django_celery_beat", "0019_alter_periodictasks_options"),
    ]

    operations = [migrations.RunPython(forward, backward)]
