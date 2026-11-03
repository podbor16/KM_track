# Вход спортсмена и личный кабинет (этап А) — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** вход на results.krasmarafon.ru по коду из почты и страница `/me` «Личный кабинет» с заявками, оформленными с этой почты.

**Architecture:** коды и сессии — две таблицы MySQL (только хэши секретов); логика в `src/krasmarafon/services/athlete_auth.py`, выборка и группировка заявок — `athlete_cabinet.py`, отправка писем — `src/core/mailer.py` (log / SMTP Яндекса). Страницы — серверный рендер Jinja (`routers/athlete.py`, шаблоны `me-login.html`, `me.html`), без JS-фреймворков.

**Tech Stack:** FastAPI, Jinja2, mysql-connector (пул `src/analytics/db_pool.get_pooled_connection`), stdlib `smtplib`/`hmac`/`secrets`, pytest.

**Спецификация:** `docs/superpowers/specs/2026-11-03-athlete-login-design.md` — читать целиком перед стартом.

**Окружение:**
- Работать в worktree `C:\Users\podbo\Работа\КРАСМАРАФОН\KM_track\.worktrees\pd-consent`, ветка `feature/athlete-login`.
- Тесты: `conda run -n base python -m pytest <путь> -v` (из worktree). Нужен `SECRET_KEY` в окружении — берётся из `.env`/`.env.local` через `tests/conftest.py`; если `.env.local` в worktree нет — скопировать из основного репозитория `C:\Users\podbo\Работа\КРАСМАРАФОН\KM_track\.env.local` (не коммитится, содержимое не выводить).
- Локальная БД — MySQL80 на 3308 (`.env.local`). Любой свой скрипт: `load_dotenv(".env.local", override=True)` до импорта `settings`.
- Многострочный `conda run python -c` зависает — одноразовые скрипты класть файлом в scratchpad.
- **Не пушить, не трогать прод.** Выкладка — только после локального теста пользователем и его «да».
- Не выводить содержимое `.env*`, пароли, коды из чужих писем.
- Проверять результат `pytest` по коду возврата, а не через `| tail` (урок: `pytest | tail && push`).

---

## Файлы

| Файл | Что |
|------|-----|
| `migrations/athlete_login.sql` (новый) | таблицы `athlete_login_codes`, `athlete_sessions` |
| `src/config/settings.py` | `MAIL_BACKEND`, `SMTP_*`, `MAIL_FROM`, `PUBLIC_BASE_URL` |
| `.env.example` | те же переменные, без значений секретов |
| `src/core/mailer.py` (новый) | `send_mail(to, subject, text, html)` |
| `src/krasmarafon/services/athlete_auth.py` (новый) | коды, лимиты, ссылки, сессии |
| `src/krasmarafon/services/athlete_cabinet.py` (новый) | выборка заявок по почте, группировка по людям |
| `src/krasmarafon/routers/athlete.py` (новый) | `/me`, `/me/login`, `/me/verify`, `/me/link`, `/me/logout`, `/me/logout-all` |
| `src/krasmarafon/router.py` | подключить `athlete_router` |
| `templates/krasmarafon/me-login.html`, `me.html` (новые) | экраны входа и кабинета |
| `static/css/me.css` (новый) | стили кабинета |
| `templates/krasmarafon/header.html` | «Войти» / «Кабинет» |
| `tests/unit/test_mailer.py`, `tests/unit/test_athlete_cabinet.py` | unit |
| `tests/integration/test_athlete_auth.py`, `tests/integration/test_athlete_routes.py` | локальная БД |

---

### Task 1: Миграция

**Files:**
- Create: `migrations/athlete_login.sql`

- [ ] **Step 1: Написать миграцию**

```sql
-- Вход спортсмена по коду из почты (2026-11-03, спецификация 2026-11-03-athlete-login-design).
-- Коды и сессии — только хэши секретов. Идемпотентно (CREATE TABLE IF NOT EXISTS).

CREATE TABLE IF NOT EXISTS athlete_login_codes (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  email VARCHAR(255) NOT NULL,
  code_hash CHAR(64) NOT NULL,
  link_hash CHAR(64) NOT NULL,
  ip VARCHAR(45) NOT NULL,
  attempts TINYINT NOT NULL DEFAULT 0,
  expires_at DATETIME NOT NULL,
  used_at DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY idx_alc_email (email, created_at),
  KEY idx_alc_ip (ip, created_at),
  UNIQUE KEY uq_alc_link (link_hash)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS athlete_sessions (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  email VARCHAR(255) NOT NULL,
  token_hash CHAR(64) NOT NULL,
  expires_at DATETIME NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  last_seen_at DATETIME NULL,
  user_agent VARCHAR(255) NULL,
  UNIQUE KEY uq_as_token (token_hash),
  KEY idx_as_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

- [ ] **Step 2: Применить к локальной БД (MySQL80:3308)**

Скрипт в scratchpad `apply_athlete_login.py`:

```python
import sys
from pathlib import Path
from dotenv import load_dotenv

root = Path(sys.argv[1])
load_dotenv(root / ".env.local", override=True)
sys.path.insert(0, str(root))
from src.analytics.db_pool import get_pooled_connection

sql = (root / "migrations" / "athlete_login.sql").read_text(encoding="utf-8")
conn = get_pooled_connection()
cur = conn.cursor()
for stmt in sql.split(";"):
    if "CREATE TABLE" in stmt:
        cur.execute(stmt)
conn.commit()
cur.execute("SHOW TABLES LIKE 'athlete_%'")
print(sorted(r[0] for r in cur.fetchall()))
```

Run: `conda run -n base python <scratchpad>\apply_athlete_login.py "C:\Users\podbo\Работа\КРАСМАРАФОН\KM_track\.worktrees\pd-consent"`
Expected: `['athlete_login_codes', 'athlete_sessions']`. Повторный запуск — тот же вывод без ошибок.

- [ ] **Step 3: Commit**

```bash
git add migrations/athlete_login.sql
git commit -m "feat(auth): таблицы кодов входа и сессий спортсмена"
```

---

### Task 2: Настройки и отправка писем

**Files:**
- Modify: `src/config/settings.py` (блок `# --- АВТОРИЗАЦИЯ ---` и список имён в конце файла)
- Modify: `.env.example`
- Create: `src/core/mailer.py`
- Test: `tests/unit/test_mailer.py`

- [ ] **Step 1: Настройки**

В `src/config/settings.py` после строки `SIBERMAN_WEBHOOK_SECRET = ...`:

```python

# --- ПИСЬМА (код входа в личный кабинет) ---
# log — письмо в лог (разработка, тесты); smtp — ящик домена в Яндексе (SMTP_SSL)
MAIL_BACKEND = os.getenv("MAIL_BACKEND", "log")
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.yandex.ru")
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
MAIL_FROM = os.getenv("MAIL_FROM", "Красмарафон <noreply@krasmarafon.ru>")
# Адрес сайта для ссылки «Войти» в письме — не из заголовка Host запроса
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "https://results.krasmarafon.ru").rstrip("/")
```

В список имён в конце файла после `"SIBERMAN_WEBHOOK_SECRET",` добавить:

```python
    "MAIL_BACKEND",
    "SMTP_HOST",
    "SMTP_PORT",
    "SMTP_USER",
    "SMTP_PASSWORD",
    "MAIL_FROM",
    "PUBLIC_BASE_URL",
```

В `.env.example` после блока `SIBERMAN_WEBHOOK_SECRET`:

```
# Письма с кодом входа: log (разработка) или smtp (прод, ящик noreply@krasmarafon.ru в Яндексе)
MAIL_BACKEND=log
SMTP_HOST=smtp.yandex.ru
SMTP_PORT=465
SMTP_USER=noreply@krasmarafon.ru
SMTP_PASSWORD=
MAIL_FROM=Красмарафон <noreply@krasmarafon.ru>
# Локально: http://localhost:8000
PUBLIC_BASE_URL=https://results.krasmarafon.ru
```

- [ ] **Step 2: Написать падающий тест**

`tests/unit/test_mailer.py`:

