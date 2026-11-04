"""Проверка адреса почты — одно правило для входа в кабинет и для правки заявки в /admin."""

import re

EMAIL_RE = re.compile(r"[^@\s,;<>()\"']+@[^@\s,;<>()\"']+\.[^@\s,;<>()\"']+")
EMAIL_MAX = 255


def is_valid_email(email: str) -> bool:
    """Одна почта без пробелов/запятых/`;<>()"'`, точка в домене, не длиннее 255. Ждёт уже нормализованную строку."""
    return len(email) <= EMAIL_MAX and bool(EMAIL_RE.fullmatch(email))
