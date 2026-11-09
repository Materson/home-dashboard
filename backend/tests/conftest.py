from __future__ import annotations

import pytest
from cryptography.fernet import Fernet
from django.conf import settings


@pytest.fixture(autouse=True, scope="session")
def _fernet_key() -> None:
    """Make sure a Fernet key is available for tests that touch encrypted fields."""
    if not getattr(settings, "FIELD_ENCRYPTION_KEY", ""):
        settings.FIELD_ENCRYPTION_KEY = Fernet.generate_key().decode()
