# DataLens «Переходы дистанций» Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Заменить некорректный чарт «Переходы дистанций» набором виджетов на материализованной таблице `km_transitions`, которую раз в час пересчитывает событие MySQL.

**Architecture:** SQL-миграция создаёт процедуру `refresh_km_transitions()` (собирает `km_transitions_new` оконными `LAG` и атомарно подменяет таблицу), саму таблицу и событие `ev_refresh_km_transitions` (EVERY 1 HOUR). DataLens читает готовую таблицу через новый датасет; виджеты и связи вкладки «Мероприятия» правятся через Public API DataLens (скрипт `dl_api.py`, проверенный 2026-11-09). Код приложения не меняется.

**Tech Stack:** MySQL 8.0 (window functions, EVENT, stored procedure), pytest (интеграционный тест на локальной БД :3308), DataLens Public API (`api.datalens.tech/rpc/*`, токен `yc iam create-token`), MCP `datalens` для удалений.

**Spec:** `docs/superpowers/specs/2026-11-09-datalens-distance-transitions-design.md`

**Важно для исполнителя:**
- Локальная БД — MySQL80 порт **3308**, креды в `.env.local` (не `.env` — там прод). Тесты: `conda run -n base python -m pytest ...` (conftest подхватывает `.env.local`).
- Прод — только через `plink.exe` (Python-сокеты на порт 22 блокирует файрвол), креды — `deploy/_vps_config.py`.
- DataLens `updateDashboard`: **не передавать `entry.revId`** — запрос с revId молча откатывает правки.
- Любое удаление в DataLens — `invoke_privileged_command` MCP, только после бэкапа JSON объекта.

---

## File Structure

| Файл | Ответственность |
|---|---|
| `migrations/km_transitions.sql` (создать) | таблица, процедура пересчёта, первичное заполнение, событие |
| `tests/integration/test_km_transitions_db.py` (создать) | правила пар на тестовых данных локальной БД |
| `C:\Users\podbo\AppData\Local\Temp\claude\f8d68d3f8dfa3109\fae156e1-906c-4972-a489-50fc0bbfd9ff\scratchpad\dl_api.py` (есть) | вызов Public API DataLens: `DLV=2 python -I dl_api.py <method> <body.json> [out.json]` |
| `Claude outputs/datalens_backup_2026-11-09/` (есть) | бэкапы объектов DataLens до правок |

---

### Task 1: Миграция и тест на локальной БД

**Files:**
- Create: `tests/integration/test_km_transitions_db.py`
- Create: `migrations/km_transitions.sql`

- [ ] **Step 1: Написать падающий тест**

