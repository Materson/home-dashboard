from __future__ import annotations

from collections.abc import Callable

from django.http import HttpRequest, HttpResponse

from .context import AccessContext


class AccessContextMiddleware:
    """Attach ``request.access_ctx`` so ``get_ctx(request)`` is O(1) later."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if getattr(request, "user", None) is not None and request.user.is_authenticated:
            request.access_ctx = AccessContext.for_user(request.user)  # type: ignore[attr-defined]
        else:
            request.access_ctx = AccessContext(user_id=None, person_id=None, is_admin=False)  # type: ignore[attr-defined]
        return self.get_response(request)
