# Siberman: приём и проверка заявок (часть A) — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** заявки из формы Тильды (вебхук + разовый CSV) попадают в `siberman_entries`; директор в табе «Заявки»
админки `/admin/draw` ставит статусы ✅/❌/⌛️/🚫 и комментарий, выгружает Excel; публичный список
`/entries/{year}` для iframe на `siberman515.com/2029_applications`.

**Architecture:** новый модуль `src/siberman/entries/` (parser → db → service → router), миграция 018, свой
маленький спул на диске (по образцу вебхука Красмарафона, без правки его кода) + повтор в существующем
`_webhook_spool_replayer` в `app.py`. Админ-UI — отдельная вкладка в `templates/siberman/draw_admin.html` со своим
JS; публичная страница — свой шаблон/CSS/JS, высота iframe — `siberman-hall.js` (тот же `postMessage`, что у блоков
зала, сниппет Тильды тот же).

**Tech Stack:** FastAPI, mysql-connector (без ORM), openpyxl, vanilla JS, pytest, node (JS-тест).

Спека: `docs/superpowers/specs/2026-10-27-siberman-entries-design.md`.

**Соглашения проекта:** ответы и комментарии — по-русски; тесты — `conda run -n base python -m pytest …`
(или `C:/Users/podbo/miniconda3/python.exe -m pytest …`); код возврата pytest не терять в конвейере с `tail`
(lessons); PII из БД в вывод не печатать; прод — только с бэкапом и по одному шагу.

---

## Карта файлов

| Файл | Что |
|---|---|
| `src/siberman/migrations/018_entries.sql` | таблицы `siberman_entries`, `siberman_entries_audit` |
| `.github/workflows/migrate_siberman.yml` | + строка 018 |
| `src/config/settings.py`, `.env.example` | `SIBERMAN_WEBHOOK_SECRET` |
| `src/siberman/entries/__init__.py` | пусто |
| `src/siberman/entries/parser.py` | тело Тильды / строка CSV → поля заявки (чистые функции) |
| `src/siberman/entries/db.py` | SQL |
| `src/siberman/entries/spool.py` | спул вебхука на диске и повтор |
| `src/siberman/entries/service.py` | приём, админ-состояние, статусы, публичный список, Excel |
| `src/siberman/entries/router.py` | вебхук, админ-API, публичные страница и API |
| `src/krasmarafon/router.py` | подключить router |
| `app.py` | повтор спула заявок в `_webhook_spool_replayer`; префиксы в `_MAINTENANCE_ALLOWED_PREFIXES` |
| `templates/siberman/draw_admin.html` | вкладка «Заявки» |
| `static/js/siberman-draw-admin.js` | `switchTab` → загрузка вкладки «Заявки», открытие по `#entries` |
| `static/js/siberman-entries-search.js` | поиск по ФИ (общий для админки и публичной страницы) |
| `static/js/siberman-entries-admin.js` | вкладка «Заявки» |
| `templates/siberman/entries_public.html`, `static/css/siberman-entries.css`, `static/js/siberman-entries.js` | публичный список |
| `docs/siberman/entries-tilda-snippet.md` | HTML-блок для Тильды и настройка вебхука в форме |
| `tests/unit/test_siberman_entries_parser.py` | parser |
| `tests/integration/test_siberman_entries.py` | db/service/router/spool на локальной БД |
| `tests/js/test_siberman_entries_search.js` | поиск |

---

### Task 1: Миграция 018 и секрет вебхука

**Files:**
- Create: `src/siberman/migrations/018_entries.sql`
- Modify: `.github/workflows/migrate_siberman.yml` (после строки с `017_draw_contacts_texts.sql`)
- Modify: `src/config/settings.py:69` и список экспорта (строка с `"TILDA_WEBHOOK_SECRET",`)
- Modify: `.env.example`

- [ ] **Step 1: Миграция**

```sql
-- Заявки на Siberman из формы Тильды (вебхук + разовый CSV), статусы директора гонки (2026-10-27,
-- спека docs/superpowers/specs/2026-10-27-siberman-entries-design.md). Одна строка — одна заявка (tranid Тильды);
-- повторная доставка обновляет поля формы, статус и комментарий не трогает.
CREATE TABLE IF NOT EXISTS siberman_entries (
  id                INT AUTO_INCREMENT PRIMARY KEY,
  race_year         SMALLINT NOT NULL,
  tranid            VARCHAR(64) NOT NULL,
  formid            VARCHAR(64) NOT NULL DEFAULT '',
  submitted_at      DATETIME NOT NULL,
  format            ENUM('individual','relay') NOT NULL,
  surname           VARCHAR(100) NOT NULL,
  name              VARCHAR(100) NOT NULL,
  gender            ENUM('M','F') NULL,
  birthdate         DATE NULL,
  city              VARCHAR(150) NOT NULL DEFAULT '',
  email             VARCHAR(255) NOT NULL DEFAULT '',
  phone             VARCHAR(64) NOT NULL DEFAULT '',
  team_name         VARCHAR(150) NOT NULL DEFAULT '',
  relay_swim        VARCHAR(255) NOT NULL DEFAULT '',
  relay_bike        VARCHAR(255) NOT NULL DEFAULT '',
  relay_run         VARCHAR(255) NOT NULL DEFAULT '',
  wildcard_reason   TEXT NULL,
  results_text      TEXT NULL,
  result_url        VARCHAR(500) NOT NULL DEFAULT '',
  raw               JSON NULL,
  status            ENUM('review','admitted','rejected','withdrawn') NOT NULL DEFAULT 'review',
  comment           TEXT NULL,
  status_updated_at DATETIME NULL,
  status_by         VARCHAR(64) NOT NULL DEFAULT '',
  UNIQUE KEY uq_entries_tranid (tranid),
  KEY idx_entries_year_time (race_year, submitted_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS siberman_entries_audit (
  id          INT AUTO_INCREMENT PRIMARY KEY,
  entry_id    INT NOT NULL,
  action      ENUM('status','comment') NOT NULL,
  old_value   TEXT NULL,
  new_value   TEXT NULL,
  admin_user  VARCHAR(64) NOT NULL DEFAULT '',
  created_at  DATETIME NOT NULL,
  KEY idx_entries_audit_entry (entry_id),
  CONSTRAINT fk_entries_audit_entry FOREIGN KEY (entry_id) REFERENCES siberman_entries (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

- [ ] **Step 2: Workflow миграций** — после блока 017 добавить:

```yaml

            # Заявки на Siberman из формы Тильды и статусы директора
            mysql -u root siberman < /opt/km_track/src/siberman/migrations/018_entries.sql
```

- [ ] **Step 3: Настройка** — в `src/config/settings.py` под `TILDA_WEBHOOK_SECRET = …`:

```python
SIBERMAN_WEBHOOK_SECRET = os.getenv("SIBERMAN_WEBHOOK_SECRET", "")
```

и в список экспорта после `"TILDA_WEBHOOK_SECRET",` — `"SIBERMAN_WEBHOOK_SECRET",`. В `.env.example` строку
`SIBERMAN_WEBHOOK_SECRET=` (с комментарием «секрет в адресе вебхука заявок Siberman, длинная случайная строка»).

- [ ] **Step 4: Применить миграцию локально**

```bash
"C:/Users/podbo/miniconda3/python.exe" -c "
import sys, os; sys.path.insert(0, os.getcwd())
from dotenv import load_dotenv; load_dotenv('.env.local', override=True)
from src.siberman.db import get_siberman_connection
conn = get_siberman_connection(); cur = conn.cursor()
sql = open('src/siberman/migrations/018_entries.sql', encoding='utf-8').read()
for stmt in [s for s in '\n'.join(l for l in sql.splitlines() if not l.startswith('--')).split(';') if s.strip()]:
    cur.execute(stmt)
