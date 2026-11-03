"""Вход спортсмена по коду из почты: коды, лимиты, ссылки, сессии
(спецификация docs/superpowers/specs/2026-11-03-athlete-login-design.md).

Секреты (код, токен ссылки, токен сессии) в БД — только хэшами. Время — NOW() MySQL."""

import hashlib
import hmac
import secrets
from typing import Optional

from src.analytics.db_pool import get_pooled_connection
from src.config import settings
from src.core.mailer import send_mail

COOKIE_NAME = "km_athlete"
CODE_TTL_MIN = 15
MAX_ATTEMPTS = 5
EMAIL_PER_HOUR = 5
IP_PER_HOUR = 10
SESSION_DAYS = 180
SHARED_SESSION_HOURS = 24


class TooManyRequests(Exception):
    """Превышен лимит запросов кода — код не создан, письмо не отправлено."""


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


def request_code(email: str, ip: str) -> None:
    """Создаёт код и ссылку, гасит прежние коды этой почты, отправляет письмо.
    TooManyRequests — лимит; ошибка поставщика писем пробрасывается."""
    email = normalize_email(email)
    conn = get_pooled_connection()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM athlete_login_codes WHERE expires_at < NOW() - INTERVAL 1 DAY")
        cur.execute(
            "SELECT COALESCE(SUM(created_at > NOW() - INTERVAL 1 MINUTE), 0), COUNT(*) "
            "FROM athlete_login_codes WHERE email = %s AND created_at > NOW() - INTERVAL 1 HOUR",
            (email,),
        )
        last_minute, last_hour = cur.fetchone()
        cur.execute(
            "SELECT COUNT(*) FROM athlete_login_codes WHERE ip = %s AND created_at > NOW() - INTERVAL 1 HOUR",
            (ip,),
        )
        (ip_hour,) = cur.fetchone()
        if last_minute or last_hour >= EMAIL_PER_HOUR or ip_hour >= IP_PER_HOUR:
            conn.commit()
            raise TooManyRequests()
        code = f"{secrets.randbelow(10 ** 6):06d}"
        token = secrets.token_urlsafe(32)
        cur.execute(
            "UPDATE athlete_login_codes SET used_at = NOW() WHERE email = %s AND used_at IS NULL", (email,)
        )
        cur.execute(
            "INSERT INTO athlete_login_codes (email, code_hash, link_hash, ip, expires_at) "
            f"VALUES (%s, %s, %s, %s, NOW() + INTERVAL {CODE_TTL_MIN} MINUTE)",
            (email, _code_hash(email, code), _link_hash(token), ip[:45]),
        )
        conn.commit()
        cur.close()
    finally:
        conn.close()
    send_mail(email, *_letter(code, token))


def verify_code(email: str, code: str) -> bool:
    """True — код верный (и теперь использован). MAX_ATTEMPTS неверных попыток гасят код."""
    email = normalize_email(email)
    code = (code or "").strip().replace(" ", "")
    conn = get_pooled_connection()
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
                "UPDATE athlete_login_codes SET used_at = IF(attempts + 1 >= %s, NOW(), NULL), "
                "attempts = attempts + 1 WHERE id = %s",
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
    conn = get_pooled_connection()
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
    conn = get_pooled_connection()
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
