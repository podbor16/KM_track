"""Вход спортсмена по коду из почты: коды, лимиты, ссылки, сессии
(спецификация docs/superpowers/specs/2026-11-03-athlete-login-design.md).

Секреты (код, токен ссылки, токен сессии) в БД — только хэшами. Время — NOW() MySQL."""

import hashlib
import hmac
import secrets
from typing import Optional

from fastapi import HTTPException

from src.analytics.db_pool import get_pooled_connection
from src.config import settings
from src.config.event_loader import get_athlete_cabinet_enabled
from src.core.auth import COOKIE_NAME as ADMIN_COOKIE, verify_session_cookie
from src.core.mailer import send_mail

COOKIE_NAME = "km_athlete"
CODE_TTL_MIN = 15
MAX_ATTEMPTS = 5
EMAIL_PER_HOUR = 5
IP_PER_HOUR = 10
SESSION_DAYS = 180
SHARED_SESSION_HOURS = 24


class TooManyRequests(Exception):
    """Превышен лимит запросов кода — код не создан, письмо не отправлено.
    retry_after — секунд до следующей попытки; recent — этой почте код ушёл меньше минуты назад
    и ещё действует (для человека не ошибка: повторная отправка формы)."""

    def __init__(self, retry_after: int, recent: bool = False):
        super().__init__(retry_after)
        self.retry_after = max(int(retry_after), 1)
        self.recent = recent


def cabinet_open(request) -> bool:
    """Кабинет (/me, иконка в шапке) доступен: всем — при включённом переключателе в /admin,
    иначе только вошедшим в админку (проверка на проде до анонса)."""
    if get_athlete_cabinet_enabled():
        return True
    token = request.cookies.get(ADMIN_COOKIE)
    if not token:
        return False
    try:
        verify_session_cookie(token)
        return True
    except HTTPException:
        return False


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def _hmac(value: str) -> str:
    return hmac.new(settings.SECRET_KEY.encode(), value.encode(), hashlib.sha256).hexdigest()


def _code_hash(email: str, code: str) -> str:
    return _hmac(f"code:{email}:{code}")


def _link_hash(token: str) -> str:
    return _hmac(f"link:{token}")


def _letter(code: str, token: str) -> tuple[str, str, str]:
    url = f"{settings.PUBLIC_BASE_URL}/me/link?t={token}"
    subject = f"Код для входа: {code[:3]} {code[3:]}"
    note = (f"Код и кнопка действуют {CODE_TTL_MIN} минут. "
            "Если вы не запрашивали вход — просто удалите это письмо.")
    text = (f"Код для входа в личный кабинет результатов Красмарафона: {code}\n\n"
            f"Или откройте ссылку: {url}\n\n{note}\n")
    html = (
        '<div style="font-family:Arial,sans-serif;font-size:15px;color:#333;max-width:420px">'
        "<p>Код для входа в личный кабинет результатов Красмарафона:</p>"
        f'<p style="font-size:30px;font-weight:bold;letter-spacing:6px;text-align:center">{code}</p>'
        "<p>Или нажмите кнопку:</p>"
        f'<p style="text-align:center"><a href="{url}" style="display:inline-block;background:#EE2D62;'
        'color:#fff;text-decoration:none;border-radius:50px;padding:10px 32px;font-weight:bold">Войти</a></p>'
        f'<p style="color:#999;font-size:12px">{note}</p></div>'
    )
    return subject, text, html


def _conn():
    conn = get_pooled_connection()
    if conn is None:
        raise RuntimeError("БД недоступна")
    return conn


def request_code(email: str, ip: str) -> None:
    """Создаёт код и ссылку, гасит прежние коды этой почты, отправляет письмо.
    TooManyRequests — лимит; ошибка поставщика писем пробрасывается.
    Проверка лимитов и запись идут под именованной блокировкой MySQL — иначе параллельные
    запросы проскакивают лимиты (autocommit, транзакций между SELECT и INSERT нет)."""
    email = normalize_email(email)
    ip = (ip or "")[:45]
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT GET_LOCK('athlete_login_code', 5)")
        if cur.fetchone()[0] != 1:
            raise TooManyRequests(5)
        try:
            cur.execute("DELETE FROM athlete_login_codes WHERE expires_at < NOW() - INTERVAL 1 DAY")
            # Секунды до снятия лимита: минутного — от последнего кода, часового — от самого старого в окне
            cur.execute(
                "SELECT TIMESTAMPDIFF(SECOND, NOW(), MAX(created_at) + INTERVAL 1 MINUTE), COUNT(*), "
                "TIMESTAMPDIFF(SECOND, NOW(), MIN(created_at) + INTERVAL 1 HOUR) "
                "FROM athlete_login_codes WHERE email = %s AND created_at > NOW() - INTERVAL 1 HOUR",
                (email,),
            )
            minute_left, email_hour, email_hour_left = cur.fetchone()
            cur.execute(
                "SELECT COUNT(*), TIMESTAMPDIFF(SECOND, NOW(), MIN(created_at) + INTERVAL 1 HOUR) "
                "FROM athlete_login_codes WHERE ip = %s AND created_at > NOW() - INTERVAL 1 HOUR",
                (ip,),
            )
            ip_hour, ip_hour_left = cur.fetchone()
            hour_left = max(email_hour_left if email_hour >= EMAIL_PER_HOUR else 0,
                            ip_hour_left if ip_hour >= IP_PER_HOUR else 0)
            if hour_left > 0:
                raise TooManyRequests(hour_left)
            if minute_left is not None and minute_left > 0:
                raise TooManyRequests(minute_left, recent=True)
            code = f"{secrets.randbelow(10 ** 6):06d}"
            token = secrets.token_urlsafe(32)
            cur.execute(
                "UPDATE athlete_login_codes SET used_at = NOW() WHERE email = %s AND used_at IS NULL", (email,)
            )
            cur.execute(
                "INSERT INTO athlete_login_codes (email, code_hash, link_hash, ip, expires_at) "
                f"VALUES (%s, %s, %s, %s, NOW() + INTERVAL {CODE_TTL_MIN} MINUTE)",
                (email, _code_hash(email, code), _link_hash(token), ip),
            )
        finally:
            cur.execute("SELECT RELEASE_LOCK('athlete_login_code')")
            cur.fetchone()
        conn.commit()
        cur.close()
    finally:
        conn.close()
    send_mail(email, *_letter(code, token))