```python
"""km_transitions (migrations/km_transitions.sql) на локальной БД (.env.local): пары «тот же забег» и «любой забег».
Тестовые данные — события 2097–2099 «Тест переходов <суффикс> …», фамилия «Тестпереходов<суффикс>», убираются после теста."""
import uuid

import pytest

from src.analytics.db_pool import get_pooled_connection

RUN = uuid.uuid4().hex[:6].translate(str.maketrans("0123456789abcdef", "бвгджзклмнпрстфх"))
EV, SUR = f"Тест переходов {RUN}", f"Тестпереходов{RUN}"


@pytest.fixture
def db():
    conn = get_pooled_connection()
    if not conn:
        pytest.skip("Нет локальной БД")
    cur = conn.cursor(dictionary=True)
    cur.execute("SHOW PROCEDURE STATUS WHERE Db = DATABASE() AND Name = 'refresh_km_transitions'")
    if not cur.fetchall():
        pytest.fail("Нет процедуры refresh_km_transitions — примените migrations/km_transitions.sql к локальной БД")

    def cleanup():
        cur.execute("SELECT id FROM events WHERE event_name LIKE %s", (f"{EV}%",))
        evs = [r["id"] for r in cur.fetchall()]
        if evs:
            ph = ",".join(map(str, evs))
            cur.execute(f"DELETE FROM leads WHERE event_id IN ({ph})")
            cur.execute(f"DELETE FROM events WHERE id IN ({ph})")
        cur.execute("DELETE FROM clients WHERE surname = %s", (SUR,))
        conn.commit()

    cleanup()
    yield cur
    cleanup()
    cur.execute("CALL refresh_km_transitions()")   # убрать тестовые строки из km_transitions
    conn.commit()
    conn.close()


def _event(cur, name, dist, year, date):
    cur.execute("INSERT INTO events (event_name, event_distance, event_year, event_date) VALUES (%s, %s, %s, %s)",
                (name, dist, year, date))
    return cur.lastrowid


def _lead(cur, ev, event_name, dist_str, year, refund=0):
    cur.execute("""INSERT INTO leads (surname, name, sex, city, birthday, phone, email, event_name, event_distance,
                   event_year, products, amount, client_id, event_id, start_number, created_at, refund)
                   VALUES (%s, 'Иван', 'Мужчина', '', '1990-01-01', '+70000000099', 'tr@test.ru', %s, %s,
                           %s, '', 0, 0, %s, NULL, '2026-01-01 10:00:00', %s)""",
                (SUR, event_name, dist_str, year, ev, refund))


def _rows(cur):
    cur.execute("CALL refresh_km_transitions()")
    cur.execute("""SELECT t.* FROM km_transitions t JOIN clients c ON c.id = t.client_id
                   WHERE c.surname = %s ORDER BY t.event_year, t.event_name""", (SUR,))
    return cur.fetchall()


def test_same_event_pairs_take_longest_distance_and_skip_refunds(db):
    a = f"{EV} A"
    a97_2, a97_7 = _event(db, a, "2", 2097, "2097-12-06"), _event(db, a, "7", 2097, "2097-12-06")
    a98_2 = _event(db, a, "2", 2098, "2098-12-06")
    a99_7 = _event(db, a, "7", 2099, "2099-12-06")
    _lead(db, a97_2, a, "2 км", 2097)
    _lead(db, a97_7, a, "7 км", 2097)            # две дистанции в 2097 → берётся 7
    _lead(db, a98_2, a, "2 км", 2098)
    _lead(db, a99_7, a, "7 км", 2099, refund=1)  # возврат — участия нет
    rows = _rows(db)
    assert [(r["event_year"], float(r["dist"]), r["event_distance"]) for r in rows] == [(2097, 7.0, "7 км"), (2098, 2.0, "2 км")]
    first, second = rows
    assert first["same_direction"] == "Впервые на забеге" and first["same_prev_year"] is None
    assert second["same_prev_year"] == 2097 and float(second["same_prev_dist"]) == 7.0
    assert second["same_direction"] == "Сократили"


def test_any_event_pair_and_kids_race(db):
    kids, b = f"{EV} Детский забег", f"{EV} B"
    k = _event(db, kids, "1", 2097, "2097-06-01")
    b1 = _event(db, b, "2", 2097, "2097-08-01")
    b2 = _event(db, b, "5", 2098, "2098-08-01")
    _lead(db, k, kids, "1 км", 2097)
    _lead(db, b1, b, "2 км", 2097)
    _lead(db, b2, b, "5 км", 2098)
    rows = {(r["event_name"], r["event_year"]): r for r in _rows(db)}
    b97, b98 = rows[(b, 2097)], rows[(b, 2098)]
    assert (b97["any_prev_event"], b97["any_prev_year"], float(b97["any_prev_dist"])) == (kids, 2097, 1.0)
    assert b98["same_direction"] == "Выросли" and b98["any_prev_event"] == b


def test_kids_race_has_no_same_event_pair(db):
    kids = "Детский забег"
    # реальное название забега: правило «Детский забег → пары тот же забег нет» привязано к нему
    k1 = _event(db, kids, "0.5", 2097, "2097-06-01")
    k2 = _event(db, kids, "1", 2098, "2098-06-01")
    try:
        _lead(db, k1, kids, "500 м", 2097)
        _lead(db, k2, kids, "1 км", 2098)
        rows = [r for r in _rows(db) if r["event_name"] == kids]
        assert [r["same_direction"] for r in rows] == [None, None]
        assert rows[1]["any_prev_event"] == kids          # пара «любой забег» есть
    finally:
        db.execute("DELETE FROM leads WHERE event_id IN (%s, %s)", (k1, k2))
        db.execute("DELETE FROM events WHERE id IN (%s, %s)", (k1, k2))
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `conda run -n base python -m pytest tests/integration/test_km_transitions_db.py -v`
Expected: 3 FAILED с «Нет процедуры refresh_km_transitions».

- [ ] **Step 3: Написать миграцию `migrations/km_transitions.sql`**

```sql
-- Переходы дистанций для DataLens (2026-11-09, spec docs/superpowers/specs/2026-11-09-datalens-distance-transitions-design.md).
-- Одна строка на участие человека в забеге в году; пары «тот же забег» и «любой забег» — оконными LAG.
-- Считается ~3 с, поэтому таблица материализуется и пересчитывается событием раз в час (event_scheduler = ON).
-- Применять от root: mysql -u root krasmarafon < migrations/km_transitions.sql