```python
from email.message import EmailMessage
from unittest.mock import MagicMock, patch

from src.core import mailer


def test_log_backend_writes_letter_to_log(caplog):
    with patch.object(mailer.settings, "MAIL_BACKEND", "log"), caplog.at_level("INFO"):
        mailer.send_mail("a@b.ru", "Тема", "Текст 123", "<b>123</b>")
    assert "a@b.ru" in caplog.text and "Текст 123" in caplog.text


def test_smtp_backend_sends_multipart_letter():
    smtp = MagicMock()
    with patch.object(mailer.settings, "MAIL_BACKEND", "smtp"), \
         patch.object(mailer.settings, "SMTP_USER", "noreply@krasmarafon.ru"), \
         patch.object(mailer.settings, "SMTP_PASSWORD", "pw"), \
         patch.object(mailer.settings, "MAIL_FROM", "Красмарафон <noreply@krasmarafon.ru>"), \
         patch("src.core.mailer.smtplib.SMTP_SSL") as cls:
        cls.return_value.__enter__.return_value = smtp
        mailer.send_mail("a@b.ru", "Код для входа: 123 456", "Текст", "<b>HTML</b>")
    cls.assert_called_once_with(mailer.settings.SMTP_HOST, mailer.settings.SMTP_PORT, timeout=15)
    smtp.login.assert_called_once_with("noreply@krasmarafon.ru", "pw")
    msg: EmailMessage = smtp.send_message.call_args[0][0]
    assert msg["To"] == "a@b.ru"
    assert msg["Subject"] == "Код для входа: 123 456"
    assert msg.get_content_type() == "multipart/alternative"
    assert [p.get_content_type() for p in msg.iter_parts()] == ["text/plain", "text/html"]
```

- [ ] **Step 3: Убедиться, что падает**

Run: `conda run -n base python -m pytest tests/unit/test_mailer.py -v`
Expected: FAIL — `ImportError: cannot import name 'mailer'`.

- [ ] **Step 4: Реализация**

`src/core/mailer.py`:

```python
"""Отправка служебных писем (код входа в личный кабинет). Поставщик — settings.MAIL_BACKEND:
log — письмо в лог (разработка, тесты), smtp — ящик домена в Яндексе (SMTP_SSL).
Смена поставщика — новая ветка здесь, вызывающий код не меняется."""

import logging
import smtplib
from email.message import EmailMessage

from src.config import settings

logger = logging.getLogger(__name__)


def send_mail(to: str, subject: str, text: str, html: str) -> None:
    """Блокирующая отправка; ошибки поставщика пробрасываются вызывающему."""
    if settings.MAIL_BACKEND != "smtp":
        logger.info("MAIL (log) to=%s subject=%s\n%s", to, subject, text)
        return
    msg = EmailMessage()
    msg["From"] = settings.MAIL_FROM
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")
    with smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as smtp:
        smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        smtp.send_message(msg)
```

- [ ] **Step 5: Тесты проходят**

Run: `conda run -n base python -m pytest tests/unit/test_mailer.py -v`
Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add src/config/settings.py .env.example src/core/mailer.py tests/unit/test_mailer.py
git commit -m "feat(auth): отправка писем — лог или SMTP Яндекса"
```

---

### Task 3: Коды входа и лимиты

**Files:**
- Create: `src/krasmarafon/services/athlete_auth.py`
- Test: `tests/integration/test_athlete_auth.py`

Тестовые почты — `*@athlete-test.local`; фикстура удаляет их строки до и после теста.

- [ ] **Step 1: Падающие тесты**

`tests/integration/test_athlete_auth.py`:

```python
"""Коды входа и сессии спортсмена на локальной БД. Тестовые почты — *@athlete-test.local."""
import re
from unittest.mock import patch

import pytest

from src.analytics.db_pool import get_pooled_connection
from src.krasmarafon.services import athlete_auth as aa

DOMAIN = "athlete-test.local"


@pytest.fixture
def db():
    conn = get_pooled_connection()
    if not conn:
        pytest.skip("Нет локальной БД")
    cur = conn.cursor(dictionary=True)
    cur.execute("SHOW TABLES LIKE 'athlete_login_codes'")
    if not cur.fetchone():
        conn.close()
        pytest.skip("Миграция athlete_login не применена")

    def cleanup():
        cur.execute("DELETE FROM athlete_login_codes WHERE email LIKE %s OR ip LIKE '203.0.113.%%'", (f"%@{DOMAIN}",))
        cur.execute("DELETE FROM athlete_sessions WHERE email LIKE %s", (f"%@{DOMAIN}",))
        conn.commit()

    cleanup()
    yield conn, cur
    cleanup()
    cur.close()
    conn.close()


def send(email, ip="203.0.113.1"):
    """request_code с перехватом письма: возвращает (код, токен ссылки)."""
    with patch.object(aa, "send_mail") as mail:
        aa.request_code(email, ip)
    to, subject, text, html = mail.call_args[0]
    assert to == aa.normalize_email(email)
    code = re.search(r"\b(\d{6})\b", text).group(1)
    token = re.search(r"/me/link\?t=([\w-]+)", text).group(1)
    assert code in subject.replace(" ", "")
    return code, token


def test_code_logs_in_once(db):
    code, _ = send(f"Petr@{DOMAIN} ")
    assert aa.verify_code(f"petr@{DOMAIN}", code)
    assert not aa.verify_code(f"petr@{DOMAIN}", code)


def test_secrets_stored_only_as_hashes(db):
    conn, cur = db
    code, token = send(f"h@{DOMAIN}")
    cur.execute("SELECT code_hash, link_hash FROM athlete_login_codes WHERE email = %s", (f"h@{DOMAIN}",))
    row = cur.fetchone()
    assert code not in row["code_hash"] and token != row["link_hash"]
    assert len(row["code_hash"]) == len(row["link_hash"]) == 64


def test_wrong_code_five_attempts_burns_code(db):
    code, _ = send(f"w@{DOMAIN}")
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(aa.MAX_ATTEMPTS):
        assert not aa.verify_code(f"w@{DOMAIN}", wrong)
    assert not aa.verify_code(f"w@{DOMAIN}", code)


def test_four_wrong_attempts_still_allow_code(db):
    code, _ = send(f"w4@{DOMAIN}")
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(aa.MAX_ATTEMPTS - 1):
        assert not aa.verify_code(f"w4@{DOMAIN}", wrong)
    assert aa.verify_code(f"w4@{DOMAIN}", code)


def test_expired_code_rejected(db):
    conn, cur = db
    code, token = send(f"e@{DOMAIN}")
    cur.execute("UPDATE athlete_login_codes SET expires_at = NOW() - INTERVAL 1 SECOND WHERE email = %s",
                (f"e@{DOMAIN}",))
    conn.commit()
    assert not aa.verify_code(f"e@{DOMAIN}", code)
    assert aa.link_email(token) is None


def test_new_code_cancels_previous(db):
    conn, cur = db
    old_code, old_token = send(f"n@{DOMAIN}")
    # обойти лимит «1 код в минуту»
    cur.execute("UPDATE athlete_login_codes SET created_at = NOW() - INTERVAL 2 MINUTE WHERE email = %s",
                (f"n@{DOMAIN}",))
    conn.commit()
    new_code, _ = send(f"n@{DOMAIN}")
    assert aa.link_email(old_token) is None
    if old_code != new_code:
        assert not aa.verify_code(f"n@{DOMAIN}", old_code)
    assert aa.verify_code(f"n@{DOMAIN}", new_code)


def test_link_shows_email_then_consumed_once(db):
    _, token = send(f"l@{DOMAIN}")
    assert aa.link_email(token) == f"l@{DOMAIN}"
    assert aa.link_email(token) == f"l@{DOMAIN}"  # просмотр страницы не тратит ссылку
    assert aa.consume_link(token) == f"l@{DOMAIN}"
    assert aa.consume_link(token) is None
    assert aa.link_email("garbage") is None


def test_limit_one_per_minute_per_email(db):
    send(f"m@{DOMAIN}")
    with patch.object(aa, "send_mail") as mail, pytest.raises(aa.TooManyRequests):
        aa.request_code(f"m@{DOMAIN}", "203.0.113.2")
    mail.assert_not_called()


