from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

from fastapi import Cookie, Depends, HTTPException, status
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import User

settings = get_settings()
_serializer = URLSafeTimedSerializer(settings.secret_key, salt="banking-legal-session")


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value.encode("ascii"))


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    n, r, p = 2**14, 8, 1
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=64)
    return f"scrypt${n}${r}${p}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, n_raw, r_raw, p_raw, salt_raw, digest_raw = encoded.split("$", 5)
        if scheme != "scrypt":
            return False
        expected = _unb64(digest_raw)
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=_unb64(salt_raw),
            n=int(n_raw),
            r=int(r_raw),
            p=int(p_raw),
            dklen=len(expected),
        )
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def create_session_token(user: User) -> str:
    return _serializer.dumps({"uid": user.id})


def read_session_token(token: str | None) -> str | None:
    if not token:
        return None
    try:
        payload = _serializer.loads(token, max_age=settings.session_ttl_seconds)
    except (BadSignature, SignatureExpired):
        return None
    if not isinstance(payload, dict):
        return None
    uid = payload.get("uid")
    return uid if isinstance(uid, str) else None


def get_optional_user(
    db: Session = Depends(get_db),
    legal_session: str | None = Cookie(default=None, alias=settings.session_cookie),
) -> User | None:
    uid = read_session_token(legal_session)
    if not uid:
        return None
    user = db.get(User, uid)
    if not user or not user.is_active:
        return None
    return user


def get_current_user(user: User | None = Depends(get_optional_user)) -> User:
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user
