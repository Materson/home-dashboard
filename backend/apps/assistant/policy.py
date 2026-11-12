"""Which model is used and which modules' data may reach it.

Per module: ``off`` (never offered to the AI), ``local`` (only to a model
on your network), ``cloud`` (also to cloud models, with private data
replaced by aliases). ``documents`` decides where photos/PDFs may go — they
can't be aliased, so a cloud setting sends them as they are.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .models import AISettings, Conversation, ProviderProfile

if TYPE_CHECKING:
    from apps.access.context import AccessContext

MODULES = ("finance", "cars", "household", "people", "health", "notes", "documents")
DEFAULT_POLICIES = {
    "finance": "cloud",
    "cars": "cloud",
    "household": "cloud",
    "people": "cloud",
    "health": "local",
    "notes": "local",
    "documents": "cloud",
}


class NotConfigured(RuntimeError):
    """No usable model for this conversation."""


def ai_settings() -> AISettings:
    obj, _ = AISettings.objects.select_related("chat_profile", "local_profile").get_or_create(pk=1)
    return obj


def policies(settings: AISettings | None = None) -> dict[str, str]:
    stored = (settings or ai_settings()).policies or {}
    return {m: stored.get(m, DEFAULT_POLICIES[m]) for m in MODULES}


def allows(policy: str, location: str) -> bool:
    return policy == "cloud" or (policy == "local" and location == ProviderProfile.Location.LOCAL)


def profile_for(conversation: Conversation, settings: AISettings | None = None) -> ProviderProfile:
    settings = settings or ai_settings()
    if conversation.private:
        profile = settings.local_profile
        if profile is None or not profile.enabled:
            raise NotConfigured("Brak lokalnego modelu — rozmowa prywatna jest niedostępna.")
        return profile
    profile = settings.chat_profile
    if profile is None or not profile.enabled:
        raise NotConfigured("Asystent nie jest jeszcze skonfigurowany (Ustawienia → AI).")
    return profile


def can_manage(ctx: AccessContext) -> bool:
    return ctx.is_admin or ctx.has("admin", "manage")
