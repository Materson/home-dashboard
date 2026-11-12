"""Register the every-5-minutes job that moves repeating notes to their next
time (celery beat's DatabaseScheduler only runs jobs stored in the DB)."""

from django.db import migrations

NAME = "notes: roll repeating reminders"


def schedule(apps, _schema_editor):
    IntervalSchedule = apps.get_model("django_celery_beat", "IntervalSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    every5, _ = IntervalSchedule.objects.get_or_create(every=5, period="minutes")
    PeriodicTask.objects.update_or_create(
        name=NAME,
        defaults={
            "task": "apps.notes.tasks.roll_repeating_notes",
            "interval": every5,
            "crontab": None,
            "enabled": True,
        },
    )


def unschedule(apps, _schema_editor):
    apps.get_model("django_celery_beat", "PeriodicTask").objects.filter(name=NAME).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("notes", "0001_create_notes"),
        ("django_celery_beat", "0019_alter_periodictasks_options"),
    ]

    operations = [migrations.RunPython(schedule, unschedule)]
