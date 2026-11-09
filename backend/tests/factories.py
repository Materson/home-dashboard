from __future__ import annotations

import factory
from django.contrib.auth.models import Group

from apps.accounts.models import User
from apps.access.models import AccessGrant
from apps.people.models import Person


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User

    email = factory.Sequence(lambda n: f"u{n}@example.com")
    first_name = "Test"
    last_name = "User"


class PersonFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Person

    display_name = factory.Sequence(lambda n: f"Person {n}")


class GroupFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Group

    name = factory.Sequence(lambda n: f"Group {n}")


class AccessGrantFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = AccessGrant

    module = "finance"
    level = "view"
    effect = AccessGrant.Effect.ALLOW
    subjects = AccessGrant.Subjects.ALL
