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
                else "Otwórz panel, aby zobaczyć szczegóły."  # private: no details off-device
            ),
            "url": reminder.link or "/",
            "tag": str(reminder.id),
            # Buttons (e.g. "Wzięte"); the service worker POSTs action urls.
            "actions": [
                {"action": a["action"], "title": a["title"], "url": a["url"]}
                for a in (reminder.actions or [])
            ],
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
