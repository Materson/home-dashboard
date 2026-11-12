from __future__ import annotations

from django.apps import AppConfig


class AssistantConfig(AppConfig):
    name = "apps.assistant"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        # Photos in a chat are core attachments of the question; the
        # conversation's owner alone may see them (Message.check_access).
        from apps.access.permissions import register_module_for  # noqa: PLC0415

        from .models import Message  # noqa: PLC0415

        register_module_for(Message, "assistant")
