"""Register the hourly dose-planning job with celery beat (the
DatabaseScheduler only runs jobs stored in the DB)."""

from django.db import migrations

NAME = "health: plan medicine doses"


def schedule(apps, _schema_editor):
    IntervalSchedule = apps.get_model("django_celery_beat", "IntervalSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    hourly, _ = IntervalSchedule.objects.get_or_create(every=1, period="hours")
    PeriodicTask.objects.update_or_create(
        name=NAME,
        defaults={
            "task": "apps.health.tasks.plan_doses",
            "interval": hourly,
            "crontab": None,
            "enabled": True,
        },
    )


def unschedule(apps, _schema_editor):
    apps.get_model("django_celery_beat", "PeriodicTask").objects.filter(name=NAME).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("health", "0001_create_health"),
        ("django_celery_beat", "0019_alter_periodictasks_options"),
    ]

    operations = [migrations.RunPython(schedule, unschedule)]