CREATE TABLE IF NOT EXISTS km_transitions (
    client_id       INT UNSIGNED  NOT NULL,
    event_name      VARCHAR(255)  NOT NULL,
    event_year      INT           NOT NULL,
    event_distance  VARCHAR(64)   NULL,
    dist            DECIMAL(5,1)  NULL,
    same_prev_year  INT           NULL,
    same_prev_dist  DECIMAL(5,1)  NULL,
    same_direction  VARCHAR(32)   NULL,
    any_prev_event  VARCHAR(255)  NULL,
    any_prev_year   INT           NULL,
    any_prev_dist   DECIMAL(5,1)  NULL,
    refreshed_at    DATETIME      NOT NULL,
    PRIMARY KEY (client_id, event_name, event_year),
    KEY idx_event (event_name, event_year)
) DEFAULT CHARSET = utf8mb4;

DROP PROCEDURE IF EXISTS refresh_km_transitions;
DELIMITER //
CREATE DEFINER = `root`@`localhost` PROCEDURE refresh_km_transitions()
BEGIN
    DROP TABLE IF EXISTS km_transitions_new;
    CREATE TABLE km_transitions_new LIKE km_transitions;
    INSERT INTO km_transitions_new
        (client_id, event_name, event_year, event_distance, dist, same_prev_year, same_prev_dist,
         same_direction, any_prev_event, any_prev_year, any_prev_dist, refreshed_at)
    WITH occ AS (
        SELECT l.client_id, l.event_name, CAST(l.event_year AS UNSIGNED) AS event_year,
               MIN(COALESCE(e.event_date, MAKEDATE(CAST(l.event_year AS UNSIGNED), 183))) AS ev_date,
               MAX(e.event_distance + 0) AS dist,
               SUBSTRING_INDEX(GROUP_CONCAT(l.event_distance ORDER BY e.event_distance + 0 DESC SEPARATOR '|'), '|', 1)
                   AS event_distance
        FROM leads l JOIN events e ON l.event_id = e.id
        WHERE l.refund = 0 AND l.client_id > 0
        GROUP BY l.client_id, l.event_name, l.event_year
    ), w AS (
        SELECT occ.*,
               LAG(event_year) OVER (PARTITION BY client_id, event_name ORDER BY event_year) AS same_prev_year,
               LAG(dist)       OVER (PARTITION BY client_id, event_name ORDER BY event_year) AS same_prev_dist,
               LAG(event_name) OVER (PARTITION BY client_id ORDER BY ev_date, event_year, event_name) AS any_prev_event,
               LAG(event_year) OVER (PARTITION BY client_id ORDER BY ev_date, event_year, event_name) AS any_prev_year,
               LAG(dist)       OVER (PARTITION BY client_id ORDER BY ev_date, event_year, event_name) AS any_prev_dist
        FROM occ
    )
    SELECT client_id, event_name, event_year, event_distance, dist,
           IF(event_name = 'Детский забег', NULL, same_prev_year),
           IF(event_name = 'Детский забег', NULL, same_prev_dist),
           CASE WHEN event_name = 'Детский забег' THEN NULL
                WHEN same_prev_dist IS NULL THEN 'Впервые на забеге'
                WHEN dist > same_prev_dist THEN 'Выросли'
                WHEN dist < same_prev_dist THEN 'Сократили'
                ELSE 'Та же дистанция' END,
           any_prev_event, any_prev_year, any_prev_dist, NOW()
    FROM w;
    DROP TABLE IF EXISTS km_transitions_old;
    RENAME TABLE km_transitions TO km_transitions_old, km_transitions_new TO km_transitions;
    DROP TABLE km_transitions_old;
