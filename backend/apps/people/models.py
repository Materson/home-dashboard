"""Person — the household member a record is *about*.

Decoupled from User: children have a Person row but no login; a User may
exist without a Person (admin-only). ``user`` is a non-nullable-but-optional
1:1 link when both exist."""

from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.core.models import Archivable, TimeStamped, UUIDModel


class Person(UUIDModel, TimeStamped, Archivable):
    display_name = models.CharField(max_length=80)
    birth_date = models.DateField(null=True, blank=True)
    color = models.CharField(max_length=7, default="#4c6ef5")  # Mantine blue
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="person",
    )

    class Meta:
        ordering = ("display_name",)

    def __str__(self) -> str:
        return self.display_name
