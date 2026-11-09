"""Permission matrix tests for AccessContext.

These are the backbone of the whole app: every module × level × person-scope
combination that matters should have a row here. REST endpoints and AI tools
both go through the same context, so a passing row here also protects both."""
from __future__ import annotations

import pytest

from apps.access.context import AccessContext
from apps.access.models import AccessGrant

from .factories import AccessGrantFactory, GroupFactory, PersonFactory, UserFactory

pytestmark = pytest.mark.django_db


def test_deny_all_by_default():
    user = UserFactory()
    ctx = AccessContext.for_user(user)
    for module in ("finance", "cars", "health"):
        assert not ctx.has(module, "view")


def test_group_grant_lifts_module_access():
    user = UserFactory()
    group = GroupFactory()
    user.groups.add(group)
    AccessGrantFactory(group=group, module="finance", level="edit")

    ctx = AccessContext.for_user(user)
    assert ctx.has("finance", "view")
    assert ctx.has("finance", "edit")
    assert not ctx.has("finance", "manage")
    assert not ctx.has("cars", "view")


def test_direct_user_deny_beats_group_allow():
    user = UserFactory()
    group = GroupFactory()
    user.groups.add(group)
    AccessGrantFactory(group=group, module="finance", level="view")
    AccessGrantFactory(user=user, module="finance", level="view", effect=AccessGrant.Effect.DENY)

    ctx = AccessContext.for_user(user)
    assert not ctx.has("finance", "view")


def test_self_subjects_scopes_to_user_person():
    person = PersonFactory()
    user = UserFactory()
    person.user = user
    person.save()
    AccessGrantFactory(user=user, module="health", level="view", subjects=AccessGrant.Subjects.SELF)

    ctx = AccessContext.for_user(user)
    assert ctx.scopes["health"].person_ids == {person.id}


def test_admin_user_has_everything():
    user = UserFactory(is_superuser=True, is_staff=True)
    ctx = AccessContext.for_user(user)
    assert ctx.is_admin
    assert ctx.has("finance", "manage")
    assert ctx.has("health", "manage")
