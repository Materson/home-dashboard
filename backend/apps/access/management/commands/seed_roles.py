"""Idempotent seed for the three starting role templates.

Run after ``migrate`` (the backend container does it on every start):

    uv run python manage.py seed_roles

Creates the Parents / Children / Admin groups and their AccessGrant rows.
Re-running is safe — existing grants with the same (group, module, level,
effect) are kept, missing ones are added, and no grant is ever deleted here."""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.access.roles import seed_roles


class Command(BaseCommand):
    help = "Create / update the default role groups and grants."

    def handle(self, *_args, **_opts) -> None:
        for line in seed_roles():
            self.stdout.write(line)