cur.execute(\"SHOW TABLES LIKE 'siberman_entries%'\"); print(cur.fetchall())"
```

Expected: `[('siberman_entries',), ('siberman_entries_audit',)]`.

- [ ] **Step 5: Commit**

```bash
git add src/siberman/migrations/018_entries.sql .github/workflows/migrate_siberman.yml src/config/settings.py .env.example
git commit -m "feat(siberman/entries): миграция 018 — заявки и журнал статусов; секрет вебхука"
```

---

### Task 2: Parser — тело Тильды / CSV → заявка

**Files:**
- Create: `src/siberman/entries/__init__.py` (пустой), `src/siberman/entries/parser.py`
- Test: `tests/unit/test_siberman_entries_parser.py`

- [ ] **Step 1: Тест**

```python
import datetime

import pytest

from src.siberman.entries.parser import BadEntry, is_test_ping, parse_csv, parse_entry

TODAY = datetime.date(2026, 10, 27)
IND = {"tranid": "123:456", "formid": "form1", "format": "Индивидуальное участие", "surname": " Иванов ",
       "Name": "Иван", "sex": "Мужской", "birthday": "05.03.1985", "city": "Красноярск", "Email": "i@ex.ru",
       "Phone": "+7 900 000-00-00", "wildcard_reason": "", "Расскажите_о_ваших_результатах": "Финишер 2019",
       "result_url": "https://ex.ru/r", "tattoo": "да"}


def test_individual_fields():
    e = parse_entry(IND, TODAY)
    assert (e["tranid"], e["format"], e["surname"], e["name"], e["gender"]) == ("123:456", "individual", "Иванов", "Иван", "M")
    assert e["birthdate"] == datetime.date(1985, 3, 5) and e["city"] == "Красноярск"
    assert (e["email"], e["phone"], e["results_text"], e["result_url"]) == ("i@ex.ru", "+7 900 000-00-00", "Финишер 2019", "https://ex.ru/r")
    assert e["relay_swim"] == "" and e["raw"]["tattoo"] == "да"          # всё тело — в raw (для части B)


def test_relay_team_and_no_gender():
    e = parse_entry({**IND, "format": "Эстафетная команда", "sex": "", "team_name": "Столбы",
                     "surname_swim": "Пловцов", "name_swim": "Пётр", "surname_bike": "Велов", "name_bike": "Вася",
                     "surname_run": "", "name_run": ""}, TODAY)
    assert (e["format"], e["gender"], e["team_name"]) == ("relay", None, "Столбы")
    assert (e["relay_swim"], e["relay_bike"], e["relay_run"]) == ("Пловцов Пётр", "Велов Вася", "")


def test_bad_birthday_is_none_not_error():
    assert parse_entry({**IND, "birthday": "31.02.1985"}, TODAY)["birthdate"] is None


@pytest.mark.parametrize("patch", [{"tranid": ""}, {"format": "Непонятно"}, {"surname": ""}, {"Name": " "}])
def test_not_an_entry(patch):
    with pytest.raises(BadEntry):
        parse_entry({**IND, **patch}, TODAY)


def test_test_ping():
    assert is_test_ping({"test": "test"}) and not is_test_ping(IND)


def test_csv_utf8_and_cp1251_with_dates():
    head = "surname;Name;Email;Phone;Date;format;sex;birthday;city;tranid"
    rows = ["Иванов;Иван;i@ex.ru;1;2026-11-01 10:00:00;Индивидуальное участие;Мужской;05.03.1985;Красноярск;1:1",
            "Петрова;Анна;p@ex.ru;2;2026-11-02 11:00:00;Индивидуальное участие;Женский;;Москва;1:2",
            "Кривой;Формат;k@ex.ru;3;2026-11-02 12:00:00;Что-то;Мужской;;Омск;1:3"]
    for enc in ("utf-8-sig", "cp1251"):
        entries, errors = parse_csv("\n".join([head, *rows]).encode(enc), TODAY)
        assert [(e["surname"], at) for e, at in entries] == [
            ("Иванов", datetime.datetime(2026, 11, 1, 10)), ("Петрова", datetime.datetime(2026, 11, 2, 11))]
        assert len(errors) == 1 and errors[0].startswith("строка 4")


def test_csv_not_tilda():
    with pytest.raises(BadEntry, match="tranid"):
        parse_csv(b"a;b\n1;2", TODAY)
```

- [ ] **Step 2: Запуск — FAIL** (`ModuleNotFoundError: src.siberman.entries`)

Run: `"C:/Users/podbo/miniconda3/python.exe" -m pytest tests/unit/test_siberman_entries_parser.py -q`

- [ ] **Step 3: Реализация** `src/siberman/entries/parser.py`

```python
"""
Заявка на Siberman из формы Тильды: тело вебхука или строка CSV-выгрузки (имена полей одинаковые) → поля
siberman_entries. Не заявка (нет tranid / ФИ / непонятный формат) — BadEntry: повтор не поможет.
"""
import csv
import datetime
import io
from typing import Optional

from src.siberman.persons.applicants import parse_birthdate

STAGES = ("swim", "bike", "run")
RESULTS_FIELD = "Расскажите_о_ваших_результатах"


class BadEntry(ValueError):
    """Тело не превращается в заявку."""


def _clean(v) -> str:
    return " ".join(str(v if v is not None else "").split())


def _text(v) -> str:
    return str(v if v is not None else "").strip()


def format_of(raw: str) -> Optional[str]:
    if raw.startswith("Индивид"):
        return "individual"
    if raw.startswith("Эстафет"):
        return "relay"
    return None


def is_test_ping(body: dict) -> bool:
    """Тильда при подключении вебхука шлёт test=test."""
    return _clean(body.get("test")) == "test"


def parse_entry(body: dict, today: datetime.date) -> dict:
    tranid = _clean(body.get("tranid"))
    if not tranid:
        raise BadEntry("нет tranid")
    fmt = format_of(_clean(body.get("format")))
    if fmt is None:
        raise BadEntry(f"формат «{_clean(body.get('format'))}»")
    surname, name = _clean(body.get("surname")), _clean(body.get("Name") or body.get("name"))
    if not surname or not name:
        raise BadEntry("нет фамилии или имени")
    relay = {f"relay_{s}": _clean(f"{_clean(body.get('surname_' + s))} {_clean(body.get('name_' + s))}")
             if fmt == "relay" else "" for s in STAGES}
    return {
        "tranid": tranid[:64], "formid": _clean(body.get("formid"))[:64], "format": fmt,
        "surname": surname[:100], "name": name[:100],
        "gender": {"Мужской": "M", "Женский": "F"}.get(_clean(body.get("sex"))) if fmt == "individual" else None,
        "birthdate": parse_birthdate(_clean(body.get("birthday")), today),
        "city": _clean(body.get("city"))[:150],
        "email": _clean(body.get("Email") or body.get("email"))[:255],
        "phone": _clean(body.get("Phone") or body.get("phone"))[:64],
        "team_name": _clean(body.get("team_name"))[:150], **relay,
        "wildcard_reason": _text(body.get("wildcard_reason")), "results_text": _text(body.get(RESULTS_FIELD)),
        "result_url": _clean(body.get("result_url"))[:500],
        "raw": {k: v for k, v in body.items() if isinstance(v, (str, int, float, list))},
    }


def _decode(data: bytes) -> str:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = data.decode("cp1251", errors="replace")
    return text.lstrip(chr(0xFEFF))


def parse_csv(data: bytes, today: datetime.date) -> tuple[list[tuple[dict, Optional[datetime.datetime]]], list[str]]:
    """CSV-выгрузка заявок Тильды («;») → ([(заявка, время подачи из Date)], ошибки по строкам)."""
    reader = csv.DictReader(io.StringIO(_decode(data), newline=""), delimiter=";")
    if not reader.fieldnames or "tranid" not in reader.fieldnames:
        raise BadEntry("это не выгрузка заявок Тильды: нет колонки tranid")
    entries, errors = [], []
    for n, row in enumerate(reader, start=2):
        try:
            e = parse_entry(row, today)
        except BadEntry as err:
            errors.append(f"строка {n}: {err}")
            continue
        try:
            at = datetime.datetime.strptime(_clean(row.get("Date")), "%Y-%m-%d %H:%M:%S")
        except ValueError:
            at = None
        entries.append((e, at))
    return entries, errors
```

- [ ] **Step 4: Запуск — PASS** (тот же Run)

- [ ] **Step 5: Commit**

```bash
git add src/siberman/entries/__init__.py src/siberman/entries/parser.py tests/unit/test_siberman_entries_parser.py
git commit -m "feat(siberman/entries): разбор заявки Тильды (вебхук и CSV)"
```

---

### Task 3: db + service (приём, статусы, списки, Excel)

**Files:**
- Create: `src/siberman/entries/db.py`, `src/siberman/entries/service.py`
- Test: `tests/integration/test_siberman_entries.py`

- [ ] **Step 1: Тест** (локальная БД; год 2090–2099 от PID, чистится до и после — как `test_siberman_draw.py`)

```python
"""
Заявки Siberman на локальной БД siberman: приём (вебхук/CSV/спул), статусы с журналом, публичный список без
контактов, Excel, маршруты. Год 2090–2099 (от PID), чистится до и после.
"""
import datetime
import io
import os

import openpyxl
import pytest

from app import app
from src.config import settings
from src.core.auth import api_require_auth
from src.siberman.db import get_siberman_connection
from src.siberman.entries import service, spool
from src.siberman.entries.service import EntryError

YEAR = 2090 + os.getpid() % 10
SIBERMAN = {"host": "siberman.localhost"}
T0 = datetime.datetime(2026, 11, 1, 10, 0)


def body(tranid, surname, name="Тест", fmt="Индивидуальное участие", sex="Мужской", **extra):
    return {"tranid": tranid, "formid": "f", "format": fmt, "surname": surname, "Name": name, "sex": sex,
            "birthday": "05.03.1985", "city": "Красноярск", "Email": f"{tranid}@ex.ru", "Phone": "+7 900", **extra}


def _clean():
    conn = get_siberman_connection()
    conn.cursor().execute("DELETE FROM siberman_entries WHERE race_year=%s", (YEAR,))
    conn.close()


@pytest.fixture
def entries():
    conn = get_siberman_connection()
    if conn is None:
        pytest.skip("Нет локальной БД siberman")
    cur = conn.cursor()
    cur.execute("SHOW TABLES LIKE 'siberman_entries'")
    if not cur.fetchone():
        conn.close()
        pytest.skip("Миграция 018 не применена")
    conn.close()
    _clean()
    service.clear_cache()
    service.ingest(YEAR, body(f"{YEAR}:1", "Яковлев"), T0)
    service.ingest(YEAR, body(f"{YEAR}:2", "Ёлкина", sex="Женский"), T0 + datetime.timedelta(minutes=5))
    service.ingest(YEAR, body(f"{YEAR}:3", "Абрамов", fmt="Эстафетная команда", sex="", team_name="Столбы"),
                   T0 + datetime.timedelta(minutes=10))
    yield {e["surname"]: e["id"] for e in service.admin_list(YEAR)["entries"]}
    _clean()
    service.clear_cache()


def test_admin_list_in_arrival_order_with_review_status(entries):
    s = service.admin_list(YEAR)
    assert [(e["n"], e["surname"], e["status"]) for e in s["entries"]] == [
        (1, "Яковлев", "review"), (2, "Ёлкина", "review"), (3, "Абрамов", "review")]
    assert s["counts"] == {"total": 3, "review": 3, "admitted": 0, "rejected": 0, "withdrawn": 0}
    assert YEAR in s["years"] and s["entries"][0]["email"] == f"{YEAR}:1@ex.ru"


def test_redelivery_updates_form_fields_but_keeps_status(entries):
    service.set_status(YEAR, entries["Яковлев"], "admitted", "director")
    service.set_comment(YEAR, entries["Яковлев"], "проверил", "director")
    assert service.ingest(YEAR, body(f"{YEAR}:1", "Яковлев", city="Омск"), T0 + datetime.timedelta(days=1)) is False
    e = service.admin_list(YEAR)["entries"][0]
    assert (e["city"], e["status"], e["comment"], e["submitted_at"]) == ("Омск", "admitted", "проверил", T0)
    card = service.entry_card(YEAR, entries["Яковлев"])
    assert [(a["action"], a["old_value"], a["new_value"], a["admin_user"]) for a in card["audit"]] == [
        ("status", "review", "admitted", "director"), ("comment", "", "проверил", "director")]


def test_status_errors(entries):
    with pytest.raises(EntryError, match="нет такого статуса"):
        service.set_status(YEAR, entries["Яковлев"], "maybe", "u")
    with pytest.raises(EntryError, match="нет такой заявки"):
        service.set_status(YEAR + 1, entries["Яковлев"], "admitted", "u")     # чужой год


def test_public_list_alphabetical_without_contacts(entries):
    service.set_status(YEAR, entries["Абрамов"], "withdrawn", "u")
    service.clear_cache()
    p = service.public_list(YEAR)
    assert (p["total"], p["admitted"]) == (3, 0)
    assert p["entries"] == [{"n": 1, "fio": "Абрамов Тест", "format": "Эстафетная команда", "status": "withdrawn"},
                            {"n": 2, "fio": "Ёлкина Тест", "format": "Индивидуальное участие", "status": "review"},
                            {"n": 3, "fio": "Яковлев Тест", "format": "Индивидуальное участие", "status": "review"}]
    assert "@ex.ru" not in str(p) and "1985" not in str(p)


def test_csv_import_adds_new_and_skips_known(entries):
    head = "surname;Name;Email;Phone;Date;format;sex;birthday;city;tranid"
    data = "\n".join([head, f"Яковлев;Тест;x@ex.ru;1;2026-10-30 09:00:00;Индивидуальное участие;Мужской;;Красноярск;{YEAR}:1",
                      f"Новенький;Тест;n@ex.ru;2;2026-10-31 09:00:00;Индивидуальное участие;Мужской;;Омск;{YEAR}:9",
                      "Кривой;Тест;k@ex.ru;3;2026-10-31 09:00:00;Что-то;Мужской;;Омск;x"]).encode("utf-8")
    r = service.import_csv(YEAR, data)
    assert (r["rows"], r["new"], r["known"], len(r["errors"])) == (3, 1, 1, 1)
    assert service.admin_list(YEAR)["entries"][0]["surname"] == "Новенький"     # по Date из CSV — раньше всех


def test_export_xlsx(entries):
    service.set_comment(YEAR, entries["Ёлкина"], "уточнить ДР", "u")
    ws = openpyxl.load_workbook(io.BytesIO(service.export_xlsx(YEAR))).active
    rows = [[c.value for c in r] for r in ws.iter_rows()]
    assert rows[0][:4] == ["№", "Дата заявки", "Фамилия Имя", "Формат участия"]
    assert [r[2] for r in rows[1:]] == ["Яковлев Тест", "Ёлкина Тест", "Абрамов Тест"]
    assert "уточнить ДР" in rows[2] and "⌛️ на изучении" in rows[1]
```

- [ ] **Step 2: Запуск — FAIL** (`ImportError: service`)

Run: `"C:/Users/podbo/miniconda3/python.exe" -m pytest tests/integration/test_siberman_entries.py -q`

- [ ] **Step 3: `src/siberman/entries/db.py`**

```python
"""Слой БД заявок Siberman — siberman_entries, siberman_entries_audit (миграция 018_entries.sql)."""
import json
from typing import Optional

FORM_FIELDS = ("formid", "format", "surname", "name", "gender", "birthdate", "city", "email", "phone", "team_name",
               "relay_swim", "relay_bike", "relay_run", "wildcard_reason", "results_text", "result_url")
LIST_FIELDS = ("id", "race_year", "tranid", "submitted_at", *FORM_FIELDS, "status", "comment",
               "status_updated_at", "status_by")


def upsert(conn, year: int, e: dict, submitted_at) -> bool:
    """True — новая заявка. Повтор того же tranid обновляет поля формы и raw; год, время подачи, статус и
    комментарий не трогает."""
    cols = ", ".join(FORM_FIELDS)
    cur = conn.cursor()
    cur.execute(
        f"INSERT INTO siberman_entries (race_year, tranid, submitted_at, raw, {cols}) "
        f"VALUES (%s, %s, %s, %s, {', '.join(['%s'] * len(FORM_FIELDS))}) "
        f"ON DUPLICATE KEY UPDATE {', '.join(f'{c}=VALUES({c})' for c in FORM_FIELDS)}, raw=VALUES(raw)",
        (year, e["tranid"], submitted_at, json.dumps(e["raw"], ensure_ascii=False), *[e[c] for c in FORM_FIELDS]))
    return cur.rowcount == 1          # MySQL: 1 — вставка, 2 — обновление, 0 — без изменений


def known_tranids(conn, tranids: list) -> set:
    if not tranids:
        return set()
    cur = conn.cursor()
    cur.execute(f"SELECT tranid FROM siberman_entries WHERE tranid IN ({', '.join(['%s'] * len(tranids))})", tranids)
    return {r[0] for r in cur.fetchall()}


def list_year(conn, year: int) -> list[dict]:
    cur = conn.cursor(dictionary=True)
    cur.execute(f"SELECT {', '.join(LIST_FIELDS)} FROM siberman_entries WHERE race_year=%s ORDER BY submitted_at, id",
                (year,))
    return cur.fetchall()


def get(conn, entry_id: int) -> Optional[dict]:
    cur = conn.cursor(dictionary=True)
    cur.execute(f"SELECT {', '.join(LIST_FIELDS)} FROM siberman_entries WHERE id=%s", (entry_id,))
    return cur.fetchone()


def years(conn) -> list[int]:
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT race_year FROM siberman_entries ORDER BY race_year")
    return [r[0] for r in cur.fetchall()]


def update(conn, entry_id: int, field: str, old: str, new: str, user: str) -> None:
    """status или comment + запись в журнал — одной транзакцией."""
    assert field in ("status", "comment")
    conn.start_transaction()
    try:
        cur = conn.cursor()
        if field == "status":
            cur.execute("UPDATE siberman_entries SET status=%s, status_updated_at=NOW(), status_by=%s WHERE id=%s",
                        (new, user[:64], entry_id))
        else:
            cur.execute("UPDATE siberman_entries SET comment=%s WHERE id=%s", (new, entry_id))
        cur.execute("INSERT INTO siberman_entries_audit (entry_id, action, old_value, new_value, admin_user, created_at) "
                    "VALUES (%s, %s, %s, %s, %s, NOW())", (entry_id, field, old, new, user[:64]))
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def audit(conn, entry_id: int) -> list[dict]:
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT action, old_value, new_value, admin_user, created_at FROM siberman_entries_audit "
                "WHERE entry_id=%s ORDER BY id", (entry_id,))
    return cur.fetchall()


