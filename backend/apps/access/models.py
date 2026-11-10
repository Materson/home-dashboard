"""Permission data model.

One row = one grant. A user's effective permissions are the merge of their
own grants plus the grants of every Group they belong to, with **deny winning
over allow** inside the same (module, level) bucket."""

from __future__ import annotations

from django.conf import settings
from django.contrib.auth.models import Group
from django.db import models

from apps.core.models import TimeStamped, UUIDModel

from .permissions import LEVELS, MODULES


class AccessGrant(UUIDModel, TimeStamped):
    class Effect(models.TextChoices):
        ALLOW = "allow", "Allow"
        DENY = "deny", "Deny"

    class Subjects(models.TextChoices):
        ALL = "all", "All persons"
        SELF = "self", "Only the user's own Person"
        SELECTED = "selected", "Selected persons"

    # Grantee: exactly one of user or group.
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="access_grants",
    )
    group = models.ForeignKey(
        Group,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="access_grants",
    )

    module = models.CharField(max_length=20, choices=[(m, m) for m in MODULES])
    level = models.CharField(max_length=10, choices=[(l, l) for l in LEVELS])
    effect = models.CharField(max_length=5, choices=Effect.choices, default=Effect.ALLOW)
    subjects = models.CharField(max_length=10, choices=Subjects.choices, default=Subjects.ALL)
    person_ids = models.JSONField(default=list, blank=True)  # UUIDs as strings
    data_from = models.DateField(null=True, blank=True)
    data_to = models.DateField(null=True, blank=True)
    valid_until = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "module"]),
            models.Index(fields=["group", "module"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(user__isnull=False, group__isnull=True)
                    | models.Q(user__isnull=True, group__isnull=False)
                ),
                name="access_grant_user_xor_group",
            )
        ]

    def __str__(self) -> str:
        who = f"user={self.user_id}" if self.user_id else f"group={self.group_id}"
        return f"{self.effect} {self.module}:{self.level} → {who}"
