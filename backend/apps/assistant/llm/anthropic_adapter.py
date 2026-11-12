"""Claude through Anthropic's official Python SDK (Messages API).

- Within one user turn the assistant's ``response.content`` goes back
  unchanged (thinking / fallback blocks included), as the API requires.
  Earlier turns are sent as plain text only — dropping *all* earlier
  thinking blocks keeps the conversation valid for the history check.
- The system prompt and tool list are stable for the whole conversation
  (page context travels in the user message), so prompt caching works.
- Current models run adaptive thinking by default; we only set ``effort``
  on models that accept it, and opt into server-side refusal fallbacks on
  the models that support them.
"""

from __future__ import annotations

import base64
from typing import Any

import anthropic

from .base import ChatMessage, Image, LLMError, Session, ToolCall, ToolResult, ToolSpec, Turn

MAX_TOKENS = 16000  # non-streaming: stays well under the SDK's HTTP timeout
TIMEOUT_S = 180.0

# Models that take output_config.effort (older Sonnet/Haiku 4.5 reject it).
_EFFORT_PREFIXES = (
    "claude-opus-5",
    "claude-opus-4-6",
    "claude-opus-4-7",
    "claude-opus-4-8",
    "claude-sonnet-5",
    "claude-sonnet-4-6",
    "claude-haiku-5",
    "claude-fable-",
    "claude-mythos-",
)
# Models with server-side refusal fallbacks (beta); "default" routes by category.
_FALLBACK_MODELS = {
    "claude-opus-5-5",
    "claude-opus-5",
    "claude-fable-5-1",
    "claude-fable-5-2",
    "claude-sonnet-5-5",
}
FALLBACK_BETA = "server-side-fallback-2026-07-01"
EFFORT = "medium"  # household Q&A with a few tool calls


def _content(msg: ChatMessage) -> list[dict[str, Any]] | str:
    if not msg.images:
        return msg.text
    blocks: list[dict[str, Any]] = []
    for img in msg.images:  # files first, then the question
        data = base64.standard_b64encode(img.data).decode()
        kind = "document" if img.mime == "application/pdf" else "image"
        blocks.append(
            {"type": kind, "source": {"type": "base64", "media_type": img.mime, "data": data}}
        )
    blocks.append({"type": "text", "text": msg.text or "Przeczytaj załączony plik."})
    return blocks


class AnthropicSession:
    def __init__(self, adapter: AnthropicAdapter, system: str, tools: list[ToolSpec], history):
        self.a = adapter
        self.system = system
        self.tools = [
            {"name": t.name, "description": t.description, "input_schema": t.parameters}
            for t in tools
        ]
        self.messages: list[dict[str, Any]] = [
            {"role": m.role, "content": _content(m)} for m in history
        ]

    def _create(self) -> Any:
        kwargs: dict[str, Any] = {
            "model": self.a.model,
            "max_tokens": MAX_TOKENS,
            "system": self.system,
            "messages": self.messages,
            "cache_control": {"type": "ephemeral"},  # stable system + tools + history prefix
        }
        if self.tools:
            kwargs["tools"] = self.tools
        if self.a.model.startswith(_EFFORT_PREFIXES):
            kwargs["output_config"] = {"effort": EFFORT}
        if self.a.model in _FALLBACK_MODELS:
            return self.a.client.beta.messages.create(
                betas=[FALLBACK_BETA], fallbacks="default", **kwargs
            )
        return self.a.client.messages.create(**kwargs)

    def step(self) -> Turn:
        try:
            response = self._create()
        except anthropic.AuthenticationError as exc:
            raise LLMError("Nieprawidłowy klucz API Anthropic.") from exc
        except anthropic.NotFoundError as exc:
            raise LLMError(f"Model {self.a.model!r} nie istnieje lub jest niedostępny.") from exc
        except anthropic.RateLimitError as exc:
            raise LLMError("Limit zapytań Anthropic — spróbuj za chwilę.") from exc
        except anthropic.BadRequestError as exc:
            raise LLMError(f"Anthropic odrzucił zapytanie: {exc.message}") from exc
        except anthropic.APIStatusError as exc:
            raise LLMError(f"Błąd serwera Anthropic ({exc.status_code}).") from exc
        except anthropic.APIConnectionError as exc:
            raise LLMError("Brak połączenia z Anthropic.") from exc

        usage = getattr(response, "usage", None)
        if response.stop_reason == "refusal":
            return Turn(
                text="Model odmówił odpowiedzi na to pytanie.",
                tool_calls=[],
                input_tokens=getattr(usage, "input_tokens", None),
                output_tokens=getattr(usage, "output_tokens", None),
                refused=True,
            )
        # Pass the content back unchanged (thinking / fallback blocks included).
        self.messages.append({"role": "assistant", "content": response.content})
        text = "".join(b.text for b in response.content if b.type == "text")
        calls = [
            ToolCall(id=b.id, name=b.name, args=dict(b.input or {}))
            for b in response.content
            if b.type == "tool_use"
        ]
        return Turn(
            text=text,
            tool_calls=calls,
            input_tokens=getattr(usage, "input_tokens", None),
            output_tokens=getattr(usage, "output_tokens", None),
        )

    def add_tool_results(self, results: list[ToolResult]) -> None:
        # All results of one response go back in a single user message.
        self.messages.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": r.call.id,
                        "content": r.content,
                        "is_error": r.is_error,
                    }
                    for r in results
                ],
            }
        )


class AnthropicAdapter:
    supported_files = frozenset({"image/jpeg", "image/png", "image/webp", "application/pdf"})

    def __init__(self, *, api_key: str, model: str, client: Any = None):
        self.model = model
        self.client = client or anthropic.Anthropic(api_key=api_key or None, timeout=TIMEOUT_S)

    def start(self, system: str, tools: list[ToolSpec], history: list[ChatMessage]) -> Session:
        return AnthropicSession(self, system, tools, history)

    def ping(self) -> str:
        """Checks the key and the model id without generating anything."""
        try:
            info = self.client.models.retrieve(self.model)
        except anthropic.AuthenticationError as exc:
            raise LLMError("Nieprawidłowy klucz API.") from exc
        except anthropic.NotFoundError as exc:
            raise LLMError(f"Model {self.model!r} nie istnieje.") from exc
        except anthropic.APIConnectionError as exc:
            raise LLMError("Brak połączenia z Anthropic.") from exc
        except anthropic.APIStatusError as exc:
            raise LLMError(f"Błąd Anthropic ({exc.status_code}).") from exc
        return getattr(info, "display_name", None) or self.model


__all__ = ["AnthropicAdapter", "Image"]
