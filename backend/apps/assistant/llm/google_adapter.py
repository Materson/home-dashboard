"""Gemini through Google's official ``google-genai`` SDK, with the SDK's
automatic function calling turned off — the agent loop runs the tools (it
has to check permissions and replace private data first)."""

from __future__ import annotations

import json
from typing import Any

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from .base import ChatMessage, LLMError, Session, ToolCall, ToolResult, ToolSpec, Turn

MAX_OUTPUT_TOKENS = 8192
HTTP_NOT_FOUND = 404
HTTP_TOO_MANY = 429


def _content(msg: ChatMessage) -> types.Content:
    parts = [types.Part.from_bytes(data=i.data, mime_type=i.mime) for i in msg.images]
    parts.append(types.Part.from_text(text=msg.text or "Przeczytaj załączony plik."))
    return types.Content(role="model" if msg.role == "assistant" else "user", parts=parts)


class GoogleSession:
    def __init__(self, adapter: GoogleAdapter, system: str, tools: list[ToolSpec], history):
        self.a = adapter
        decls = [
            types.FunctionDeclaration(
                name=t.name, description=t.description, parameters_json_schema=t.parameters
            )
            for t in tools
        ]
        self.config = types.GenerateContentConfig(
            system_instruction=system,
            tools=[types.Tool(function_declarations=decls)] if decls else None,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            max_output_tokens=MAX_OUTPUT_TOKENS,
        )
        self.contents: list[types.Content] = [_content(m) for m in history]

    def step(self) -> Turn:
        try:
            response = self.a.client.models.generate_content(
                model=self.a.model, contents=self.contents, config=self.config
            )
        except genai_errors.ClientError as exc:
            if exc.code in (401, 403):
                raise LLMError("Nieprawidłowy klucz API Google.") from exc
            if exc.code == HTTP_NOT_FOUND:
                raise LLMError(f"Model {self.a.model!r} nie istnieje.") from exc
            if exc.code == HTTP_TOO_MANY:
                raise LLMError("Limit zapytań Google — spróbuj za chwilę.") from exc
            raise LLMError(f"Google odrzucił zapytanie ({exc.code}).") from exc
        except genai_errors.ServerError as exc:
            raise LLMError(f"Błąd serwera Google ({exc.code}).") from exc

        usage = response.usage_metadata
        tokens = {
            "input_tokens": getattr(usage, "prompt_token_count", None),
            "output_tokens": getattr(usage, "candidates_token_count", None),
        }
        candidate = response.candidates[0] if response.candidates else None
        if candidate is None or candidate.content is None:
            reason = getattr(candidate, "finish_reason", None)
            return (
                Turn(
                    text="Model odmówił odpowiedzi na to pytanie.",
                    tool_calls=[],
                    refused=True,
                    **tokens,
                )
                if reason
                else Turn(text="", tool_calls=[], **tokens)
            )
        self.contents.append(candidate.content)
        parts = candidate.content.parts or []
        text = "".join(p.text for p in parts if p.text and not getattr(p, "thought", False))
        calls = [
            ToolCall(id=fc.id or f"call_{i}", name=fc.name, args=dict(fc.args or {}))
            for i, fc in enumerate(response.function_calls or [])
        ]
        return Turn(text=text, tool_calls=calls, **tokens)

    def add_tool_results(self, results: list[ToolResult]) -> None:
        parts = []
        for r in results:
            try:
                payload = json.loads(r.content)
            except json.JSONDecodeError:
                payload = r.content
            key = "error" if r.is_error else "result"
            parts.append(
                types.Part.from_function_response(name=r.call.name, response={key: payload})
            )
        self.contents.append(types.Content(role="user", parts=parts))


class GoogleAdapter:
    supported_files = frozenset({"image/jpeg", "image/png", "image/webp", "application/pdf"})

    def __init__(self, *, api_key: str, model: str, client: Any = None):
        self.model = model
        self.client = client or genai.Client(api_key=api_key)

    def start(self, system: str, tools: list[ToolSpec], history: list[ChatMessage]) -> Session:
        return GoogleSession(self, system, tools, history)

    def ping(self) -> str:
        try:
            info = self.client.models.get(model=self.model)
        except genai_errors.ClientError as exc:
            raise LLMError(f"Google: {exc.code} — sprawdź klucz i nazwę modelu.") from exc
        except genai_errors.ServerError as exc:
            raise LLMError(f"Błąd serwera Google ({exc.code}).") from exc
        return getattr(info, "display_name", None) or self.model
