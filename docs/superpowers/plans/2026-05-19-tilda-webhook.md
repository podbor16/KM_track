# Tilda Webhook Endpoint Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Заменить Nodul: принимать webhook от Tilda напрямую в FastAPI, трансформировать данные и вставлять в таблицу `leads`.

**Architecture:** Новый роутер `src/tracker/routers/webhook.py` добавляет `POST /webhook/tilda/{token}`. Логика трансформации вынесена в `src/tracker/services/tilda_webhook.py` (чистые функции, без зависимостей от FastAPI). Токен хранится в `.env` как `TILDA_WEBHOOK_SECRET`, проверяется в path. INSERT в `leads` через существующий пул `get_pooled_connection()`. Tilda ожидает 200 OK — отвечаем 200 всегда, ошибки логируем.

**Tech Stack:** FastAPI, Python 3.13, mysql-connector-python, python-dotenv

---

## Файловая структура

| Файл | Действие | Назначение |
|------|----------|------------|
| `src/tracker/services/tilda_webhook.py` | создать | Все функции трансформации (parse, normalize, decode) |
| `src/tracker/routers/webhook.py` | создать | FastAPI роутер POST /webhook/tilda/{token} |
| `src/tracker/router.py` | изменить | Подключить webhook router |
| `src/config/settings.py` | изменить | Добавить TILDA_WEBHOOK_SECRET |
| `.env` | изменить | Добавить TILDA_WEBHOOK_SECRET=... |
| `tests/unit/test_tilda_webhook.py` | создать | Unit-тесты трансформации |

---

### Task 1: Секретный токен в конфиге

**Files:**
- Modify: `src/config/settings.py:82-90`
- Modify: `.env`

- [ ] **Step 1: Добавить TILDA_WEBHOOK_SECRET в settings.py**

В `src/config/settings.py` найти блок `# --- АВТОРИЗАЦИЯ ---` и добавить после `SECRET_KEY`:

```python
TILDA_WEBHOOK_SECRET = os.getenv("TILDA_WEBHOOK_SECRET", "")
```

В `__all__` добавить `"TILDA_WEBHOOK_SECRET"`.

- [ ] **Step 2: Сгенерировать токен и добавить в .env**

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Скопировать вывод и добавить в `.env`:
```
TILDA_WEBHOOK_SECRET=<сгенерированный_токен>
```

- [ ] **Step 3: Commit**

```bash
git add src/config/settings.py .env
git commit -m "feat: TILDA_WEBHOOK_SECRET в конфиг"
```

---

### Task 2: Логика трансформации

**Files:**
- Create: `src/tracker/services/tilda_webhook.py`
- Test: `tests/unit/test_tilda_webhook.py`

- [ ] **Step 1: Написать failing тесты**

Создать `tests/unit/test_tilda_webhook.py`:

