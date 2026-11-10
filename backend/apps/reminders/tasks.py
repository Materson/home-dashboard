"""Celery tasks for reminder dispatch.

``dispatch_due_reminders`` is the only task that transitions scheduled
reminders to ``sent``. It uses ``SELECT … FOR UPDATE SKIP LOCKED`` so
multiple workers don't deliver the same reminder twice."""

from __future__ import annotations

import logging

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from apps.notifications.dispatch import deliver

from .models import Reminder
from .services import mark_sent

log = logging.getLogger(__name__)


@shared_task
def dispatch_due_reminders(batch_size: int = 100) -> int:
    """Called every minute by beat."""
    now = timezone.now()
    sent = 0
    with transaction.atomic():
        due_qs = (
            Reminder.objects.select_for_update(skip_locked=True)
            .filter(status=Reminder.Status.SCHEDULED, due_at__lte=now)
            .order_by("due_at")[:batch_size]
        )
        for reminder in due_qs:
            try:
                deliver(reminder)
                mark_sent(reminder)
                sent += 1
            except Exception:  # noqa: BLE001
                log.exception("reminder %s delivery failed", reminder.id)
    return sent
