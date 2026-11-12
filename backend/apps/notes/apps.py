from __future__ import annotations

from django.apps import AppConfig


class NotesConfig(AppConfig):
    name = "apps.notes"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        # Lets core attachments find the module; the note itself decides who
        # may see it (Note.check_access).
        from apps.access.permissions import register_module_for  # noqa: PLC0415

        from .models import Note  # noqa: PLC0415

        register_module_for(Note, "notes")
