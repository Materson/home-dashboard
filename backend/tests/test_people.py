"""People page permissions: parents manage everyone; a child edits only
themself (when granted), even if they can see the whole family."""

from __future__ import annotations

import pytest
from django.core.exceptions import PermissionDenied
from django.http import Http404

from apps.access.context import AccessContext
from apps.access.models import AccessGrant
from apps.people import selectors, services

from .factories import AccessGrantFactory, PersonFactory, UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def family():
    parent_user, child_user = UserFactory(), UserFactory()
    AccessGrantFactory(user=parent_user, module="people", level="manage")
    AccessGrantFactory(user=child_user, module="people", level="view")  # sees everyone
    AccessGrantFactory(
        user=child_user, module="people", level="edit", subjects=AccessGrant.Subjects.SELF
    )
    mom = PersonFactory(display_name="Mama", user=parent_user)
    kid = PersonFactory(display_name="Zosia", user=child_user)
    return {
        "parent": AccessContext.for_user(parent_user),
        "child": AccessContext.for_user(child_user),
        "mom": mom,
        "kid": kid,
    }


def test_parent_adds_edits_and_archives(family):
    baby = services.create_person(family["parent"], display_name="Staś")
    services.update_person(family["parent"], family["kid"].id, display_name="Zosia K.")
    services.archive_person(family["parent"], baby.id)
    assert {p.display_name for p in selectors.list_people(family["parent"])} == {"Mama", "Zosia K."}


def test_child_edits_only_themself(family):
    child = family["child"]
    assert len(selectors.list_people(child)) == 2  # sees the family
    services.update_person(child, family["kid"].id, display_name="Zosia ✿")
    with pytest.raises(Http404):
        services.update_person(child, family["mom"].id, display_name="hacked")
    with pytest.raises(PermissionDenied):
        services.create_person(child, display_name="Nowy")
    with pytest.raises(PermissionDenied):
        services.archive_person(child, family["kid"].id)
    assert selectors.editable_person_ids(child) == {family["kid"].id}


def test_people_api_reports_what_the_caller_may_edit(client, family):
    client.force_login(family["kid"].user)
    rows = {p["display_name"]: p["can_edit"] for p in client.get("/api/people/").json()}
    assert rows == {"Mama": False, "Zosia": True}
