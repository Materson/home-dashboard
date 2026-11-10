"""API-wide security: session auth + CSRF on every endpoint except healthz."""

from __future__ import annotations

import pytest
from django.test import Client

from .factories import UserFactory

pytestmark = pytest.mark.django_db


def test_anonymous_requests_get_401():
    assert Client().get("/api/finance/categories").status_code == 401
    assert Client().get("/api/healthz").status_code == 200  # stays public


def test_unsafe_requests_need_a_csrf_token():
    client = Client(enforce_csrf_checks=True)
    client.force_login(UserFactory(is_superuser=True))
    body = {"key": "x.test", "name": "Test"}

    resp = client.post("/api/finance/categories", body, content_type="application/json")
    assert resp.status_code == 403  # no token → rejected

    client.get("/api/csrf")  # sets the csrftoken cookie
    token = client.cookies["csrftoken"].value
    resp = client.post(
        "/api/finance/categories", body, content_type="application/json", HTTP_X_CSRFTOKEN=token
    )
    assert resp.status_code == 200