def public_rows(conn, year: int) -> list[dict]:
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT id, surname, name, format, status FROM siberman_entries WHERE race_year=%s", (year,))
    return cur.fetchall()
```

- [ ] **Step 4: `src/siberman/entries/service.py`**

```python
"""
Заявки Siberman: приём (вебхук Тильды, спул, CSV), вкладка «Заявки» админки (статусы, комментарий, журнал,
Excel) и публичный список для iframe в Тильде (только ФИ, формат, статус).
"""
import datetime
import io
import threading
import time
from zoneinfo import ZoneInfo

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

from src.config import settings
from src.siberman.db import get_siberman_connection
from src.siberman.entries import db as edb
from src.siberman.entries.parser import BadEntry, is_test_ping, parse_csv, parse_entry

KRS = ZoneInfo("Asia/Krasnoyarsk")
STATUSES = ("review", "admitted", "rejected", "withdrawn")
STATUS_LABELS = {"review": "⌛️ на изучении", "admitted": "✅ допущена", "rejected": "❌ не соответствует",
                 "withdrawn": "🚫 отказ от жеребьёвки"}
FORMAT_LABELS = {"individual": "Индивидуальное участие", "relay": "Эстафетная команда"}
PUBLIC_TTL_S = 5.0
_public_cache: dict = {}
_lock = threading.Lock()


class EntryError(Exception):
    """Ошибка, которую директор видит как есть (409)."""


class EntriesUnavailable(EntryError):
    """БД недоступна (503)."""


def clear_cache() -> None:
    with _lock:
        _public_cache.clear()


def _connect():
    conn = get_siberman_connection()
    if conn is None:
        raise EntriesUnavailable("база данных временно недоступна")
    return conn


