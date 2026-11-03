# Флаг «не согласен на публикацию ПД» — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** оператор отмечает в админке заявку «не согласен на ПД» — во всех публичных выдачах этого участника на этом событии вместо ФИ «Спортсмен», без ДР и ссылки на карточку.

**Architecture:** колонка `leads.pd_refused`; запросы результатов подтягивают флаг подзапросом по `event_id + start_number` (общая SQL-константа `PD_REFUSED_SQL`); одна функция `mask_runner()` применяется в каждой публичной выдаче до кешей.

**Tech Stack:** Python 3.13, FastAPI, mysql-connector (без ORM), pytest; админка — `templates/krasmarafon/admin.html` (ванильный JS).

Спецификация: `docs/superpowers/specs/2026-11-03-pd-consent-flag-design.md`.

**Команды тестов** (Windows, conda base, из корня репозитория):
- unit: `conda run --no-capture-output -n base python -m pytest tests/unit/ -q`
- интеграция (локальная БД MySQL80:3308 через `.env.local`, подхватывает `tests/conftest.py`): `conda run --no-capture-output -n base python -m pytest tests/integration/<файл> -q`

**Отклонение от спецификации (п. 7):** `/api/race-stats` читает старый снимок Copernico `data/race_data.json`, где нет `event_id`, — сопоставить с заявками по номеру надёжно нельзя. Вместо маскировки по номеру запасная выдача отдаёт лучший результат **без ФИ**. Согласовать с пользователем перед Task 8.

---

## Файлы

| Файл | Что |
|------|-----|
| Create `migrations/lead_pd_refused.sql` | колонка `leads.pd_refused` |
| Create `src/krasmarafon/services/public_pd.py` | `PLACEHOLDER`, `mask_runner()` |
| Modify `src/analytics/db_results.py` | `PD_REFUSED_SQL`; флаг в SELECT результатов (2 функции), рейтингах отрезков, статистике; `set_lead_pd_refused()` |
| Modify `src/krasmarafon/services/results_service.py` | маскировка в `assemble_event_results` |
| Modify `src/krasmarafon/services/live_top10_export.py` | флаг + маскировка топ-3 |
| Modify `src/krasmarafon/services/diploma_service.py` | маскировка обоих дипломов |
| Modify `src/analytics/db_athletes.py` | исключить события с отказом из профиля |
| Modify `src/krasmarafon/routers/admin.py` | `POST /api/admin/leads/{id}/pd-refused` |
| Modify `src/krasmarafon/routers/api.py` | маскировка рейтингов отрезков; `/api/race-stats` без ФИ; удалить `/api/analytics` |
| Modify `src/krasmarafon/models/startlist.py` | `LeadAdminItem.pd_refused` |
| Modify `templates/krasmarafon/admin.html` | кнопка и бейдж |
| Tests | `tests/unit/test_public_pd.py`, `tests/integration/test_lead_pd_refused.py`, дополнения в существующих unit-тестах |

---

### Task 1: Миграция и функция маскировки

**Files:**
- Create: `migrations/lead_pd_refused.sql`
- Create: `src/krasmarafon/services/public_pd.py`
- Test: `tests/unit/test_public_pd.py`

- [ ] **Step 1: Миграция**

```sql
-- Отказ от публикации ПД на заявке (2026-11-03, с Снежной семёрки 2026 согласие — на бумаге
-- при получении номера, отдельное на каждое событие). 1 — на публичных страницах вместо ФИ
-- «Спортсмен», без ДР и карточки. Ставится вручную в /admin → «Заявки». Идемпотентно.

SET @has_col := (SELECT COUNT(*) FROM information_schema.columns
                 WHERE table_schema = DATABASE() AND table_name = 'leads' AND column_name = 'pd_refused');
SET @ddl := IF(@has_col = 0,
    'ALTER TABLE leads ADD COLUMN pd_refused TINYINT(1) NOT NULL DEFAULT 0',
    'DO 0');
PREPARE st FROM @ddl;
EXECUTE st;
DEALLOCATE PREPARE st;
```

- [ ] **Step 2: Применить к локальной БД** (дважды — проверка идемпотентности)

```bash
conda run --no-capture-output -n base python -c "
from dotenv import load_dotenv; load_dotenv('.env'); load_dotenv('.env.local', override=True)
import os, mysql.connector
c = mysql.connector.connect(host=os.getenv('DB_HOST','localhost'), port=int(os.getenv('DB_PORT')), user=os.getenv('DB_USER'), password=os.getenv('DB_PASSWORD'), database=os.getenv('DB_NAME'), autocommit=True)
cur = c.cursor(); sql = open('migrations/lead_pd_refused.sql', encoding='utf-8').read()
for _ in range(2):
    for s in sql.split(';'):
        s = '\n'.join(l for l in s.splitlines() if not l.strip().startswith('--')).strip()
        if s: cur.execute(s)
cur.execute(\"SHOW COLUMNS FROM leads LIKE 'pd_refused'\"); print(cur.fetchall())"
```
Expected: `[('pd_refused', 'tinyint(1)', 'NO', '', '0', '')]`