```python
import pytest
from src.tracker.services.tilda_webhook import (
    decode_from_db_format,
    convert_birthday,
    normalize_name,
    parse_products,
    parse_payment,
    transform_tilda_payload,
)


def test_decode_from_db_format_simple():
    assert decode_from_db_format("4.9") == 4.9


def test_decode_from_db_format_encoded():
    # значение > 1e9: (num - 1e6) → intPart / fracPart
    encoded = 1000000000 + 1e6 + 490 * 1e7  # 490.00 encoded
    assert decode_from_db_format(str(int(encoded))) == pytest.approx(490.0, rel=1e-3)


def test_decode_from_db_format_string_passthrough():
    assert decode_from_db_format("не число") == "не число"


def test_convert_birthday_ru_format():
    assert convert_birthday("01.05.1990") == "1990-05-01"


def test_convert_birthday_iso_passthrough():
    assert convert_birthday("1990-05-01") == "1990-05-01"


def test_convert_birthday_none():
    assert convert_birthday(None) is None


def test_normalize_name():
    assert normalize_name("ИВАНОВ") == "Иванов"
    assert normalize_name("иван петров") == "Иван Петров"


def test_parse_products_standard():
    products = ["5 км Весна 2027 (Vesna5b-2027, Выберите категорию: Пенсионеры)=490"]
    result = parse_products(products)
    assert result["event_distance"] == "5 км"
    assert result["event_name"] == "Весна"
    assert result["event_year"] == "2027"


def test_parse_products_km_latin():
    products = ["10 km Summer 2026 (event=100)"]
    result = parse_products(products)
    assert result["event_distance"] == "10 км"


def test_parse_products_empty():
    result = parse_products([])
    assert result == {"event_distance": "", "event_name": "", "event_year": ""}


def test_parse_products_detsky_zabeg():
    products = ["Детский забег 2027 (child)=200"]
    result = parse_products(products, birthday="2021-06-01")
    # 2027 - 2021 = 6, возраст >= 6 → 1 км
    assert result["event_name"] == "Детский забег"
    assert result["event_distance"] == "1 км"
    assert result["event_year"] == "2027"


def test_parse_payment():
    payment_str = (
        '{"sys":"cloudpayments","systranid":"3521002298","orderid":"1869817991",'
        '"products":["5 км Весна 2027 (Vesna5b-2027)=490"],'
        '"promocode":"TEST","discount":"485.1","amount":"4.9"}'
    )
    result = parse_payment(payment_str)
    assert result["payment_system"] == "cloudpayments"
    assert result["transaction_id"] == "3521002298"
    assert result["amount"] == pytest.approx(4.9)
    assert result["discount"] == pytest.approx(485.1)


def test_transform_full_payload():
    body = {
        "surname": "ИВАНОВ",
        "name": "иван",
        "sex": "мужской",
        "city": "Красноярск",
        "birthday": "01.01.1990",
        "email": "test@test.ru",
        "phone": "+7-900-000-0000",
        "payment": (
            '{"sys":"cloudpayments","systranid":"123","orderid":"456",'
            '"products":["5 км Весна 2027 (test)=490"],'
            '"promocode":"","discount":"0","amount":"490"}'
        ),
    }
    result = transform_tilda_payload(body)
    assert result["surname"] == "Иванов"
    assert result["name"] == "Иван"
    assert result["birthday"] == "1990-01-01"
    assert result["event_name"] == "Весна"
    assert result["event_distance"] == "5 км"
    assert result["is_name_suspicious"] == 0
    assert result["client_id"] == 0
    assert result["event_id"] == 0
```

- [ ] **Step 2: Запустить тесты — убедиться что падают**

```bash
conda run -n base python -m pytest tests/unit/test_tilda_webhook.py -v
```

Ожидаемый результат: `ImportError: cannot import name 'decode_from_db_format'`

- [ ] **Step 3: Создать `src/tracker/services/tilda_webhook.py`**