def test_limit_five_per_hour_per_email(db):
    conn, cur = db
    for i in range(aa.EMAIL_PER_HOUR):
        send(f"hr@{DOMAIN}", ip=f"203.0.113.{10 + i}")
        cur.execute("UPDATE athlete_login_codes SET created_at = NOW() - INTERVAL 2 MINUTE WHERE email = %s",
                    (f"hr@{DOMAIN}",))
        conn.commit()
    with pytest.raises(aa.TooManyRequests):
        aa.request_code(f"hr@{DOMAIN}", "203.0.113.99")


def test_limit_ten_per_hour_per_ip(db):
    for i in range(aa.IP_PER_HOUR):
        send(f"ip{i}@{DOMAIN}", ip="203.0.113.50")
    with pytest.raises(aa.TooManyRequests):
        aa.request_code(f"ipx@{DOMAIN}", "203.0.113.50")
```

- [ ] **Step 2: Убедиться, что падают**

Run: `conda run -n base python -m pytest tests/integration/test_athlete_auth.py -v`
Expected: FAIL — `ImportError: cannot import name 'athlete_auth'`.

- [ ] **Step 3: Реализация**

`src/krasmarafon/services/athlete_auth.py`:

```python
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
```

- [ ] **Step 4: Тесты проходят**

Run: `conda run -n base python -m pytest tests/integration/test_athlete_auth.py -v`
Expected: 10 passed.

- [ ] **Step 5: Commit**

```bash
git add src/krasmarafon/services/athlete_auth.py tests/integration/test_athlete_auth.py
git commit -m "feat(auth): одноразовые коды и ссылки входа с лимитами"
```

---

### Task 4: Сессии

**Files:**
- Modify: `src/krasmarafon/services/athlete_auth.py` (дописать в конец)
- Test: `tests/integration/test_athlete_auth.py` (дописать в конец)

- [ ] **Step 1: Падающие тесты** (в конец `tests/integration/test_athlete_auth.py`)

```python
def test_session_roundtrip_and_logout(db):
    conn, cur = db
    token = aa.create_session(f"s@{DOMAIN}", shared=False, user_agent="pytest")
    assert aa.session_email(token) == f"s@{DOMAIN}"
    cur.execute("SELECT token_hash, TIMESTAMPDIFF(DAY, NOW(), expires_at) AS d FROM athlete_sessions "
                "WHERE email = %s", (f"s@{DOMAIN}",))
    row = cur.fetchone()
    assert row["token_hash"] != token and row["d"] >= aa.SESSION_DAYS - 1
    aa.delete_session(token)
    assert aa.session_email(token) is None


def test_shared_session_lives_one_day(db):
    conn, cur = db
    aa.create_session(f"sh@{DOMAIN}", shared=True, user_agent=None)
    cur.execute("SELECT TIMESTAMPDIFF(HOUR, NOW(), expires_at) AS h FROM athlete_sessions WHERE email = %s",
                (f"sh@{DOMAIN}",))
    assert cur.fetchone()["h"] <= aa.SHARED_SESSION_HOURS


def test_expired_session_rejected(db):
    conn, cur = db
    token = aa.create_session(f"x@{DOMAIN}", shared=False, user_agent=None)
    cur.execute("UPDATE athlete_sessions SET expires_at = NOW() - INTERVAL 1 SECOND WHERE email = %s",
                (f"x@{DOMAIN}",))
    conn.commit()
    assert aa.session_email(token) is None


def test_logout_everywhere(db):
    a = aa.create_session(f"all@{DOMAIN}", shared=False, user_agent=None)
    b = aa.create_session(f"all@{DOMAIN}", shared=True, user_agent=None)
    other = aa.create_session(f"other@{DOMAIN}", shared=False, user_agent=None)
    aa.delete_all_sessions(f"all@{DOMAIN}")
    assert aa.session_email(a) is None and aa.session_email(b) is None
    assert aa.session_email(other) == f"other@{DOMAIN}"


def test_garbage_session_token(db):
    assert aa.session_email("") is None
    assert aa.session_email("nope") is None
```

- [ ] **Step 2: Убедиться, что падают**

Run: `conda run -n base python -m pytest tests/integration/test_athlete_auth.py -v`
Expected: 5 новых FAIL — `AttributeError: ... has no attribute 'create_session'`.

- [ ] **Step 3: Реализация** (в конец `athlete_auth.py`)

```python
def _token_hash(token: str) -> str:
    return hashlib.sha256((token or "").encode()).hexdigest()


def create_session(email: str, shared: bool, user_agent: Optional[str]) -> str:
    """Новая сессия; возвращает токен для cookie (в БД — его SHA-256).
    shared («Чужой компьютер») — сутки, иначе SESSION_DAYS."""
    token = secrets.token_urlsafe(32)
    ttl = f"INTERVAL {SHARED_SESSION_HOURS} HOUR" if shared else f"INTERVAL {SESSION_DAYS} DAY"
    conn = get_pooled_connection()
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
    conn = get_pooled_connection()
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
    conn = get_pooled_connection()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM athlete_sessions WHERE token_hash = %s", (_token_hash(token),))
        conn.commit()
        cur.close()
    finally:
        conn.close()


def delete_all_sessions(email: str) -> None:
    """«Выйти на всех устройствах»."""
    conn = get_pooled_connection()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM athlete_sessions WHERE email = %s", (normalize_email(email),))
        conn.commit()
        cur.close()
    finally:
        conn.close()
```

- [ ] **Step 4: Тесты проходят**

Run: `conda run -n base python -m pytest tests/integration/test_athlete_auth.py -v`
Expected: 15 passed.

- [ ] **Step 5: Commit**

```bash
git add src/krasmarafon/services/athlete_auth.py tests/integration/test_athlete_auth.py
git commit -m "feat(auth): сессии спортсмена, выход на всех устройствах"
```

---

### Task 5: Заявки кабинета — выборка и группировка по людям

**Files:**
- Create: `src/krasmarafon/services/athlete_cabinet.py`
- Test: `tests/unit/test_athlete_cabinet.py`

Правила — из спецификации, раздел «Страница /me»: группа = `client_id`, без него — фамилия+имя (регистр и «ё» не важны); заголовок — ФИ самой новой заявки (максимальный `id`); «Заявки» — дата события ≥ сегодня или даты нет, ближайшие сверху (без даты — в конце); «Результаты» — прошедшие, новые сверху; порядок людей — с предстоящими по ближайшей дате, затем без предстоящих по последней дате. Время — `time_clear_finish`, иначе `time_gun_finish`; место — `rank_category_clean` при чистом времени, иначе `rank_category`; результат есть только при `race_status = 'Finished'` и времени.

- [ ] **Step 1: Падающие тесты**

`tests/unit/test_athlete_cabinet.py`:

```python
import datetime as dt

from src.krasmarafon.services.athlete_cabinet import group_by_person, protocol_url

TODAY = dt.date(2026, 11, 3)


def lead(id, surname="Иванов", name="Пётр", client_id=None, date=None, **kw):
    row = dict(id=id, surname=surname, name=name, client_id=client_id, event_id=100 + id,
               event_name="Жара", event_distance="21 км", event_year=2026, event_date=date,
               start_number=None, refund=0, race_status=None, time_clear_finish=None,
               time_gun_finish=None, rank_category=None, rank_category_clean=None)
    row.update(kw)
    return row


def test_groups_by_client_id_then_by_name():
    rows = [lead(1, client_id=7), lead(2, surname="ИВАНОВ", name="Петр", client_id=7),
            lead(3, surname="Иванова", name="Маша"), lead(4, surname="иванова", name="маша")]
    people = group_by_person(rows, TODAY)
    assert sorted(len(p["upcoming"]) + len(p["past"]) for p in people) == [2, 2]


def test_title_from_newest_lead():
    people = group_by_person([lead(1, surname="Иванов", name="Петя", client_id=7),
                              lead(5, surname="Иванов", name="Пётр", client_id=7)], TODAY)
    assert people[0]["title"] == "Иванов Пётр"


def test_upcoming_vs_past_and_sorting():
    rows = [lead(1, date=dt.date(2026, 12, 6)), lead(2, date=dt.date(2026, 11, 3)), lead(3, date=None),
            lead(4, date=dt.date(2026, 7, 12)), lead(5, date=dt.date(2026, 4, 26))]
    p = group_by_person(rows, TODAY)[0]
    assert [e["lead_id"] for e in p["upcoming"]] == [2, 1, 3]
    assert [e["lead_id"] for e in p["past"]] == [4, 5]