- [ ] **Step 3: Падающий тест**

```python
"""mask_runner — публичный вид участника без согласия на публикацию ПД."""
from src.krasmarafon.services.public_pd import PLACEHOLDER, mask_runner

ROW = {"surname": "Иванов", "name": "Иван", "full_name": "Иванов Иван", "birthday": "1990-01-01",
       "client_id": 5, "start_number": 101, "sex": "Мужчина", "category": "М", "rank_absolute": 3}


def test_refused_hides_name_birthday_card():
    out = mask_runner(ROW, True)
    assert (out["surname"], out["name"], out["full_name"]) == (PLACEHOLDER, "", PLACEHOLDER)
    assert out["birthday"] is None and out["client_id"] is None
    assert (out["start_number"], out["sex"], out["category"], out["rank_absolute"]) == (101, "Мужчина", "М", 3)


def test_not_refused_returns_row_as_is():
    assert mask_runner(ROW, False) is ROW
    assert mask_runner(ROW, None) is ROW


def test_source_row_not_modified_and_missing_keys_not_added():
    mask_runner(ROW, True)
    assert ROW["surname"] == "Иванов"
    assert mask_runner({"surname": "Петров", "time": "20:00"}, 1) == {"surname": PLACEHOLDER, "time": "20:00"}


def test_placeholder_text():
    assert PLACEHOLDER == "Спортсмен"
```

- [ ] **Step 4: Убедиться, что падает**

Run: `conda run --no-capture-output -n base python -m pytest tests/unit/test_public_pd.py -q`
Expected: FAIL — `ModuleNotFoundError: src.krasmarafon.services.public_pd`

- [ ] **Step 5: Реализация** `src/krasmarafon/services/public_pd.py`

```python
"""Публичный вид участника без согласия на публикацию ПД (leads.pd_refused, с Снежной семёрки 2026):
вместо ФИ — «Спортсмен», без даты рождения и ссылки на карточку. Номер, пол, категория, время и места
остаются. Вызывается в каждой публичной выдаче до кешей — настоящие ФИ не попадают в ответ."""

PLACEHOLDER = "Спортсмен"
_FULL_NAME_KEYS = ("full_name", "fullName")
_HIDDEN_KEYS = ("birthday", "birth_year", "client_id")


def mask_runner(row: dict, refused) -> dict:
    """refused — копия строки со скрытыми ПД; иначе та же строка."""
    if not refused:
        return row
    out = dict(row)
    if "surname" in out:
        out["surname"] = PLACEHOLDER
    if "name" in out:
        out["name"] = ""
    for key in _FULL_NAME_KEYS:
        if key in out:
            out[key] = PLACEHOLDER
    for key in _HIDDEN_KEYS:
        if key in out:
            out[key] = None
    return out
```

- [ ] **Step 6: Тесты проходят**

Run: `conda run --no-capture-output -n base python -m pytest tests/unit/test_public_pd.py -q`
Expected: `4 passed`

- [ ] **Step 7: Commit**

```bash
git add migrations/lead_pd_refused.sql src/krasmarafon/services/public_pd.py tests/unit/test_public_pd.py
git commit -m "feat(pd): колонка leads.pd_refused и mask_runner"
```

---

### Task 2: Админка — флаг на заявке

**Files:**
- Modify: `src/analytics/db_results.py` (после `set_lead_elite`, ~стр. 2039)
- Modify: `src/krasmarafon/routers/admin.py` (после `mark_lead_elite`, ~стр. 479)
- Modify: `src/krasmarafon/models/startlist.py:64` (после `is_pacer`)
- Modify: `templates/krasmarafon/admin.html:1139-1141` и `_renderDupBadge` (~1147)
- Test: `tests/integration/test_lead_pd_refused.py`

- [ ] **Step 1: Падающий интеграционный тест** (образец — `tests/integration/test_lead_flags.py`)

