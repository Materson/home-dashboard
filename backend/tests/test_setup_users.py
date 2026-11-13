"""First-time setup, accounts made by an admin, one-time password links,
roles and grants — all from the app, no Django admin."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.auth.models import Group
from django.test import Client
from django.utils import timezone

from apps.access.models import AccessGrant
from apps.access.roles import ADMIN, CHILD, PARENT, seed_roles
from apps.accounts.models import PasswordLink, User
from apps.people.models import Person

from .factories import PersonFactory, UserFactory

pytestmark = pytest.mark.django_db

GOOD = "a-long-family-password"
JSON = "application/json"


def post(client, url, body=None):
    return client.post(url, body or {}, content_type=JSON)


def put(client, url, body):
    return client.put(url, body, content_type=JSON)


def setup_body(**kw):
    return {"email": "mama@example.com", "password": GOOD, "name": "Mama", "locale": "pl", **kw}


# ---- first-time setup -----------------------------------------------------------


def test_fresh_install_sets_up_the_first_admin(client):
    assert client.get("/api/setup").json() == {"needs_setup": True}
    assert post(client, "/api/setup", setup_body()).status_code == 200

    admin = User.objects.get()
    assert admin.is_superuser and admin.check_password(GOOD) and admin.locale == "pl"
    assert set(admin.groups.values_list("name", flat=True)) == {ADMIN, PARENT}
    assert admin.person.display_name == "Mama"
    assert set(Group.objects.values_list("name", flat=True)) >= {ADMIN, PARENT, CHILD}
    assert client.get("/api/me/").json()["email"] == "mama@example.com"  # logged in
    assert client.get("/api/setup").json() == {"needs_setup": False}


def test_setup_runs_only_once(client):
    post(client, "/api/setup", setup_body())
    resp = post(Client(), "/api/setup", setup_body(email="intruder@example.com"))
    assert resp.status_code == 422
    assert resp.json()["detail"] == "already_set_up"
    assert User.objects.count() == 1


def test_setup_checks_the_password_and_email(client):
    resp = post(client, "/api/setup", setup_body(password="short"))
    assert resp.status_code == 422
    assert "password_too_short" in resp.json()["codes"]
    assert (
        post(client, "/api/setup", setup_body(email="not-an-email")).json()["detail"]
        == "email_invalid"
    )
    assert not User.objects.exists()


def test_setup_needs_a_csrf_token():
    client = Client(enforce_csrf_checks=True)
    assert post(client, "/api/setup", setup_body()).status_code == 403
    client.get("/api/csrf")
    resp = client.post(
        "/api/setup",
        setup_body(),
        content_type=JSON,
        HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value,
    )
    assert resp.status_code == 200


# ---- accounts and invite links ----------------------------------------------------


@pytest.fixture
def admin_client(client):
    seed_roles()
    client.force_login(UserFactory(is_superuser=True))
    return client


def role(name):
    return Group.objects.get(name=name).pk


def test_admin_invites_a_family_member(admin_client):
    resp = post(
        admin_client,
        "/api/users",
        {
            "email": "zosia@example.com",
            "name": "Zosia",
            "role_ids": [role(CHILD)],
            "new_person": True,
        },
    )
    assert resp.status_code == 200
    created = resp.json()
    token = created["link"]["token"]
    assert created["link"]["purpose"] == "invite"
    assert created["user"]["open_link"]["purpose"] == "invite"
    assert created["user"]["person"]["display_name"] == "Zosia"
    zosia = User.objects.get(email="zosia@example.com")
    assert not zosia.has_usable_password()
    assert PasswordLink.objects.get().token_hash != token  # only the hash is kept

    visitor = Client()
    assert visitor.get(f"/api/invites/{token}").json() == {
        "email": "zosia@example.com",
        "name": "Zosia",
        "purpose": "invite",
    }
    assert post(visitor, f"/api/invites/{token}", {"password": "short"}).status_code == 422
    assert post(visitor, f"/api/invites/{token}", {"password": GOOD}).status_code == 200
    assert visitor.get("/api/me/").json()["email"] == "zosia@example.com"  # logged in
    zosia.refresh_from_db()
    assert zosia.check_password(GOOD)
    # Used up.
    assert visitor.get(f"/api/invites/{token}").status_code == 404
    assert (
        post(Client(), f"/api/invites/{token}", {"password": GOOD}).json()["detail"]
        == "link_invalid"
    )


def test_links_expire_and_a_new_one_replaces_the_old(admin_client):
    user = UserFactory()
    user.set_password(GOOD)
    user.save()
    first = post(admin_client, f"/api/users/{user.pk}/link").json()
    assert first["purpose"] == "reset"  # has a password: a reset
    second = post(admin_client, f"/api/users/{user.pk}/link").json()
    assert Client().get(f"/api/invites/{first['token']}").status_code == 404
    PasswordLink.objects.update(expires_at=timezone.now() - timedelta(minutes=1))
    assert Client().get(f"/api/invites/{second['token']}").status_code == 404


def test_account_list_and_edits(admin_client):
    tata = PersonFactory(display_name="Tata")
    user = UserFactory(email="tata@example.com")
    resp = put(
        admin_client,
        f"/api/users/{user.pk}",
        {
            "email": "TATA@example.com",
            "name": "Tata",
            "locale": "en",
            "is_active": True,
            "role_ids": [role(PARENT)],
            "person_id": str(tata.id),
        },
    )
    assert resp.status_code == 200, resp.json()
    out = resp.json()
    assert out["roles"] == [{"id": role(PARENT), "name": PARENT}]
    assert out["person"]["display_name"] == "Tata"
    rows = {u["email"]: u for u in admin_client.get("/api/users").json()}
    assert rows["TATA@example.com"]["locale"] == "en"

    # Someone else's person can't be taken; an address can't be used twice.
    other = UserFactory()
    body = {**{k: out[k] for k in ("email", "name", "locale", "is_active")}, "role_ids": []}
    assert put(admin_client, f"/api/users/{other.pk}", {**body, "person_id": str(tata.id)}).json()[
        "detail"
    ] in {"person_taken", "email_taken"}
    resp = put(
        admin_client,
        f"/api/users/{other.pk}",
        {**body, "email": "tata@EXAMPLE.com", "person_id": None},
    )
    assert resp.json()["detail"] == "email_taken"


def test_nobody_switches_themself_off(client):
    me = UserFactory(is_superuser=True)
    client.force_login(me)
    body = {
        "email": me.email,
        "name": "",
        "locale": "pl",
        "is_active": False,
        "role_ids": [],
        "person_id": None,
    }
    assert put(client, f"/api/users/{me.pk}", body).json()["detail"] == "deactivate_self"


def test_switched_off_account_loses_its_link(admin_client):
    created = post(admin_client, "/api/users", {"email": "x@example.com", "name": "X"}).json()
    body = {
        "email": "x@example.com",
        "name": "X",
        "locale": "pl",
        "is_active": False,
        "role_ids": [],
        "person_id": None,
    }
    put(admin_client, f"/api/users/{created['user']['id']}", body)
    assert Client().get(f"/api/invites/{created['link']['token']}").status_code == 404


# ---- who may manage ---------------------------------------------------------------


@pytest.fixture
def role_admin(client):
    """An admin by the Admin role (not a main admin)."""
    seed_roles()
    user = UserFactory()
    user.groups.add(Group.objects.get(name=ADMIN), Group.objects.get(name=PARENT))
    client.force_login(user)
    return client, user


def test_only_admins_manage_accounts_and_roles(client):
    seed_roles()
    parent = UserFactory()
    parent.groups.add(Group.objects.get(name=PARENT))
    client.force_login(parent)
    assert client.get("/api/users").status_code == 403
    assert post(client, "/api/users", {"email": "x@example.com", "name": "X"}).status_code == 403
    assert client.get("/api/access/roles").status_code == 403
    assert post(client, "/api/access/roles", {"name": "Babcia"}).status_code == 403


def test_an_admin_cannot_lock_themself_out(role_admin):
    client, me = role_admin
    body = {"email": me.email, "name": "", "locale": "pl", "is_active": True, "person_id": None}
    resp = put(client, f"/api/users/{me.pk}", {**body, "role_ids": [role(PARENT)]})
    assert resp.json()["detail"] == "lose_admin"
    assert me.groups.filter(name=ADMIN).exists()  # rolled back

    admin_grant = AccessGrant.objects.get(group__name=ADMIN, module="admin")
    assert client.delete(f"/api/access/grants/{admin_grant.id}").json()["detail"] == "lose_admin"
    assert AccessGrant.objects.filter(pk=admin_grant.id).exists()


def test_only_a_main_admin_changes_a_main_admin(role_admin):
    client, _ = role_admin
    boss = UserFactory(is_superuser=True)
    body = {"email": boss.email, "name": "Boss", "locale": "pl", "role_ids": [], "person_id": None}
    assert put(client, f"/api/users/{boss.pk}", {**body, "is_active": False}).status_code == 403
    assert (
        put(client, f"/api/users/{boss.pk}", {**body, "is_active": True}).status_code == 200
    )  # name only


# ---- roles and exceptions ------------------------------------------------------------


def test_roles_and_their_grants(admin_client):
    babcia = post(admin_client, "/api/access/roles", {"name": "Babcia"}).json()
    assert (
        post(admin_client, "/api/access/roles", {"name": "babcia"}).json()["detail"] == "role_taken"
    )
    resp = post(
        admin_client,
        "/api/access/grants",
        {"group_id": babcia["id"], "module": "health", "level": "view", "subjects": "all"},
    )
    assert resp.status_code == 200
    roles = {r["name"]: r for r in admin_client.get("/api/access/roles").json()}
    assert [g["module"] for g in roles["Babcia"]["grants"]] == ["health"]
    assert roles[ADMIN]["builtin"] and not roles["Babcia"]["builtin"]

    assert (
        put(admin_client, f"/api/access/roles/{babcia['id']}", {"name": "Dziadkowie"}).status_code
        == 200
    )
    assert (
        put(admin_client, f"/api/access/roles/{role(ADMIN)}", {"name": "X"}).json()["detail"]
        == "builtin_role"
    )
    assert (
        admin_client.delete(f"/api/access/roles/{role(CHILD)}").json()["detail"] == "builtin_role"
    )
    assert admin_client.delete(f"/api/access/roles/{babcia['id']}").status_code == 200
    assert not AccessGrant.objects.filter(
        module="health", group__isnull=True, user__isnull=True
    ).exists()


def test_an_accounts_own_exception_counts(admin_client):
    kid_person = PersonFactory(display_name="Zosia")
    parent = UserFactory()
    parent.groups.add(Group.objects.get(name=PARENT))
    # Parent, but no finance; and health only for Zosia until a date.
    post(
        admin_client,
        "/api/access/grants",
        {"user_id": parent.pk, "module": "finance", "level": "view", "effect": "deny"},
    )
    resp = post(
        admin_client,
        "/api/access/grants",
        {
            "user_id": parent.pk,
            "module": "health",
            "level": "view",
            "subjects": "selected",
            "person_ids": [],
        },
    )
    assert resp.json()["detail"] == "persons_required"
    post(
        admin_client,
        "/api/access/grants",
        {
            "user_id": parent.pk,
            "module": "notes",
            "level": "view",
            "subjects": "selected",
            "person_ids": [str(kid_person.id)],
        },
    )
    assert [
        g["module"] for g in admin_client.get(f"/api/access/grants?user_id={parent.pk}").json()
    ] == [
        "finance",
        "notes",
    ]
    client = Client()
    client.force_login(parent)
    modules = client.get("/api/me/permissions").json()["modules"]
    assert modules["finance"]["view"] is False  # denied, despite the Parent role
    assert modules["cars"]["edit"] is True


def test_setup_person_is_the_admins_own(client):
    post(client, "/api/setup", setup_body(name="  Mama  Kasia "))
    assert Person.objects.get().display_name == "Mama Kasia"