def now_krs() -> datetime.datetime:
    return datetime.datetime.now(KRS).replace(tzinfo=None, microsecond=0)


def _fio(e: dict) -> str:
    return f"{e['surname']} {e['name']}".strip()


def _norm(s: str) -> str:
    return (s or "").lower().replace("ё", "е")


# ── Приём ───────────────────────────────────────────────────────────────────

def ingest(year: int, body: dict, received_at: datetime.datetime):
    """Тело вебхука → заявка. None — тестовый запрос Тильды; True/False — новая / уже была.
    BadEntry — не заявка (в failed/), прочие исключения — сбой БД (повтор из спула)."""
    if is_test_ping(body):
        return None
    e = parse_entry(body, received_at.date())
    conn = _connect()
    try:
        new = edb.upsert(conn, year, e, received_at)
    finally:
        conn.close()
    clear_cache()
    return new


def import_csv(year: int, data: bytes) -> dict:
    """Разовая загрузка выгрузки Тильды: новые добавляются (время — Date из CSV), известные обновляют поля формы."""
    try:
        rows, errors = parse_csv(data, datetime.date.today())
    except BadEntry as e:
        raise EntryError(str(e)) from None
    conn = _connect()
    try:
        known = edb.known_tranids(conn, [e["tranid"] for e, _ in rows])
        for e, at in rows:
            edb.upsert(conn, year, e, at or now_krs())
    finally:
        conn.close()
    clear_cache()
    return {"rows": len(rows) + len(errors), "new": sum(1 for e, _ in rows if e["tranid"] not in known),
            "known": sum(1 for e, _ in rows if e["tranid"] in known), "errors": errors}


# ── Админка ─────────────────────────────────────────────────────────────────

def webhook_path(year: int):
    secret = settings.SIBERMAN_WEBHOOK_SECRET
    return f"/webhook/siberman/{secret}/{year}" if secret else None


def admin_list(year: int) -> dict:
    conn = _connect()
    try:
        rows, years = edb.list_year(conn, year), edb.years(conn)
    finally:
        conn.close()
    counts = {"total": len(rows), **{s: sum(1 for r in rows if r["status"] == s) for s in STATUSES}}
    for n, r in enumerate(rows, start=1):
        r["n"], r["comment"] = n, r["comment"] or ""
    return {"year": year, "entries": rows, "counts": counts, "years": sorted(set(years) | {year}),
            "webhook_path": webhook_path(year)}


def _entry(conn, year: int, entry_id: int) -> dict:
    e = edb.get(conn, entry_id)
    if e is None or e["race_year"] != year:
        raise EntryError("нет такой заявки")
    return e


def entry_card(year: int, entry_id: int) -> dict:
    conn = _connect()
    try:
        e = _entry(conn, year, entry_id)
        e["audit"] = edb.audit(conn, entry_id)
    finally:
        conn.close()
    return e


def set_status(year: int, entry_id: int, status: str, user: str) -> dict:
    if status not in STATUSES:
        raise EntryError("нет такого статуса")
    conn = _connect()
    try:
        e = _entry(conn, year, entry_id)
        if e["status"] != status:
            edb.update(conn, entry_id, "status", e["status"], status, user)
    finally:
        conn.close()
    clear_cache()
    return {"ok": True}


def set_comment(year: int, entry_id: int, comment: str, user: str) -> dict:
    comment = (comment or "").strip()[:2000]
    conn = _connect()
    try:
        e = _entry(conn, year, entry_id)
        if (e["comment"] or "") != comment:
            edb.update(conn, entry_id, "comment", e["comment"] or "", comment, user)
    finally:
        conn.close()
    return {"ok": True}


EXPORT_COLUMNS = (("n", "№", 5), ("submitted_at", "Дата заявки", 18), ("fio", "Фамилия Имя", 28),
                  ("format", "Формат участия", 22), ("gender", "Пол", 6), ("birthdate", "Дата рождения", 13),
                  ("city", "Город", 18), ("email", "E-mail", 28), ("phone", "Телефон", 18),
                  ("status", "Статус", 22), ("comment", "Комментарий", 30), ("team_name", "Команда", 20),
                  ("relay_swim", "Плавание", 22), ("relay_bike", "Велосипед", 22), ("relay_run", "Бег", 22),
                  ("wildcard_reason", "Почему wild card", 30), ("results_text", "О результатах", 30),
                  ("result_url", "Ссылка на результаты", 30))


def export_xlsx(year: int) -> bytes:
    rows = admin_list(year)["entries"]
    wb = Workbook()
    ws = wb.active
    ws.title = f"Заявки {year}"
    ws.append([t for _, t, _ in EXPORT_COLUMNS])
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for r in rows:
        v = {**r, "fio": _fio(r), "format": FORMAT_LABELS[r["format"]], "status": STATUS_LABELS[r["status"]],
             "gender": {"M": "М", "F": "Ж"}.get(r["gender"], "")}
        ws.append([v.get(k) if v.get(k) is not None else "" for k, _, _ in EXPORT_COLUMNS])
    for i, (key, _, width) in enumerate(EXPORT_COLUMNS, start=1):
        ws.column_dimensions[get_column_letter(i)].width = width
        fmt = {"submitted_at": "DD.MM.YYYY HH:MM", "birthdate": "DD.MM.YYYY"}.get(key)
        if fmt:
            for (cell,) in ws.iter_rows(min_row=2, min_col=i, max_col=i):
                cell.number_format = fmt
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ── Публичный список ────────────────────────────────────────────────────────

def public_list(year: int) -> dict:
    """По алфавиту (фамилия, имя; ё = е); только ФИ, формат, статус. Кэш воркера на PUBLIC_TTL_S."""
    with _lock:
        hit = _public_cache.get(year)
        if hit and time.monotonic() - hit[0] < PUBLIC_TTL_S:
            return hit[1]
    conn = _connect()
    try:
        rows = edb.public_rows(conn, year)
    finally:
        conn.close()
    rows.sort(key=lambda r: (_norm(r["surname"]), _norm(r["name"]), r["id"]))
    data = {"year": year, "total": len(rows), "admitted": sum(1 for r in rows if r["status"] == "admitted"),
            "entries": [{"n": n, "fio": _fio(r), "format": FORMAT_LABELS[r["format"]], "status": r["status"]}
                        for n, r in enumerate(rows, start=1)]}
    with _lock:
        _public_cache[year] = (time.monotonic(), data)
    return data
```

- [ ] **Step 5: Запуск — PASS** (тот же Run). Затем unit-набор: `"C:/Users/podbo/miniconda3/python.exe" -m pytest tests/unit/ -q` — без падений.

- [ ] **Step 6: Commit**

```bash
git add src/siberman/entries/db.py src/siberman/entries/service.py tests/integration/test_siberman_entries.py
git commit -m "feat(siberman/entries): приём, статусы с журналом, публичный список и Excel"
```

---

### Task 4: Спул вебхука и повтор

**Files:**
- Create: `src/siberman/entries/spool.py`
- Modify: `app.py` (`_webhook_spool_replayer`, ~строки 328–353)
- Test: `tests/integration/test_siberman_entries.py` (дописать)

- [ ] **Step 1: Тест** (дописать в конец файла)

```python
def test_spool_replay_saves_entry_and_moves_bad_to_failed(entries, tmp_path, monkeypatch):
    monkeypatch.setattr(spool, "SPOOL_DIR", tmp_path)
    good = spool.save(body(f"{YEAR}:7", "Повторный"), YEAR, T0)
    bad = spool.save({"tranid": f"{YEAR}:8", "format": "???"}, YEAR, T0)
    assert spool.replay(service.ingest, min_age_s=0) == {"replayed": 1, "failed": 0, "bad": 1, "oldest_failed_age_s": 0}
    assert not good.exists() and (tmp_path / "failed" / bad.name).exists()
    assert "Повторный" in [e["surname"] for e in service.admin_list(YEAR)["entries"]]


def test_spool_keeps_file_when_db_fails(entries, tmp_path, monkeypatch):
    monkeypatch.setattr(spool, "SPOOL_DIR", tmp_path)
    path = spool.save(body(f"{YEAR}:7", "Повторный"), YEAR, T0)

    def broken(*a):
        raise RuntimeError("БД упала")
    done = spool.replay(broken, min_age_s=0)
    assert (done["replayed"], done["failed"]) == (0, 1) and path.exists()
```

- [ ] **Step 2: Запуск — FAIL** (`AttributeError: module … has no attribute 'save'`)

Run: `"C:/Users/podbo/miniconda3/python.exe" -m pytest tests/integration/test_siberman_entries.py -q -k spool`

- [ ] **Step 3: `src/siberman/entries/spool.py`**

```python
"""
Спул вебхука заявок Siberman (как у Красмарафона, src/krasmarafon/routers/webhook.py): разобранное тело
пишется на диск до записи в БД; сбой БД — файл остаётся, лидер-воркер повторяет его каждые 5 минут
(app.py, _webhook_spool_replayer). Тело, которое не превращается в заявку, — в failed/ (разбор вручную).
"""
import datetime
import json
import logging
import os
import time
import uuid
from pathlib import Path

from src.siberman.entries.parser import BadEntry

_log = logging.getLogger(__name__)
SPOOL_DIR = Path(os.environ.get("SIBERMAN_SPOOL_DIR") or
                 Path(__file__).resolve().parents[3] / "var" / "webhook_spool" / "siberman")
REPLAY_MIN_AGE_S = 120


