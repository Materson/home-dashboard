"""Print fresh secrets for the NAS stack, to paste into Portainer (Stacks →
Environment variables). Run once, with the backend's Python (it has the
`cryptography` package for the web push keys):

    backend\\.venv\\Scripts\\python ops\\gen-secrets.py

Keep a copy in your password manager: FIELD_ENCRYPTION_KEY decrypts the stored
AI / Google keys, BACKUP_PASSPHRASE opens the backups — lose them and those
are gone. Never commit them.
"""

from __future__ import annotations

import base64
import os
import secrets


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def vapid_keys() -> tuple[str, str] | None:
    """Web push (VAPID): an EC P-256 key pair, base64url (raw private key,
    uncompressed public point) — the format pywebpush and browsers take."""
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ec
    except ImportError:
        return None
    key = ec.generate_private_key(ec.SECP256R1())
    private = key.private_numbers().private_value.to_bytes(32, "big")
    public = key.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    return b64url(private), b64url(public)


def main() -> None:
    values = {
        "DJANGO_SECRET_KEY": secrets.token_urlsafe(50),
        # Fernet: 32 random bytes, base64url.
        "FIELD_ENCRYPTION_KEY": base64.urlsafe_b64encode(os.urandom(32)).decode(),
        # Hex only: they're part of the database URL.
        "MARIADB_PASSWORD": secrets.token_hex(24),
        "MARIADB_ROOT_PASSWORD": secrets.token_hex(24),
        "BACKUP_PASSPHRASE": secrets.token_urlsafe(32),
    }
    vapid = vapid_keys()
    if vapid:
        values["VAPID_PRIVATE_KEY"], values["VAPID_PUBLIC_KEY"] = vapid
    for name, value in values.items():
        print(f"{name}={value}")
    if not vapid:
        print("# (VAPID keys need the `cryptography` package: run with the backend's Python)")


if __name__ == "__main__":
    main()
