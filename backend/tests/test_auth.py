"""The SPA's login (allauth headless): admin-made accounts can log in, and
nobody can sign up on their own."""

from __future__ import annotations

import pytest

from tests.factories import UserFactory

LOGIN = "/api/_allauth/browser/v1/auth/login"
SIGNUP = "/api/_allauth/browser/v1/auth/signup"

pytestmark = pytest.mark.django_db


def _user():
    user = UserFactory()
    user.set_password("a-long-test-password")
    user.save()
    return user


def test_admin_made_account_logs_in(client):
    # No verified address on record — as after createsuperuser or the admin.
    user = _user()
    resp = client.post(
        LOGIN,
        {"email": user.email, "password": "a-long-test-password"},
        content_type="application/json",
    )
    assert resp.status_code == 200, resp.json()
    assert resp.json()["data"]["user"]["email"] == user.email


def test_wrong_password_is_refused(client):
    user = _user()
    resp = client.post(
        LOGIN, {"email": user.email, "password": "wrong"}, content_type="application/json"
    )
    assert resp.status_code == 400


def test_no_sign_up(client):
    resp = client.post(
        SIGNUP,
        {"email": "stranger@example.com", "password": "a-long-test-password"},
        content_type="application/json",
    )
    assert resp.status_code == 403
    from apps.accounts.models import User  # noqa: PLC0415

    assert not User.objects.filter(email="stranger@example.com").exists()