def save(body: dict, year: int, received_at: datetime.datetime) -> Path:
    SPOOL_DIR.mkdir(parents=True, exist_ok=True)
    path = SPOOL_DIR / f"{received_at:%Y%m%dT%H%M%S}_{uuid.uuid4().hex[:8]}.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"year": year, "received_at": received_at.isoformat(), "body": body},
                              ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)
    return path


def done(path: Path) -> None:
    path.unlink(missing_ok=True)


def fail(path: Path) -> None:
    failed = SPOOL_DIR / "failed"
    failed.mkdir(parents=True, exist_ok=True)
    path.replace(failed / path.name)


def replay(process, min_age_s: int = REPLAY_MIN_AGE_S) -> dict:
    """process(year, body, received_at) — service.ingest."""
    out = {"replayed": 0, "failed": 0, "bad": 0, "oldest_failed_age_s": 0}
    if not SPOOL_DIR.exists():
        return out
    now = time.time()
    for path in sorted(SPOOL_DIR.glob("*.json")):
        age = now - path.stat().st_mtime
        if age < min_age_s:
            continue
        try:
            rec = json.loads(path.read_text(encoding="utf-8"))
            process(rec["year"], rec["body"], datetime.datetime.fromisoformat(rec["received_at"]))
            done(path)
            out["replayed"] += 1
        except BadEntry as e:
            fail(path)
            out["bad"] += 1
            _log.error(f"siberman entries: {path.name} не заявка — в failed/: {e}")
        except Exception as e:
            out["failed"] += 1
            out["oldest_failed_age_s"] = max(out["oldest_failed_age_s"], int(age))
            _log.error(f"siberman entries: повтор {path.name} не удался: {e}")
    return out
```

- [ ] **Step 4: Повтор в `app.py`** — в `_webhook_spool_replayer` сразу после
`done = await asyncio.get_event_loop().run_in_executor(None, replay_spool)`:

```python
                from src.siberman.entries import service as entries_service, spool as entries_spool
                sib = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: entries_spool.replay(entries_service.ingest))
                if sib["replayed"] or sib["failed"] or sib["bad"]:
                    settings.logger.info(f"[webhook] спул заявок Siberman: {sib}")
                done["failed"] += sib["failed"]
                done["bad"] = done.get("bad", 0) + sib["bad"]
                done["oldest_failed_age_s"] = max(done["oldest_failed_age_s"], sib["oldest_failed_age_s"])
```

(дальше существующий код уже шлёт ntfy, если застряло > 30 мин или есть `bad`.)

- [ ] **Step 5: Запуск — PASS** (тот же Run), затем `-m pytest tests/unit/ -q`.

- [ ] **Step 6: Commit**

```bash
git add src/siberman/entries/spool.py app.py tests/integration/test_siberman_entries.py
git commit -m "feat(siberman/entries): спул вебхука заявок и повтор лидер-воркером"
```

---

### Task 5: Router — вебхук, админ-API, публичный API и страница

**Files:**
- Create: `src/siberman/entries/router.py`
- Modify: `src/krasmarafon/router.py` (после `siberman_hall_router`), `app.py` (`_MAINTENANCE_ALLOWED_PREFIXES`)
- Create: `templates/siberman/entries_public.html` (заглушка-разметка; стили/JS — Task 7)
- Test: `tests/integration/test_siberman_entries.py` (дописать)

- [ ] **Step 1: Тест**

```python
def test_webhook_secret_ping_and_entry(entries, client, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "SIBERMAN_WEBHOOK_SECRET", "s3cret")
    monkeypatch.setattr(spool, "SPOOL_DIR", tmp_path)
    url = f"/webhook/siberman/s3cret/{YEAR}"
    assert client.post(f"/webhook/siberman/wrong/{YEAR}", data={"test": "test"}).status_code == 403
    assert client.post("/webhook/siberman/s3cret/1999", data={"test": "test"}).status_code == 404
    r = client.post(url, data={"test": "test"})
    assert r.status_code == 200 and r.text == "ok"
    assert client.post(url, data=body(f"{YEAR}:5", "Вебхуков")).status_code == 200
    assert client.post(url, data={"tranid": f"{YEAR}:6", "format": "???"}).status_code == 200   # не заявка — 200, в failed/
    assert "Вебхуков" in [e["surname"] for e in service.admin_list(YEAR)["entries"]]
    assert not list(tmp_path.glob("*.json")) and len(list((tmp_path / "failed").glob("*.json"))) == 1


def test_admin_api_requires_auth_and_works(entries, client):
    base = f"/api/siberman/admin/entries/{YEAR}"
    assert client.get(base).status_code == 401
    app.dependency_overrides[api_require_auth] = lambda: "director"
    try:
        assert client.get(base).json()["counts"]["total"] == 3
        eid = entries["Ёлкина"]
        assert client.post(f"{base}/{eid}/status", json={"status": "rejected"}).status_code == 200
        assert client.post(f"{base}/{eid}/status", json={"status": "maybe"}).status_code == 409
        assert client.post(f"{base}/{eid}/comment", json={"comment": "нет ДР"}).status_code == 200
        card = client.get(f"{base}/{eid}").json()
        assert card["status"] == "rejected" and card["comment"] == "нет ДР" and len(card["audit"]) == 2
        assert client.get(f"{base}/999999999").status_code == 409
        x = client.get(f"{base}/export.xlsx")
        assert x.status_code == 200 and x.headers["content-type"].startswith("application/vnd.openxml")
        up = client.post(f"{base}/import", files={"file": ("a.csv", b"a;b\n1;2", "text/csv")})
        assert up.status_code == 409 and "tranid" in up.json()["detail"]
    finally:
        app.dependency_overrides.pop(api_require_auth, None)


def test_public_api_and_page(entries, client):
    service.clear_cache()
    data = client.get(f"/api/siberman/entries/{YEAR}").json()
    assert data["total"] == 3 and set(data["entries"][0]) == {"n", "fio", "format", "status"}
    assert client.get(f"/entries/{YEAR}", headers=SIBERMAN).status_code == 200
    assert client.get(f"/entries/{YEAR}").status_code == 404                  # только домен Siberman
    assert client.get("/api/siberman/entries/1999").status_code == 404
```

- [ ] **Step 2: Запуск — FAIL** (404 на маршрутах)

Run: `"C:/Users/podbo/miniconda3/python.exe" -m pytest tests/integration/test_siberman_entries.py -q`

- [ ] **Step 3: `src/siberman/entries/router.py`**

```python
"""
Заявки Siberman: вебхук Тильды (POST /webhook/siberman/{секрет}/{год}), API вкладки «Заявки» админки
(/api/siberman/admin/entries/{год}/…) и публичный список для iframe (/entries/{год}, /api/siberman/entries/{год}).
"""
import datetime
import hmac
import logging

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, Response
from pydantic import BaseModel

from src.common import ntfy
from src.config import settings
from src.core.auth import api_require_auth
from src.krasmarafon.routers.webhook import parse_body
from src.siberman.entries import service, spool
from src.siberman.entries.parser import BadEntry, is_test_ping
from src.siberman.entries.service import EntriesUnavailable, EntryError
from src.siberman.router import templates

router = APIRouter(tags=["Siberman entries"])
_log = logging.getLogger(__name__)
YEARS = range(2020, 2101)
NO_STORE = {"Cache-Control": "no-store"}
MAX_CSV_BYTES = 5 * 1024 * 1024
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class StatusIn(BaseModel):
    status: str


class CommentIn(BaseModel):
    comment: str = ""


def _check_year(year: int) -> None:
    if year not in YEARS:
        raise HTTPException(status_code=404)


def _run(fn, *args) -> JSONResponse:
    try:
        return JSONResponse(jsonable_encoder(fn(*args)), headers=NO_STORE)
    except EntryError as e:
        return JSONResponse({"detail": str(e)}, status_code=503 if isinstance(e, EntriesUnavailable) else 409,
                            headers=NO_STORE)


# ── Вебхук ──────────────────────────────────────────────────────────────────

@router.post("/webhook/siberman/{token}/{year}")
async def entries_webhook(token: str, year: int, request: Request):
    secret = settings.SIBERMAN_WEBHOOK_SECRET
    if not secret or not hmac.compare_digest(token.encode(), secret.encode()):
        raise HTTPException(status_code=403)
    _check_year(year)
    ct = request.headers.get("content-type", "")
    try:
        if "multipart/form-data" in ct:
            body = {k: v for k, v in (await request.form()).items() if isinstance(v, str)}
        else:
            body = parse_body(await request.body(), ct)
    except Exception as e:
        _log.error(f"siberman entries webhook: тело не разобрано: {e}")
        ntfy.send("Siberman: заявка из Тильды не разобрана", ["Тело запроса не читается — см. лог сервера"],
                  priority="high")
        return PlainTextResponse("ok")
    if is_test_ping(body):
        return PlainTextResponse("ok")
    received_at = service.now_krs()
    path = spool.save(body, year, received_at)
    try:
        await run_in_threadpool(service.ingest, year, body, received_at)
        spool.done(path)
    except BadEntry as e:
        spool.fail(path)
        _log.error(f"siberman entries webhook: не заявка ({e}) — {path.name} в failed/")
        ntfy.send("Siberman: заявка из Тильды не разобрана", [str(e), f"Файл: failed/{path.name}"], priority="high")
    except Exception as e:
        _log.error(f"siberman entries webhook: запись не удалась, повтор из спула: {e}")
    return PlainTextResponse("ok")