def verify_code(email: str, code: str) -> bool:
    """True — код верный (и теперь использован). MAX_ATTEMPTS неверных попыток гасят код."""
    email = normalize_email(email)
    code = (code or "").strip().replace(" ", "")
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, code_hash, attempts FROM athlete_login_codes "
            "WHERE email = %s AND used_at IS NULL AND expires_at > NOW() ORDER BY id DESC LIMIT 1",
            (email,),
        )
        row = cur.fetchone()
        if not row:
            return False
        code_id, code_hash, attempts = row
        if hmac.compare_digest(code_hash, _code_hash(email, code)):
            # used_at IS NULL — два одновременных верных ввода не дадут две сессии
            cur.execute("UPDATE athlete_login_codes SET used_at = NOW() WHERE id = %s AND used_at IS NULL",
                        (code_id,))
            ok = cur.rowcount == 1
        else:
            cur.execute(
                # used_at — до attempts: MySQL вычисляет SET слева направо
                "UPDATE athlete_login_codes SET used_at = IF(attempts + 1 >= %s, NOW(), used_at), "
                "attempts = attempts + 1 WHERE id = %s AND used_at IS NULL",
                (MAX_ATTEMPTS, code_id),
            )
            ok = False
        conn.commit()
        cur.close()
        return ok
    finally:
        conn.close()


def link_email(token: str) -> Optional[str]:
    """Почта действующей ссылки — для страницы «Войти как …?» (ссылку не тратит)."""
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT email FROM athlete_login_codes WHERE link_hash = %s AND used_at IS NULL AND expires_at > NOW()",
            (_link_hash(token or ""),),
        )
        row = cur.fetchone()
        cur.close()
        return row[0] if row else None
    finally:
        conn.close()


def consume_link(token: str) -> Optional[str]:
    """Тратит ссылку; почта — если ссылка была действующей."""
    h = _link_hash(token or "")
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE athlete_login_codes SET used_at = NOW() "
            "WHERE link_hash = %s AND used_at IS NULL AND expires_at > NOW()",
            (h,),
        )
        if cur.rowcount != 1:
            conn.commit()
            return None
        cur.execute("SELECT email FROM athlete_login_codes WHERE link_hash = %s", (h,))
        (email,) = cur.fetchone()
        conn.commit()
        cur.close()
        return email
    finally:
        conn.close()


def _token_hash(token: str) -> str:
    return hashlib.sha256((token or "").encode()).hexdigest()


def create_session(email: str, shared: bool, user_agent: Optional[str]) -> str:
    """Новая сессия; возвращает токен для cookie (в БД — его SHA-256).
    shared («Чужой компьютер») — сутки, иначе SESSION_DAYS."""
    token = secrets.token_urlsafe(32)
    ttl = f"INTERVAL {SHARED_SESSION_HOURS} HOUR" if shared else f"INTERVAL {SESSION_DAYS} DAY"
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM athlete_sessions WHERE expires_at < NOW()")
        cur.execute(
            f"INSERT INTO athlete_sessions (email, token_hash, expires_at, user_agent) VALUES (%s, %s, NOW() + {ttl}, %s)",
            (normalize_email(email), _token_hash(token), (user_agent or "")[:255] or None),
        )
        conn.commit()
        cur.close()
        return token
    finally:
        conn.close()


def session_email(token: Optional[str]) -> Optional[str]:
    """Почта действующей сессии или None."""
    if not token:
        return None
    h = _token_hash(token)
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT email FROM athlete_sessions WHERE token_hash = %s AND expires_at > NOW()", (h,))
        row = cur.fetchone()
        if row:
            cur.execute("UPDATE athlete_sessions SET last_seen_at = NOW() WHERE token_hash = %s", (h,))
            conn.commit()
        cur.close()
        return row[0] if row else None
    finally:
        conn.close()


def delete_session(token: Optional[str]) -> None:
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM athlete_sessions WHERE token_hash = %s", (_token_hash(token),))
        conn.commit()
        cur.close()
    finally:
        conn.close()


def delete_all_sessions(email: str) -> None:
    """«Выйти на всех устройствах»."""
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM athlete_sessions WHERE email = %s", (normalize_email(email),))
        conn.commit()
        cur.close()
    finally:
        conn.close()