```python
"""Флаг «не согласен на ПД» на реальной БД (локальный снимок): set_lead_pd_refused ставит/снимает
флаг и пишет в журнал dq_actions. Тестовые записи — событие «Тест ПД» 2099 года, убираются."""
import json

import pytest

from src.analytics.db_pool import get_pooled_connection
from src.analytics.db_results import set_lead_pd_refused

EV = "Тест ПД"


@pytest.fixture
def db():
    conn = get_pooled_connection()
    if not conn:
        pytest.skip("Нет локальной БД")
    cur = conn.cursor(dictionary=True)
    cur.execute("SHOW COLUMNS FROM leads LIKE 'pd_refused'")
    if not cur.fetchone():
        conn.close()
        pytest.skip("Миграция lead_pd_refused не применена")

    def cleanup():
        cur.execute("SELECT id, client_id FROM leads WHERE event_name = %s", (EV,))
        rows = cur.fetchall()
        if rows:
            ids = ",".join(str(r["id"]) for r in rows)
            keys = ",".join(f"'lead:{r['id']}'" for r in rows)
            cur.execute(f"DELETE FROM dq_actions WHERE finding_key IN ({keys})")
            cur.execute(f"DELETE FROM leads WHERE id IN ({ids})")
            cards = ",".join(str(r["client_id"]) for r in rows if r["client_id"])
            if cards:
                cur.execute(f"DELETE FROM clients WHERE id IN ({cards})")
        conn.commit()

    cleanup()
    yield conn, cur
    cleanup()
    cur.close()
    conn.close()


def add_lead(cur):
    cur.execute("""INSERT INTO leads (surname, name, sex, city, club, birthday, email, phone, event_name, event_distance,
                   event_year, products, amount, client_id, event_id, is_duplicate, status, is_new, is_new_event,
                   is_name_suspicious, created_at)
                   VALUES ('Тестпд', 'Иван', 'Мужчина', '', '', '1990-01-01', 'pd@test.ru', '', %s, '5 км', 2099,
                           '', 0, 0, 0, 0, 0, 0, 0, 0, NOW())""", (EV,))
    return cur.lastrowid


def test_set_and_clear_pd_refused_with_journal(db):
    conn, cur = db
    lead = add_lead(cur)
    conn.commit()

    assert set_lead_pd_refused(lead, True, "tester")
    cur.execute("SELECT pd_refused FROM leads WHERE id = %s", (lead,))
    assert cur.fetchone()["pd_refused"] == 1

    assert set_lead_pd_refused(lead, False, "tester")
    cur.execute("SELECT pd_refused FROM leads WHERE id = %s", (lead,))
    assert cur.fetchone()["pd_refused"] == 0

    cur.execute("SELECT action, details, done_by FROM dq_actions WHERE finding_key = %s ORDER BY id", (f"lead:{lead}",))
    log = cur.fetchall()
    assert [r["action"] for r in log] == ["pd_refused", "pd_refused"]
    assert [json.loads(r["details"])["pd_refused"] for r in log] == [1, 0]
    assert {r["done_by"] for r in log} == {"tester"}


def test_unknown_lead_returns_false(db):
    assert not set_lead_pd_refused(10 ** 12, True, "tester")
```

- [ ] **Step 2: Убедиться, что падает**

Run: `conda run --no-capture-output -n base python -m pytest tests/integration/test_lead_pd_refused.py -q`
Expected: FAIL — `ImportError: cannot import name 'set_lead_pd_refused'`

- [ ] **Step 3: `set_lead_pd_refused` в `db_results.py`** (сразу после `set_lead_elite`)

```python
def set_lead_pd_refused(lead_id: int, refused: bool, user: str) -> bool:
    """Кнопка «Не согласен на ПД» / «Снять» (leads.pd_refused): на публичных страницах этого события
    вместо ФИ — «Спортсмен». Изменение — в журнал dq_actions. Кеши результатов истекают сами (5–30 с)."""
    conn = get_pooled_connection()
    if not conn:
        return False
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM leads WHERE id = %s", (lead_id,))
        if cur.fetchone() is None:
            return False
        cur.execute("UPDATE leads SET pd_refused = %s WHERE id = %s", (int(refused), lead_id))
        cur.execute("INSERT INTO dq_actions (action, finding_key, details, done_by) VALUES (%s, %s, %s, %s)",
                    ("pd_refused", f"lead:{lead_id}", json.dumps({"pd_refused": int(refused)}), user or ""))
        conn.commit()
        cur.close()
        invalidate_start_list_cache()
        return True
    finally:
        conn.close()
```

(`json` в `db_results.py` уже импортирован — используется в `delete_lead`.)

- [ ] **Step 4: Тест проходит**

Run: `conda run --no-capture-output -n base python -m pytest tests/integration/test_lead_pd_refused.py -q`
Expected: `2 passed`

- [ ] **Step 5: Эндпоинт в `admin.py`** (после `mark_lead_elite`)

```python
@router.post("/api/admin/leads/{lead_id}/pd-refused")
async def mark_lead_pd_refused(lead_id: int, refused: bool = True, user: str = Depends(api_require_auth)) -> dict:
    """«Не согласен на ПД» / «Снять» (leads.pd_refused): на сайте вместо ФИ — «Спортсмен»."""
    from src.analytics.db_results import set_lead_pd_refused

    if not await asyncio.get_event_loop().run_in_executor(None, lambda: set_lead_pd_refused(lead_id, refused, user)):
        raise HTTPException(status_code=404, detail=f"Заявка {lead_id} не найдена")
    return {"status": "ok"}
```

- [ ] **Step 6: Модель** — в `LeadAdminItem` после `is_pacer`:

```python
    pd_refused: Optional[int] = None   # «Не согласен на ПД» — на сайте вместо ФИ «Спортсмен»
```

- [ ] **Step 7: Интерфейс** — в `admin.html` после блока «Элита» (стр. 1139-1141):

```javascript
        // Согласие на ПД — на бумаге при получении номера; без согласия на сайте вместо ФИ «Спортсмен»
        actions.appendChild(lead.pd_refused
            ? _leadActionBtn('Снять «без ПД»', `/api/admin/leads/${lead.id}/pd-refused?refused=false`)
            : _leadActionBtn('Не согласен на ПД', `/api/admin/leads/${lead.id}/pd-refused?refused=true`,
                             `Отметить: ${lead.surname} ${lead.name} не согласен на публикацию ПД?\nНа сайте вместо ФИ будет «Спортсмен».`));
```

В конце `_renderDupBadge`, после `cell.appendChild(badge);`:

```javascript
        if (lead.pd_refused) {
            const pd = document.createElement('span');
            pd.className = 'admin-badge admin-badge--inactive';
            pd.style.marginLeft = '4px';
            pd.textContent = 'Без ПД';
            pd.title = 'Не согласен на публикацию ПД — на сайте «Спортсмен»';
            cell.appendChild(pd);
        }
```

- [ ] **Step 8: Unit-тесты не сломаны**

Run: `conda run --no-capture-output -n base python -m pytest tests/unit/ -q`
Expected: все проходят

- [ ] **Step 9: Commit**

```bash
git add src/analytics/db_results.py src/krasmarafon/routers/admin.py src/krasmarafon/models/startlist.py templates/krasmarafon/admin.html tests/integration/test_lead_pd_refused.py
git commit -m "feat(admin): флаг «Не согласен на ПД» на заявке"
```

---

### Task 3: Результаты, трекер, SSE

**Files:**
- Modify: `src/analytics/db_results.py` — константа рядом с кешами (~стр. 31-46); SELECT в `get_race_results_by_event_id` (~стр. 77-125) и `get_race_results_by_event_id_and_year` (~стр. 171-219)
- Modify: `src/krasmarafon/services/results_service.py:317` (`results.append({...})`)
- Test: `tests/unit/test_results_service_client_id.py` (добавить тест)

- [ ] **Step 1: Падающий тест** — дописать в `tests/unit/test_results_service_client_id.py`:

```python
def test_refused_runner_is_masked():
    from src.krasmarafon.services import results_service as rs
    runner = {"id": 8, "client_id": 40803, "surname": "Пцарев", "name": "Александр", "start_number": 1013,
              "birthday": date(2008, 5, 1), "race_status": "Finished", "time_gun_finish": timedelta(minutes=9),
              "sex": "Мужчина", "category": "М", "pd_refused": 1}
    ev = {"event_name": "Детский забег", "event_distance": 1.0, "event_year": 2016, "event_date": date(2016, 8, 28)}
    with patch(f"{DB}.get_race_results_by_event_id", return_value=[runner]), \
            patch(f"{DB}.get_event_info_by_id", return_value=ev), \
            patch(f"{DB}.get_category_avg_paces", return_value={}), \
            patch(f"{DB}.get_prev_year_results", return_value=[]):
        resp = rs._do_build(151, None, None, {})
    row = resp.results[0]
    assert (row["surname"], row["name"], row["full_name"]) == ("Спортсмен", "", "Спортсмен")
    assert row["birthday"] is None and row["client_id"] is None
    assert row["start_number"] == 1013
```

- [ ] **Step 2: Убедиться, что падает**

Run: `conda run --no-capture-output -n base python -m pytest tests/unit/test_results_service_client_id.py -q`
Expected: FAIL — `assert ('Пцарев', 'Александр', ...) == ('Спортсмен', ...)`

- [ ] **Step 3: Маскировка в `assemble_event_results`**

В импорт `results_service.py` добавить:

```python
from src.krasmarafon.services.public_pd import mask_runner
```

Заменить `results.append({` … `})` (стр. 317 и до закрывающей скобки словаря) на сборку в переменную и маскировку:

```python
        item = {
            # ... все существующие ключи без изменений ...
        }
        results.append(mask_runner(item, runner.get('pd_refused')))
```

(тело словаря не менять — только `results.append({` → `item = {` и закрывающее `})` → `}` + строка `results.append(...)`.)

- [ ] **Step 4: Тест проходит**

Run: `conda run --no-capture-output -n base python -m pytest tests/unit/test_results_service_client_id.py -q`
Expected: `2 passed`

- [ ] **Step 5: Флаг в SQL результатов** — в `db_results.py` рядом с объявлением кешей:

```python
# Отказ от публикации ПД (leads.pd_refused) для строки results r — по заявке того же события и номера
PD_REFUSED_SQL = ("EXISTS (SELECT 1 FROM leads pl WHERE pl.event_id = r.event_id "
                  "AND pl.start_number = r.start_number AND pl.pd_refused = 1)")
```

