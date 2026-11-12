"""OpenRouter: one key for many providers' models, spoken over the OpenAI API
(the chat itself runs through ``openai_adapter``). Here: the privacy routing
sent with every request, the key check and the model catalogue.

Docs: https://openrouter.ai/docs/guides/routing/provider-selection,
https://openrouter.ai/docs/api-reference/limits (GET /key),
https://openrouter.ai/docs/api/api-reference/models/list-all-models-and-their-properties
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from .base import LLMError

URL = "https://openrouter.ai/api/v1"
# Only providers that don't collect (store / train on) prompts get our requests.
PRIVACY = {"provider": {"data_collection": "deny"}}
TIMEOUT_S = 20.0
MAX_PAGES = 10
CACHE_S = 3600


@dataclass(frozen=True, slots=True)
class Model:
    id: str
    name: str
    vision: bool  # accepts images
    tools: bool  # function calling — the assistant needs it
    context: int | None
    price_in: str | None  # USD per 1M input tokens
    price_out: str | None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _per_million(per_token: Any) -> str | None:
    try:
        value = Decimal(str(per_token)) * 1_000_000
    except (InvalidOperation, ValueError):
        return None
    return f"{value.quantize(Decimal('0.01')).normalize():f}" if value >= 0 else None


def parse_models(payload: dict[str, Any]) -> list[Model]:
    out = []
    for m in payload.get("data") or []:
        arch = m.get("architecture") or {}
        pricing = m.get("pricing") or {}
        out.append(
            Model(
                id=m["id"],
                name=m.get("name") or m["id"],
                vision="image" in (arch.get("input_modalities") or []),
                tools="tools" in (m.get("supported_parameters") or []),
                context=m.get("context_length"),
                price_in=_per_million(pricing.get("prompt")),
                price_out=_per_million(pricing.get("completion")),
            )
        )
    return out


def _headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"} if api_key else {}


def list_models(api_key: str = "", *, get=httpx.get, base_url: str = URL) -> list[Model]:
    """Every model (following pages), as OpenRouter describes them."""
    models: list[Model] = []
    url: str | None = f"{base_url}/models"
    for _ in range(MAX_PAGES):
        if not url:
            break
        try:
            resp = get(url, headers=_headers(api_key), timeout=TIMEOUT_S)
        except httpx.HTTPError as exc:
            raise LLMError("Brak połączenia z OpenRouter.") from exc
        if resp.status_code == httpx.codes.UNAUTHORIZED:
            raise LLMError("Nieprawidłowy klucz API.")
        if resp.status_code >= httpx.codes.BAD_REQUEST:
            raise LLMError(f"Błąd OpenRouter ({resp.status_code}).")
        payload = resp.json()
        models += parse_models(payload)
        nxt = (payload.get("links") or {}).get("next")
        url = nxt if nxt and nxt.startswith("http") else (f"{base_url}{nxt}" if nxt else None)
    return models


_cache: dict[str, tuple[float, list[Model]]] = {}


def tool_models(api_key: str = "") -> list[Model]:
    """Models the assistant can use (with function calling), cached an hour."""
    hit = _cache.get("models")
    if hit and time.monotonic() - hit[0] < CACHE_S:
        return hit[1]
    models = sorted((m for m in list_models(api_key) if m.tools), key=lambda m: m.id)
    _cache["models"] = (time.monotonic(), models)
    return models


def check_key(api_key: str, *, get=httpx.get, base_url: str = URL) -> dict[str, Any]:
    """The key works and has credit left; returns OpenRouter's key info."""
    if not api_key:
        raise LLMError("Brak klucza API.")
    try:
        resp = get(f"{base_url}/key", headers=_headers(api_key), timeout=TIMEOUT_S)
    except httpx.HTTPError as exc:
        raise LLMError("Brak połączenia z OpenRouter.") from exc
    if resp.status_code == httpx.codes.UNAUTHORIZED:
        raise LLMError("Nieprawidłowy klucz API.")
    if resp.status_code >= httpx.codes.BAD_REQUEST:
        raise LLMError(f"Błąd OpenRouter ({resp.status_code}).")
    data = resp.json().get("data") or {}
    remaining = data.get("limit_remaining")
    if remaining is not None and remaining <= 0:
        raise LLMError("Klucz OpenRouter wyczerpał swój limit kredytów.")
    return data
