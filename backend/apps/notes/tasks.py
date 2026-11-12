from __future__ import annotations

from celery import shared_task

from .services import roll_due_repeats


@shared_task
def roll_repeating_notes() -> int:
    """Every 5 minutes: repeating notes whose time passed get their next reminder."""
    return roll_due_repeats()
