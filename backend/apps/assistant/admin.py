from __future__ import annotations

from django.contrib import admin

from .models import AISettings, LLMCall, ProviderProfile


@admin.register(ProviderProfile)
class ProviderProfileAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "model", "location", "enabled")
    exclude = ("api_key",)  # set it in Settings → AI; never shown back


@admin.register(AISettings)
class AISettingsAdmin(admin.ModelAdmin):
    list_display = ("__str__", "chat_profile", "local_profile")


@admin.register(LLMCall)
class LLMCallAdmin(admin.ModelAdmin):
    """Audit: who sent what where. Conversation text isn't listed here."""

    list_display = ("created_at", "user", "provider", "model", "location", "modules", "ok")
    list_filter = ("provider", "location", "ok")
    fields = (
        "created_at",
        "user",
        "provider",
        "model",
        "location",
        "modules",
        "input_tokens",
        "output_tokens",
        "ok",
        "error",
    )
    readonly_fields = fields
