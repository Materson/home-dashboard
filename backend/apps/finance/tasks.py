from __future__ import annotations

from celery import shared_task

from .recurring import materialize_due


@shared_task
def materialize_recurring_transactions() -> int:
    """Daily beat task — creates the day's auto-recurring transactions."""
    return materialize_due()
