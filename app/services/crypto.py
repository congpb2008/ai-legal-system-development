from __future__ import annotations

import base64
import os
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings


@lru_cache
def _get_fernet() -> Fernet | None:
    settings = get_settings()
    key = os.environ.get("SETTINGS_ENCRYPTION_KEY") or settings.secret_key
    try:
        if not key:
            return None
        # Fernet requires 32 url-safe base64-encoded bytes
        if len(key) == 44 and key.endswith("="):
            return Fernet(key.encode("utf-8"))
        # Derive a key from the secret
        digest = base64.urlsafe_b64encode(key.encode("utf-8").ljust(32)[:32])
        return Fernet(digest)
    except Exception:
        return None


def encrypt_secret(value: str | None) -> str | None:
    if value is None or value == "":
        return value
    f = _get_fernet()
    if not f:
        return value
    try:
        token = f.encrypt(value.encode("utf-8"))
        return token.decode("utf-8")
    except Exception:
        return value


def decrypt_secret(value: str | None) -> str | None:
    if value is None or value == "":
        return value
    f = _get_fernet()
    if not f:
        return value
    try:
        if isinstance(value, str) and value.startswith("gAAAA"):
            return f.decrypt(value.encode("utf-8")).decode("utf-8")
        return value
    except (InvalidToken, Exception):
        return value
