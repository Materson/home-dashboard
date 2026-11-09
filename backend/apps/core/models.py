"""Base models reused across apps."""
from __future__ import annotations

import uuid
from typing import Any

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models

from .money import DEFAULT_CURRENCY
from .uuid7 import uuid7


class UUIDModel(models.Model):
    """PK = UUIDv7 (sortable by creation time)."""

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)

    class Meta:
        abstract = True


class TimeStamped(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Archivable(models.Model):
    """Soft-delete via ``archived_at``. ``objects.active()`` hides archived rows."""

    archived_at = models.DateTimeField(null=True, blank=True, db_index=True)

    objects = models.Manager()

    class Meta:
        abstract = True

    def archive(self) -> None:
        from django.utils import timezone

        if self.archived_at is None:
            self.archived_at = timezone.now()
            self.save(update_fields=["archived_at"])


class ActiveManager(models.Manager):
    def get_queryset(self) -> models.QuerySet[Any]:
        return super().get_queryset().filter(archived_at__isnull=True)


def money_amount_field(**kwargs: Any) -> models.DecimalField:
    """DECIMAL(12,2) — ±9 999 999 999.99."""
    kwargs.setdefault("max_digits", 12)
    kwargs.setdefault("decimal_places", 2)
    return models.DecimalField(**kwargs)


def currency_field(**kwargs: Any) -> models.CharField:
    kwargs.setdefault("max_length", 3)
    kwargs.setdefault("default", DEFAULT_CURRENCY)
    return models.CharField(**kwargs)


class Attachment(UUIDModel, TimeStamped):
    """A file attached to any record via a generic FK.

    Stored under ``media/attachments/YYYY/MM/<uuid>.<ext>``; served through
    ``/api/media/<id>/`` which checks the subject's permissions then returns
    an ``X-Accel-Redirect`` to the internal nginx location."""

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.UUIDField()
    subject = GenericForeignKey("content_type", "object_id")

    file = models.FileField(upload_to="attachments/%Y/%m/")
    original_name = models.CharField(max_length=255)
    mime_type = models.CharField(max_length=127)
    size_bytes = models.PositiveBigIntegerField()
    sha256 = models.CharField(max_length=64, db_index=True)

    class Meta:
        indexes = [models.Index(fields=["content_type", "object_id"])]
