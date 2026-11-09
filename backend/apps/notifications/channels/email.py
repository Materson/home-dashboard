from __future__ import annotations

from django.conf import settings
from django.core.mail import send_mail

from apps.reminders.models import Reminder


class EmailChannel:
    name = "email"

    def send(self, user, reminder: Reminder) -> None:
        subject = reminder.title
        body = self._body(reminder)
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [user.email])

    def _body(self, reminder: Reminder) -> str:
        if reminder.sensitivity == Reminder.Sensitivity.PRIVATE:
            return "You have a reminder — open the dashboard to view it."
        return reminder.body or reminder.title
