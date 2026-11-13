"""Assistant REST API — thin wrappers over selectors/services."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from django.contrib.contenttypes.models import ContentType
from django.http import HttpRequest
from ninja import File, Form, Router, Schema
from ninja.files import UploadedFile

from apps.access.context import get_ctx
from apps.core.attachments import AttachmentError
from apps.core.models import Attachment

from . import actions, policy, selectors, services
from .llm import LLMError
from .models import Message, PendingAction, ProviderProfile

router = Router()


# -------------------- Status --------------------


class ProfileBrief(Schema):
    id: UUID
    name: str
    kind: str
    model: str
    location: str


class ModelOption(ProfileBrief):
    """A model one can pick in the chat."""

    vision: bool  # reads photos / documents


class StatusOut(Schema):
    can_use: bool
    configured: bool
    private_available: bool
    can_manage: bool
    chat_profile: ProfileBrief | None
    local_profile: ProfileBrief | None
    file_profile: ProfileBrief | None  # default for messages with files (None: the chat model)
    models: list[ModelOption]  # switched on, to pick in the chat
    documents: str  # where photos / PDFs may go: off / local / cloud


@router.get("/status", response=StatusOut)
def status(request: HttpRequest) -> dict[str, Any]:
    ctx = get_ctx(request)
    s = policy.ai_settings()
    chat = s.chat_profile if s.chat_profile and s.chat_profile.enabled else None
    local = s.local_profile if s.local_profile and s.local_profile.enabled else None
    files = s.file_profile if s.file_profile and s.file_profile.enabled else None
    return {
        "can_use": bool(ctx.user_id) and ctx.has("assistant", "view"),
        "configured": chat is not None,
        "private_available": local is not None,
        "can_manage": policy.can_manage(ctx),
        "chat_profile": chat,
        "local_profile": local,
        "file_profile": files,
        "models": list(ProviderProfile.objects.filter(enabled=True)),
        "documents": policy.policies(s)["documents"],
    }


# -------------------- Conversations --------------------


class ConversationOut(Schema):
    id: UUID
    title: str
    private: bool
    updated_at: datetime
    text_profile_id: UUID | None  # picked in the chat (None: the default)
    file_profile_id: UUID | None


class ConversationIn(Schema):
    private: bool = False
    text_profile_id: UUID | None = None
    file_profile_id: UUID | None = None


class ModelsIn(Schema):
    text_profile_id: UUID | None
    file_profile_id: UUID | None


class TitleIn(Schema):
    title: str


class ActionOut(Schema):
    id: UUID
    kind: str
    payload: dict
    status: str
    auto: bool
    error: str


class FileOut(Schema):
    id: UUID
    url: str
    mime_type: str
    original_name: str


class MessageOut(Schema):
    id: UUID
    role: str
    text: str
    error: bool
    created_at: datetime
    files: list[FileOut]
    actions: list[ActionOut]
    has_calls: bool


def _message(m: Message) -> dict[str, Any]:
    ct = ContentType.objects.get_for_model(Message)
    files = Attachment.objects.filter(content_type=ct, object_id=m.pk)
    return {
        "id": m.id,
        "role": m.role,
        "text": m.text,
        "error": m.error,
        "created_at": m.created_at,
        "files": [
            {
                "id": f.id,
                "url": f"/api/media/{f.id}/",
                "mime_type": f.mime_type,
                "original_name": f.original_name,
            }
            for f in files
        ],
        "actions": list(m.actions.all()),
        "has_calls": m.role == "assistant" and m.calls.exists(),
    }


@router.get("/conversations", response=list[ConversationOut])
def list_conversations(request: HttpRequest) -> Any:
    return selectors.list_conversations(get_ctx(request))


@router.post("/conversations", response={200: ConversationOut, 422: dict})
def create_conversation(request: HttpRequest, payload: ConversationIn):
    try:
        return services.create_conversation(get_ctx(request), **payload.dict())
    except ValueError as exc:
        return 422, {"detail": str(exc)}


@router.put("/conversations/{conversation_id}/models", response={200: ConversationOut, 422: dict})
def set_models(request: HttpRequest, conversation_id: UUID, payload: ModelsIn):
    """Which models answer from now on: for text, and for messages with files."""
    try:
        return services.set_models(get_ctx(request), conversation_id, **payload.dict())
    except ValueError as exc:
        return 422, {"detail": str(exc)}


@router.put("/conversations/{conversation_id}", response=ConversationOut)
def rename_conversation(request: HttpRequest, conversation_id: UUID, payload: TitleIn) -> Any:
    return services.update_conversation(get_ctx(request), conversation_id, title=payload.title)


@router.delete("/conversations/{conversation_id}")
def delete_conversation(request: HttpRequest, conversation_id: UUID) -> dict[str, bool]:
    services.delete_conversation(get_ctx(request), conversation_id)
    return {"deleted": True}


@router.get("/conversations/{conversation_id}/messages", response=list[MessageOut])
def list_messages(request: HttpRequest, conversation_id: UUID) -> list[dict[str, Any]]:
    return [_message(m) for m in selectors.list_messages(get_ctx(request), conversation_id)]


class ExchangeOut(Schema):
    question: MessageOut
    answer: MessageOut


@router.post("/conversations/{conversation_id}/messages", response={200: ExchangeOut, 422: dict})
def send_message(
    request: HttpRequest,
    conversation_id: UUID,
    text: Form[str] = "",
    page: Form[str] = "",
    files: File[list[UploadedFile]] = None,
):
    """Ask (optionally with photos / PDFs). Waits for the answer."""
    try:
        question, answer = services.send_message(
            get_ctx(request), conversation_id, text=text, page=page, files=files or []
        )
    except (ValueError, AttachmentError) as exc:
        return 422, {"detail": str(exc)}
    return {"question": _message(question), "answer": _message(answer)}


class CallOut(Schema):
    created_at: datetime
    profile_name: str
    provider: str
    model: str
    location: str
    modules: list[str]
    sent: list[dict]
    images: int
    input_tokens: int | None
    output_tokens: int | None
    ok: bool
    error: str


@router.get("/messages/{message_id}/calls", response=list[CallOut])
def message_calls(request: HttpRequest, message_id: UUID) -> Any:
    """Exactly what went to the model for this answer (aliases included)."""
    return selectors.calls_for(get_ctx(request), message_id)


# -------------------- Proposed changes --------------------


@router.post("/actions/{action_id}/{decision}", response={200: ActionOut, 409: dict})
def decide(
    request: HttpRequest, action_id: UUID, decision: Literal["confirm", "cancel", "undo"]
) -> Any:
    fn = {"confirm": actions.confirm, "cancel": actions.cancel, "undo": actions.undo}[decision]
    try:
        action: PendingAction = fn(get_ctx(request), action_id)
    except ValueError as exc:
        return 409, {"detail": str(exc)}
    return action


# -------------------- Settings (admin) --------------------


class ProfileIn(Schema):
    name: str
    kind: Literal["anthropic", "openai", "google", "openrouter", "ollama", "openai_compatible"]
    model: str
    base_url: str = ""
    api_key: str = ""  # empty on update = keep the stored one
    location: Literal["cloud", "local"] = "cloud"
    vision: bool = True
    allow_data_collection: bool = False  # OpenRouter: providers that may store prompts
    enabled: bool = True


class ProfileOut(Schema):
    id: UUID
    name: str
    kind: str
    model: str
    base_url: str
    location: str
    vision: bool
    allow_data_collection: bool
    enabled: bool
    has_key: bool

    @staticmethod
    def resolve_has_key(obj: ProviderProfile) -> bool:
        return bool(obj.api_key)


class SettingsIn(Schema):
    """Only the fields sent change (the page saves one at a time)."""

    chat_profile_id: UUID | None = None
    local_profile_id: UUID | None = None
    file_profile_id: UUID | None = None
    policies: dict[str, str] = {}


class SettingsOut(Schema):
    chat_profile_id: UUID | None
    local_profile_id: UUID | None
    file_profile_id: UUID | None
    policies: dict[str, str]
    profiles: list[ProfileOut]


def _settings_out() -> dict[str, Any]:
    s = policy.ai_settings()
    return {
        "chat_profile_id": s.chat_profile_id,
        "local_profile_id": s.local_profile_id,
        "file_profile_id": s.file_profile_id,
        "policies": policy.policies(s),
        "profiles": list(ProviderProfile.objects.all()),
    }


@router.get("/settings", response=SettingsOut)
def get_settings(request: HttpRequest) -> dict[str, Any]:
    services._require_manage(get_ctx(request))
    return _settings_out()


@router.put("/settings", response={200: SettingsOut, 422: dict})
def put_settings(request: HttpRequest, payload: SettingsIn):
    try:
        services.save_settings(get_ctx(request), payload.dict(exclude_unset=True))
    except ValueError as exc:
        return 422, {"detail": str(exc)}
    return _settings_out()


@router.post("/profiles", response={200: ProfileOut, 422: dict})
def create_profile(request: HttpRequest, payload: ProfileIn):
    try:
        return services.save_profile(get_ctx(request), payload.dict())
    except ValueError as exc:
        return 422, {"detail": str(exc)}


@router.put("/profiles/{profile_id}", response={200: ProfileOut, 422: dict})
def update_profile(request: HttpRequest, profile_id: UUID, payload: ProfileIn):
    try:
        return services.save_profile(get_ctx(request), payload.dict(), profile_id)
    except ValueError as exc:
        return 422, {"detail": str(exc)}


@router.delete("/profiles/{profile_id}")
def delete_profile(request: HttpRequest, profile_id: UUID) -> dict[str, bool]:
    services.delete_profile(get_ctx(request), profile_id)
    return {"deleted": True}


class OpenRouterModelOut(Schema):
    id: str
    name: str
    vision: bool
    context: int | None
    price_in: str | None  # USD per 1M tokens
    price_out: str | None


@router.get("/openrouter/models", response={200: list[OpenRouterModelOut], 422: dict})
def openrouter_models(request: HttpRequest, profile_id: UUID | None = None):
    """OpenRouter's models that can use tools, to pick one in the profile form."""
    try:
        models = services.openrouter_models(get_ctx(request), profile_id)
    except LLMError as exc:
        return 422, {"detail": exc.user_text}
    return [m.as_dict() for m in models]


class TestOut(Schema):
    ok: bool
    detail: str


@router.post("/profiles/{profile_id}/test", response=TestOut)
def test_profile(request: HttpRequest, profile_id: UUID) -> dict[str, Any]:
    try:
        return {"ok": True, "detail": services.test_profile(get_ctx(request), profile_id)}
    except LLMError as exc:
        return {"ok": False, "detail": exc.user_text}
