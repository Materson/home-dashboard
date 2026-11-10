"""Protected media serving.

``serve_protected`` is called *after* the caller's permission on the
attachment's subject was checked. In production it hands the file to nginx
with ``X-Accel-Redirect`` to the internal location
``/protected-media/<relative-path>`` (never reachable directly). In
development (DEBUG, plain runserver, no nginx) it streams the file itself.

The frontend reaches files at ``/api/media/<attachment-id>/``."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import TYPE_CHECKING
from urllib.parse import quote

from django.conf import settings
from django.http import FileResponse, HttpResponse
from django.utils.http import content_disposition_header

if TYPE_CHECKING:
    from .models import Attachment


def serve_protected(att: Attachment) -> HttpResponse:
    if settings.DEBUG:
        response: HttpResponse = FileResponse(
            att.file.open("rb"), content_type=att.mime_type, filename=att.original_name
        )
    else:
        internal = quote(  # header must be ASCII even for legacy file names
            str(PurePosixPath(settings.INTERNAL_MEDIA_PREFIX) / att.file.name.lstrip("/"))
        )
        response = HttpResponse(status=200)
        response["Content-Type"] = att.mime_type
        response["X-Accel-Redirect"] = internal
    # RFC 6266 encoding, so non-ASCII names (wyniki_badań.pdf) survive.
    response["Content-Disposition"] = content_disposition_header(False, att.original_name)
    # nginx sets caching too, but never let a proxy keep health documents.
    response["Cache-Control"] = "private, no-store"
    return response