В обоих SELECT после строки `r.rank_category_clean,` добавить строку:

```python
            {PD_REFUSED_SQL} AS pd_refused,
```

`get_race_results_by_event_id` уже f-строка. В `get_race_results_by_event_id_and_year` `query = """` → `query = f"""` (других `{` в запросе нет).

- [ ] **Step 6: Проверить запрос на локальной БД**

```bash
conda run --no-capture-output -n base python -c "
from dotenv import load_dotenv; load_dotenv('.env'); load_dotenv('.env.local', override=True)
from src.analytics.db_results import get_race_results_by_event_id, get_race_results_by_event_id_and_year
r = get_race_results_by_event_id(104); print(len(r), r[0]['pd_refused'] if r else None)
r = get_race_results_by_event_id_and_year('Жара', 2026); print(len(r), r[0]['pd_refused'] if r else None)"
```
Expected: число строк > 0 и `0` в обеих строках.

- [ ] **Step 7: Unit-тесты**

Run: `conda run --no-capture-output -n base python -m pytest tests/unit/ -q`
Expected: все проходят

- [ ] **Step 8: Commit**

```bash
git add src/analytics/db_results.py src/krasmarafon/services/results_service.py tests/unit/test_results_service_client_id.py
git commit -m "feat(pd): «Спортсмен» в результатах, трекере и SSE"
```

---

### Task 4: Рейтинги отрезков и статистика забега

**Files:**
- Modify: `src/analytics/db_results.py` — `get_event_segment_rankings` (~стр. 802), `get_race_stats_from_db` (~стр. 549, 647)
- Test: `tests/unit/test_public_pd_queries.py`

- [ ] **Step 1: Падающий тест**

```python
"""Публичные запросы db_results отдают флаг отказа и маскируют ФИ."""
from datetime import timedelta
from unittest.mock import MagicMock, patch

from src.analytics import db_results


def _conn(rows):
    cur = MagicMock()
    cur.fetchall.return_value = rows
    conn = MagicMock()
    conn.cursor.return_value = cur
    return conn, cur


def test_segment_rankings_mask_refused():
    rows = [{"result_id": 1, "segment_code": "kt1-kt2", "sg_time_clear": timedelta(minutes=5), "sg_time_gun": None,
             "sg_pace_avg": None, "sg_pace_avg_gun": None, "surname": "Иванов", "name": "Иван",
             "start_number": 7, "sex": "Мужчина", "category": "М", "pd_refused": 1}]
    conn, cur = _conn(rows)
    with patch.object(db_results, "get_pooled_connection", return_value=conn):
        out = db_results.get_event_segment_rankings(1, "kt1-kt2")
    assert "pd_refused" in cur.execute.call_args[0][0]
    assert (out[0]["surname"], out[0]["name"], out[0]["start_number"]) == ("Спортсмен", "", 7)


def test_race_stats_best_result_masked():
    rows = [{"surname": "Иванов", "name": "Иван", "sex": "Мужчина", "time_clear_finish": timedelta(minutes=20),
             "time_gun_finish": None, "finish_pace_avg_clean": timedelta(minutes=4), "finish_pace_avg_gun": None,
             "race_status": "Finished", "event_distance": 5, "event_year": 2026, "pd_refused": 1}]
    conn, cur = _conn(rows)
    db_results._stats_cache.clear()
    with patch.object(db_results, "get_pooled_connection", return_value=conn):
        out = db_results.get_race_stats_from_db("Тест статистики")
    best = out["distances"][0]["best_result"]
    assert (best["surname"], best["name"]) == ("Спортсмен", "")
```

(Перед Step 3 сверить ключи ответа `get_race_stats_from_db` — `distances` / `best_result` — по коду ниже стр. 660 и поправить пути в тесте, если названия другие.)

- [ ] **Step 2: Убедиться, что падает**

Run: `conda run --no-capture-output -n base python -m pytest tests/unit/test_public_pd_queries.py -q`
Expected: FAIL (в SQL нет `pd_refused`, ФИ не замаскированы)

- [ ] **Step 3: Реализация**

Импорт в начало `db_results.py`:

```python
from src.krasmarafon.services.public_pd import mask_runner
```

(Проверить отсутствие циклического импорта: `public_pd` ничего не импортирует.)

`get_event_segment_rankings` — запрос в f-строку и флаг:

```python
        query = f"""
        SELECT
            rs.result_id,
            rs.segment_code,
            rs.sg_time_clear, rs.sg_time_gun,
            rs.sg_pace_avg,   rs.sg_pace_avg_gun,
            rs.sg_rank_absolute,     rs.sg_rank_sex,     rs.sg_rank_category,
            rs.sg_rank_absolute_gun, rs.sg_rank_sex_gun, rs.sg_rank_category_gun,
            r.surname, r.name, r.start_number, r.sex, r.category,
            {PD_REFUSED_SQL} AS pd_refused
        FROM `result_segments` rs
        JOIN `results` r ON rs.result_id = r.id
        WHERE rs.event_id = %s AND rs.segment_code = %s
          AND rs.sg_time_clear IS NOT NULL
        ORDER BY rs.sg_time_clear ASC
        """
```

