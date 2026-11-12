"""Provider adapters behind one small interface (see ``base``)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Adapter, ChatMessage, Image, LLMError, ToolCall, ToolResult, ToolSpec, Turn

if TYPE_CHECKING:
    from apps.assistant.models import ProviderProfile

__all__ = [
    "Adapter",
    "ChatMessage",
    "Image",
    "LLMError",
    "ToolCall",
    "ToolResult",
    "ToolSpec",
    "Turn",
    "build_adapter",
]

# Tests swap this for a fake (``build_adapter`` returns it when set).
TEST_ADAPTER: Adapter | None = None


def build_adapter(profile: ProviderProfile) -> Adapter:
    """The adapter for a profile — imports only the SDK it needs."""
    if TEST_ADAPTER is not None:
        return TEST_ADAPTER
    if profile.kind == "anthropic":
        from .anthropic_adapter import AnthropicAdapter  # noqa: PLC0415

        return AnthropicAdapter(api_key=profile.api_key, model=profile.model)
    if profile.kind == "google":
        from .google_adapter import GoogleAdapter  # noqa: PLC0415

        return GoogleAdapter(api_key=profile.api_key, model=profile.model)
    if profile.kind in ("openai", "openrouter", "ollama", "openai_compatible"):
        from .openai_adapter import OpenAIAdapter  # noqa: PLC0415

        return OpenAIAdapter(
            api_key=profile.api_key,
            model=profile.model,
            base_url=profile.base_url,
            kind=profile.kind,
            allow_data_collection=profile.allow_data_collection,
        )
    raise LLMError(f"Nieznany dostawca: {profile.kind}")