END //
DELIMITER ;

CALL refresh_km_transitions();

DROP EVENT IF EXISTS ev_refresh_km_transitions;
CREATE DEFINER = `root`@`localhost` EVENT ev_refresh_km_transitions
    ON SCHEDULE EVERY 1 HOUR STARTS CURRENT_TIMESTAMP + INTERVAL 5 MINUTE
    DO CALL refresh_km_transitions();
```

- [ ] **Step 4: Применить к локальной БД**

Run (Git Bash, пароль из `.env.local`):
```bash
cd "C:/Users/podbo/Работа/КРАСМАРАФОН/KM_track"
PW=$(grep '^DB_PASSWORD=' .env.local | cut -d= -f2-)
"/c/Program Files/MySQL/MySQL Server 8.0/bin/mysql.exe" -h 127.0.0.1 -P 3308 -u root -p"$PW" --default-character-set=utf8mb4 krasmarafon < migrations/km_transitions.sql
"/c/Program Files/MySQL/MySQL Server 8.0/bin/mysql.exe" -h 127.0.0.1 -P 3308 -u root -p"$PW" krasmarafon -e "SELECT COUNT(*), MAX(refreshed_at) FROM km_transitions; SHOW EVENTS LIKE 'ev_refresh_km_transitions';"
```
Expected: `COUNT(*)` ≈ 50–55 тыс. (людей-участий меньше заявок), событие `ENABLED`.

- [ ] **Step 5: Запустить тесты — проходят**

Run: `conda run -n base python -m pytest tests/integration/test_km_transitions_db.py -v`
Expected: 3 passed. Если упало на `event_distance + 0` для «0.5»/«21.1» — проверить тип `events.event_distance` (`SHOW COLUMNS FROM events LIKE 'event_distance'`) и поправить приведение.

- [ ] **Step 6: Сверка с контрольными цифрами (локальная БД — снимок от 2026-10-06, цифры будут меньше прода)**

Run:
```bash
"/c/Program Files/MySQL/MySQL Server 8.0/bin/mysql.exe" -h 127.0.0.1 -P 3308 -u root -p"$PW" krasmarafon -e "SELECT same_direction, COUNT(*) FROM km_transitions WHERE event_name='Снежная семерка' AND event_year=2026 GROUP BY 1;"
```
Expected: 4 группы (`Впервые на забеге`, `Та же дистанция`, `Выросли`, `Сократили`), числа того же порядка, что в спеке.

- [ ] **Step 7: Полный прогон unit-тестов и коммит**

Run: `conda run -n base python -m pytest tests/unit/ -q`
Expected: all passed.
```bash
git add migrations/km_transitions.sql tests/integration/test_km_transitions_db.py
git commit -m "feat(analytics): km_transitions — переходы дистанций для DataLens"
```

---

### Task 2: Применить на проде

**Files:** — (только прод)

- [ ] **Step 1: Применить миграцию от root через plink**

```bash
cd "C:/Users/podbo/Работа/КРАСМАРАФОН/KM_track"
python - <<'EOF'
import subprocess, sys
sys.path.insert(0, ".")
from deploy._vps_config import VPS_HOST, VPS_USER, VPS_PASSWORD
sql = open("migrations/km_transitions.sql", "rb").read()
r = subprocess.run([r"C:\Program Files\PuTTY\plink.exe", "-ssh", "-batch", "-pw", VPS_PASSWORD, f"{VPS_USER}@{VPS_HOST}",
                    "mysql -u root --default-character-set=utf8mb4 krasmarafon"], input=sql, capture_output=True, timeout=180)
