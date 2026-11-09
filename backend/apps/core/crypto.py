"""Field-level encryption via Fernet.

Use ``EncryptedTextField`` for API keys, OAuth refresh tokens, webhook secrets.
The key is ``settings.FIELD_ENCRYPTION_KEY`` (generated once with
``Fernet.generate_key()``) and is **never** rotated in-place — rotate by
re-encrypting all rows in a data migration."""
from __future__ import annotations

from functools import lru_cache
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import models


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    key = settings.FIELD_ENCRYPTION_KEY
    if not key:
        raise ImproperlyConfigured("FIELD_ENCRYPTION_KEY is not set")
    return Fernet(key.encode() if isinstance(key, str) else key)


class EncryptedTextField(models.TextField):
    """Transparently Fernet-encrypted TextField.

    The DB stores the ciphertext as text (base64). Searching by value is not
    possible — that's intentional."""

    description = "Fernet-encrypted text"

    def from_db_value(self, value: Any, _expression: Any, _connection: Any) -> str | None:
        if value is None or value == "":
            return value
        try:
            return _fernet().decrypt(value.encode()).decode()
        except InvalidToken as exc:  # pragma: no cover
            raise ValueError("ciphertext is not valid for this FIELD_ENCRYPTION_KEY") from exc

    def to_python(self, value: Any) -> str | None:
        if value is None or isinstance(value, str):
            return value
        return str(value)

    def get_prep_value(self, value: Any) -> str | None:
        if value is None or value == "":
            return value
        return _fernet().encrypt(str(value).encode()).decode()