и в цикле `result.append(row)` → `result.append(mask_runner(row, row.pop('pd_refused', 0)))`.

`get_race_stats_from_db` — в SELECT (стр. ~551) `r.race_status, e.event_distance, e.event_year` → добавить `, {PD_REFUSED_SQL} AS pd_refused` (строку запроса сделать f-строкой); в построении `dist_best`:

```python
                            dist_best = mask_runner({
                                'surname': r.get('surname', ''),
                                'name': r.get('name', ''),
                                'time': _time_str(tc),
                                'pace': _pace_str(pace_sec_best),
                                'year': year,
                            }, r.get('pd_refused'))
```

- [ ] **Step 4: Тесты проходят**

Run: `conda run --no-capture-output -n base python -m pytest tests/unit/test_public_pd_queries.py tests/unit/ -q`
Expected: все проходят

- [ ] **Step 5: Commit**

```bash
git add src/analytics/db_results.py tests/unit/test_public_pd_queries.py
git commit -m "feat(pd): «Спортсмен» в рейтингах отрезков и статистике забега"
```

---

### Task 5: JSON топ-10 для трансляции

**Files:**
- Modify: `src/krasmarafon/services/live_top10_export.py` — `_query_top3` (~стр. 54), `_build_checkpoint` (~стр. 73)
- Test: `tests/unit/test_live_top10_export.py`

- [ ] **Step 1: Падающий тест** — дописать:

```python
def test_build_checkpoint_masks_refused():
    cur = MagicMock()
    cur.fetchall.return_value = [{"surname": "Иванов", "name": "Иван", "time_clear": timedelta(minutes=30),
                                  "pd_refused": 1}]
    conn = MagicMock()
    conn.cursor.return_value = cur
    cp = _build_checkpoint(conn, 1, code="finish", label="Финиш", time_col="time_clear_finish")
    assert cp["top3_male"][0]["full_name"] == "Спортсмен"
    assert "pd_refused" in cur.execute.call_args[0][0]
```

- [ ] **Step 2: Убедиться, что падает**

Run: `conda run --no-capture-output -n base python -m pytest tests/unit/test_live_top10_export.py -q`
Expected: FAIL — `'Иванов Иван' == 'Спортсмен'`

- [ ] **Step 3: Реализация**

```python
from src.analytics.db_results import PD_REFUSED_SQL
from src.krasmarafon.services.public_pd import mask_runner
```

`_query_top3`:

```python
        cur.execute(
            f"SELECT r.surname, r.name, r.{time_col} AS time_clear, {PD_REFUSED_SQL} AS pd_refused "
            f"FROM results r "
            f"WHERE r.event_id = %s AND r.sex = %s AND r.{time_col} IS NOT NULL "
            f"ORDER BY r.{time_col} ASC "
            f"LIMIT {_TOP_N}",
            (event_id, sex),
        )
```

`_build_checkpoint.build_list`:

```python
        return [
            mask_runner({
                "full_name": f"{rec['surname']} {rec['name']}".strip(),
                "time": _seconds_to_time_str(_td_to_seconds(rec["time_clear"])),
            }, rec.get("pd_refused"))
            for rec in rows
        ]
```

(Если `src.analytics.db_results` тянет тяжёлые импорты и ломает загрузчик — перенести `PD_REFUSED_SQL` в `public_pd.py` и импортировать оттуда в обоих местах.)

- [ ] **Step 4: Тесты проходят**

Run: `conda run --no-capture-output -n base python -m pytest tests/unit/test_live_top10_export.py -q`
Expected: все проходят

- [ ] **Step 5: Commit**

```bash
git add src/krasmarafon/services/live_top10_export.py tests/unit/test_live_top10_export.py
git commit -m "feat(pd): «Спортсмен» в live-JSON топ-10"
```

---

### Task 6: Дипломы

**Files:**
- Modify: `src/krasmarafon/services/diploma_service.py` — `get_participant_diploma_data` (~стр. 67), `get_diploma_data` return (~стр. 129)
- Test: `tests/unit/test_diploma_service.py`

- [ ] **Step 1: Падающие тесты** — дописать (сверить имя патча с существующими тестами файла):

