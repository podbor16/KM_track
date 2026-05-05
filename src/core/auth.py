"""
Cookie-based session auth для страницы бизнес-аналитики.
Без внешних зависимостей — stdlib hmac/hashlib/time.
"""

import hmac
import hashlib
import time
from fastapi import Cookie, HTTPException, status
from fastapi.responses import RedirectResponse

COOKIE_NAME = "km_session"
EXPIRY_SECONDS = 8 * 3600  # 8 часов


def _get_secret() -> bytes:
    from src.config import settings
    return settings.SECRET_KEY.encode()


def _sign(value: str) -> str:
    return hmac.new(_get_secret(), value.encode(), hashlib.sha256).hexdigest()


def create_session_cookie(username: str) -> str:
    expiry = int(time.time()) + EXPIRY_SECONDS
    value = f"{username}:{expiry}"
    return f"{value}:{_sign(value)}"


def verify_session_cookie(token: str) -> str:
    """Возвращает username или бросает HTTPException 401."""
    try:
        parts = token.rsplit(":", 2)
        if len(parts) != 3:
            raise ValueError("bad format")
        username, expiry_str, sig = parts
        value = f"{username}:{expiry_str}"
        if not hmac.compare_digest(_sign(value), sig):
            raise ValueError("bad signature")
        if int(expiry_str) < int(time.time()):
            raise ValueError("expired")
        return username
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)


def require_auth(km_session: str | None = Cookie(default=None)):
    """FastAPI dependency: проверяет сессию, редиректит на /login если невалидна."""
    if not km_session:
        return RedirectResponse(url="/login", status_code=302)
    try:
        return verify_session_cookie(km_session)
    except HTTPException:
        return RedirectResponse(url="/login", status_code=302)
