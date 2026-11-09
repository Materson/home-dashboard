from __future__ import annotations

from typing import Protocol, TYPE_CHECKING

if TYPE_CHECKING:
    from apps.accounts.models import User
    from apps.reminders.models import Reminder


class Channel(Protocol):
    name: str

    def send(self, user: "User", reminder: "Reminder") -> None: ...