```python
import json
import math
import re
from datetime import datetime


def decode_from_db_format(value):
    if value is None or value == "":
        return value
    try:
        num = float(value)
    except (TypeError, ValueError):
        return value
    if num > 1e9:
        without_offset = num - 1e6
        int_part = math.floor(without_offset / 1e10)
        remainder = without_offset % 1e10
        frac = math.floor(remainder / 1e7)
        return int_part + frac / 100
    return num


def convert_birthday(birthday):
    if not birthday or not isinstance(birthday, str):
        return birthday
    birthday = birthday.strip()
    match = re.match(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})$", birthday)
    if match:
        day = match.group(1).zfill(2)
        month = match.group(2).zfill(2)
        year = match.group(3)
        return f"{year}-{month}-{day}"
    if re.match(r"^\d{4}-\d{2}-\d{2}$", birthday):
        return birthday
    return birthday


def normalize_name(s):
    if not s or not isinstance(s, str):
        return s
    return " ".join(w.capitalize() for w in s.strip().split())


def parse_products(products, birthday=None):
    """Извлекает event_distance, event_name, event_year из массива products."""
    empty = {"event_distance": "", "event_name": "", "event_year": ""}
    if not products:
        return empty

    products_str = products[0] if isinstance(products, list) else str(products)

    # Стандартный формат: "5 км Весна 2027 (...)"
    match = re.match(
        r"^(\d+(?:\.\d+)?)\s+(км|km)\s+(.+?)\s+(\d{4})\s*\(",
        products_str,
        re.IGNORECASE,
    )
    if match:
        distance_num = match.group(1)
        unit = "км"  # всегда кириллица
        event_name = match.group(3).strip()
        event_name = re.sub(r"\s+северная\s+ходьба\s*", " ", event_name, flags=re.IGNORECASE).strip()
        event_year = match.group(4)
        return {
            "event_distance": f"{distance_num} {unit}",
            "event_name": event_name,
            "event_year": event_year,
        }

    # Детский забег
    if re.search(r"детск.*забег", products_str, re.IGNORECASE):
        year_match = re.search(r"\b(20\d{2})\b", products_str)
        event_year = year_match.group(1) if year_match else ""
        event_distance = ""
        if birthday and event_year:
            try:
                birth_year = int(birthday[:4])
                race_year = int(event_year)
                age = race_year - birth_year
                event_distance = "500 м" if age < 6 else "1 км"
            except (ValueError, IndexError):
                pass
        return {"event_distance": event_distance, "event_name": "Детский забег", "event_year": event_year}

    return empty


def parse_payment(payment_raw):
    """Парсит JSON-строку поля payment из Tilda."""
    result = {
        "payment_system": "",
        "transaction_id": "",
        "order_id": "",
        "products_raw": "",
        "promocode": "",
        "discount": 0.0,
        "amount": 0.0,
    }
    if not payment_raw:
        return result
    try:
        parsed = json.loads(payment_raw) if isinstance(payment_raw, str) else payment_raw
    except (json.JSONDecodeError, TypeError):
        return result

    result["payment_system"] = parsed.get("sys", "")
    result["transaction_id"] = parsed.get("systranid", "")
    result["order_id"] = parsed.get("orderid", "")
    result["products_raw"] = parsed.get("products", "")
    result["promocode"] = parsed.get("promocode", "")

    for field in ("discount", "amount"):
        raw = parsed.get(field)
        if raw is not None and raw != "":
            result[field] = decode_from_db_format(str(raw))

    return result


def transform_tilda_payload(body: dict) -> dict:
    """Трансформирует тело webhook Tilda в dict для INSERT INTO leads."""
    payment_raw = body.get("payment", "")
    payment = parse_payment(payment_raw)

    birthday = convert_birthday(body.get("birthday"))
    products_list = payment["products_raw"]
    event_info = parse_products(
        products_list if isinstance(products_list, list) else [products_list],
        birthday=birthday,
    )

    surname = normalize_name(body.get("surname", ""))
    name = normalize_name(body.get("name", ""))
    is_name_suspicious = int(
        bool(surname and " " in surname) or bool(name and " " in name)
    )

    products_str = (
        ", ".join(products_list)
        if isinstance(products_list, list)
        else str(products_list or "")
    )

    return {
        "surname": surname,
        "name": name,
        "sex": body.get("sex", ""),
        "city": body.get("city", ""),
        "birthday": birthday,
        "email": body.get("email", ""),
        "phone": body.get("phone", ""),
        "event_name": event_info["event_name"],
        "event_distance": event_info["event_distance"],
        "event_year": event_info["event_year"],
        "products": products_str,
        "payment_system": payment["payment_system"],
        "transaction_id": payment["transaction_id"],
        "order_id": payment["order_id"],
        "promocode": payment["promocode"],
        "discount": payment["discount"],
        "amount": payment["amount"],
        "is_name_suspicious": is_name_suspicious,
        "client_id": 0,   # тригер trg_leads_before_insert заменит
        "event_id": 0,    # тригер заменит
        "is_duplicate": 0,
        "status": 0,
        "is_new": 0,
        "is_new_event": 0,
    }
```