def test_result_time_place_and_no_result():
    rows = [lead(1, date=dt.date(2026, 7, 12), race_status="Finished",
                 time_clear_finish=dt.timedelta(hours=1, minutes=42, seconds=15),
                 time_gun_finish=dt.timedelta(hours=1, minutes=43), rank_category=20, rank_category_clean=18),
            lead(2, date=dt.date(2026, 4, 26), race_status="Finished",
                 time_gun_finish=dt.timedelta(minutes=25, seconds=3), rank_category=4),
            lead(3, date=dt.date(2026, 3, 1), race_status="DNF", time_gun_finish=dt.timedelta(minutes=50)),
            lead(4, date=dt.date(2026, 2, 1), refund=1)]
    past = {e["lead_id"]: e for e in group_by_person(rows, TODAY)[0]["past"]}
    assert (past[1]["time"], past[1]["place"]) == ("1:42:15", 18)
    assert (past[2]["time"], past[2]["place"]) == ("0:25:03", 4)
    assert past[3]["time"] is None
    assert past[4]["time"] is None and past[4]["refund"]


def test_people_order_nearest_upcoming_first():
    rows = [lead(1, surname="А", name="А", date=dt.date(2026, 12, 20)),
            lead(2, surname="Б", name="Б", date=dt.date(2026, 12, 6)),
            lead(3, surname="В", name="В", date=dt.date(2026, 7, 1)),
            lead(4, surname="Г", name="Г", date=dt.date(2026, 9, 1))]
    assert [p["title"] for p in group_by_person(rows, TODAY)] == ["Б Б", "А А", "Г Г", "В В"]


def test_protocol_url_known_and_unknown_event():
    url = protocol_url("Жара", 2026, "Иванов", {"Жара": "zhara"})
    assert url == "/results?event=zhara&year=2026&search=%D0%98%D0%B2%D0%B0%D0%BD%D0%BE%D0%B2"
    assert protocol_url("Неизвестный", 2026, "Иванов", {"Жара": "zhara"}) is None
```

- [ ] **Step 2: Убедиться, что падают**

Run: `conda run -n base python -m pytest tests/unit/test_athlete_cabinet.py -v`
Expected: FAIL — `ModuleNotFoundError: ... athlete_cabinet`.

- [ ] **Step 3: Реализация**

`src/krasmarafon/services/athlete_cabinet.py`:

```python
"""Личный кабинет (этап А): заявки, оформленные с почты (leads.email или ma_email), по людям —
задел под этап Б, где человек заявит карточку. Правила — спецификация 2026-11-03-athlete-login-design."""

import datetime as dt
from typing import Optional
from urllib.parse import quote

from src.analytics.db_pool import get_pooled_connection
from src.config import settings

_SQL = """
    SELECT l.id, l.client_id, l.surname, l.name, l.event_id, l.start_number, l.refund,
           l.event_name, l.event_distance, l.event_year, e.event_date,
           r.race_status, r.time_clear_finish, r.time_gun_finish, r.rank_category, r.rank_category_clean
    FROM leads l
    LEFT JOIN events e ON e.id = l.event_id
    LEFT JOIN results r ON r.event_id = l.event_id AND r.start_number = l.start_number
    WHERE (LOWER(l.email) = %s OR LOWER(l.ma_email) = %s) AND l.is_duplicate = 0
    ORDER BY l.id
"""


def fetch_leads(email: str) -> list[dict]:
    """Заявки почты; при двух результатах с одним номером — одна строка на заявку."""
    conn = get_pooled_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(_SQL, (email, email))
        rows = {}
        for row in cur.fetchall():
            rows.setdefault(row["id"], row)
        cur.close()
        return list(rows.values())
    finally:
        conn.close()


def _norm(s: Optional[str]) -> str:
    return (s or "").strip().lower().replace("ё", "е")


def _fmt(td: Optional[dt.timedelta]) -> Optional[str]:
    if td is None:
        return None
    s = int(td.total_seconds())
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}"


def protocol_url(event_name: str, year: int, surname: str, codes: dict) -> Optional[str]:
    code = codes.get(event_name)
    if not code:
        return None
    return f"/results?event={code}&year={year}&search={quote(surname or '')}"


def _entry(r: dict, codes: dict) -> dict:
    clean = r["time_clear_finish"] is not None
    finished = r["race_status"] == "Finished" and (clean or r["time_gun_finish"] is not None)
    return {
        "lead_id": r["id"],
        "event_id": r["event_id"],
        "event_name": r["event_name"],
        "distance": r["event_distance"],
        "date": r["event_date"],
        "year": r["event_year"],
        "start_number": r["start_number"],
        "refund": bool(r["refund"]),
        "time": _fmt(r["time_clear_finish"] if clean else r["time_gun_finish"]) if finished else None,
        "place": ((r["rank_category_clean"] or r["rank_category"]) if clean else r["rank_category"])
                 if finished else None,
        "protocol_url": protocol_url(r["event_name"], r["event_year"], r["surname"], codes) if finished else None,
    }


def group_by_person(rows: list[dict], today: dt.date, codes: Optional[dict] = None) -> list[dict]:
    """[{title, upcoming: [...], past: [...]}] в порядке показа."""
    codes = codes or {}
    groups: dict = {}
    for r in sorted(rows, key=lambda r: r["id"]):
        key = ("c", r["client_id"]) if r["client_id"] else ("n", _norm(r["surname"]), _norm(r["name"]))
        g = groups.setdefault(key, {"upcoming": [], "past": []})
        g["title"] = f"{r['surname'] or ''} {r['name'] or ''}".strip()  # перезаписывается — останется самая новая
        e = _entry(r, codes)
        (g["upcoming"] if e["date"] is None or e["date"] >= today else g["past"]).append(e)
    far = dt.date.max
    for g in groups.values():
        g["upcoming"].sort(key=lambda e: e["date"] or far)
        g["past"].sort(key=lambda e: e["date"], reverse=True)

    def order(g):
        if g["upcoming"]:
            return (0, (g["upcoming"][0]["date"] or far).toordinal())
        return (1, -g["past"][0]["date"].toordinal())

    return sorted(groups.values(), key=order)


def cabinet(email: str, today: Optional[dt.date] = None) -> list[dict]:
    codes = {ev.name: ev.code for ev in settings.EVENTS.values()}
    return group_by_person(fetch_leads(email), today or dt.date.today(), codes)
```

- [ ] **Step 4: Тесты проходят**

Run: `conda run -n base python -m pytest tests/unit/test_athlete_cabinet.py -v`
Expected: 6 passed.

- [ ] **Step 5: Проверить на локальной БД, что запрос работает**

Скрипт в scratchpad `cabinet_smoke.py` (почту взять любую из локальной `leads`, в вывод — только число людей и заявок, без ПД):

```python
import sys
from pathlib import Path
from dotenv import load_dotenv

root = Path(sys.argv[1])
load_dotenv(root / ".env.local", override=True)
sys.path.insert(0, str(root))
from src.analytics.db_pool import get_pooled_connection
from src.krasmarafon.services.athlete_cabinet import cabinet

