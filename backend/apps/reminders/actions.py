"""Snooze / Done buttons on a push notification.

The service worker POSTs a button's url without a session or CSRF token, so
the url carries a signed, expiring token naming one reminder and one action
— that token *is* the authorization."""

from __future__ import annotations

from datetime import timedelta

from django.core import signing
from django.utils import timezone

from . import services
from .models import Reminder

TOKEN_SALT = "reminders.action"
TOKEN_MAX_AGE = 7 * 24 * 3600
SNOOZE_MINUTES = {"snooze10": 10, "snooze60": 60}
TITLES = {"snooze10": "Za 10 min", "snooze60": "Za godzinę", "done": "Zrobione"}


def token(reminder: Reminder, action: str) -> str:
    return signing.dumps({"r": str(reminder.id), "a": action}, salt=TOKEN_SALT)


def buttons(reminder: Reminder, actions: tuple[str, ...] = ("snooze10", "done")) -> list[dict]:
    """Browsers show at most two buttons."""
    return [
        {
            "action": a,
            "title": TITLES[a],
            "url": f"/api/reminders/action?token={token(reminder, a)}",
        }
        for a in actions
    ]


def add_buttons(reminder: Reminder, actions: tuple[str, ...] = ("snooze10", "done")) -> None:
    reminder.actions = buttons(reminder, actions)
    reminder.save(update_fields=["actions"])


def apply(signed: str) -> Reminder:
    """Run the action in ``signed``. Raises ``signing.BadSignature`` (incl.
    expired) and ``Reminder.DoesNotExist``."""
    data = signing.loads(signed, salt=TOKEN_SALT, max_age=TOKEN_MAX_AGE)
    reminder = Reminder.objects.get(pk=data["r"])
    action = data["a"]
    if action == "done":
        services.mark_done(reminder)
    elif action in SNOOZE_MINUTES:
        services.snooze(reminder, timezone.now() + timedelta(minutes=SNOOZE_MINUTES[action]))
    else:
        raise signing.BadSignature("unknown action")
    return reminder