print(r.returncode, r.stdout.decode(errors="replace"), r.stderr.decode(errors="replace"))
EOF
```
Expected: `0`, без ошибок.

- [ ] **Step 2: Проверить таблицу, событие и права DataLens**

```bash
python - <<'EOF'
import subprocess, sys
sys.path.insert(0, ".")
from deploy._vps_config import VPS_HOST, VPS_USER, VPS_PASSWORD
q = ("SELECT COUNT(*), MAX(refreshed_at) FROM krasmarafon.km_transitions;"
     "SELECT same_direction, COUNT(*) FROM krasmarafon.km_transitions WHERE event_name='Снежная семерка' AND event_year=2026 GROUP BY 1;"
     "SHOW EVENTS FROM krasmarafon LIKE 'ev_refresh_km_transitions';"
     "SHOW GRANTS FOR 'datalens_ro'@'%';")
r = subprocess.run([r"C:\Program Files\PuTTY\plink.exe", "-ssh", "-batch", "-pw", VPS_PASSWORD, f"{VPS_USER}@{VPS_HOST}",
                    f'mysql -u root -e "{q}"'], capture_output=True, timeout=120)
print(r.stdout.decode(errors="replace"), r.stderr.decode(errors="replace"))
EOF
```
Expected: строк ≈ 55 тыс.; по Снежной 2026 — `Впервые на забеге` ≈ 230, `Та же дистанция` ≈ 188, `Выросли` ≈ 9, `Сократили` ≈ 6 (по людям может быть чуть меньше); событие `ENABLED`, `EVERY 1 HOUR`; у `datalens_ro` есть `SELECT ON krasmarafon.*`.

- [ ] **Step 3: Через ~6 минут убедиться, что событие сработало**

Повторить запрос `SELECT MAX(refreshed_at) FROM krasmarafon.km_transitions` — время обновилось (событие стартует через 5 мин после создания).

---

### Task 3: Датасет `km_transitions` в DataLens

**Files:** `scratchpad/w/create_ds.json` (рабочий)

- [ ] **Step 1: Узнать схему `createDataset`**

MCP `describe_commands(["createDataset"])` — результат большой, читать из файла `tool-results`, нужны поля `data.dataset.sources[]` (`source_type: MYSQL_TABLE`, `parameters: {db_name, table_name}`, `connection_id`), `source_avatars[]`, `result_schema[]` и `workbook_id`/`name`.

- [ ] **Step 2: Собрать тело по образцу существующего табличного датасета**

Образец — `km_clients` (источник `MYSQL_TABLE clients` на подключении `qke7wvinjzs0a`): взять из `scratchpad/dl/dataset_v7jgd1n51f6mf.json` блоки `sources[0]` и `source_avatars[0]`, заменить `table_name` на `km_transitions`, `title` на `km_transitions`, новые `id` (uuid4) для source и avatar, `result_schema: []` (DataLens заполнит поля сам при валидации). Имя датасета — `km_transitions`, воркбук `tnh9eu5ziv8md`.

- [ ] **Step 3: Валидировать и создать**

```bash
cd "C:/Users/podbo/AppData/Local/Temp/claude/f8d68d3f8dfa3109/fae156e1-906c-4972-a489-50fc0bbfd9ff/scratchpad"
DLV=2 python -I dl_api.py validateDataset w/val_new_ds.json w/val_new_ds_res.json
```
Expected: `code: OK`, в `result_schema` 12 полей таблицы. Затем `createDataset` (через MCP `invoke_write_command`) с телом из валидации; запомнить `datasetId`.

- [ ] **Step 4: Проверить**

`getDataset` нового id: 12 полей, `component_errors` пусто; `getDatasetData` (MCP read) по полям `event_name`, `same_direction` — данные есть.

---

### Task 4: Виджеты

**Files:** `scratchpad/w/chart_*.json` (рабочие)

Шаблоны — существующие чарты того же типа (взять `data` из `scratchpad/dl/widget_*.json`, заменить `datasetsIds`, `datasetsPartialFields`, поля в `visualization.placeholders`, `filters`):
- индикатор — `widget_kw9h2xt2wojg4.json` («Ф3 - Количество заявок», metric_wizard_node);
- таблица — `widget_eq3e9ve9c1xky.json` («Ф7 - Эффективность промокодов», table_wizard_node).

- [ ] **Step 1: Индикаторы (4 шт.)**

Для каждого `createWizardChart` (имя, фильтр чарта, показатель `COUNT([client_id])` — строка таблицы = одно участие человека):
| Имя | Фильтр чарта |
|---|---|
| `П1 - Выросли` | `same_direction` = `Выросли` |
| `П2 - Сократили` | `same_direction` = `Сократили` |
| `П3 - Та же дистанция` | `same_direction` = `Та же дистанция` |
| `П4 - Впервые на забеге` | `same_direction` = `Впервые на забеге` |

Индикатор показывает одно число, поэтому доли — отдельной таблицей в одну строку (Step 1a).

- [ ] **Step 1a: Таблица долей `П7 - Доли повторных участников`**

`createWizardChart` табличный, без измерений, три локальных показателя (условные агрегаты одного уровня — без FIXED/AMONG; строка таблицы = одно участие человека, поэтому COUNT по строкам = люди):
```
Выросли, %          = COUNT_IF([client_id], [same_direction] = "Выросли") * 100.0 / COUNT_IF([client_id], [same_prev_dist] IS NOT NULL)
Сократили, %        = COUNT_IF([client_id], [same_direction] = "Сократили") * 100.0 / COUNT_IF([client_id], [same_prev_dist] IS NOT NULL)
Та же дистанция, %  = COUNT_IF([client_id], [same_direction] = "Та же дистанция") * 100.0 / COUNT_IF([client_id], [same_prev_dist] IS NOT NULL)
```
Формат — 1 знак после запятой, постфикс «%».

- [ ] **Step 2: Матрица «было → стало»**

`createWizardChart`, тип визуализации — сводная таблица (`pivotTable`; если API не принимает — обычная таблица с колонками `same_prev_dist`, `dist`, `Люди`). Строки — `same_prev_dist`, столбцы — `dist`, показатель — `COUNT([client_id])`, фильтр чарта — `same_prev_dist` не пусто, итоги по строкам и столбцам включены. Имя `П5 - Было → стало (тот же забег)`.

- [ ] **Step 3: Таблица потоков**

`createWizardChart` табличный: колонки `any_prev_event`, `any_prev_dist`, `dist`, `Люди` = `COUNT([client_id])`; фильтр чарта — локальное поле `Другой забег` = `[any_prev_event] != [event_name]` равно `true`; сортировка по `Люди` убыв. Имя `П6 - Пришли с других забегов`.

- [ ] **Step 4: Fallback, если `createWizardChart` (experimental) не принимает тело**

Остановиться и дать пользователю пошаговую инструкцию по сборке П1–П7 в мастере чартов DataLens с теми же полями/фильтрами (≈15 мин), затем продолжить с Task 5.

- [ ] **Step 5: Проверить каждый чарт**

`getWizardChart` каждого id — `valid` у всех полей; данные — через Task 6 (embed run).

---

### Task 5: Вкладка «Мероприятия»

**Files:** `scratchpad/w/upd_dash_tr.json` (рабочий), бэкап `Claude outputs/datalens_backup_2026-11-09/dashboard_before_transitions.json`

- [ ] **Step 1: Бэкап и свежий дашборд**

```bash
cd "C:/Users/podbo/AppData/Local/Temp/claude/f8d68d3f8dfa3109/fae156e1-906c-4972-a489-50fc0bbfd9ff/scratchpad"
DLV=2 python -I dl_api.py getDashboard w/get_dash.json w/dash_tr_before.json > /dev/null
cp w/dash_tr_before.json "C:/Users/podbo/Работа/КРАСМАРАФОН/KM_track/Claude outputs/datalens_backup_2026-11-09/dashboard_before_transitions.json"
```

- [ ] **Step 2: Собрать изменения скриптом**

На вкладке `title == "Мероприятия"`:
- заменить виджет `jVW` (чарт `1dptx5bwmbxil`) виджетами П1–П7: новые item-id из `data.counter` (+1 на каждый, обновить `counter`), элементы `{"type": "widget", "namespace": "default", "data": {"hideTitle": false, "tabs": [{"id": <новый>, "title": <имя>, "chartId": <id>, "isDefault": true, "params": {}, "autoHeight": true, "description": "", "enableDescription": false, "hint": "", "enableHint": false}]}}`;
- раскладка (`layout`, сетка шириной 36): 4 индикатора в ряд `w=9,h=6` на месте старого виджета, под ними таблица долей П7 `w=36,h=4`, ниже матрица `w=18,h=14` и таблица потоков `w=18,h=14`;
- `aliases.default`: удалить `["event_year_myhe", "from_distance_ofgi"]`; добавить пары guid полей km_leads ↔ km_transitions: `event_year`, `event_name`, `event_distance` (guid km_leads: `event_year_jr76`, `event_name_2iel`, `event_distance_6efj`; guid km_transitions — из Task 3);
- `connections`: удалить элементы с `kind: "ignore"` между `XXA` и `271`.
Тело: `{"entry": {"entryId", "data", "meta"}, "mode": "publish"}` — **без revId**.

- [ ] **Step 3: Отправить и проверить**

```bash
DLV=2 python -I dl_api.py updateDashboard w/upd_dash_tr.json w/dash_tr_res.json > /dev/null
DLV=2 python -I dl_api.py getDashboard w/get_dash.json w/dash_tr_after.json > /dev/null
```
Скриптом сравнить: изменилась только вкладка «Мероприятия», новый `revId`, виджеты П1–П7 на месте, алиасы как задумано.

---

### Task 6: Проверка

- [ ] **Step 1: Все виджеты строятся**

```bash
"C:/Users/podbo/miniconda3/python.exe" "C:/Users/podbo/AppData/Local/Temp/claude/f8d68d3f8dfa3109/fae156e1-906c-4972-a489-50fc0bbfd9ff/scratchpad/run_all_charts.py" | tail -3
```
Expected: `ИТОГО ok 62 bad 0` (56 − 1 старый + 7 новых; старый снят с дашборда и не прогоняется).

- [ ] **Step 2: Селекторы фильтруют новые виджеты**

Через `dash_export.run_chart(<id П4>, {"event_name_2iel": ["Снежная семерка"], "event_year_jr76": ["2026"]}, <tab_id Мероприятий>)` — значение «Впервые на забеге» совпадает с SQL Task 2 Step 2 (≈230); без параметров — больше (все забеги).

- [ ] **Step 3: Нагрузка**

`SHOW GLOBAL STATUS LIKE 'Max_execution_time_exceeded'` на проде — не вырос относительно значения до Task 5.

---

### Task 7: Уборка и документация

- [ ] **Step 1: Удалить старый чарт и датасет (после Task 6)**

Бэкапы уже лежат в `scratchpad/dl/widget_1dptx5bwmbxil.json`, `dataset_mx42k9w98oi06.json` — скопировать в `Claude outputs/datalens_backup_2026-11-09/`. Проверить `getEntriesRelations` — связей с дашбордом нет. MCP `invoke_privileged_command`: `deleteWizardChart {"chartId": "1dptx5bwmbxil"}`, `deleteDataset {"datasetId": "mx42k9w98oi06"}`.

- [ ] **Step 2: Obsidian**

`knowledge/integrations/datalens-inspekciya-2026-11-09.md` — п.6 выполнен (ссылка на spec/план); `knowledge/integrations/datalens-obzor-dashborda.md` — вкладка «Мероприятия»: новые виджеты, датасет `km_transitions`, пересчёт раз в час; `00-home/текущие приоритеты.md` — отметить.

- [ ] **Step 3: Коммит плана/отметок**

```bash
git add docs/superpowers/plans/2026-11-09-datalens-distance-transitions.md .taskmaster/tasks/todo.md
git commit -m "docs(plan): DataLens — переходы дистанций выполнены"
```