# ── Админка ─────────────────────────────────────────────────────────────────

ADMIN = "/api/siberman/admin/entries/{year}"


@router.get(ADMIN)
def entries_admin_list(year: int, user: str = Depends(api_require_auth)):
    _check_year(year)
    return _run(service.admin_list, year)


@router.get(ADMIN + "/export.xlsx")
def entries_export(year: int, user: str = Depends(api_require_auth)):
    _check_year(year)
    try:
        data = service.export_xlsx(year)
    except EntryError as e:
        return JSONResponse({"detail": str(e)}, status_code=503, headers=NO_STORE)
    name = f"siberman_{year}_zayavki_{datetime.datetime.now():%Y%m%d_%H%M}.xlsx"
    return Response(data, media_type=XLSX, headers={"Content-Disposition": f'attachment; filename="{name}"', **NO_STORE})


@router.post(ADMIN + "/import")
def entries_import(year: int, file: UploadFile = File(...), user: str = Depends(api_require_auth)):
    _check_year(year)
    data = file.file.read(MAX_CSV_BYTES + 1)
    if len(data) > MAX_CSV_BYTES:
        return JSONResponse({"detail": "файл слишком большой"}, status_code=409, headers=NO_STORE)
    return _run(service.import_csv, year, data)


@router.get(ADMIN + "/{entry_id}")
def entries_card(year: int, entry_id: int, user: str = Depends(api_require_auth)):
    _check_year(year)
    return _run(service.entry_card, year, entry_id)


@router.post(ADMIN + "/{entry_id}/status")
def entries_status(year: int, entry_id: int, body: StatusIn, user: str = Depends(api_require_auth)):
    _check_year(year)
    return _run(service.set_status, year, entry_id, body.status, user)


@router.post(ADMIN + "/{entry_id}/comment")
def entries_comment(year: int, entry_id: int, body: CommentIn, user: str = Depends(api_require_auth)):
    _check_year(year)
    return _run(service.set_comment, year, entry_id, body.comment, user)


# ── Публичный список ────────────────────────────────────────────────────────

@router.get("/entries/{year}", response_class=HTMLResponse)
async def entries_public_page(request: Request, year: int):
    _check_year(year)
    if getattr(request.state, "domain", "") != "siberman":
        raise HTTPException(status_code=404)
    return templates.TemplateResponse("siberman/entries_public.html", {"request": request, "year": year})


@router.get("/api/siberman/entries/{year}")
def entries_public_api(year: int):
    _check_year(year)
    return _run(service.public_list, year)
```

- [ ] **Step 4: Подключение** — `src/krasmarafon/router.py` после строк `siberman_hall_router`:

```python
from src.siberman.entries.router import router as siberman_entries_router
router.include_router(siberman_entries_router)
```

`app.py`, `_MAINTENANCE_ALLOWED_PREFIXES` — после `"/athlete/",`:

```python
    # заявки Siberman: вебхук Тильды и публичный список не должны падать при техработах Красмарафона
    "/webhook/siberman/",
    "/entries/",
    "/api/siberman/entries",
```

- [ ] **Step 5: Шаблон** `templates/siberman/entries_public.html`

```html
<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Siberman {{ year }} — заявки</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Roboto:wght@300;400&display=swap">
<link rel="stylesheet" href="/static/css/siberman-entries.css?v={{ v }}">
</head>
<body>
<div class="hall entries" id="entries" data-year="{{ year }}">
  <p class="lead">Список обновляется автоматически</p>
  <p class="counts" id="counts"></p>
  <ul class="legend">
    <li>✅ — заявка допущена к жеребьёвке</li>
    <li>❌ — заявка не соответствует требованиям</li>
    <li>⌛️ — заявка в процессе изучения</li>
    <li>🚫 — отказ от участия в жеребьёвке</li>
  </ul>
  <input id="q" class="search" type="search" placeholder="Поиск по фамилии и имени" autocomplete="off">
  <table class="list">
    <thead><tr><th class="n"></th><th>Фамилия Имя</th><th>Формат участия</th><th class="st">Статус заявки</th></tr></thead>
    <tbody id="rows"><tr><td colspan="4" class="msg">Загрузка…</td></tr></tbody>
  </table>
</div>
<script src="/static/js/siberman-hall.js?v={{ v }}"></script>
<script src="/static/js/siberman-entries-search.js?v={{ v }}"></script>
<script src="/static/js/siberman-entries.js?v={{ v }}"></script>
</body>
</html>
```

- [ ] **Step 6: Запуск — PASS** (тот же Run) + `tests/unit/ -q`.

- [ ] **Step 7: Commit**

```bash
git add src/siberman/entries/router.py src/krasmarafon/router.py app.py templates/siberman/entries_public.html tests/integration/test_siberman_entries.py
git commit -m "feat(siberman/entries): вебхук Тильды, API вкладки «Заявки» и публичный список"
```

---

### Task 6: Поиск по ФИ (JS, общий)

**Files:**
- Create: `static/js/siberman-entries-search.js`
- Test: `tests/js/test_siberman_entries_search.js`

- [ ] **Step 1: Тест**

```js
// Поиск заявок по фамилии и имени (админка и публичный список). Запуск: node tests/js/test_siberman_entries_search.js
const assert = require('assert');
const { entryMatches } = require('../../static/js/siberman-entries-search.js');

assert.ok(entryMatches('Ёлкина Мария', 'елк'));             // ё = е, без регистра
assert.ok(entryMatches('Ёлкина Мария', 'мария ёлкина'));    // любой порядок слов
assert.ok(entryMatches('Ёлкина Мария', 'мар ел'));          // начала слов
assert.ok(entryMatches('Ёлкина Мария', '  '));              // пустой запрос — всё
assert.ok(!entryMatches('Ёлкина Мария', 'ина'));            // не середина слова
assert.ok(!entryMatches('Ёлкина Мария', 'елкина анна'));
console.log('ok');
```

- [ ] **Step 2: Запуск — FAIL** (`Cannot find module`)

Run: `node tests/js/test_siberman_entries_search.js`

- [ ] **Step 3: Реализация**

```js
'use strict';
// Поиск заявок Siberman по фамилии и имени: без регистра, ё = е, слова запроса — начала слов ФИ в любом порядке.

function entryNorm(s) { return String(s ?? '').toLowerCase().replace(/ё/g, 'е').trim(); }

function entryMatches(fio, query) {
  const words = entryNorm(fio).split(/\s+/);
  return entryNorm(query).split(/\s+/).filter(Boolean).every(q => words.some(w => w.startsWith(q)));
}

