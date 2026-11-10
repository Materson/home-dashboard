"""Core endpoints — healthz and protected media."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from django.http import HttpRequest, HttpResponse
from django.middleware.csrf import get_token
from django.shortcuts import get_object_or_404
from ninja import File, Form, Router, Schema
from ninja.files import UploadedFile

from apps.access.context import get_ctx
from apps.access.permissions import module_for_model

from . import attachments
from .media import serve_protected
from .models import Attachment

router = Router()


@router.get("/healthz", auth=None)
def healthz(request: HttpRequest) -> dict[str, str]:
    return {"status": "ok"}


@router.get("/csrf", auth=None)
def csrf(request: HttpRequest) -> dict[str, bool]:
    """Sets the ``csrftoken`` cookie (e.g. before login) — the SPA echoes it
    in ``X-CSRFToken`` on every unsafe request."""
    get_token(request)
    return {"ok": True}


@router.get("/media/{attachment_id}/")
def media(request: HttpRequest, attachment_id: str) -> HttpResponse:
    """Return the attachment's file iff the caller can view its subject."""
    att = get_object_or_404(Attachment.objects.select_related("content_type"), pk=attachment_id)
    ctx = get_ctx(request)
    subject = att.subject
    if subject is None:
        return HttpResponse(status=404)
    module = module_for_model(type(subject))
    ctx.require(module, "view", subject)
    return serve_protected(att)


class AttachmentOut(Schema):
    id: UUID
    original_name: str
    mime_type: str
    size_bytes: int
    created_at: datetime
    url: str

    @staticmethod
    def resolve_url(obj: Attachment) -> str:
        return f"/api/media/{obj.id}/"


@router.get("/attachments", response=list[AttachmentOut])
def list_attachments(request: HttpRequest, subject_type: str, subject_id: UUID) -> list[Attachment]:
    """Files attached to a record, e.g. ``subject_type=health.testresult``."""
    try:
        subject = attachments.resolve_subject(subject_type, subject_id)
    except attachments.AttachmentError:
        return []
    return list(attachments.list_for(get_ctx(request), subject))


@router.post("/attachments", response={200: AttachmentOut, 422: dict})
def upload_attachment(
    request: HttpRequest,
    subject_type: Form[str],
    subject_id: Form[UUID],
    file: File[UploadedFile],
):
    try:
        subject = attachments.resolve_subject(subject_type, subject_id)
        return attachments.upload(get_ctx(request), subject, file)
    except attachments.AttachmentError as exc:
        return 422, {"detail": str(exc)}


@router.delete("/attachments/{attachment_id}")
def delete_attachment(request: HttpRequest, attachment_id: UUID) -> dict[str, bool]:
    attachments.delete(get_ctx(request), attachment_id)
    return {"deleted": True}
