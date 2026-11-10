"""Idempotent seed for the three starting role templates.

Run after ``migrate``:
    uv run python manage.py seed_roles

Creates the Parents / Children / Admin groups and their AccessGrant rows.
Re-running is safe — existing grants with the same (group, module, level,
effect) are kept, missing ones are added, and no grant is ever deleted here."""

from __future__ import annotations

from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand

from apps.access.models import AccessGrant

ROLES: dict[str, list[tuple[str, str, str, str]]] = {
    # group: [(module, level, effect, subjects), ...]
    "Admin": [
        ("admin", "manage", "allow", "all"),
        ("people", "manage", "allow", "all"),
        ("assistant", "manage", "allow", "all"),
    ],
    "Parent": [
        ("finance", "edit", "allow", "all"),
        ("cars", "edit", "allow", "all"),
        ("health", "edit", "allow", "all"),
        ("household", "edit", "allow", "all"),
        ("calendar", "edit", "allow", "all"),
        ("notes", "edit", "allow", "all"),
        ("assistant", "edit", "allow", "all"),
        ("people", "view", "allow", "all"),
    ],
    "Child": [
        ("health", "view", "allow", "self"),
        ("household", "edit", "allow", "all"),
        ("calendar", "edit", "allow", "self"),
        ("notes", "edit", "allow", "self"),
        ("assistant", "view", "allow", "self"),
    ],
}


class Command(BaseCommand):
    help = "Create / update the default role groups and grants."

    def handle(self, *_args, **_opts) -> None:
        for group_name, rows in ROLES.items():
            group, created = Group.objects.get_or_create(name=group_name)
            self.stdout.write(f"{'+' if created else '='} group {group_name}")
            for module, level, effect, subjects in rows:
                grant, created = AccessGrant.objects.get_or_create(
                    group=group,
                    module=module,
                    level=level,
                    effect=effect,
                    defaults={"subjects": subjects},
                )
                if not created and grant.subjects != subjects:
                    grant.subjects = subjects
                    grant.save(update_fields=["subjects"])
                self.stdout.write(
                    f"  {'+' if created else '='} {module}:{level}:{effect} ({subjects})"
                )