```python
from datetime import timedelta
from unittest.mock import MagicMock, patch


def test_diploma_masks_refused():
    from src.krasmarafon.services import diploma_service as ds
    rows = [{"start_number": 5, "surname": "Иванов", "name": "Иван", "race_status": "Finished", "sex": "Мужчина",
             "category": "М", "time_clear_finish": timedelta(minutes=25), "rank_absolute": 1, "rank_sex": 1,
             "rank_category": 1, "event_name": "Весна", "pd_refused": 1}]
    with patch.object(ds, "get_race_results_by_event_id", return_value=rows):
        d = ds.get_diploma_data(1, "5")
    assert (d["surname"], d["name"]) == ("Спортсмен", "")


def test_participant_diploma_masks_refused():
    from src.krasmarafon.services import diploma_service as ds
    cur = MagicMock()
    cur.fetchone.return_value = {"surname": "Иванов", "name": "Иван", "sex": "Мужчина", "event_id": 1, "pd_refused": 1}
    conn = MagicMock()
    conn.cursor.return_value = cur
    with patch.object(ds, "get_pooled_connection", return_value=conn):
        d = ds.get_participant_diploma_data(10)
    assert (d["surname"], d["name"]) == ("Спортсмен", "")
    assert "pd_refused" in cur.execute.call_args[0][0]
```

- [ ] **Step 2: Убедиться, что падает**

Run: `conda run --no-capture-output -n base python -m pytest tests/unit/test_diploma_service.py -q`
Expected: FAIL

- [ ] **Step 3: Реализация**

```python
from src.krasmarafon.services.public_pd import mask_runner
```

`get_participant_diploma_data`: SELECT → `"SELECT surname, name, sex, event_id, pd_refused FROM leads WHERE id = %s"`; `return row` → `return mask_runner(row, row.get("pd_refused")) if row else row`.

`get_diploma_data`: `return {` … `}` → `return mask_runner({` … `}, target.get('pd_refused'))`.

- [ ] **Step 4: Тесты проходят**

Run: `conda run --no-capture-output -n base python -m pytest tests/unit/test_diploma_service.py -q`
Expected: все проходят

- [ ] **Step 5: Commit**

```bash
git add src/krasmarafon/services/diploma_service.py tests/unit/test_diploma_service.py
git commit -m "feat(pd): «Спортсмен» на публичных дипломах"
```

---

### Task 7: Профиль «История участия»

**Files:**
- Modify: `src/analytics/db_athletes.py:66-72` (`get_athlete_by_client`)
- Test: `tests/integration/test_lead_pd_refused.py` (в Task 9)

- [ ] **Step 1: Реализация** — исключить события с отказом:

```python
from src.analytics.db_results import PD_REFUSED_SQL
```

```python
        cursor.execute(
            f"""SELECT r.*, e.event_name, e.event_distance, e.event_year, e.event_date
               FROM results r
               LEFT JOIN events e ON r.event_id = e.id
               WHERE r.client_id = %s AND NOT {PD_REFUSED_SQL}
               ORDER BY e.event_year DESC, e.event_date DESC, r.id DESC""",
            (card["id"],),
        )
```

(Проверка — интеграционным тестом в Task 9.)

- [ ] **Step 2: Тесты профиля не сломаны**

Run: `conda run --no-capture-output -n base python -m pytest tests/integration/test_athletes_by_card_db.py tests/integration/test_athlete_api.py -q`
Expected: все проходят

- [ ] **Step 3: Commit**

```bash
git add src/analytics/db_athletes.py
git commit -m "feat(pd): события без согласия не попадают в публичный профиль"
```

---

### Task 8: Старые выдачи из race_data.json

**Files:**
- Modify: `src/krasmarafon/routers/api.py` — удалить `/api/analytics` (~стр. 332-350); `/api/race-stats` (~стр. 607-611)

- [ ] **Step 1: Убедиться, что `/api/analytics` нигде не вызывается**

Run: `grep -rn "api/analytics\b" static templates src tests --include=*.js --include=*.html --include=*.py | grep -v "analytics-export\|/api/analytics/"`
Expected: только объявление в `api.py` (и, возможно, тесты — удалить их вместе с эндпоинтом).

- [ ] **Step 2: Удалить эндпоинт `get_analytics`** и неиспользуемые после этого импорты (`AnalyticsResponse`, `Analytics`, `get_formatted_analytics` — только если больше нигде в файле не используются).

- [ ] **Step 3: `/api/race-stats` без ФИ** — в `best_runner` убрать `'full_name': r.get('fullName', ''),`:

```python
                    best_runner = {
                        'time': f"{int(ts//60)}:{int(ts%60):02d}",
                        'pace': r.get('intervalaverages_:::full-1:::'),
                    }
```

Проверить, что `static/js/race-analysis.js:154` (`distObj.best_result`) переживает отсутствие имени (выводит пусто, не `undefined`); при необходимости — `best.full_name || ''`.

- [ ] **Step 4: Unit-тесты**

Run: `conda run --no-capture-output -n base python -m pytest tests/unit/ -q`
Expected: все проходят

- [ ] **Step 5: Commit**

