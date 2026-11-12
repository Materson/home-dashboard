"""Reminders — time-based or odometer-based, delivered via one or more channels."""

from __future__ import annotations

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models

from apps.core.models import TimeStamped, UUIDModel


class Reminder(UUIDModel, TimeStamped):
    class Status(models.TextChoices):
        SCHEDULED = "scheduled", "Scheduled"
        SENT = "sent", "Sent"
        SNOOZED = "snoozed", "Snoozed"
        DONE = "done", "Done"
        CANCELLED = "cancelled", "Cancelled"

    class Sensitivity(models.TextChoices):
        NORMAL = "normal", "Normal"
        PRIVATE = "private", "Private (redacted on cloud channels)"

    title = models.CharField(max_length=200)
    body = models.TextField(blank=True)
    sensitivity = models.CharField(
        max_length=10, choices=Sensitivity.choices, default=Sensitivity.NORMAL
    )

    # Target: an optional record this reminder is "about" (oil change, appointment, …).
    content_type = models.ForeignKey(ContentType, null=True, blank=True, on_delete=models.SET_NULL)
    object_id = models.UUIDField(null=True, blank=True)
    target = GenericForeignKey("content_type", "object_id")

    # Who it's for and who should receive it.
    recipients = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name="reminders")

    # Triggering.
    due_at = models.DateTimeField(null=True, blank=True, db_index=True)
    due_odometer_km = models.PositiveIntegerField(null=True, blank=True)
    car_id = models.UUIDField(null=True, blank=True)  # when due_odometer_km is set

    # Channels (list of channel names enabled for this reminder).
    channels = models.JSONField(default=list)
    # Buttons shown on the push notification:
    # [{"action": "taken", "title": "Wzięte", "url": "/api/...?token=..."}].
    # The url is POSTed by the service worker, so it must carry its own
    # signed token (no session cookie / CSRF header is available there).
    actions = models.JSONField(default=list, blank=True)
    # Page opened when the notification is clicked (e.g. "/notes?open=<id>").
    link = models.CharField(max_length=200, blank=True)

    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.SCHEDULED, db_index=True
    )
    sent_at = models.DateTimeField(null=True, blank=True)
    snoozed_until = models.DateTimeField(null=True, blank=True)
    done_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["status", "due_at"]),
            models.Index(fields=["status", "car_id"]),
        ]

    def __str__(self) -> str:
        return self.title
