from __future__ import annotations

import hashlib
import hmac
import secrets
import time


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_participant_token() -> str:
    return secrets.token_urlsafe(32)


def make_teacher_token(secret: str, ttl_seconds: int = 43_200) -> str:
    expires = str(int(time.time()) + ttl_seconds)
    signature = hmac.new(secret.encode(), expires.encode(), hashlib.sha256).hexdigest()
    return f"{expires}.{signature}"


def verify_teacher_token(token: str | None, secret: str) -> bool:
    if not token:
        return False
    try:
        expires, signature = token.split(".", 1)
        if int(expires) < time.time():
            return False
    except (ValueError, TypeError):
        return False
    expected = hmac.new(secret.encode(), expires.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, expected)
