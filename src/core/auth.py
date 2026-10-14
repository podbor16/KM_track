"""
Cookie-based session auth для страницы бизнес-аналитики.
Без внешних зависимостей — stdlib hmac/hashlib/time.
"""

import hmac
import hashlib
import time
from urllib.parse import quote

from fastapi import Cookie, HTTPException, Request, status
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


def require_auth_for(login_path: str):
    """Фабрика require_auth с редиректом на СВОЙ login_path — нужна продуктам
    на отдельных доменах (siberman/triatleta), где общий /login с домена
    krasmarafon недоступен из-за nginx domain isolation (см.
    deploy/nginx.conf, каждый домен видит только свои префиксы)."""
    def _dep(request: Request, km_session: str | None = Cookie(default=None)):
        # После входа — обратно на запрошенную страницу (?next=), а не всегда на /admin
        here = request.url.path + (f"?{request.url.query}" if request.url.query else "")
        to_login = RedirectResponse(url=f"{login_path}?next={quote(here, safe='')}", status_code=302)
        if not km_session:
            return to_login
        try:
            return verify_session_cookie(km_session)
        except HTTPException:
            return to_login
    return _dep


def safe_next(target: str | None) -> str | None:
    """Адрес возврата после входа — только путь этого же сайта (иначе ссылка на /login
    могла бы увести на чужой домен: «//evil», «https://evil», «/\\evil»)."""
    if target and target.startswith("/") and not target.startswith("//") and "\\" not in target:
        return target
    return None


require_auth = require_auth_for("/login")


def api_require_auth(km_session: str | None = Cookie(default=None)) -> str:
    """FastAPI dependency для API: бросает 401 если сессия невалидна."""
    if not km_session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    return verify_session_cookie(km_session)
