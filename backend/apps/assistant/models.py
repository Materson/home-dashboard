"""AI assistant: provider profiles (chosen in Settings), per-module privacy
policy, conversations, proposed changes waiting for confirmation, and a log
of every call to a model (what was sent where).

Nothing here is tied to one vendor: a ``ProviderProfile`` names the kind of
API (Anthropic, OpenAI, Google, Ollama or any OpenAI-compatible server) and
``apps.assistant.llm`` has one thin adapter per kind.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db import models

from apps.core.crypto import EncryptedTextField
from apps.core.models import TimeStamped, UUIDModel

if TYPE_CHECKING:
    from apps.access.context import AccessContext


class ProviderProfile(UUIDModel, TimeStamped):
    class Kind(models.TextChoices):
        ANTHROPIC = "anthropic", "Anthropic (Claude)"
        OPENAI = "openai", "OpenAI (ChatGPT)"
        GOOGLE = "google", "Google (Gemini)"
        OLLAMA = "ollama", "Ollama"
        OPENAI_COMPATIBLE = "openai_compatible", "OpenAI-compatible server"

    class Location(models.TextChoices):
        CLOUD = "cloud", "Cloud"
        LOCAL = "local", "Local (on my network)"

    name = models.CharField(max_length=80)
    kind = models.CharField(max_length=20, choices=Kind.choices)
    model = models.CharField(max_length=120, help_text="Model id, e.g. claude-opus-5-5.")
    base_url = models.CharField(max_length=300, blank=True, help_text="Ollama / self-hosted URL.")
    api_key = EncryptedTextField(blank=True)  # never returned to the browser
    location = models.CharField(max_length=5, choices=Location.choices, default=Location.CLOUD)
    vision = models.BooleanField(default=True, help_text="Can read photos and documents.")
    enabled = models.BooleanField(default=True)

    class Meta:
        ordering = ("name",)

    def __str__(self) -> str:
        return f"{self.name} ({self.kind}: {self.model})"


class AISettings(models.Model):
    """One row (pk=1): which profile does what, and the per-module policy."""

    class Policy(models.TextChoices):
        OFF = "off", "Off"
        LOCAL = "local", "Local model only"
        CLOUD = "cloud", "Cloud allowed (with aliases)"

    chat_profile = models.ForeignKey(
        ProviderProfile, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    local_profile = models.ForeignKey(
        ProviderProfile,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Used for private conversations and local-only modules.",
    )
    # {"finance": "cloud", "health": "local", ...}; missing → DEFAULT_POLICIES.
    policies = models.JSONField(default=dict, blank=True)

    def __str__(self) -> str:
        return "AI settings"


class Conversation(UUIDModel, TimeStamped):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="conversations"
    )
    title = models.CharField(max_length=120, blank=True)
    # Private: everything goes to the local model only.
    private = models.BooleanField(default=False)
    # Stable aliases for this conversation: {"[P1]": "Zosia", "[TEL1]": "600 100 200"}.
    aliases = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("-updated_at",)

    def __str__(self) -> str:
        return self.title or "Rozmowa"


class Message(UUIDModel, TimeStamped):
    class Role(models.TextChoices):
        USER = "user", "User"
        ASSISTANT = "assistant", "Assistant"

    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name="messages"
    )
    role = models.CharField(max_length=10, choices=Role.choices)
    text = models.TextField(blank=True)  # real (re-hydrated) text, as the user sees it
    page = models.CharField(max_length=200, blank=True)  # where the user was when asking
    error = models.BooleanField(default=False)

    class Meta:
        ordering = ("created_at",)

    def __str__(self) -> str:
        return f"{self.role}: {self.text[:40]}"

    def check_access(self, ctx: AccessContext, level: str) -> None:
        """Photos in a conversation are its owner's only (see core attachments)."""
        if self.conversation.owner_id != ctx.user_id:
            raise PermissionDenied("not your conversation")


class PendingAction(UUIDModel, TimeStamped):
    """A change the assistant proposed. ``auto`` ones (own notes, shopping
    lines) were done at once and can be undone; the rest wait for Confirm."""

    class Status(models.TextChoices):
        PROPOSED = "proposed", "Proposed"
        DONE = "done", "Done"
        CANCELLED = "cancelled", "Cancelled"
        UNDONE = "undone", "Undone"
        FAILED = "failed", "Failed"

    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="actions")
    message = models.ForeignKey(
        Message, null=True, blank=True, on_delete=models.SET_NULL, related_name="actions"
    )
    kind = models.CharField(max_length=40)  # e.g. "finance.transaction"
    payload = models.JSONField(default=dict)  # real values (never aliases)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PROPOSED)
    auto = models.BooleanField(default=False)
    # What was created, for undo: [{"type": "notes.note", "id": "…"}, …]
    result = models.JSONField(default=list, blank=True)
    error = models.TextField(blank=True)

    class Meta:
        ordering = ("created_at",)

    def __str__(self) -> str:
        return f"{self.kind} ({self.status})"


class LLMCall(UUIDModel, TimeStamped):
    """One request to a model: who, which provider/location, which modules'
    data were in it, and the messages exactly as sent (aliases included)."""

    conversation = models.ForeignKey(
        Conversation, null=True, blank=True, on_delete=models.CASCADE, related_name="calls"
    )
    message = models.ForeignKey(
        Message, null=True, blank=True, on_delete=models.SET_NULL, related_name="calls"
    )
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    profile_name = models.CharField(max_length=80)
    provider = models.CharField(max_length=20)
    model = models.CharField(max_length=120)
    location = models.CharField(max_length=5)
    modules = models.JSONField(default=list)  # modules whose tool results were sent
    sent = models.JSONField(default=list)  # [{"role": …, "text": …}] as sent
    images = models.PositiveSmallIntegerField(default=0)
    input_tokens = models.PositiveIntegerField(null=True)
    output_tokens = models.PositiveIntegerField(null=True)
    ok = models.BooleanField(default=True)
    error = models.TextField(blank=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.provider}/{self.model} @ {self.created_at:%Y-%m-%d %H:%M}"
