"""The vendor-neutral surface of the LLM layer.

The agent loop (``apps.assistant.loop``) talks only to an ``Adapter``; each
adapter turns these neutral shapes into its own SDK's request/response and
keeps the provider-native transcript of the current turn in a ``Session``
(so e.g. Claude's thinking blocks go back unchanged within a tool loop).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


class LLMError(RuntimeError):
    """A provider call failed (network, auth, quota, refusal…). ``user_text``
    is safe to show; the original exception is chained."""

    def __init__(self, user_text: str):
        super().__init__(user_text)
        self.user_text = user_text


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]  # JSON schema (type: object)


@dataclass(frozen=True, slots=True)
class Image:
    mime: str  # image/jpeg, image/png, image/webp, application/pdf
    data: bytes


@dataclass(slots=True)
class ChatMessage:
    """Earlier turns: plain text only (no tool calls / thinking from the past)."""

    role: str  # "user" | "assistant"
    text: str
    images: list[Image] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ToolCall:
    id: str
    name: str
    args: dict[str, Any]


@dataclass(slots=True)
class Turn:
    """One model response."""

    text: str
    tool_calls: list[ToolCall]
    input_tokens: int | None = None
    output_tokens: int | None = None
    refused: bool = False


@dataclass(frozen=True, slots=True)
class ToolResult:
    call: ToolCall
    content: str  # JSON text
    is_error: bool = False


class Session(Protocol):
    """One user turn's conversation with the model (provider-native inside)."""

    def step(self) -> Turn: ...

    def add_tool_results(self, results: list[ToolResult]) -> None: ...


class Adapter(Protocol):
    supported_files: frozenset[str]

    def start(self, system: str, tools: list[ToolSpec], history: list[ChatMessage]) -> Session: ...

    def ping(self) -> str: ...
