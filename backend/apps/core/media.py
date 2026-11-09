"""Protected media serving.

The attachment view checks the *subject* record's permissions (via
``AccessContext``) then hands the file to nginx with ``X-Accel-Redirect`` to
the internal location ``/protected-media/<relative-path>``.

The frontend reaches it at ``/api/media/<attachment-id>/``."""
from __future__ import annotations

from pathlib import PurePosixPath

from django.conf import settings
from django.http import HttpResponse


def accel_redirect(storage_path: str, filename: str, content_type: str) -> HttpResponse:
    """Build an X-Accel-Redirect response for a file under ``MEDIA_ROOT``."""
    # strip any leading slash; join with the internal nginx prefix.
    internal = str(PurePosixPath(settings.INTERNAL_MEDIA_PREFIX) / storage_path.lstrip("/"))
    response = HttpResponse(status=200)
    response["Content-Type"] = content_type
    response["Content-Disposition"] = f'inline; filename="{filename}"'
    response["X-Accel-Redirect"] = internal
    # belt & braces: nginx must set caching, but if someone bypasses it:
    response["Cache-Control"] = "private, no-store"
    return response
