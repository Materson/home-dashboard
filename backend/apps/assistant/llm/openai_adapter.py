"""OpenAI (ChatGPT), Ollama and any OpenAI-compatible server (LM Studio,
vLLM…) through OpenAI's official Python SDK — the Chat Completions API,
which all of them speak, including function calling."""

from __future__ import annotations

import base64
import json
from typing import Any

import openai

from .base import ChatMessage, LLMError, Session, ToolCall, ToolResult, ToolSpec, Turn

TIMEOUT_S = 180.0
OLLAMA_DEFAULT_URL = "http://localhost:11434/v1"


def _content(msg: ChatMessage) -> list[dict[str, Any]] | str:
    images = [i for i in msg.images if i.mime.startswith("image/")]
    if not images:
        return msg.text
    parts: list[dict[str, Any]] = [
        {"type": "text", "text": msg.text or "Przeczytaj załączony obraz."}
    ]
    for img in images:
        url = f"data:{img.mime};base64,{base64.standard_b64encode(img.data).decode()}"
        parts.append({"type": "image_url", "image_url": {"url": url}})
    return parts


class OpenAISession:
    def __init__(self, adapter: OpenAIAdapter, system: str, tools: list[ToolSpec], history):
        self.a = adapter
        self.tools = [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
            for t in tools
        ]
        self.messages: list[dict[str, Any]] = [{"role": "system", "content": system}]
        self.messages += [{"role": m.role, "content": _content(m)} for m in history]

    def step(self) -> Turn:
        kwargs: dict[str, Any] = {"model": self.a.model, "messages": self.messages}
        if self.tools:
            kwargs["tools"] = self.tools
        if self.a.official:
            kwargs["max_completion_tokens"] = 8000
        try:
            response = self.a.client.chat.completions.create(**kwargs)
        except openai.AuthenticationError as exc:
            raise LLMError("Nieprawidłowy klucz API.") from exc
        except openai.NotFoundError as exc:
            raise LLMError(f"Model {self.a.model!r} nie istnieje na tym serwerze.") from exc
        except openai.RateLimitError as exc:
            raise LLMError("Limit zapytań — spróbuj za chwilę.") from exc
        except openai.BadRequestError as exc:
            raise LLMError(f"Serwer odrzucił zapytanie: {exc.message}") from exc
        except openai.APIStatusError as exc:
            raise LLMError(f"Błąd serwera AI ({exc.status_code}).") from exc
        except openai.APIConnectionError as exc:
            raise LLMError("Brak połączenia z serwerem AI.") from exc

        msg = response.choices[0].message
        usage = getattr(response, "usage", None)
        tokens = {
            "input_tokens": getattr(usage, "prompt_tokens", None),
            "output_tokens": getattr(usage, "completion_tokens", None),
        }
        if getattr(msg, "refusal", None):
            return Turn(
                text="Model odmówił odpowiedzi na to pytanie.",
                tool_calls=[],
                refused=True,
                **tokens,
            )

        calls: list[ToolCall] = []
        native_calls = []
        for tc in msg.tool_calls or []:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {"_invalid_json": tc.function.arguments}
            calls.append(ToolCall(id=tc.id, name=tc.function.name, args=args))
            native_calls.append(
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
            )
        assistant: dict[str, Any] = {"role": "assistant", "content": msg.content or ""}
        if native_calls:
            assistant["tool_calls"] = native_calls
        self.messages.append(assistant)
        return Turn(text=msg.content or "", tool_calls=calls, **tokens)

    def add_tool_results(self, results: list[ToolResult]) -> None:
        for r in results:
            self.messages.append({"role": "tool", "tool_call_id": r.call.id, "content": r.content})


class OpenAIAdapter:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str = "",
        kind: str = "openai",
        client: Any = None,
    ):
        self.model = model
        self.official = kind == "openai"
        if kind == "ollama":
            base_url = base_url or OLLAMA_DEFAULT_URL
        self.client = client or openai.OpenAI(
            api_key=api_key or "not-needed",  # Ollama / local servers ignore it
            base_url=base_url or None,
            timeout=TIMEOUT_S,
        )
        self.supported_files = frozenset({"image/jpeg", "image/png", "image/webp"})

    def start(self, system: str, tools: list[ToolSpec], history: list[ChatMessage]) -> Session:
        return OpenAISession(self, system, tools, history)

    def ping(self) -> str:
        try:
            ids = {m.id for m in self.client.models.list()}
        except openai.AuthenticationError as exc:
            raise LLMError("Nieprawidłowy klucz API.") from exc
        except openai.APIConnectionError as exc:
            raise LLMError("Brak połączenia z serwerem — sprawdź adres.") from exc
        except openai.APIStatusError as exc:
            raise LLMError(f"Błąd serwera AI ({exc.status_code}).") from exc
        if self.model not in ids and f"{self.model}:latest" not in ids:
            raise LLMError(f"Serwer działa, ale nie ma modelu {self.model!r}.")
        return self.model