if (typeof module !== 'undefined') module.exports = { entryNorm, entryMatches };
```

- [ ] **Step 4: Запуск — PASS** (`ok`)

- [ ] **Step 5: Commit**

```bash
git add static/js/siberman-entries-search.js tests/js/test_siberman_entries_search.js
git commit -m "feat(siberman/entries): поиск заявок по фамилии и имени"
```

---

### Task 7: Публичная страница — стиль `2028_applications`

**Files:**
- Create: `static/css/siberman-entries.css`, `static/js/siberman-entries.js`
- Create: `docs/siberman/entries-tilda-snippet.md`

- [ ] **Step 1: CSS** (светлая тема, Roboto Light, серый текст, по центру, зебра #f0f0f0, чёрная линия под шапкой)

```css
/* Публичный список заявок Siberman (iframe на siberman515.com/{год}_applications) — в стиле прежней таблицы Тильды. */
html, body { margin: 0; background: #fff; }
.entries { max-width: 1160px; margin: 0 auto; padding: 8px 16px 16px; font-family: 'Roboto', Arial, sans-serif;
           font-weight: 300; color: #000; text-align: center; box-sizing: border-box; }
.entries .lead { font-size: 20px; margin: 0 0 8px; }
.entries .counts { font-size: 18px; font-weight: 400; margin: 0 0 24px; }
.entries .legend { list-style: none; padding: 0; margin: 0 auto 28px; display: inline-block; text-align: left;
                   font-size: 14px; line-height: 1.7; }
.entries .search { display: block; width: 100%; max-width: 420px; margin: 0 auto 24px; padding: 10px 14px;
                   font: inherit; font-size: 16px; border: 1px solid #ccc; border-radius: 4px; box-sizing: border-box; }
.entries .list { width: 100%; border-collapse: collapse; font-size: 18px; color: #555; }
.entries .list th { font-weight: 400; color: #000; padding: 16px 8px; border-bottom: 1px solid #000; }
.entries .list td { padding: 10px 8px; border-bottom: 1px solid #e5e5e5; }
.entries .list tbody tr:nth-child(even) td { background: #f0f0f0; }
.entries .list td.n { color: #6aabd7; }
.entries .list .msg { color: #888; padding: 24px; }
@media (max-width: 600px) {
  .entries { padding: 4px 8px 12px; }
  .entries .list { font-size: 14px; }
  .entries .list th, .entries .list td { padding: 8px 4px; }
  .entries .list .n { width: 28px; }
  .entries .list .st { width: 64px; }
}
```

- [ ] **Step 2: JS** `static/js/siberman-entries.js`

```js
'use strict';
// Публичный список заявок Siberman (/entries/{год}): по алфавиту, поиск по ФИ (номера — из полного списка),
// обновление раз в минуту; высоту iframe сообщает siberman-hall.js.

const root = document.getElementById('entries');
const API = `/api/siberman/entries/${root.dataset.year}`;
const EMOJI = { admitted: '✅', rejected: '❌', review: '⌛️', withdrawn: '🚫' };
let data = null;

function render() {
  const q = document.getElementById('q').value;
  const rows = data.entries.filter(e => entryMatches(e.fio, q));
  document.getElementById('rows').innerHTML = rows.map(e =>
    `<tr><td class="n">${e.n}</td><td>${hallEsc(e.fio)}</td><td>${hallEsc(e.format)}</td><td class="st">${EMOJI[e.status] || ''}</td></tr>`
  ).join('') || `<tr><td colspan="4" class="msg">${data.total ? 'Никого не нашли' : 'Заявок пока нет'}</td></tr>`;
  document.getElementById('counts').textContent = `Заявок: ${data.total}, допущено: ${data.admitted}`;
}

async function load() {
  try {
    data = await hallLoad(API);
    render();
  } catch (err) {
    if (!data) document.getElementById('rows').innerHTML = `<tr><td colspan="4" class="msg">${hallEsc(err.message)}</td></tr>`;
  }
}

document.getElementById('q').addEventListener('input', () => data && render());
load();
setInterval(load, 60000);
```

- [ ] **Step 3: Сниппет для Тильды** `docs/siberman/entries-tilda-snippet.md`

````markdown
# Список заявок Siberman — вставка в Тильду (siberman515.com/{год}_applications)

1. Скопировать страницу `2028_applications` → `2029_applications` (шапка, меню, заголовок «Siberman 2029»).
2. Удалить блоки «Список заявок обновляется каждый понедельник», «Последнее обновление…», легенду и таблицу.
3. На их место — HTML-блок **T123** («Другое → HTML-код»):

```html
<iframe class="sbm-hall" src="https://live.siberman515.com/entries/2029" style="width:100%;border:0;height:1500px" title="Siberman 2029 — заявки"></iframe>
<script>
window.addEventListener('message', function (e) {
  if (e.origin !== 'https://live.siberman515.com' || !e.data || !e.data.sibermanHallHeight) return;
  document.querySelectorAll('iframe.sbm-hall').forEach(function (f) {
    if (f.contentWindow === e.source) f.style.height = e.data.sibermanHallHeight + 'px';
  });
});
</script>
```

## Вебхук в форме заявок

Тильда → настройки сайта → Формы → «Webhook» → адрес из админки (`/admin/draw?year=2029` → «Заявки» →
«Скопировать адрес вебхука»). Отметить «Отправлять данные …» в формате по умолчанию (x-www-form-urlencoded).
В настройках блока формы на странице заявки включить этот приёмник рядом с Tilda CRM. При подключении Тильда
шлёт тестовый запрос — сервер отвечает «ok», заявка не создаётся. Проверка: отправить тестовую заявку с
сайта → она появилась во вкладке «Заявки» со статусом ⌛️ → поставить ❌ и комментарий «тест».
````

- [ ] **Step 4: Проверка в браузере** — локальный сервер (`scratchpad/serve.py`, порт 8011), год 2091 с тремя
тестовыми заявками (ingest как в фикстуре теста), Playwright: `http://siberman.localhost:8011/entries/2091` на
1400×900 и 390×844 — порядок по алфавиту, счётчик, поиск «елк» оставляет одну строку с её номером из полного
списка, на телефоне колонка статуса видна целиком, ошибок JS нет. Скриншоты сравнить глазами со скриншотом
`siberman515.com/2028_applications`. Тестовый год удалить.

- [ ] **Step 5: Commit**

```bash
git add static/css/siberman-entries.css static/js/siberman-entries.js docs/siberman/entries-tilda-snippet.md
git commit -m "feat(siberman/entries): публичный список заявок в стиле страницы Тильды"
```

---

### Task 8: Вкладка «Заявки» в админке

**Files:**
- Modify: `templates/siberman/draw_admin.html` (кнопка вкладки после «Настройки» ~стр. 85–90, секция перед
  `<script>const DRAW_YEAR`, стили в `<style>`)
- Modify: `static/js/siberman-draw-admin.js:483-487` (`switchTab`) и конец файла
- Create: `static/js/siberman-entries-admin.js`

- [ ] **Step 1: Разметка** — кнопка вкладки:

```html
    <button class="admin-tab" onclick="switchTab('entries', this)">Заявки</button>
```

секция:

```html
  <section id="tab-entries" class="tab-content">
    <div class="card">
      <div class="ent-head">
        <label>Год заявок <select id="ent-year"></select></label>
        <span id="ent-counts" class="muted"></span>
      </div>
      <div class="ent-tools">
        <input id="ent-q" class="search" placeholder="Поиск по фамилии и имени" autocomplete="off">
        <select id="ent-filter">
          <option value="">Все статусы</option><option value="review">⌛️ на изучении</option>
          <option value="admitted">✅ допущена</option><option value="rejected">❌ не соответствует</option>
          <option value="withdrawn">🚫 отказ от жеребьёвки</option>
        </select>
        <a class="btn btn-primary" id="ent-export">Скачать Excel</a>
      </div>
      <div id="ent-msg"></div>
      <div class="ent-table-wrap"><table class="ent-table">
        <thead><tr><th>№</th><th>Дата</th><th>Фамилия Имя</th><th>Формат</th><th>Пол</th><th>Город</th>
          <th>E-mail</th><th>Телефон</th><th>Статус</th><th>Комментарий</th></tr></thead>
        <tbody id="ent-rows"></tbody>
      </table></div>
    </div>
    <div class="card">
      <h2>Приём заявок из Тильды</h2>
      <p class="muted">Адрес вебхука для формы заявок (Тильда → Формы → Webhook). Секрет в адресе — не публикуйте.</p>
      <p><code id="ent-webhook"></code> <button class="btn-small" id="ent-webhook-copy">Скопировать адрес вебхука</button></p>
      <p class="muted">Заявки, пришедшие до подключения вебхука, — CSV-выгрузкой Тильды (повторы не задваиваются).</p>
      <input type="file" id="ent-file" accept=".csv,text/csv">
      <button class="btn" id="ent-upload">Загрузить CSV из Тильды</button>
      <div id="ent-import-report"></div>
    </div>
    <div id="ent-card" class="ent-card" hidden></div>
  </section>
```

стили (в `<style>`):

```css
.ent-head, .ent-tools { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; margin-bottom: 12px; }
.ent-tools .search { flex: 1 1 260px; }
.ent-table-wrap { overflow-x: auto; }
.ent-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.ent-table th, .ent-table td { padding: 6px 8px; border-bottom: 1px solid #e0e0e0; text-align: left; vertical-align: top; }
.ent-table tbody tr { cursor: pointer; } .ent-table tbody tr:hover { background: #f7f7f7; }
.ent-table textarea { width: 180px; min-height: 32px; font: inherit; }
.ent-card { position: fixed; right: 16px; top: 80px; width: min(480px, calc(100% - 32px)); max-height: calc(100% - 100px);
            overflow: auto; background: #fff; border: 1px solid #ccc; border-radius: 8px; padding: 16px;
            box-shadow: 0 8px 24px rgba(0,0,0,.15); z-index: 20; }
.ent-card .text { white-space: pre-wrap; }
```

и `<script src="/static/js/siberman-entries-search.js?v={{ v }}"></script>` + `<script src="/static/js/siberman-entries-admin.js?v={{ v }}"></script>`
после `siberman-draw-admin.js`.

- [ ] **Step 2: `switchTab`** — в функции `switchTab(name, btn)` сразу после двух строк
`document.querySelectorAll('.tab-content')…` / `document.querySelectorAll('.admin-tab')…` и **до** строки
`if (!S) return;` (вкладке «Заявки» состояние жеребьёвки `S` не нужно) вставить:

```js
  if (name === 'entries') { entriesLoad(); history.replaceState(null, '', '#entries'); return; }
  if (location.hash === '#entries') history.replaceState(null, '', location.pathname + location.search);
```

и в конец файла:

```js
// Смена года во вкладке «Заявки» перезагружает страницу с ?year= — вкладка открывается снова
if (location.hash === '#entries') {
  const btn = [...document.querySelectorAll('.admin-tab')].find(b => b.textContent.trim() === 'Заявки');
  if (btn) switchTab('entries', btn);
}
```

- [ ] **Step 3: `static/js/siberman-entries-admin.js`**

```js
'use strict';
// Вкладка «Заявки» админки жеребьёвки: заявки года по порядку прихода, статус и комментарий директора
// (сохраняются сразу), поиск, фильтр, карточка с журналом, Excel, загрузка CSV Тильды, адрес вебхука.

const ENT_API = `/api/siberman/admin/entries/${DRAW_YEAR}`;
const ENT_STATUS = { review: '⌛️ на изучении', admitted: '✅ допущена', rejected: '❌ не соответствует',
                     withdrawn: '🚫 отказ от жеребьёвки' };
const ENT_FORMAT = { individual: 'Личное', relay: 'Эстафета' };
let ENT = null;
const entEl = id => document.getElementById(id);
const entEsc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const entDate = s => s ? `${s.slice(8, 10)}.${s.slice(5, 7)}.${s.slice(0, 4)} ${s.slice(11, 16)}` : '';

async function entFetch(path, opt = {}) {
  const r = await fetch(ENT_API + path, { cache: 'no-store', ...opt });
  if (r.status === 401) { location.href = '/login?next=' + encodeURIComponent(location.pathname + location.search + '#entries'); throw new Error('нужен вход'); }
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || `ошибка ${r.status}`);
  return data;
}

function entMsg(text, kind = 'ok') {
  entEl('ent-msg').innerHTML = text ? `<div class="msg msg-${kind}">${entEsc(text)}</div>` : '';
}

async function entriesLoad() {
  try {
    ENT = await entFetch('');
    entEl('ent-year').innerHTML = ENT.years.map(y => `<option${y === DRAW_YEAR ? ' selected' : ''}>${y}</option>`).join('')
      + `<option value="${Math.max(...ENT.years) + 1}">${Math.max(...ENT.years) + 1}</option>`;
    entEl('ent-export').href = `${ENT_API}/export.xlsx`;
    entEl('ent-webhook').textContent = ENT.webhook_path ? location.origin + ENT.webhook_path : 'не настроен (нет SIBERMAN_WEBHOOK_SECRET)';
    entRender();
  } catch (e) { entMsg(e.message, 'err'); }
}

function entRender() {
  const c = ENT.counts;
  entEl('ent-counts').textContent = `Всего ${c.total} · ⌛️ ${c.review} · ✅ ${c.admitted} · ❌ ${c.rejected} · 🚫 ${c.withdrawn}`;
  const q = entEl('ent-q').value, f = entEl('ent-filter').value;
  const rows = ENT.entries.filter(e => (!f || e.status === f) && entryMatches(`${e.surname} ${e.name}`, q));
  entEl('ent-rows').innerHTML = rows.map(e => `<tr data-id="${e.id}">
    <td>${e.n}</td><td>${entDate(e.submitted_at)}</td><td><b>${entEsc(e.surname + ' ' + e.name)}</b></td>
    <td>${ENT_FORMAT[e.format]}</td><td>${{ M: 'М', F: 'Ж' }[e.gender] || ''}</td><td>${entEsc(e.city)}</td>
    <td>${entEsc(e.email)}</td><td>${entEsc(e.phone)}</td>
    <td><select data-status="${e.id}">${Object.entries(ENT_STATUS).map(([k, v]) => `<option value="${k}"${k === e.status ? ' selected' : ''}>${v}</option>`).join('')}</select></td>
    <td><textarea data-comment="${e.id}">${entEsc(e.comment)}</textarea></td></tr>`).join('')
    || '<tr><td colspan="10" class="muted">Заявок нет</td></tr>';
}

async function entSetStatus(sel) {
  const e = ENT.entries.find(x => x.id === +sel.dataset.status), old = e.status;
  try {
    await entFetch(`/${e.id}/status`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ status: sel.value }) });
    e.status = sel.value;
    ENT.counts[old]--; ENT.counts[sel.value]++;
    entMsg(`${e.surname} ${e.name}: ${ENT_STATUS[sel.value]}`);
    entRender();
  } catch (err) { sel.value = old; entMsg(`Статус не сохранён: ${err.message}`, 'err'); }
}

async function entSetComment(area) {
  const e = ENT.entries.find(x => x.id === +area.dataset.comment);
  if (area.value.trim() === e.comment) return;
  try {
    await entFetch(`/${e.id}/comment`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ comment: area.value }) });
    e.comment = area.value.trim();
    entMsg(`${e.surname} ${e.name}: комментарий сохранён`);
  } catch (err) { entMsg(`Комментарий не сохранён: ${err.message}`, 'err'); }
}

async function entOpenCard(id) {
  try {
    const e = await entFetch(`/${id}`);
    const relay = e.format === 'relay' ? `<p>Команда: <b>${entEsc(e.team_name)}</b><br>Плавание: ${entEsc(e.relay_swim)}<br>Велосипед: ${entEsc(e.relay_bike)}<br>Бег: ${entEsc(e.relay_run)}</p>` : '';
    const audit = e.audit.map(a => `<li>${entDate(a.created_at)} · ${entEsc(a.admin_user)} · ${a.action === 'status' ? `${ENT_STATUS[a.old_value]} → ${ENT_STATUS[a.new_value]}` : `комментарий: «${entEsc(a.new_value)}»`}</li>`).join('');
    entEl('ent-card').innerHTML = `<button class="btn-small" style="float:right" onclick="entEl('ent-card').hidden = true">×</button>
      <h3>${entEsc(e.surname + ' ' + e.name)}</h3>
      <p>${ENT_FORMAT[e.format]} · ${entEsc(e.city)} · ДР ${e.birthdate ? e.birthdate.split('-').reverse().join('.') : '—'}<br>${entEsc(e.email)} · ${entEsc(e.phone)}</p>${relay}
      ${e.wildcard_reason ? `<h4>Почему wild card</h4><div class="text">${entEsc(e.wildcard_reason)}</div>` : ''}
      ${e.results_text ? `<h4>О результатах</h4><div class="text">${entEsc(e.results_text)}</div>` : ''}
      ${e.result_url ? `<p><a href="${entEsc(e.result_url)}" target="_blank" rel="noopener">Ссылка на результаты</a></p>` : ''}
      <h4>Журнал</h4><ul>${audit || '<li class="muted">изменений не было</li>'}</ul>`;
    entEl('ent-card').hidden = false;
  } catch (err) { entMsg(err.message, 'err'); }
}

async function entUpload() {
  const file = entEl('ent-file').files[0];
  if (!file) return entMsg('Выберите CSV-файл', 'err');
  const fd = new FormData(); fd.append('file', file);
  try {
    const r = await entFetch('/import', { method: 'POST', body: fd });
    entEl('ent-import-report').innerHTML = `<p>Строк: ${r.rows}, новых: ${r.new}, уже были: ${r.known}, с ошибкой: ${r.errors.length}</p>`
      + (r.errors.length ? `<ul>${r.errors.map(x => `<li>${entEsc(x)}</li>`).join('')}</ul>` : '');
    await entriesLoad();
  } catch (err) { entMsg(err.message, 'err'); }
}

entEl('ent-q').addEventListener('input', () => ENT && entRender());
entEl('ent-filter').addEventListener('change', () => ENT && entRender());
entEl('ent-year').addEventListener('change', e => { location.href = `${location.pathname}?year=${e.target.value}#entries`; });
entEl('ent-upload').addEventListener('click', entUpload);
entEl('ent-webhook-copy').addEventListener('click', () => navigator.clipboard.writeText(entEl('ent-webhook').textContent).then(() => entMsg('Адрес вебхука скопирован')));
entEl('ent-rows').addEventListener('change', e => { if (e.target.dataset.status) entSetStatus(e.target); });
entEl('ent-rows').addEventListener('focusout', e => { if (e.target.dataset.comment) entSetComment(e.target); });
entEl('ent-rows').addEventListener('click', e => {
  if (e.target.closest('select, textarea')) return;
  const tr = e.target.closest('tr[data-id]');
  if (tr) entOpenCard(+tr.dataset.id);
});
```

- [ ] **Step 4: Проверка в браузере** — локальный сервер, cookie админа (`scratchpad/mkcookie9.py`), год 2091 с
тестовыми заявками: `/admin/draw?year=2091#entries` открывает вкладку; смена статуса → счётчик и сообщение,
после перезагрузки статус тот же; комментарий сохраняется при уходе с поля; поиск «елк» и фильтр ✅; клик по
строке — карточка с журналом; «Скачать Excel» скачивает файл; загрузка CSV — отчёт; смена года — страница с
`?year=…#entries`. Ошибок JS нет. Остальные вкладки (Жеребьёвка/Оплаты/Настройки) работают как раньше.
Тестовый год удалить.

- [ ] **Step 5: Commit**

```bash
git add templates/siberman/draw_admin.html static/js/siberman-draw-admin.js static/js/siberman-entries-admin.js
git commit -m "feat(siberman/entries): вкладка «Заявки» в админке — статусы, комментарии, Excel, CSV"
```

---

### Task 9: Полная проверка и прод

- [ ] **Step 1:** `"C:/Users/podbo/miniconda3/python.exe" -m pytest tests/unit/ tests/integration/test_siberman_entries.py tests/integration/test_siberman_draw.py -q -p no:cacheprovider > out.txt 2>&1; echo "exit=$?"; tail -1 out.txt` — exit=0; `node tests/js/test_siberman_entries_search.js` — ok.
- [ ] **Step 2:** Обновить `.taskmaster/tasks/todo.md` (секция с чекбоксами и ревью), Obsidian: строка в «Текущих
  приоритетах» (часть A сделана), сессия.
- [ ] **Step 3 (прод, по одному шагу, с разрешения пользователя):**
  1. бэкап: `mysqldump -u root --single-transaction siberman | gzip > /root/backups/siberman_before_entries_<дата>.sql.gz`;
  2. миграция: `mysql -u root siberman < 018_entries.sql` (через `prod_run.py` со stdin-файлом), проверка `SHOW TABLES LIKE 'siberman_entries%'`;
  3. секрет: сгенерировать на сервере (`python3 -c "import secrets;print(secrets.token_urlsafe(24))"`) и дописать
     `SIBERMAN_WEBHOOK_SECRET=…` в `/opt/km_track/.env`, не печатая значение;
  4. push → деплой (watch), затем: `/entries/2029` на siberman-домене 200, `/api/siberman/entries/2029` → `total: 0`;
     тестовый POST `test=test` на адрес вебхука → `ok`, неверный секрет → 403.
- [ ] **Step 4:** Пользователю: ссылка `/admin/draw?year=2029#entries`, сниппет `docs/siberman/entries-tilda-snippet.md`
  (копия страницы `2028_applications` → `2029_applications`, блок T123, вебхук в форме), просьба отправить
  тестовую заявку и потом поставить ей ❌ / удалить её из Tilda CRM.
