"""Assistant writes: conversations, sending a message (with photos), AI
settings and provider profiles (admin only)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from django.core.exceptions import PermissionDenied
from django.db.transaction import atomic

from apps.core import attachments

from . import loop, policy
from .llm import Image, LLMError, build_adapter, openrouter
from .models import AISettings, Conversation, Message, ProviderProfile
from .selectors import get_conversation, require_use

if TYPE_CHECKING:
    from django.core.files.uploadedfile import UploadedFile

    from apps.access.context import AccessContext

    from .llm.openrouter import Model

MAX_FILES = 4
MAX_TEXT = 4000


# -------------------- Conversations --------------------


def create_conversation(ctx: AccessContext, *, private: bool = False) -> Conversation:
    require_use(ctx)
    return Conversation.objects.create(owner_id=ctx.user_id, private=private)


def update_conversation(ctx: AccessContext, conversation_id: UUID, *, title: str) -> Conversation:
    conv = get_conversation(ctx, conversation_id)
    conv.title = title.strip()[:120]
    conv.save(update_fields=["title", "updated_at"])
    return conv


@atomic
def delete_conversation(ctx: AccessContext, conversation_id: UUID) -> None:
    conv = get_conversation(ctx, conversation_id)
    for message in conv.messages.all():
        attachments.delete_all_for(message)
    conv.delete()


def send_message(
    ctx: AccessContext,
    conversation_id: UUID,
    *,
    text: str,
    page: str = "",
    files: list[UploadedFile] | None = None,
) -> tuple[Message, Message]:
    """Store the question (and its photos), get the answer. Not atomic on
    purpose: the model call can take a while and the question stays even
    if the answer fails."""
    conv = get_conversation(ctx, conversation_id)
    files = files or []
    text = text.strip()[:MAX_TEXT]
    if not text and not files:
        raise ValueError("empty message")
    if len(files) > MAX_FILES:
        raise ValueError(f"at most {MAX_FILES} files")
    question = Message.objects.create(
        conversation=conv, role=Message.Role.USER, text=text, page=page[:200]
    )
    images = []
    for f in files:
        att = attachments.store(question, f, uploaded_by_id=ctx.user_id)
        with att.file.open("rb") as fh:
            images.append(Image(mime=att.mime_type, data=fh.read()))
    answer = loop.run_turn(ctx, conv, question, images)
    return question, answer


# -------------------- Settings (admin) --------------------


# Services on the internet (never on the home network), each needing a key.
HOSTED = ("anthropic", "openai", "google", "openrouter")


def _require_manage(ctx: AccessContext) -> None:
    if not policy.can_manage(ctx):
        raise PermissionDenied("only an admin manages AI settings")


@atomic
def save_settings(ctx: AccessContext, data: dict[str, Any]) -> AISettings:
    _require_manage(ctx)
    settings = policy.ai_settings()
    for key in ("chat_profile_id", "local_profile_id"):
        if key in data:
            pid = data[key]
            if pid and not ProviderProfile.objects.filter(pk=pid).exists():
                raise ValueError(f"unknown profile {pid}")
            setattr(settings, key, pid or None)
    if settings.local_profile_id:
        local = ProviderProfile.objects.get(pk=settings.local_profile_id)
        if local.location != ProviderProfile.Location.LOCAL:
            raise ValueError("the private-conversation model must be a local one")
    if "policies" in data:
        bad = {
            k: v
            for k, v in data["policies"].items()
            if k not in policy.MODULES or v not in AISettings.Policy.values
        }
        if bad:
            raise ValueError(f"invalid policies: {bad}")
        settings.policies = {**policy.policies(settings), **data["policies"]}
    settings.save()
    return policy.ai_settings()


@atomic
def save_profile(
    ctx: AccessContext, data: dict[str, Any], profile_id: UUID | None = None
) -> ProviderProfile:
    _require_manage(ctx)
    profile = ProviderProfile.objects.get(pk=profile_id) if profile_id else ProviderProfile()
    api_key = data.pop("api_key", None)
    for k, v in data.items():
        setattr(profile, k, v)
    if api_key:  # empty = keep the stored key
        profile.api_key = api_key
    if profile.kind == "openai_compatible" and not profile.base_url:
        raise ValueError("an OpenAI-compatible server needs its URL")
    if profile.kind in HOSTED and not profile.api_key:
        raise ValueError("this provider needs an API key")
    if profile.kind in HOSTED:
        # Always "cloud": a hosted service marked local would get local-only
        # data (health, notes) without aliases.
        profile.location = ProviderProfile.Location.CLOUD
    if profile.kind == "openrouter":
        profile.base_url = ""  # always openrouter.ai
    else:
        profile.allow_data_collection = False  # an OpenRouter routing choice only
    profile.save()
    return profile


def openrouter_models(ctx: AccessContext, profile_id: UUID | None = None) -> list[Model]:
    """OpenRouter's models that can use tools (for picking one in the form),
    asked with that profile's key when there is one."""
    _require_manage(ctx)
    profile = ProviderProfile.objects.filter(pk=profile_id).first() if profile_id else None
    return openrouter.tool_models(profile.api_key if profile else "")


def delete_profile(ctx: AccessContext, profile_id: UUID) -> None:
    _require_manage(ctx)
    ProviderProfile.objects.filter(pk=profile_id).delete()


def test_profile(ctx: AccessContext, profile_id: UUID) -> str:
    """Checks the key/URL and the model name; raises LLMError with a readable text."""
    _require_manage(ctx)
    profile = ProviderProfile.objects.get(pk=profile_id)
    return build_adapter(profile).ping()


__all__ = ["LLMError"]
