"""The starting role templates (Admin / Parent / Child) and their grants.

``seed_roles()`` is idempotent: missing groups and grants are added, a grant's
``subjects`` is brought back in line, nothing is ever deleted — so roles edited
in the app keep their extra grants. Run by first-time setup and on every
backend start (``manage.py seed_roles``)."""

from __future__ import annotations

from django.contrib.auth.models import Group

from .models import AccessGrant

ADMIN = "Admin"
PARENT = "Parent"
CHILD = "Child"

ROLES: dict[str, list[tuple[str, str, str, str]]] = {
    # group: [(module, level, effect, subjects), ...]
    ADMIN: [
        ("admin", "manage", "allow", "all"),
        ("people", "manage", "allow", "all"),
        ("assistant", "manage", "allow", "all"),
    ],
    PARENT: [
        ("finance", "edit", "allow", "all"),
        ("cars", "edit", "allow", "all"),
        ("health", "edit", "allow", "all"),
        ("household", "edit", "allow", "all"),
        ("calendar", "edit", "allow", "all"),
        ("notes", "edit", "allow", "all"),
        ("assistant", "edit", "allow", "all"),
        ("people", "manage", "allow", "all"),  # add / edit / archive family members
    ],
    CHILD: [
        ("health", "view", "allow", "self"),
        ("household", "edit", "allow", "all"),
        ("calendar", "edit", "allow", "self"),
        ("notes", "edit", "allow", "self"),
        ("assistant", "view", "allow", "self"),
    ],
}


def seed_roles() -> list[str]:
    """Create / update the default role groups and grants; returns what it did,
    one line each ("+" added, "=" already there)."""
    log: list[str] = []
    for group_name, rows in ROLES.items():
        group, created = Group.objects.get_or_create(name=group_name)
        log.append(f"{'+' if created else '='} group {group_name}")
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
            log.append(f"  {'+' if created else '='} {module}:{level}:{effect} ({subjects})")
    return log
