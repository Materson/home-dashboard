"""Beat schedule entries for reminder dispatch.

Imported from ``config.celery`` via Celery's autodiscovery — the schedule is
stored in the DB by ``django-celery-beat``, so this file only exists as
documentation of the expected rows. Run ``manage.py seed_beat`` to create
them (added in the next milestone if we need it)."""
from __future__ import annotations

BEAT_SCHEDULE: dict[str, dict] = {
    "dispatch-due-reminders": {
        "task": "apps.reminders.tasks.dispatch_due_reminders",
        "schedule": 60.0,  # every minute
    }
}