```bash
git add src/krasmarafon/routers/api.py static/js/race-analysis.js
git commit -m "fix(pd): убрать неиспользуемый /api/analytics, /api/race-stats без ФИ"
```

---

### Task 9: Сквозная проверка на локальной БД

**Files:**
- Test: `tests/integration/test_lead_pd_refused.py` (дописать)

- [ ] **Step 1: Тест** — заявка + результат с одним номером на тестовом событии; флаг → ФИ нет в публичных выдачах:

```python
from src.analytics.db_athletes import get_athlete_by_client
from src.analytics import db_results


def add_event_with_result(cur):
    cur.execute("INSERT INTO events (event_name, event_distance, event_year, event_date) VALUES (%s, 5, 2099, '2099-01-01')", (EV,))
    ev = cur.lastrowid
    lead = add_lead(cur)
    cur.execute("UPDATE leads SET event_id = %s, start_number = 9901 WHERE id = %s", (ev, lead))
    cur.execute("""INSERT INTO results (surname, name, birthday, sex, event_id, start_number, race_status,
                   time_gun_finish, rank_absolute) VALUES ('Тестпд', 'Иван', '1990-01-01', 'Мужчина', %s, 9901,
                   'Finished', '00:25:00', 1)""", (ev,))
    return ev, lead


def test_refused_hidden_everywhere(db):
    conn, cur = db
    ev, lead = add_event_with_result(cur)
    conn.commit()
    db_results._results_cache.clear()
    assert db_results.get_race_results_by_event_id(ev)[0]["pd_refused"] == 0

    set_lead_pd_refused(lead, True, "tester")
    db_results._results_cache.clear()
    row = db_results.get_race_results_by_event_id(ev)[0]
    assert row["pd_refused"] == 1

    cur.execute("SELECT client_id FROM results WHERE event_id = %s", (ev,))
    client = cur.fetchone()["client_id"]
    athlete, results = get_athlete_by_client(client)
    assert all(r["event_id"] != ev for r in results)
```

Дополнить `cleanup()` фикстуры удалением результатов и события:

```python
        cur.execute("SELECT id FROM events WHERE event_name = %s", (EV,))
        evs = [r["id"] for r in cur.fetchall()]
        if evs:
            ph = ",".join(map(str, evs))
            cur.execute(f"SELECT DISTINCT client_id FROM results WHERE event_id IN ({ph})")
            res_cards = [r["client_id"] for r in cur.fetchall() if r["client_id"]]
            cur.execute(f"DELETE FROM results WHERE event_id IN ({ph})")
            cur.execute(f"DELETE FROM events WHERE id IN ({ph})")
            if res_cards:
                cur.execute(f"DELETE FROM clients WHERE id IN ({','.join(map(str, res_cards))}) "
                            f"AND id NOT IN (SELECT client_id FROM leads) AND id NOT IN (SELECT client_id FROM results)")
```

(Сверить обязательные колонки `events`/`results` с `SHOW CREATE TABLE` на локальной БД и дополнить INSERT при ошибке.)

- [ ] **Step 2: Запуск**

Run: `conda run --no-capture-output -n base python -m pytest tests/integration/test_lead_pd_refused.py -q`
Expected: `3 passed`; повторный запуск — тоже (cleanup работает)

- [ ] **Step 3: Полный прогон**

Run: `conda run --no-capture-output -n base python -m pytest tests/unit/ -q` и `conda run --no-capture-output -n base python -m pytest tests/integration/ -q`
Expected: unit — все; integration — без новых падений относительно main

- [ ] **Step 4: Браузерная проверка на локальной БД** (`dev.ps1`): поставить флаг на реальную заявку прошедшего события в `/admin` → через ≤30 с на `/results` и трекере по номеру — «Спортсмен», без кнопки профиля; диплом `/diploma/{event_id}/{bib}` — «Спортсмен»; снять флаг — ФИ вернулись. Бейдж «Без ПД» и кнопка в админке.

- [ ] **Step 5: Commit**

```bash
git add tests/integration/test_lead_pd_refused.py
git commit -m "test(pd): сквозная проверка флага на локальной БД"
```

---

### Task 10: Выкладка (только с «да» пользователя)

- [ ] **Step 1:** миграция на прод: `conda run --no-capture-output -n base python -m deploy.ssh_apply_migrations migrations/lead_pd_refused.sql`; проверить колонку `SHOW COLUMNS FROM leads LIKE 'pd_refused'` на VPS.
- [ ] **Step 2:** проверить, что в `origin/main..main` только коммиты этой задачи (иначе — cherry-pick в отдельный worktree, как 2026-11-03 с `ma_*`); тесты — отдельной командой, **не** через `| tail && git push`.
- [ ] **Step 3:** `git push origin main`; `gh run watch` — test + deploy зелёные; `/health` 200; `/results` открывается.
- [ ] **Step 4:** Obsidian — перенести выполненную часть в архив Красмарафона, в приоритетах оставить части 2–5.