- [ ] **Step 4: Запустить тесты — убедиться что проходят**

```bash
conda run -n base python -m pytest tests/unit/test_tilda_webhook.py -v
```

Ожидаемый результат: все тесты `PASSED`.

- [ ] **Step 5: Commit**

```bash
git add src/tracker/services/tilda_webhook.py tests/unit/test_tilda_webhook.py
git commit -m "feat: tilda_webhook.py — трансформация payload Tilda"
```

---

### Task 3: FastAPI роутер

**Files:**
- Create: `src/tracker/routers/webhook.py`

- [ ] **Step 1: Создать `src/tracker/routers/webhook.py`**

```python
"""
Webhook endpoint для приёма регистраций из Tilda.
POST /webhook/tilda/{token}
"""

import json
import logging

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse

from src.config import settings
from src.analytics.db_connection_optimized import get_pooled_connection
from src.tracker.services.tilda_webhook import transform_tilda_payload

router = APIRouter(prefix="/webhook", tags=["webhook"])
_log = logging.getLogger("km_track.webhook")


@router.post("/tilda/{token}")
async def tilda_webhook(token: str, request: Request):
    # Проверка токена
    if not settings.TILDA_WEBHOOK_SECRET or token != settings.TILDA_WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="Invalid token")

    # Парсим тело — Tilda шлёт JSON
    try:
        body = await request.json()
    except Exception:
        raw = await request.body()
        try:
            body = json.loads(raw)
        except Exception:
            _log.warning("tilda_webhook: не удалось распарсить тело запроса")
            return JSONResponse({"ok": False, "error": "bad body"})

    try:
        data = transform_tilda_payload(body)
    except Exception as e:
        _log.error(f"tilda_webhook: ошибка трансформации: {e}", exc_info=True)
        return JSONResponse({"ok": False, "error": "transform failed"})

    try:
        _insert_lead(data)
        _log.info(
            f"tilda_webhook: lead вставлен — {data.get('surname')} {data.get('name')}, "
            f"event={data.get('event_name')} {data.get('event_year')}"
        )
    except Exception as e:
        _log.error(f"tilda_webhook: ошибка INSERT: {e}", exc_info=True)
        return JSONResponse({"ok": False, "error": "db error"})

    return JSONResponse({"ok": True})


def _insert_lead(data: dict):
    conn = get_pooled_connection()
    if not conn:
        raise RuntimeError("No DB connection available")
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO leads (
                surname, name, sex, city, birthday,
                email, phone,
                event_name, event_distance, event_year,
                products, payment_system, transaction_id, order_id,
                promocode, discount, amount,
                is_name_suspicious, client_id, event_id,
                is_duplicate, status, is_new, is_new_event
            ) VALUES (
                %(surname)s, %(name)s, %(sex)s, %(city)s, %(birthday)s,
                %(email)s, %(phone)s,
                %(event_name)s, %(event_distance)s, %(event_year)s,
                %(products)s, %(payment_system)s, %(transaction_id)s, %(order_id)s,
                %(promocode)s, %(discount)s, %(amount)s,
                %(is_name_suspicious)s, %(client_id)s, %(event_id)s,
                %(is_duplicate)s, %(status)s, %(is_new)s, %(is_new_event)s
            )
            """,
            data,
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()
```

- [ ] **Step 2: Commit**

```bash
git add src/tracker/routers/webhook.py
git commit -m "feat: POST /webhook/tilda/{token} — приём webhook от Tilda"
```

---

### Task 4: Подключить роутер

**Files:**
- Modify: `src/tracker/router.py`

- [ ] **Step 1: Добавить webhook router в router.py**

В `src/tracker/router.py` изменить на:

```python
"""
Главный роутер трекера.
Подключает страницы и API-эндпоинты из подмодулей.
"""

from fastapi import APIRouter

from src.tracker.routers.pages import router as pages_router
from src.tracker.routers.api import router as api_router
from src.tracker.routers.webhook import router as webhook_router

router = APIRouter(prefix="", tags=["tracker"])
router.include_router(pages_router)
router.include_router(api_router)
router.include_router(webhook_router)
```

- [ ] **Step 2: Проверить что приложение стартует**

```bash
conda run -n base python -c "from src.tracker.router import router; print('OK', len(router.routes), 'routes')"
```

Ожидаемый результат: `OK N routes` (число больше 0, нет ошибок).

- [ ] **Step 3: Commit**

```bash
git add src/tracker/router.py
git commit -m "feat: подключить webhook router"
```

---

### Task 5: Проверить схему leads и deploy

**Files:**
- нет изменений кода

- [ ] **Step 1: Проверить что все нужные колонки есть в leads**

```bash
conda run -n base python tests/load/_check_db.py
```

Или напрямую через SSH:

```python
# tests/load/_check_leads_schema.py
import paramiko
c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("89.108.88.104", username="root", password="shsfzw5fHiQY8v6g", timeout=30)
_, o, _ = c.exec_command("mysql -u root krasmarafon -e \"DESCRIBE leads;\"", timeout=10)
print(o.read().decode())
c.close()
```

Запустить: `conda run -n base python tests/load/_check_leads_schema.py`

Убедиться что все колонки из INSERT присутствуют: surname, name, sex, city, birthday, email, phone, event_name, event_distance, event_year, products, payment_system, transaction_id, order_id, promocode, discount, amount, is_name_suspicious, client_id, event_id, is_duplicate, status, is_new, is_new_event.

Если какой-то колонки нет — добавить её через `ALTER TABLE leads ADD COLUMN ...` перед деплоем.

- [ ] **Step 2: Push и deploy на VPS**

```bash
git push origin Map
```

На VPS (через deploy-скрипт или SSH):
```bash
cd /opt/km_track && git pull && systemctl restart km_track
```

Или через paramiko:
```python
# tests/load/_restart.py (уже существует)
conda run -n base python tests/load/_restart.py
```

- [ ] **Step 3: Проверить что endpoint доступен**

```bash
curl -s -X POST https://analytics.krasmarafon.ru/webhook/tilda/WRONG_TOKEN \
  -H "Content-Type: application/json" \
  -d "{}" | python -m json.tool
```

Ожидаемый результат: `{"detail": "Invalid token"}`

```bash
TOKEN=$(grep TILDA_WEBHOOK_SECRET .env | cut -d= -f2)
curl -s -X POST https://analytics.krasmarafon.ru/webhook/tilda/$TOKEN \
  -H "Content-Type: application/json" \
  -d '{"surname":"Тест","name":"Webhook","sex":"мужской","city":"Красноярск","birthday":"01.01.1990","email":"test@test.ru","phone":"+7-900-000-0000","payment":"{\"sys\":\"test\",\"systranid\":\"999\",\"orderid\":\"888\",\"products\":[\"5 км Весна 2027 (test)=100\"],\"promocode\":\"\",\"discount\":\"0\",\"amount\":\"100\"}"}' \
  | python -m json.tool
```

Ожидаемый результат: `{"ok": true}`

- [ ] **Step 4: Обновить URL в Tilda**

В настройках Tilda → Webhook URL заменить:
```
https://webhook.nodul.ru/7841/dev/bf016984-03da-45ed-997f-162937dc4d73
```
на:
```
https://analytics.krasmarafon.ru/webhook/tilda/<TILDA_WEBHOOK_SECRET>
```

Сделать тестовую регистрацию через форму Tilda → убедиться что запись появилась в `leads`.

- [ ] **Step 5: Финальный commit**

```bash
git add .
git commit -m "test: webhook endpoint проверен, Tilda переключена"
```
