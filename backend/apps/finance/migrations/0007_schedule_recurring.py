"""Register the daily recurring-transactions job with celery beat
(DatabaseScheduler only runs jobs stored in the DB)."""

from django.db import migrations

NAME = "finance: materialize recurring transactions"


def schedule(apps, _schema_editor):
    CrontabSchedule = apps.get_model("django_celery_beat", "CrontabSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    nightly, _ = CrontabSchedule.objects.get_or_create(
        minute="5",
        hour="3",
        day_of_week="*",
        day_of_month="*",
        month_of_year="*",
        timezone="Europe/Warsaw",
    )
    PeriodicTask.objects.update_or_create(
        name=NAME,
        defaults={
            "task": "apps.finance.tasks.materialize_recurring_transactions",
            "crontab": nightly,
            "interval": None,
            "enabled": True,
        },
    )


def unschedule(apps, _schema_editor):
    apps.get_model("django_celery_beat", "PeriodicTask").objects.filter(name=NAME).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("finance", "0006_seed_system_categories"),
        ("django_celery_beat", "0019_alter_periodictasks_options"),
    ]

    operations = [migrations.RunPython(schedule, unschedule)]
