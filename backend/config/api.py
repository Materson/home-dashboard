"""The single Django Ninja API. Each app exposes its own router and registers
here so there's one OpenAPI schema for the SPA to generate its client from."""
from __future__ import annotations

from ninja import NinjaAPI

from apps.accounts.api import router as accounts_router
from apps.access.api import router as access_router
from apps.core.api import router as core_router
from apps.notifications.api import router as notifications_router
from apps.people.api import router as people_router
from apps.reminders.api import router as reminders_router

api = NinjaAPI(
    title="Home Dashboard API",
    version="0.1.0",
    # cookie-session auth is applied per-router; healthz stays public.
    docs_url="/docs" if __debug__ else None,
    csrf=True,
)

api.add_router("/me", accounts_router, tags=["me"])
api.add_router("/people", people_router, tags=["people"])
api.add_router("/access", access_router, tags=["access"])
api.add_router("/reminders", reminders_router, tags=["reminders"])
api.add_router("/notifications", notifications_router, tags=["notifications"])
api.add_router("", core_router, tags=["core"])
