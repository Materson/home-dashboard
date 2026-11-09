from __future__ import annotations

import json
import logging

from django.conf import settings

from apps.reminders.models import Reminder

log = logging.getLogger(__name__)


class WebPushChannel:
    name = "webpush"

    def send(self, user, reminder: Reminder) -> None:
        if not settings.VAPID_PRIVATE_KEY:
            log.warning("VAPID keys not configured; skipping web push")
            return
        from pywebpush import WebPushException, webpush

        payload = {
            "title": reminder.title,
            "body": (
                reminder.body
                if reminder.sensitivity != Reminder.Sensitivity.PRIVATE
                else "Open the dashboard to view."
            ),
            "url": "/reminders",
        }
        subs = user.push_subscriptions.all()
        for sub in subs:
            try:
                webpush(
                    subscription_info={
                        "endpoint": sub.endpoint,
                        "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
                    },
                    data=json.dumps(payload),
                    vapid_private_key=settings.VAPID_PRIVATE_KEY,
                    vapid_claims={"sub": f"mailto:{settings.VAPID_ADMIN_EMAIL}"},
                )
            except WebPushException as exc:
                log.warning("web push failed for sub=%s: %s", sub.id, exc)
                if exc.response and exc.response.status_code in (404, 410):
                    sub.delete()
