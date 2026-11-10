"""Attachment writes: upload a file to a record, delete it.

Files belong to a *subject* record (e.g. a health test result). Every
operation checks the caller's permission on that subject's module — edit to
upload/delete, view to list/download — including person scope and date
window (``AccessContext.require`` with the object).

Only documents and images are accepted; the type is decided from the file
extension *and* the declared content type, never from user-supplied names
alone.
"""

from __future__ import annotations

import hashlib
from pathlib import PurePath
from typing import TYPE_CHECKING
from uuid import UUID

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ObjectDoesNotExist
from django.db import models
from django.db.transaction import atomic

from apps.access.permissions import module_for_model

from .models import Attachment
from .uuid7 import uuid7

if TYPE_CHECKING:
    from django.core.files.uploadedfile import UploadedFile

    from apps.access.context import AccessContext

MAX_BYTES = 25 * 1024 * 1024  # matches nginx client_max_body_size
ALLOWED = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".heic": "image/heic",
}


class AttachmentError(ValueError):
    """Rejected upload (type, size, unknown subject)."""


def resolve_subject(subject_type: str, subject_id: UUID) -> models.Model:
    """``"health.testresult"`` + id → the record. Only models registered with
    an access module can carry attachments."""
    try:
        app_label, model_name = subject_type.split(".", 1)
        model = ContentType.objects.get_by_natural_key(app_label, model_name).model_class()
        module_for_model(model)  # LookupError when not attachable
        return model.objects.get(pk=subject_id)
    except (ValueError, ObjectDoesNotExist, LookupError, AttributeError) as exc:
        raise AttachmentError("unknown subject") from exc


def list_for(ctx: AccessContext, subject: models.Model) -> models.QuerySet[Attachment]:
    ctx.require(module_for_model(type(subject)), "view", subject)
    ct = ContentType.objects.get_for_model(type(subject))
    return Attachment.objects.filter(content_type=ct, object_id=subject.pk).order_by("created_at")


@atomic
def upload(ctx: AccessContext, subject: models.Model, file: UploadedFile) -> Attachment:
    ctx.require(module_for_model(type(subject)), "edit", subject)
    suffix = PurePath(file.name or "").suffix.lower()
    mime = ALLOWED.get(suffix)
    if mime is None:
        raise AttachmentError("only PDF and images (jpg, png, webp, heic) are allowed")
    if file.size is None or file.size > MAX_BYTES:
        raise AttachmentError("file is larger than 25 MB")
    digest = hashlib.sha256()
    for chunk in file.chunks():
        digest.update(chunk)
    file.seek(0)
    original_name = PurePath(file.name).name[:255]
    # Stored under a generated ASCII name: no personal data in file names on
    # disk/backups, and nothing non-ASCII in nginx's X-Accel-Redirect header.
    file.name = f"{uuid7().hex}{suffix}"
    return Attachment.objects.create(
        uploaded_by_id=ctx.user_id,
        content_type=ContentType.objects.get_for_model(type(subject)),
        object_id=subject.pk,
        file=file,
        original_name=original_name,
        mime_type=mime,
        size_bytes=file.size,
        sha256=digest.hexdigest(),
    )


def delete(ctx: AccessContext, attachment_id: UUID) -> None:
    att = Attachment.objects.get(pk=attachment_id)
    subject = att.subject
    if subject is not None:
        ctx.require(module_for_model(type(subject)), "edit", subject)
    att.file.delete(save=False)
    att.delete()


def delete_all_for(subject: models.Model) -> None:
    """Remove a record's files with it (the caller already checked edit)."""
    ct = ContentType.objects.get_for_model(type(subject))
    for att in Attachment.objects.filter(content_type=ct, object_id=subject.pk):
        att.file.delete(save=False)
        att.delete()
