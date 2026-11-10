from __future__ import annotations

from celery import shared_task

from .doses import plan_all


@shared_task
def plan_doses() -> int:
    """Hourly: keep the next 48 h of medicine doses (and reminders) planned."""
    return plan_all()