cur = get_pooled_connection().cursor()
cur.execute("SELECT LOWER(email) FROM leads WHERE email <> '' GROUP BY LOWER(email) HAVING COUNT(*) > 3 LIMIT 1")
email = cur.fetchone()[0]
people = cabinet(email)
print(len(people), [len(p["upcoming"]) + len(p["past"]) for p in people])
```

Expected: числа без ошибок (например `2 [3, 2]`).

- [ ] **Step 6: Commit**

```bash
git add src/krasmarafon/services/athlete_cabinet.py tests/unit/test_athlete_cabinet.py
git commit -m "feat(auth): заявки кабинета по почте, группировка по людям"
```

---

### Task 6: Маршруты и экраны входа

**Files:**
- Create: `src/krasmarafon/routers/athlete.py`
- Create: `templates/krasmarafon/me-login.html`, `templates/krasmarafon/me.html`
- Create: `static/css/me.css` (стили входа; в Task 7 дописываются стили кабинета)
- Modify: `src/krasmarafon/router.py` (импорт и `include_router` рядом с `pages_router`)
- Test: `tests/integration/test_athlete_routes.py`

Маршруты (спецификация, раздел «Вход»):

| Метод, путь | Что |
|---|---|
| `GET /me/login` | экран «почта»; с сессией → 302 `/me` |
| `POST /me/login` (`email`, `shared`) | `request_code` → экран «код»; лимит → экран «почта» с «Слишком много попыток, попробуйте позже»; ошибка отправки → «Не удалось отправить код, попробуйте позже» |
| `POST /me/verify` (`email`, `code`, `shared`) | верно → сессия + cookie, 303 `/me`; нет → экран «код» с «Код неверный или устарел» |
| `GET /me/link?t=` | действующая → экран «Войти как …?»; нет → экран «почта» с «Ссылка устарела — запросите новый код» |
| `POST /me/link` (`t`) | `consume_link` → сессия, 303 `/me`; нет → как выше |
| `POST /me/logout`, `POST /me/logout-all` | удалить сессию(и), стереть cookie, 303 `/` |

Все POST: если заголовок `Origin` есть и его хост ≠ `Host` запроса → 403 (защита от отправки форм с чужих сайтов).

- [ ] **Step 1: Падающие тесты**

`tests/integration/test_athlete_routes.py`:

```python
"""Вход и кабинет через HTTP на локальной БД. Тестовые почты — *@athlete-test.local."""
import re
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app import app
from src.analytics.db_pool import get_pooled_connection
from src.krasmarafon.services import athlete_auth as aa

DOMAIN = "athlete-test.local"
EV = "Тест кабинет"


@pytest.fixture
def db():
    conn = get_pooled_connection()
    if not conn:
        pytest.skip("Нет локальной БД")
    cur = conn.cursor(dictionary=True)
    cur.execute("SHOW TABLES LIKE 'athlete_sessions'")
    if not cur.fetchone():
        conn.close()
        pytest.skip("Миграция athlete_login не применена")

    def cleanup():
        cur.execute("DELETE FROM athlete_login_codes WHERE email LIKE %s OR ip = 'testclient'", (f"%@{DOMAIN}",))
        cur.execute("DELETE FROM athlete_sessions WHERE email LIKE %s", (f"%@{DOMAIN}",))
        cur.execute("DELETE FROM leads WHERE event_name = %s", (EV,))
        conn.commit()

    cleanup()
    yield conn, cur
    cleanup()
    cur.close()
    conn.close()


@pytest.fixture
def client():
    return TestClient(app, base_url="https://testserver")


def request_code(client, email):
    with patch.object(aa, "send_mail") as mail:
        r = client.post("/me/login", data={"email": email})
    assert r.status_code == 200
    text = mail.call_args[0][2]
    return r, re.search(r"\b(\d{6})\b", text).group(1), re.search(r"/me/link\?t=([\w-]+)", text).group(1)


def add_lead(cur, surname, email="", ma_email=None):
    cur.execute("""INSERT INTO leads (surname, name, sex, city, club, birthday, email, ma_email, phone, event_name,
                   event_distance, event_year, products, amount, client_id, event_id, is_duplicate, status, is_new,
                   is_new_event, is_name_suspicious, created_at)
                   VALUES (%s, 'Тест', 'Мужчина', '', '', '1990-01-01', %s, %s, '', %s, '5 км', 2099,
                           '', 0, NULL, NULL, 0, 0, 0, 0, 0, NOW())""", (surname, email, ma_email, EV))


