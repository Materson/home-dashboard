"""Register the reminder dispatch job with celery beat.

Beat runs with the DatabaseScheduler, which only knows jobs stored in the DB
— without this row reminders were saved but never sent."""

from django.db import migrations

NAME = "reminders: dispatch due reminders"


def schedule(apps, _schema_editor):
    IntervalSchedule = apps.get_model("django_celery_beat", "IntervalSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    every_minute, _ = IntervalSchedule.objects.get_or_create(every=1, period="minutes")
    PeriodicTask.objects.update_or_create(
        name=NAME,
        defaults={
            "task": "apps.reminders.tasks.dispatch_due_reminders",
            "interval": every_minute,
            "crontab": None,
            "enabled": True,
        },
    )


def unschedule(apps, _schema_editor):
    apps.get_model("django_celery_beat", "PeriodicTask").objects.filter(name=NAME).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("reminders", "0001_initial"),
        ("django_celery_beat", "0019_alter_periodictasks_options"),
    ]

    operations = [migrations.RunPython(schedule, unschedule)]
