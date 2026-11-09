from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.core.models import TimeStamped, UUIDModel


class PushSubscription(UUIDModel, TimeStamped):
    """A browser push endpoint registered by the SPA."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="push_subscriptions"
    )
    endpoint = models.URLField(max_length=500, unique=True)
    p256dh = models.CharField(max_length=200)
    auth = models.CharField(max_length=200)
    user_agent = models.CharField(max_length=200, blank=True)

    def __str__(self) -> str:
        return f"push:{self.user_id}:{self.endpoint[:40]}"


class NotificationPreference(TimeStamped):
    """Per-user, per-channel on/off and quiet hours."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notification_pref"
    )
    email_enabled = models.BooleanField(default=True)
    webpush_enabled = models.BooleanField(default=True)
    slack_enabled = models.BooleanField(default=False)
    quiet_start = models.TimeField(null=True, blank=True)
    quiet_end = models.TimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f"prefs:{self.user_id}"
