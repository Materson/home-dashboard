"""Notes: private by default, shareable with chosen family members (view or
edit), with an optional checklist, files and a reminder (once or repeating,
to the owner and optionally to others).

Access isn't by person or date like health — it's the note itself: the
owner, or someone it's shared with. ``check_access`` is what
``AccessContext.require(..., obj=note)`` calls (e.g. for attachments).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db import models

from apps.core.models import Archivable, TimeStamped, UUIDModel

if TYPE_CHECKING:
    from apps.access.context import AccessContext


class Note(UUIDModel, TimeStamped, Archivable):
    class Repeat(models.TextChoices):
        NONE = "", "Once"
        DAILY = "daily", "Daily"
        WEEKLY = "weekly", "Weekly"
        MONTHLY = "monthly", "Monthly"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notes"
    )
    title = models.CharField(max_length=200, blank=True)
    body = models.TextField(blank=True)
    # [{"text": "Mleko", "done": false}, …]
    checklist = models.JSONField(default=list, blank=True)
    pinned = models.BooleanField(default=False)

    remind_at = models.DateTimeField(null=True, blank=True, db_index=True)
    repeat = models.CharField(max_length=8, choices=Repeat.choices, blank=True, default="")
    # Reminded besides the owner (they get the note shared, view at least).
    remind_others = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name="+")

    class Meta:
        ordering = ("-pinned", "-updated_at")

    def __str__(self) -> str:
        return self.title or self.body[:40] or "Notatka"

    def share_for(self, user_id) -> NoteShare | None:
        return next((s for s in self.shares.all() if s.user_id == user_id), None)

    def can_view(self, user_id) -> bool:
        return self.owner_id == user_id or self.share_for(user_id) is not None

    def can_edit(self, user_id) -> bool:
        share = self.share_for(user_id)
        return self.owner_id == user_id or bool(share and share.can_edit)

    def check_access(self, ctx: AccessContext, level: str) -> None:
        allowed = self.can_view(ctx.user_id) if level == "view" else self.can_edit(ctx.user_id)
        if not allowed:
            raise PermissionDenied("not your note")


class NoteShare(models.Model):
    note = models.ForeignKey(Note, on_delete=models.CASCADE, related_name="shares")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    can_edit = models.BooleanField(default=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["note", "user"], name="one_share_per_user")]

    def __str__(self) -> str:
        return f"{self.note_id} → {self.user_id}"