def test_me_without_session_redirects_to_login(client):
    r = client.get("/me", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == "/me/login"


def test_full_login_by_code_shows_leads_by_email_and_ma_email(db, client):
    conn, cur = db
    add_lead(cur, "Формапочта", email=f"Me@{DOMAIN}")
    add_lead(cur, "Кабинетпочта", ma_email=f"me@{DOMAIN}")
    add_lead(cur, "Чужойчеловек", email=f"other@{DOMAIN}")
    conn.commit()

    r, code, _ = request_code(client, f"me@{DOMAIN}")
    assert "Введите код" in r.text
    r = client.post("/me/verify", data={"email": f"me@{DOMAIN}", "code": code}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/me"
    cookie = r.headers["set-cookie"]
    assert "km_athlete=" in cookie and "HttpOnly" in cookie and "Secure" in cookie
    assert "samesite=lax" in cookie.lower() and "Max-Age" in cookie

    page = client.get("/me").text
    assert "Формапочта" in page and "Кабинетпочта" in page and "Чужойчеловек" not in page


def test_wrong_code_shows_error(db, client):
    request_code(client, f"wrong@{DOMAIN}")
    r = client.post("/me/verify", data={"email": f"wrong@{DOMAIN}", "code": "abcdef"})
    assert "Код неверный или устарел" in r.text
    assert "km_athlete" not in r.headers.get("set-cookie", "")


def test_shared_computer_cookie_without_max_age(db, client):
    _, code, _ = request_code(client, f"shared@{DOMAIN}")
    r = client.post("/me/verify", data={"email": f"shared@{DOMAIN}", "code": code, "shared": "1"},
                    follow_redirects=False)
    assert "km_athlete=" in r.headers["set-cookie"] and "Max-Age" not in r.headers["set-cookie"]


def test_link_shows_button_then_logs_in(db, client):
    _, _, token = request_code(client, f"link@{DOMAIN}")
    r = client.get(f"/me/link?t={token}")
    assert f"link@{DOMAIN}" in r.text and "km_athlete" not in r.headers.get("set-cookie", "")
    r = client.post("/me/link", data={"t": token}, follow_redirects=False)
    assert r.status_code == 303 and "km_athlete=" in r.headers["set-cookie"]
    assert "Ссылка устарела" in client.get(f"/me/link?t={token}").text


def test_rate_limit_message(db, client):
    request_code(client, f"rl@{DOMAIN}")
    with patch.object(aa, "send_mail") as mail:
        r = client.post("/me/login", data={"email": f"rl@{DOMAIN}"})
    assert "Слишком много попыток" in r.text
    mail.assert_not_called()


def test_mail_failure_message(db, client):
    with patch.object(aa, "send_mail", side_effect=OSError("smtp down")):
        r = client.post("/me/login", data={"email": f"fail@{DOMAIN}"})
    assert "Не удалось отправить код" in r.text


def test_logout_everywhere(db, client):
    _, code, _ = request_code(client, f"out@{DOMAIN}")
    client.post("/me/verify", data={"email": f"out@{DOMAIN}", "code": code})
    other = aa.create_session(f"out@{DOMAIN}", shared=False, user_agent=None)
    r = client.post("/me/logout-all", follow_redirects=False)
    assert r.status_code == 303
    assert aa.session_email(other) is None
    assert client.get("/me", follow_redirects=False).status_code == 302


def test_foreign_origin_post_rejected(db, client):
    with patch.object(aa, "send_mail") as mail:
        r = client.post("/me/login", data={"email": f"csrf@{DOMAIN}"}, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403
    mail.assert_not_called()


def test_empty_cabinet_message(db, client):
    _, code, _ = request_code(client, f"empty@{DOMAIN}")
    client.post("/me/verify", data={"email": f"empty@{DOMAIN}", "code": code})
    assert "Заявок с этой почты не найдено" in client.get("/me").text
```

- [ ] **Step 2: Убедиться, что падают**

Run: `conda run -n base python -m pytest tests/integration/test_athlete_routes.py -v`
Expected: FAIL — 404 на `/me`, `/me/login`.

- [ ] **Step 3: Роутер**

`src/krasmarafon/routers/athlete.py`:

```python
"""Личный кабинет спортсмена: вход по коду из почты и /me (этап А,
спецификация docs/superpowers/specs/2026-11-03-athlete-login-design.md)."""

import logging
from urllib.parse import urlparse

from fastapi import APIRouter, Cookie, Form, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, RedirectResponse

from src.krasmarafon.routers.pages import templates, _diploma_event_ids
from src.krasmarafon.services import athlete_auth as aa
from src.krasmarafon.services.athlete_cabinet import cabinet

logger = logging.getLogger(__name__)
router = APIRouter()

ERR_CODE = "Код неверный или устарел"
ERR_LINK = "Ссылка устарела — запросите новый код"
ERR_LIMIT = "Слишком много попыток, попробуйте позже"
ERR_MAIL = "Не удалось отправить код, попробуйте позже"


def _foreign_origin(request: Request) -> bool:
    origin = request.headers.get("origin")
    return bool(origin) and urlparse(origin).netloc != request.headers.get("host")


def _https(request: Request) -> bool:
    # По схеме запроса (nginx: X-Forwarded-Proto), не по settings.DEBUG — на проде он True
    return request.headers.get("x-forwarded-proto", request.url.scheme) == "https"


def _client_ip(request: Request) -> str:
    return request.headers.get("x-real-ip") or (request.client.host if request.client else "")


def _login_page(request: Request, step: str, **ctx) -> HTMLResponse:
    return templates.TemplateResponse("krasmarafon/me-login.html", {"request": request, "step": step, **ctx})


async def _start_session(request: Request, email: str, shared: bool) -> RedirectResponse:
    token = await run_in_threadpool(aa.create_session, email, shared, request.headers.get("user-agent"))
    response = RedirectResponse("/me", status_code=303)
    response.set_cookie(
        aa.COOKIE_NAME, token, httponly=True, secure=_https(request), samesite="lax",
        max_age=None if shared else aa.SESSION_DAYS * 86400,
    )
    return response


def _forbidden() -> HTMLResponse:
    return HTMLResponse("Forbidden", status_code=403)


@router.get("/me/login", response_class=HTMLResponse)
async def login_page(request: Request, km_athlete: str | None = Cookie(default=None)):
    if km_athlete and await run_in_threadpool(aa.session_email, km_athlete):
        return RedirectResponse("/me", status_code=302)
    return _login_page(request, "email")


@router.post("/me/login", response_class=HTMLResponse)
async def login_send_code(request: Request, email: str = Form(...), shared: str = Form("")):
    if _foreign_origin(request):
        return _forbidden()
    email = aa.normalize_email(email)
    if "@" not in email:
        return _login_page(request, "email", error="Проверьте почту", email=email, shared=bool(shared))
    try:
        await run_in_threadpool(aa.request_code, email, _client_ip(request))
    except aa.TooManyRequests:
        return _login_page(request, "email", error=ERR_LIMIT, email=email, shared=bool(shared))
    except Exception:
        logger.exception("Письмо с кодом входа не отправлено")
        return _login_page(request, "email", error=ERR_MAIL, email=email, shared=bool(shared))
    return _login_page(request, "code", email=email, shared=bool(shared))


@router.post("/me/verify", response_class=HTMLResponse)
async def login_verify(request: Request, email: str = Form(...), code: str = Form(...), shared: str = Form("")):
    if _foreign_origin(request):
        return _forbidden()
    email = aa.normalize_email(email)
    if await run_in_threadpool(aa.verify_code, email, code):
        return await _start_session(request, email, bool(shared))
    return _login_page(request, "code", error=ERR_CODE, email=email, shared=bool(shared))


@router.get("/me/link", response_class=HTMLResponse)
async def link_page(request: Request, t: str = ""):
    email = await run_in_threadpool(aa.link_email, t)
    if not email:
        return _login_page(request, "email", error=ERR_LINK)
    return _login_page(request, "link", email=email, token=t)


@router.post("/me/link", response_class=HTMLResponse)
async def link_login(request: Request, t: str = Form(...)):
    if _foreign_origin(request):
        return _forbidden()
    email = await run_in_threadpool(aa.consume_link, t)
    if not email:
        return _login_page(request, "email", error=ERR_LINK)
    return await _start_session(request, email, False)


def _logged_out() -> RedirectResponse:
    response = RedirectResponse("/", status_code=303)
    response.delete_cookie(aa.COOKIE_NAME)
    return response


@router.post("/me/logout")
async def logout(request: Request, km_athlete: str | None = Cookie(default=None)):
    if _foreign_origin(request):
        return _forbidden()
    if km_athlete:
        await run_in_threadpool(aa.delete_session, km_athlete)
    return _logged_out()


@router.post("/me/logout-all")
async def logout_all(request: Request, km_athlete: str | None = Cookie(default=None)):
    if _foreign_origin(request):
        return _forbidden()
    email = await run_in_threadpool(aa.session_email, km_athlete)
    if email:
        await run_in_threadpool(aa.delete_all_sessions, email)
    return _logged_out()


@router.get("/me", response_class=HTMLResponse)
async def me_page(request: Request, km_athlete: str | None = Cookie(default=None)):
    email = await run_in_threadpool(aa.session_email, km_athlete)
    if not email:
        return RedirectResponse("/me/login", status_code=302)
    people = await run_in_threadpool(cabinet, email)
    return templates.TemplateResponse("krasmarafon/me.html", {
        "request": request, "email": email, "people": people,
        "diploma_event_ids": set(_diploma_event_ids()),
    })
```

В `src/krasmarafon/router.py` рядом с импортом `pages_router` добавить импорт и после `router.include_router(pages_router)`:

```python
from src.krasmarafon.routers.athlete import router as athlete_router
...
router.include_router(athlete_router)
```

(Повторить стиль импорта, принятый в файле.)

- [ ] **Step 4: Шаблон входа**

`templates/krasmarafon/me-login.html` — три состояния одного шаблона (`step`: `email` / `code` / `link`), тексты — дословно из спецификации, раздел «Экраны входа»:

```html
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="robots" content="noindex">
    <title>Вход в личный кабинет — Красмарафон</title>
    <link rel="icon" href="/static/images/krasmarafon/favicon.ico" sizes="any">
    <link rel="stylesheet" href="/static/css/km-design-tokens.css?v={{ v }}">
    <link rel="stylesheet" href="/static/css/krasmarafon-header.css?v={{ v }}">
    <link rel="stylesheet" href="/static/css/krasmarafon-footer.css?v={{ v }}">
    <link rel="stylesheet" href="/static/css/me.css?v={{ v }}">
</head>
<body>
{% include 'krasmarafon/header.html' %}
<main class="me-auth">
    {% if step == 'email' %}
    <h1>Вход в личный кабинет</h1>
    <p class="me-muted">Введите почту — пришлём код. Пароль не нужен.</p>
    {% if error %}<p class="me-error">{{ error }}</p>{% endif %}
    <form method="post" action="/me/login">
        <input class="me-input" type="email" name="email" value="{{ email or '' }}" placeholder="почта@example.ru"
               autocomplete="email" required autofocus>
        <label class="me-check"><input type="checkbox" name="shared" value="1" {% if shared %}checked{% endif %}>
            Чужой компьютер — не запоминать вход</label>
        <button class="me-btn" type="submit">Получить код</button>
    </form>
    <p class="me-hint">Подойдёт почта, на которую оформляли заявку, или почта кабинета на сайте Красмарафона</p>

    {% elif step == 'code' %}
    <h1>Введите код</h1>
    <p class="me-muted">Отправили 6 цифр на {{ email }}. Код действует 15 минут. Нет письма — проверьте «Спам».</p>
    {% if error %}<p class="me-error">{{ error }}</p>{% endif %}
    <form method="post" action="/me/verify">
        <input type="hidden" name="email" value="{{ email }}">
        {% if shared %}<input type="hidden" name="shared" value="1">{% endif %}
        <input class="me-input me-code" name="code" inputmode="numeric" autocomplete="one-time-code"
               pattern="[0-9 ]*" maxlength="7" placeholder="••••••" required autofocus>
        <button class="me-btn" type="submit">Войти</button>
    </form>
    <form method="post" action="/me/login" class="me-resend">
        <input type="hidden" name="email" value="{{ email }}">
        {% if shared %}<input type="hidden" name="shared" value="1">{% endif %}
        <button class="me-link" type="submit" id="resend" disabled>Отправить код ещё раз</button>
    </form>
    <a class="me-link" href="/me/login">Другая почта</a>
    <script>
        // «Отправить ещё раз» — не раньше чем через минуту (лимит на сервере тот же)
        (function () {
            const btn = document.getElementById('resend');
            let left = 60;
            const tick = () => {
                if (left <= 0) { btn.disabled = false; btn.textContent = 'Отправить код ещё раз'; return; }
                btn.textContent = `Отправить код ещё раз (через 0:${String(left).padStart(2, '0')})`;
                left -= 1;
                setTimeout(tick, 1000);
            };
            tick();
        })();
    </script>

    {% elif step == 'link' %}
    <h1>Вход в личный кабинет</h1>
    <p class="me-muted">Войти как {{ email }}?</p>
    <form method="post" action="/me/link">
        <input type="hidden" name="t" value="{{ token }}">
        <button class="me-btn" type="submit">Войти</button>
    </form>
    {% endif %}
</main>
{% include 'krasmarafon/krasmarafon_footer.html' %}
</body>
</html>
```

Одно поле кода вместо шести — так работает вставка из буфера и автоподстановка кода из SMS/почты на телефоне (`one-time-code`); визуально — крупные моноширинные цифры с разрядкой (`.me-code`).

- [ ] **Step 5: Стили входа**

`static/css/me.css`:

```css
/* Личный кабинет спортсмена (/me, /me/login) — токены km-design-tokens.css */
.me-auth { max-width: 400px; margin: 40px auto; padding: 0 16px; }
.me-auth h1 { font-family: var(--km-font-brand); font-size: 24px; margin-bottom: 8px; color: var(--km-dark); }
.me-muted { color: var(--km-text-secondary); font-size: 14px; line-height: 1.45; margin-bottom: 16px; }
.me-hint { color: var(--km-text-muted); font-size: 12px; text-align: center; margin-top: 14px; line-height: 1.4; }
.me-error { background: #fdecea; color: #b3261e; border-radius: var(--km-radius-input); padding: 10px 12px;
            font-size: 14px; margin-bottom: 12px; }
.me-input { width: 100%; padding: 12px; font-size: 16px; border: 1px solid var(--km-border-light);
            border-radius: var(--km-radius-input); background: var(--km-bg-card); margin-bottom: 12px; }
.me-code { font-family: monospace; font-size: 26px; letter-spacing: 10px; text-align: center; }
.me-check { display: flex; gap: 8px; align-items: center; font-size: 14px; color: var(--km-text-secondary);
            margin-bottom: 16px; }
.me-btn { width: 100%; padding: 12px; border: 0; border-radius: var(--km-radius-btn); background: var(--km-primary);
          color: #fff; font-size: 16px; font-weight: 700; cursor: pointer; }
.me-link { display: block; width: 100%; background: none; border: 0; color: var(--km-primary); font-size: 14px;
           text-align: center; margin-top: 12px; cursor: pointer; text-decoration: none; font-family: inherit; }
.me-link:disabled { color: var(--km-text-muted); cursor: default; }
```

- [ ] **Step 6: Шаблон кабинета** (макет C1; стили — в Task 7)

`templates/krasmarafon/me.html`:

```html
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="robots" content="noindex">
    <title>Личный кабинет — Красмарафон</title>
    <link rel="icon" href="/static/images/krasmarafon/favicon.ico" sizes="any">
    <link rel="stylesheet" href="/static/css/km-design-tokens.css?v={{ v }}">
    <link rel="stylesheet" href="/static/css/krasmarafon-header.css?v={{ v }}">
    <link rel="stylesheet" href="/static/css/krasmarafon-footer.css?v={{ v }}">
    <link rel="stylesheet" href="/static/css/me.css?v={{ v }}">
</head>
<body>
{% include 'krasmarafon/header.html' %}
{% set months = ['янв','фев','мар','апр','мая','июн','июл','авг','сен','окт','ноя','дек'] %}
<main class="me-page">
    <h1>Личный кабинет</h1>
    <div class="me-account">
        <span>{{ email }}</span>
        <form method="post" action="/me/logout"><button class="me-inline" type="submit">Выйти</button></form>
        <form method="post" action="/me/logout-all"><button class="me-inline" type="submit">Выйти на всех устройствах</button></form>
    </div>

    {% if not people %}
    <p class="me-empty">Заявок с этой почты не найдено</p>
    {% endif %}

    {% for p in people %}
    <section class="me-person">
        <div class="me-person-head">
            <div class="me-avatar">{{ p.title.split()|map('first')|join('')|upper }}</div>
            <h2>{{ p.title }}</h2>
        </div>

        {% if p.upcoming %}
        <div class="me-sub">🎟 Заявки</div>
        {% for e in p.upcoming %}
        <div class="me-ticket">
            <div class="me-ticket-date">
                {% if e.date %}{{ e.date.day }}<small>{{ months[e.date.month - 1] }}</small>{% else %}—<small>{{ e.year }}</small>{% endif %}
            </div>
            <div class="me-ticket-body">
                <div class="me-title">{{ e.event_name }} · {{ e.distance }}</div>
                <div class="me-meta">
                    {% if e.start_number %}№{{ e.start_number }}{% else %}номер ещё не присвоен{% endif %} ·
                    {% if e.refund %}<span class="me-tag me-tag--refund">возврат</span>{% else %}<span class="me-tag">оплачено</span>{% endif %}
                </div>
            </div>
        </div>
        {% endfor %}
        {% endif %}

        {% if p.past %}
        <div class="me-sub">🏁 Результаты</div>
        {% for e in p.past %}
        <div class="me-result{% if not e.time %} me-result--none{% endif %}">
            <div class="me-result-body">
                <div class="me-title">{{ e.event_name }} · {{ e.distance }}</div>
                <div class="me-meta">
                    {% if e.date %}{{ e.date.day }} {{ months[e.date.month - 1] }} {{ e.date.year }}{% else %}{{ e.year }}{% endif %}
                    {% if e.refund %} · <span class="me-tag me-tag--refund">возврат</span>{% endif %}
                    {% if e.protocol_url %} · <a href="{{ e.protocol_url }}">протокол</a>{% endif %}
                    {% if e.time and e.event_id in diploma_event_ids and e.start_number %} · <a href="/diploma/{{ e.event_id }}/{{ e.start_number }}" target="_blank">диплом</a>{% endif %}
                </div>
            </div>
            <div class="me-time">
                {% if e.time %}{{ e.time }}{% if e.place %}<small>{{ e.place }} место в категории</small>{% endif %}
                {% elif e.refund %}—{% else %}нет результата{% endif %}
            </div>
        </div>
        {% endfor %}
        {% endif %}
    </section>
    {% endfor %}
</main>
{% include 'krasmarafon/krasmarafon_footer.html' %}
</body>
</html>
```

- [ ] **Step 7: Тесты проходят**

Run: `conda run -n base python -m pytest tests/integration/test_athlete_routes.py tests/integration/test_athlete_auth.py -v`
Expected: все passed.

- [ ] **Step 8: Commit**

```bash
git add src/krasmarafon/routers/athlete.py src/krasmarafon/router.py templates/krasmarafon/me-login.html templates/krasmarafon/me.html static/css/me.css tests/integration/test_athlete_routes.py
git commit -m "feat(auth): страницы входа по коду и ссылке, выход"
```

---

### Task 7: Страница кабинета и кнопка в шапке

**Files:**
- Modify: `static/css/me.css` (дописать)
- Modify: `templates/krasmarafon/header.html`
- Test: `tests/integration/test_athlete_routes.py` (дописать)

Макет — вариант C1 (спецификация, «Страница /me»): по людям, у каждого «🎟 Заявки» (билет с датой) и «🏁 Результаты» (строка с крупным временем); пустой подраздел не показывается.

- [ ] **Step 1: Шаблон кабинета** — уже создан в Task 6, Step 6; здесь не меняется.

- [ ] **Step 2: Стили кабинета** (в конец `static/css/me.css`)

```css
.me-page { max-width: 640px; margin: 24px auto 40px; padding: 0 16px; }
.me-page h1 { font-family: var(--km-font-brand); font-size: 26px; color: var(--km-dark); }
.me-account { display: flex; flex-wrap: wrap; gap: 4px 14px; align-items: center; color: var(--km-text-secondary);
              font-size: 14px; margin: 4px 0 8px; }
.me-account form { display: inline; }
.me-inline { background: none; border: 0; color: var(--km-primary); font-size: 14px; cursor: pointer; padding: 0;
             font-family: inherit; }
.me-empty { color: var(--km-text-secondary); margin-top: 24px; }
.me-person { margin-top: 22px; }
.me-person-head { display: flex; align-items: center; gap: 10px; margin-bottom: 6px; }
.me-person-head h2 { font-size: 18px; color: var(--km-dark); }
.me-avatar { width: 34px; height: 34px; border-radius: 50%; background: var(--km-primary); color: #fff;
             display: flex; align-items: center; justify-content: center; font-weight: 700; font-size: 13px; }
.me-sub { font-size: 12px; text-transform: uppercase; letter-spacing: .5px; color: var(--km-text-muted);
          margin: 12px 0 6px; }
.me-title { font-weight: 700; font-size: 15px; }
.me-meta { color: var(--km-text-secondary); font-size: 13px; margin-top: 2px; }
.me-meta a { color: var(--km-primary); text-decoration: none; }
.me-tag { display: inline-block; font-size: 12px; padding: 1px 8px; border-radius: 20px; background: #e8f6ec;
          color: #1d7a3a; }
.me-tag--refund { background: #fdecea; color: #b3261e; }
.me-ticket { display: flex; background: var(--km-bg-card); border: 1px solid #f3c2cf;
             border-radius: var(--km-radius-card); overflow: hidden; margin-bottom: 8px; }
.me-ticket-date { background: var(--km-primary); color: #fff; width: 58px; flex-shrink: 0; display: flex;
                  flex-direction: column; align-items: center; justify-content: center; font-weight: 700;
                  font-size: 20px; line-height: 1.1; }
.me-ticket-date small { font-size: 12px; font-weight: 400; }
.me-ticket-body { padding: 10px 12px; }
.me-result { display: flex; align-items: center; gap: 10px; background: var(--km-bg-card);
             border-radius: var(--km-radius-card); box-shadow: var(--km-shadow); padding: 10px 12px; margin-bottom: 8px; }
.me-result-body { flex: 1; min-width: 0; }
.me-time { text-align: right; font-size: 20px; font-weight: 700; color: var(--km-dark); white-space: nowrap; }
.me-time small { display: block; font-size: 12px; color: var(--km-primary); }
.me-result--none { box-shadow: none; border: 1px solid var(--km-border-light); }
.me-result--none .me-title, .me-result--none .me-time { color: var(--km-text-muted); }
.me-result--none .me-time { font-size: 13px; font-weight: 400; }
```

- [ ] **Step 3: Кнопка в шапке**

В `templates/krasmarafon/header.html` перед закрывающим `</ul>` пункта меню (после блока `{% if history_enabled() %}…{% endif %}`):

```html
            <li class="navbar-item">
                {% if request and request.cookies.get('km_athlete') %}
                <a href="/me" class="navbar-link navbar-link--account">КАБИНЕТ</a>
                {% else %}
                <a href="/me/login" class="navbar-link navbar-link--account">ВОЙТИ</a>
                {% endif %}
            </li>
```

В конец `static/css/krasmarafon-header.css`:

```css
/* «Войти» / «Кабинет» — личный кабинет спортсмена (/me) */
.navbar-link--account { border: 1px solid var(--km-primary, #EE2D62); border-radius: 50px; padding: 4px 14px; }
```

Проверить `updateActiveNavLink()` в `header.html`: подсветка идёт по индексам `navbarLinks[0..]` — новый пункт последний, индексы трекера/результатов/истории не меняются. Добавить в ту же функцию ветку: `else if (currentPath.startsWith('/me')) { document.querySelector('.navbar-link--account')?.classList.add('active'); }`.

Если в каком-то шаблоне, где подключается `header.html`, нет `request` в контексте — условие `request and …` даст «ВОЙТИ», ошибки не будет.

- [ ] **Step 4: Тесты страницы** (в конец `tests/integration/test_athlete_routes.py`)

```python
def test_cabinet_groups_upcoming_and_results(db, client):
    conn, cur = db
    cur.execute("SELECT id FROM events WHERE event_date < CURDATE() AND event_name = 'Жара' "
                "ORDER BY event_date DESC LIMIT 1")
    past_ev = cur.fetchone()
    add_lead(cur, "Будущий", email=f"cab@{DOMAIN}")  # event_id NULL → даты нет → «Заявки»
    if past_ev:
        add_lead(cur, "Прошлый", email=f"cab@{DOMAIN}")
        cur.execute("UPDATE leads SET event_id = %s WHERE event_name = %s AND surname = 'Прошлый'",
                    (past_ev["id"], EV))
    conn.commit()
    _, code, _ = request_code(client, f"cab@{DOMAIN}")
    client.post("/me/verify", data={"email": f"cab@{DOMAIN}", "code": code})
    page = client.get("/me").text
    assert "🎟 Заявки" in page and "номер ещё не присвоен" in page
    if past_ev:
        assert "🏁 Результаты" in page and "нет результата" in page


def test_header_shows_login_or_cabinet(db, client):
    assert "ВОЙТИ" in client.get("/results").text
    _, code, _ = request_code(client, f"hdr@{DOMAIN}")
    client.post("/me/verify", data={"email": f"hdr@{DOMAIN}", "code": code})
    assert "КАБИНЕТ" in client.get("/results").text
```

Примечание: `add_lead` ставит `event_name = EV`, поэтому cleanup фикстуры удаляет и эти заявки.

- [ ] **Step 5: Тесты проходят**

Run: `conda run -n base python -m pytest tests/integration/test_athlete_routes.py -v`
Expected: все passed.

- [ ] **Step 6: Commit**

```bash
git add static/css/me.css templates/krasmarafon/header.html static/css/krasmarafon-header.css tests/integration/test_athlete_routes.py
git commit -m "feat(auth): страница личного кабинета (по людям: заявки и результаты), кнопка в шапке"
```

---

### Task 8: Полный прогон и локальная проверка пользователем

- [ ] **Step 1: Все unit-тесты**

Run: `conda run -n base python -m pytest tests/unit/ -q`
Expected: все passed (код возврата 0).

- [ ] **Step 2: Интеграционные тесты, затронутые фичей и шапкой**

Run: `conda run -n base python -m pytest tests/integration/test_athlete_auth.py tests/integration/test_athlete_routes.py tests/integration/test_lead_pd_refused.py tests/integration/test_history_toggle_routes.py tests/integration/test_diploma_route.py -q`
Expected: все passed. Известные падения Siberman (4 failed, 23 errors на main) к задаче не относятся — сверить, что их число не выросло: `conda run -n base python -m pytest tests/integration -q` на ветке и сравнить с main.

- [ ] **Step 3: Локальный сервер**

Убедиться, что в `.env.local` worktree есть `PUBLIC_BASE_URL=http://localhost:8000` (дописать строку, если нет; `MAIL_BACKEND` не задавать → `log`). Перезапустить dev-сервер (`.\dev.ps1` из worktree), открыть `http://localhost:8000/me/login`.

- [ ] **Step 4: Чек-лист для пользователя** (передать пользователю; код из письма — в логе сервера, строка `MAIL (log)`)

1. Шапка на `/results`: справа «ВОЙТИ».
2. `/me/login` → своя почта из локальной БД (с заявками) → экран «Введите код», отсчёт «Отправить код ещё раз».
3. Код из лога → «Личный кабинет»: люди, у каждого «🎟 Заявки» / «🏁 Результаты»; время, место, ссылки «протокол» и «диплом» открываются.
4. Неверный код 5 раз → верный уже не принимается → запросить новый.
5. Ссылка из лога → страница «Войти как …?» → «Войти» → кабинет; повторно та же ссылка — «Ссылка устарела».
6. «Чужой компьютер» → после закрытия браузера вход сброшен.
7. «Выйти на всех устройствах» → в другом браузере тоже вышли.
8. Почта без заявок → «Заявок с этой почты не найдено».
9. Телефон (или узкое окно ~375px): экраны входа и кабинета без горизонтальной прокрутки.

- [ ] **Step 5: Документация** — `.taskmaster/tasks/todo.md`: секция ревью этапа А; Obsidian `inbox/2026-11-03-krasmarafon-athlete-auth.md` и «текущие приоритеты» — статус «этап А реализован, ждёт локальной проверки».

**Выкладка — не в этом плане.** После «да» пользователя: ящик `noreply@krasmarafon.ru` + пароль приложения в `/opt/km_track/.env` (пользователь), `MAIL_BACKEND=smtp`, `SMTP_*`, `MAIL_FROM`; миграция `athlete_login.sql` на проде; push в main.
