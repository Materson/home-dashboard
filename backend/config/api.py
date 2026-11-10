"""The single Django Ninja API. Each app exposes its own router and registers
here so there's one OpenAPI schema for the SPA to generate its client from."""
from __future__ import annotations

from ninja import NinjaAPI
from ninja.security import django_auth

from apps.accounts.api import router as accounts_router
from apps.access.api import router as access_router
from apps.cars.api import router as cars_router
from apps.core.api import router as core_router
from apps.finance.api import router as finance_router
from apps.health.api import router as health_router
from apps.notifications.api import router as notifications_router
from apps.people.api import router as people_router
from apps.reminders.api import router as reminders_router

api = NinjaAPI(
    title="Home Dashboard API",
    version="0.1.0",
    # Every endpoint needs a logged-in session (401 otherwise), and session
    # auth makes Ninja enforce CSRF on unsafe methods — Ninja views are
    # csrf_exempt, so Django's middleware alone does NOT protect them.
    # Public endpoints opt out explicitly with auth=None (healthz, csrf).
    auth=django_auth,
    docs_url="/docs" if __debug__ else None,
)

api.add_router("/me", accounts_router, tags=["me"])
api.add_router("/people", people_router, tags=["people"])
api.add_router("/access", access_router, tags=["access"])
api.add_router("/reminders", reminders_router, tags=["reminders"])
api.add_router("/notifications", notifications_router, tags=["notifications"])
api.add_router("/finance", finance_router, tags=["finance"])
api.add_router("/cars", cars_router, tags=["cars"])
api.add_router("/health", health_router, tags=["health"])
api.add_router("", core_router, tags=["core"])
