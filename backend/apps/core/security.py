"""Auth for the few endpoints that work before anyone is logged in."""

from __future__ import annotations

from django.http import HttpRequest
from ninja.errors import HttpError
from ninja.utils import check_csrf


def anonymous_with_csrf(request: HttpRequest) -> bool:
    """No login needed, but the CSRF token must match — for public POSTs that
    log someone in (first-time setup, accepting an invite). Ninja checks CSRF
    only for session auth, and its views are csrf_exempt."""
    if check_csrf(request):
        raise HttpError(403, "CSRF check failed")
    return True
