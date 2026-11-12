"""OpenAI (ChatGPT), OpenRouter, Ollama and any OpenAI-compatible server
(LM Studio, vLLM…) through OpenAI's official Python SDK — the Chat
Completions API, which all of them speak, including function calling.
OpenRouter requests only go to providers that don't collect prompts and may
carry PDFs (see ``openrouter``)."""

from __future__ import annotations

import base64
import json
from typing import Any

import openai

from . import openrouter
from .base import ChatMessage, LLMError, Session, ToolCall, ToolResult, ToolSpec, Turn

TIMEOUT_S = 180.0
OLLAMA_DEFAULT_URL = "http://localhost:11434/v1"


PDF = "application/pdf"
IMAGES = frozenset({"image/jpeg", "image/png", "image/webp"})


def _b64(data: bytes) -> str:
    return base64.standard_b64encode(data).decode()


def _content(msg: ChatMessage, *, pdf: bool = False) -> list[dict[str, Any]] | str:
    images = [i for i in msg.images if i.mime.startswith("image/")]
    pdfs = [i for i in msg.images if pdf and i.mime == PDF]
    if not images and not pdfs:
        return msg.text
    parts: list[dict[str, Any]] = [
        {"type": "text", "text": msg.text or "Przeczytaj załączony plik."}
    ]
    for img in images:
        url = f"data:{img.mime};base64,{_b64(img.data)}"
        parts.append({"type": "image_url", "image_url": {"url": url}})
    for n, doc in enumerate(pdfs, 1):
        parts.append(
            {
                "type": "file",
                "file": {
                    "filename": f"plik-{n}.pdf",
                    "file_data": f"data:{PDF};base64,{_b64(doc.data)}",
                },
            }
        )
    return parts


def _privacy_block(exc: openai.APIStatusError) -> bool:
    """OpenRouter found no provider for this model that keeps to the
    no-data-collection rule."""
    text = str(exc.message).lower()
    return any(w in text for w in ("data policy", "data_collection", "routing requirements"))


def _status_error(adapter: OpenAIAdapter, exc: openai.APIStatusError) -> LLMError:
    if exc.status_code == 402:  # noqa: PLR2004 — Payment Required
        return LLMError("Brak środków na koncie u dostawcy AI — doładuj kredyty.")
    if adapter.openrouter and _privacy_block(exc):
        if adapter.private_routing:
            return LLMError(
                "Żaden dostawca tego modelu nie gwarantuje, że nie zbiera danych z zapytań "
                "(tak jest z darmowymi modelami). Wybierz inny model albo włącz w profilu "
                "„Dopuść dostawców, którzy mogą zapisywać zapytania”."
            )
        # Our routing allows them, so the account's own privacy settings refuse.
        return LLMError(
            "Ustawienia prywatności konta OpenRouter nie dopuszczają tego modelu — zmień je na "
            f"openrouter.ai/settings/privacy albo wybierz inny model. ({exc.message})"
        )
    if isinstance(exc, openai.NotFoundError):
        return LLMError(f"Model {adapter.model!r} nie istnieje na tym serwerze.")
    if isinstance(exc, openai.BadRequestError):
        return LLMError(f"Serwer odrzucił zapytanie: {exc.message}")
    return LLMError(f"Błąd serwera AI ({exc.status_code}).")


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
        self.messages += [
            {"role": m.role, "content": _content(m, pdf=adapter.openrouter)} for m in history
        ]

    def step(self) -> Turn:
        kwargs: dict[str, Any] = {"model": self.a.model, "messages": self.messages}
        if self.tools:
            kwargs["tools"] = self.tools
        if self.a.official:
            kwargs["max_completion_tokens"] = 8000
        if self.a.private_routing:
            kwargs["extra_body"] = openrouter.PRIVACY
        try:
            response = self.a.client.chat.completions.create(**kwargs)
        except openai.AuthenticationError as exc:
            raise LLMError("Nieprawidłowy klucz API.") from exc
        except openai.RateLimitError as exc:
            raise LLMError("Limit zapytań — spróbuj za chwilę.") from exc
        except openai.APIStatusError as exc:
            raise _status_error(self.a, exc) from exc
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
        allow_data_collection: bool = False,
        client: Any = None,
    ):
        self.model = model
        self.official = kind == "openai"
        self.openrouter = kind == "openrouter"
        # OpenRouter: only providers that don't collect prompts, unless the
        # profile allows the others too (free models run only on those).
        self.private_routing = self.openrouter and not allow_data_collection
        self.api_key = api_key
        if kind == "ollama":
            base_url = base_url or OLLAMA_DEFAULT_URL
        if self.openrouter:
            base_url = base_url or openrouter.URL
        self.client = client or openai.OpenAI(
            api_key=api_key or "not-needed",  # Ollama / local servers ignore it
            base_url=base_url or None,
            timeout=TIMEOUT_S,
        )
        self.supported_files = IMAGES | {PDF} if self.openrouter else IMAGES

    def start(self, system: str, tools: list[ToolSpec], history: list[ChatMessage]) -> Session:
        return OpenAISession(self, system, tools, history)

    def ping(self) -> str:
        if self.openrouter:
            # Its model list may be public, so check the key itself first.
            base = str(self.client.base_url).rstrip("/")
            info = openrouter.check_key(self.api_key, base_url=base)
            ids = {m.id for m in openrouter.list_models(self.api_key, base_url=base)}
            if self.model not in ids:
                raise LLMError(f"OpenRouter nie ma modelu {self.model!r}.")
            label = info.get("label")
            return f"{self.model} (klucz: {label})" if label else self.model
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
