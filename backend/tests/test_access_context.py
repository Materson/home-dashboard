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


def _kid_with_person():
    user = UserFactory()
    me = PersonFactory(user=user)
    return user, me


def test_edit_self_does_not_inherit_view_everyone():
    """Regression: person sets were merged across levels, so "view everyone"
    + "edit self" let the user edit everyone."""
    user, me = _kid_with_person()
    sibling = PersonFactory()
    AccessGrantFactory(user=user, module="people", level="view", subjects=AccessGrant.Subjects.ALL)
    AccessGrantFactory(user=user, module="people", level="edit", subjects=AccessGrant.Subjects.SELF)
    ctx = AccessContext.for_user(user)

    assert ctx.scopes["people"].persons_for("view") is None  # sees everyone
    assert ctx.scopes["people"].persons_for("edit") == {me.id}  # edits only self
    assert sibling.id not in (ctx.scopes["people"].persons_for("edit") or set())


def test_higher_grant_covers_lower_levels():
    user, me = _kid_with_person()
    AccessGrantFactory(user=user, module="health", level="edit", subjects=AccessGrant.Subjects.SELF)
    scope = AccessContext.for_user(user).scopes["health"]
    assert scope.persons_for("view") == {me.id}
    assert scope.persons_for("manage") == set()


@pytest.mark.parametrize("first", ["self", "all"])
def test_everyone_grant_wins_regardless_of_order(first):
    """Regression: the merge depended on grant order (everyone-then-self
    narrowed to self)."""
    user, _me = _kid_with_person()
    subjects = ["self", "all"] if first == "self" else ["all", "self"]
    for s in subjects:
        AccessGrantFactory(user=user, module="health", level="view", subjects=s)
    assert AccessContext.for_user(user).scopes["health"].persons_for("view") is None


def test_deny_takes_its_level_and_everything_above():
    user = UserFactory()
    group = GroupFactory()
    user.groups.add(group)
    AccessGrantFactory(group=group, module="finance", level="edit")
    AccessGrantFactory(group=group, module="cars", level="edit")
    AccessGrantFactory(user=user, module="finance", level="view", effect=AccessGrant.Effect.DENY)
    AccessGrantFactory(user=user, module="cars", level="edit", effect=AccessGrant.Effect.DENY)

    ctx = AccessContext.for_user(user)
    assert not ctx.has("finance", "view")  # denied view: nothing left
    assert ctx.has("cars", "view") and not ctx.has("cars", "edit")  # denied edit: view only
