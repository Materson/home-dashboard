from __future__ import annotations

import logging

from .channels import REGISTRY
from .models import NotificationPreference

log = logging.getLogger(__name__)


def deliver(reminder) -> None:
    """Send ``reminder`` to every recipient, through every channel they have on."""
    channels_wanted = set(reminder.channels or ["email", "webpush"])
    for user in reminder.recipients.all():
        prefs, _ = NotificationPreference.objects.get_or_create(user=user)
        enabled = {
            "email": prefs.email_enabled,
            "webpush": prefs.webpush_enabled,
            "slack": prefs.slack_enabled,
        }
        for ch_name in channels_wanted:
            if not enabled.get(ch_name, False):
                continue
            channel = REGISTRY.get(ch_name)
            if channel is None:
                log.warning("unknown channel %r", ch_name)
                continue
            try:
                channel.send(user, reminder)
            except Exception:  # noqa: BLE001
                log.exception("channel %s failed for user %s", ch_name, user.id)
