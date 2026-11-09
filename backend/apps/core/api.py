"""Core endpoints — healthz and protected media."""
from __future__ import annotations

from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404
from ninja import Router

from apps.access.context import get_ctx
from apps.access.permissions import module_for_model

from .media import accel_redirect
from .models import Attachment

router = Router()


@router.get("/healthz", auth=None)
def healthz(request: HttpRequest) -> dict[str, str]:  # noqa: ARG001
    return {"status": "ok"}


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
    return accel_redirect(att.file.name, att.original_name, att.mime_type)
