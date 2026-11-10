"""Background jobs must be registered for the DB-backed beat scheduler."""

from __future__ import annotations

import pytest
from celery import current_app
from django_celery_beat.models import PeriodicTask

pytestmark = pytest.mark.django_db


def test_every_scheduled_task_is_registered_and_exists():
    tasks = dict(PeriodicTask.objects.values_list("task", "enabled"))
    assert tasks.get("apps.reminders.tasks.dispatch_due_reminders") is True
    assert tasks.get("apps.finance.tasks.materialize_recurring_transactions") is True
    assert tasks.get("apps.health.tasks.plan_doses") is True

    current_app.loader.import_default_modules()  # autodiscover tasks.py modules
    for task in tasks:
        assert task in current_app.tasks, f"beat would call unknown task {task}"
