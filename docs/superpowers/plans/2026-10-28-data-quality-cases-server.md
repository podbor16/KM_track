# «Качество данных»: дела и вопросы (сервер) — план реализации (этап 2 из 3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Сервер отдаёт находки «Качества данных» как **дела о людях** с **вопросами** человеческим языком; ответ на вопрос выполняет цепочку действий целиком (с журналом и отменой). Старый UI продолжает работать до этапа 3.

**Architecture:** `src/analytics/data_quality.py` (1257 строк) делится на `dq_checks.py` (данные, правила, проверки) и `dq_actions.py` (действия, журнал, отмена), `data_quality.py` остаётся фасадом-реэкспортом. Новый `dq_cases.py`: группировка находок в дела, ступени, построение вопросов, применение ответа, откладывание. Новые эндпоинты — в существующем `src/krasmarafon/routers/data_quality.py`.

**Tech Stack:** Python 3.13, FastAPI 0.104, mysql-connector (без ORM), pytest.

Спецификация: `docs/superpowers/specs/2026-10-28-data-quality-cases-design.md` → «Этап 2».

Уточнение к спецификации (принято при планировании): вход «дело по человеку» — `GET /api/admin/data-quality/person/{client_id}` (поиск карточки по ФИО уже есть: `GET /api/admin/data-quality/cards?q=`).

---

## Общее

- Тесты: `C:/Users/podbo/miniconda3/python.exe -m pytest <путь> -q -p no:warnings` из корня репозитория (если `conda run` не зависает — можно и им). Интеграционные тесты сами берут локальную БД из `.env.local` (`tests/conftest.py`), не прод.
- Тестовые данные в БД — только на событиях 2099 года с уникальными фамилиями, с уборкой до и после (образец — фикстура `db` в `tests/integration/test_data_quality_undo.py`).
- Каждый коммит заканчивается строкой `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Python, генерирующий код через строки, не использовать для правки JS/шаблонов (в этом этапе их нет).

## Файлы

| Файл | Ответственность |
|---|---|
| `src/analytics/dq_checks.py` (новый) | `Finding`, `Data`, `load`, правила (`cat_rule`, `real_bd`, …), все `check_*`, `run_checks(data, event_ids=None, card_ids=None)` |
| `src/analytics/dq_actions.py` (новый) | решения, `finding_view`, `edit_record_view`, `merge_cards`, `move_row`, `edit_record`, `fix_fio`, `delete_result`, `dismiss`, `apply_auto`, журнал, `undo_action`, `search_cards` |
| `src/analytics/data_quality.py` | фасад: `from dq_checks import *`, `from dq_actions import *` |
| `src/analytics/dq_cases.py` (новый) | дела, ступени, вопросы, `apply_answer`, `postpone_case`, `list_cases`, `get_case`, `case_for_card` |
| `src/krasmarafon/routers/data_quality.py` | + 5 эндпоинтов дел |
| `tests/unit/test_dq_cases.py` (новый) | группировка, ступени, вопросы — без БД |
| `tests/integration/test_dq_cases_db.py` (новый) | ответы и цепочки на локальной БД + сквозные проверки страниц |
| `tests/integration/test_admin_dq_cases.py` (новый) | API дел (БД замокана) |

---

### Task 1: Разделить `data_quality.py` на `dq_checks.py` и `dq_actions.py`

Чистый перенос кода без изменений поведения. Граница — строка-маркер `# ---------------------------------------------------------------- решения и действия (dq_decisions, dq_actions)` (сейчас строка 537).

**Files:**
- Create: `src/analytics/dq_checks.py`, `src/analytics/dq_actions.py`
- Modify: `src/analytics/data_quality.py` (становится фасадом)
- Modify: `tests/unit/test_data_quality.py:221, 234` (цель подмены `apply_merge`)

- [ ] **Step 1: Зафиксировать «до»** — полный прогон, запомнить число passed.

Run: `C:/Users/podbo/miniconda3/python.exe -m pytest tests/unit/ tests/integration/ -q -p no:warnings`
Expected: все passed (на момент плана — 1284).

- [ ] **Step 2: Создать `src/analytics/dq_checks.py`**

Содержимое = строки `data_quality.py` от начала файла **до** строки-маркера (не включая её), с заменой docstring модуля на:

```python
"""
Проверки привязки заявок и результатов к карточкам клиентов (только чтение): данные, правила, находки.

Карточку триггеры ищут по точному «фамилия + имя + ДР» (результат — сначала
через заявку того же забега с тем же номером, см. migrations/results_link_via_lead.sql),
поэтому заглушка ДР в протоколе, опечатка или «Ира» вместо «Ирина» создают новую
карточку. Проверки находят такие случаи; предохранители говорят, когда склеивать
нельзя. Правило ДР: хронометраж важнее заявки (решение пользователя 2026-10-01).
Действия по находкам — src/analytics/dq_actions.py, дела и вопросы — src/analytics/dq_cases.py.
"""
```

Импорты оставить те, что нужны проверкам. Удалить из `dq_checks.py` импорты, которые используются только в нижней части (`json`, `os`, `tempfile`, `apply_merge`, `recompute_aggregates`, `recompute_duplicates`, `normalize_person_name`) — проверить командой из Step 5.

- [ ] **Step 3: Создать `src/analytics/dq_actions.py`**

Содержимое = строки от строки-маркера до конца `data_quality.py`, сверху:

```python
"""
Действия по находкам «Качества данных»: решения (dq_decisions), склейка, перенос строки, правка полей,
удаление «Not started», ФИО в канонический вид; журнал dq_actions и отмена любого действия.
"""

import collections
import dataclasses
from datetime import datetime
import json
import os
import re
import tempfile

from src.analytics.client_merge import apply as apply_merge, recompute_aggregates
from src.analytics.db_results import recompute_duplicates
from src.analytics.dq_checks import (NOT_STARTED, SHORT_NAMES, cat_rule, fio_key, load, merge_blockers,
                                     propose_birthday, real_bd, run_checks)
from src.common.names import norm, normalize_person_name
```

(Если Step 5 покажет ещё неопределённые имена — добавить их в этот импорт из `dq_checks` или `src.common.names`.)

- [ ] **Step 4: `src/analytics/data_quality.py` → фасад**

Весь файл:

```python
"""
Фасад «Качества данных» (обратная совместимость импортов): проверки — dq_checks, действия — dq_actions,
дела и вопросы — dq_cases.
"""

from src.analytics.dq_actions import *  # noqa: F401,F403
from src.analytics.dq_checks import *  # noqa: F401,F403
```

- [ ] **Step 5: Нет неопределённых и лишних имён**

Run: `C:/Users/podbo/miniconda3/python.exe -m pyflakes src/analytics/dq_checks.py src/analytics/dq_actions.py`
(если `pyflakes` не установлен: `C:/Users/podbo/miniconda3/python.exe -m pip install pyflakes`)
Expected: нет `undefined name`; `imported but unused` — убрать такой импорт.

- [ ] **Step 6: Цель подмены в двух unit-тестах**

В `tests/unit/test_data_quality.py` заменить оба `patch("src.analytics.data_quality.apply_merge"` на `patch("src.analytics.dq_actions.apply_merge"`.

- [ ] **Step 7: Полный прогон — то же число passed, что в Step 1**

Run: `C:/Users/podbo/miniconda3/python.exe -m pytest tests/unit/ tests/integration/ -q -p no:warnings`
Также: `C:/Users/podbo/miniconda3/python.exe scripts/data_quality.py --help` (скрипт импортирует `apply_auto`, `pending_findings` из фасада) — без ImportError.

- [ ] **Step 8: Commit**

```bash
git add src/analytics/dq_checks.py src/analytics/dq_actions.py src/analytics/data_quality.py tests/unit/test_data_quality.py
git commit -m "refactor(data-quality): проверки — dq_checks, действия — dq_actions, data_quality — фасад"
```

---

### Task 2: `run_checks` по картам дела и дата события в `Data`

**Files:**
- Modify: `src/analytics/dq_checks.py` (`load`, `run_checks`)
- Test: `tests/unit/test_dq_cases.py` (новый)

- [ ] **Step 1: Падающий тест** — `tests/unit/test_dq_cases.py`:

```python
"""Дела и вопросы «Качества данных» (src/analytics/dq_cases.py) — без БД."""
import datetime

from src.analytics.dq_checks import Data, run_checks
from src.common.names import Names

EVENTS = [
    {"id": 10, "event_name": "Детский забег", "event_distance": 1.0, "event_year": 2016, "event_date": datetime.date(2016, 8, 28)},
    {"id": 11, "event_name": "Жара", "event_distance": 21.1, "event_year": 2016, "event_date": datetime.date(2016, 8, 27)},
    {"id": 12, "event_name": "Детский забег", "event_distance": 1.0, "event_year": 2015, "event_date": None},
]


def C(i, s, n, bd):
    return {"id": i, "surname": s, "name": n, "birthday": bd}


def R(i, cid, s, n, bd, eid, bib, cat="", status="Finished", sex="Мужчина"):
    return {"id": i, "client_id": cid, "surname": s, "name": n, "birthday": bd, "sex": sex, "event_id": eid,
            "start_number": bib, "category": cat, "race_status": status}


def L(i, cid, s, n, bd, eid, dist="1 км", bib=None):
    return {"id": i, "client_id": cid, "surname": s, "name": n, "birthday": bd, "sex": "Мужчина", "event_id": eid,
            "event_distance": dist, "start_number": bib}


def data(clients, leads=(), results=()):
    d = Data(list(clients), list(leads), list(results), EVENTS)
    d.names = Names([("Пцарев", "Александр", "Мужчина"), ("Пцарев", "Марк", "Мужчина")] * 5)
    return d


# Пцаревы (реальный случай 2026-10-28): детский результат 2016 на карточке отца, сын — «Саша» + заглушка
def pcarev():
    clients = [C(1, "Пцарев", "Александр", "1980-03-09"), C(2, "Пцарев", "Саша", "2013-12-20"),
               C(3, "Пцарев", "Александр", "2013-01-01"), C(4, "Пцарев", "Марк", "2006-06-20")]
    results = [R(100, 1, "Пцарев", "Александр", "1980-03-09", 11, 3470, "М35-39"),
               R(101, 1, "Пцарев", "Александр", "1980-03-09", 10, 1012, "Мальчики 2005 г.р. и младше"),
               R(102, 4, "Пцарев", "Марк", "2006-06-20", 10, 1013, "Мальчики 2005 г.р. и младше"),
               R(103, 3, "Пцарев", "Александр", "2013-01-01", 12, 104, "Мальчики")]
    return data(clients, results=results)


def test_run_checks_card_scope_keeps_only_findings_of_these_cards():
    d = pcarev()
    every = run_checks(d)
    scoped = run_checks(d, card_ids={1, 2})
    assert scoped and all(set(f.client_ids) & {1, 2} for f in scoped)
    assert {f.key for f in scoped} <= {f.key for f in every}
    assert any(f.code == "R-FOREIGN" and f.result_id == 101 for f in scoped)
```

- [ ] **Step 2: Запустить — падает** (`TypeError: run_checks() got an unexpected keyword argument 'card_ids'`).

Run: `C:/Users/podbo/miniconda3/python.exe -m pytest tests/unit/test_dq_cases.py -q -p no:warnings`

- [ ] **Step 3: `run_checks` с `card_ids`** — в `src/analytics/dq_checks.py` заменить функцию целиком:

```python
def run_checks(data, event_ids=None, card_ids=None):
    """Без event_ids — вся база (двойники — для карточек с результатами); с event_ids —
    результаты этих забегов, двойники — и для карточек их заявок (проверка после импорта).
    card_ids — только находки, касающиеся этих карточек (дело после ответа на вопрос)."""
    results = [r for r in data.results if not event_ids or r["event_id"] in event_ids]
    leads = [l for l in data.leads if not event_ids or l["event_id"] in event_ids]
    if card_ids:
        results = [r for r in results if r["client_id"] in card_ids]
        leads = [l for l in leads if l["client_id"] in card_ids]
    cards = {r["client_id"] for r in results}
    if event_ids:
        cards |= {l["client_id"] for l in leads}
    if card_ids:
        cards = set(card_ids)
    cards = sorted(cards)
    found = (check_lead_on_other_card(data, results) + check_duplicates(data, results) + check_result_vs_card(data, results)
             + check_category(data, results) + check_twins(data, cards) + check_hygiene(data, results)
             + check_kids_leads(data, event_ids, from_year=datetime.now().year) + check_foreign(data, results, leads))
    if card_ids:
        found = [f for f in found if set(f.client_ids) & set(card_ids)]
    return found
```

(Сверить с текущей `run_checks`: поведение без `card_ids` не меняется — те же вызовы `check_*`, `check_kids_leads` — с теми же аргументами, что сейчас.)

- [ ] **Step 4: `event_date` в `load`** — в `load()` заменить
`cur.execute("SELECT id, event_name, event_distance, event_year FROM events")`
на
`cur.execute("SELECT id, event_name, event_distance, event_year, event_date FROM events")`.

- [ ] **Step 5: Запустить** `tests/unit/test_dq_cases.py` и `tests/unit/test_data_quality.py tests/integration/test_data_quality_undo.py` — все passed.

- [ ] **Step 6: Commit**

```bash
git add src/analytics/dq_checks.py tests/unit/test_dq_cases.py
git commit -m "feat(data-quality): run_checks по карточкам дела, дата события в данных проверок"
```

---

### Task 3: Дела — группировка находок, ступени, ключ, заголовок

**Files:**
- Create: `src/analytics/dq_cases.py`
- Test: `tests/unit/test_dq_cases.py` (дополнить)

- [ ] **Step 1: Падающие тесты** — дописать в `tests/unit/test_dq_cases.py`:

```python
from src.analytics.dq_cases import STAGES, group_cases
from src.analytics.dq_checks import Finding


def test_namesakes_with_findings_join_one_case_brother_does_not():
    d = pcarev()
    findings = run_checks(d)
    cases = group_cases(findings, d)
    p = next(c for c in cases if 1 in c["cards"])
    assert p["key"] == "c1" and set(p["cards"]) >= {1, 2, 3} and 4 not in p["cards"]
    assert p["title"] == "Пцарев Александр"              # карточка с наибольшим числом строк — отца
    assert {f.key for f in p["findings"]} == {f.key for f in findings if set(f.client_ids) & set(p["cards"])}


def test_finding_without_cards_is_own_case():
    d = pcarev()
    f = Finding("R-CARD", "high", "результат #999 без карточки", (), 999, 10)
    [case] = group_cases([f], d)
    assert case["key"] == "r999" and case["cards"] == [] and case["title"] == "Результат #999 без карточки"


def test_stages_order():
    assert [STAGES[c] for c in ("C-TWIN", "R-LEAD", "R-FOREIGN")] == [1, 1, 1]
    assert STAGES["R-DUP"] == 2
    assert {STAGES[c] for c in ("R-CARD", "R-CAT", "HYG", "L-KID")} == {3}
```

- [ ] **Step 2: Запустить — падает** (`ModuleNotFoundError: src.analytics.dq_cases`).

- [ ] **Step 3: Создать `src/analytics/dq_cases.py`**

```python
"""
«Качество данных» как дела о людях (спецификация docs/superpowers/specs/2026-10-28-data-quality-cases-design.md).

Дело — связная группа карточек: карточки одной находки связаны; тёзки с находками (та же фамилия,
совместимое имя: «Саша» — «Александр») — в одном деле. Вопросы дела идут ступенями: кто есть кто →
лишние строки → поля. Ответ на вопрос выполняет цепочку действий из dq_actions (журнал и отмена — там).
"""

import collections

from src.analytics.dq_checks import names_compatible
from src.common.names import norm

STAGES = {"C-TWIN": 1, "R-LEAD": 1, "R-FOREIGN": 1, "R-DUP": 2, "R-CARD": 3, "R-CAT": 3, "HYG": 3, "L-KID": 3}
STAGE_TITLES = {1: "Кто есть кто", 2: "Лишние строки", 3: "Поля"}


def _rows_count(data, cid):
    return len(data.res_by_card[cid]) + len(data.leads_by_card[cid])


def _namesakes(data, a, b):
    ca, cb = data.clients.get(a), data.clients.get(b)
    return bool(ca and cb and norm(ca["surname"]) == norm(cb["surname"])
                and names_compatible(ca["name"], cb["name"], data.names))


def group_cases(findings, data):
    """Находки -> дела [{key, title, cards, findings}], ключ — «c<наименьшая карточка>» или «r<результат>»."""
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        parent[find(a)] = find(b)

    orphans = []
    for f in findings:
        ids = [i for i in f.client_ids if i]
        if not ids:
            orphans.append(f)
            continue
        for i in ids:
            find(i)
        for i in ids[1:]:
            union(ids[0], i)
    cards = sorted(parent)
    by_surname = collections.defaultdict(list)
    for i in cards:
        c = data.clients.get(i)
        if c:
            by_surname[norm(c["surname"])].append(i)
    for same in by_surname.values():
        for x, y in ((x, y) for k, x in enumerate(same) for y in same[k + 1:]):
            if _namesakes(data, x, y):
                union(x, y)
    groups = collections.defaultdict(list)
    for i in cards:
        groups[find(i)].append(i)
    out = []
    for ids in groups.values():
        ids = sorted(ids)
        own = [f for f in findings if set(f.client_ids) & set(ids)]
        main = max(ids, key=lambda i: (_rows_count(data, i), -i))
        c = data.clients.get(main, {})
        out.append({"key": f"c{ids[0]}", "title": f'{c.get("surname", "")} {c.get("name", "")}'.strip() or f"#{main}",
                    "cards": ids, "findings": own})
    for f in orphans:
        out.append({"key": f"r{f.result_id}" if f.result_id else f"l{f.lead_id}",
                    "title": f.message[:1].upper() + f.message[1:], "cards": [], "findings": [f]})
    return out
```

- [ ] **Step 4: Запустить** — `tests/unit/test_dq_cases.py` passed.

- [ ] **Step 5: Commit**

```bash
git add src/analytics/dq_cases.py tests/unit/test_dq_cases.py
git commit -m "feat(data-quality): дела о людях — группировка находок, тёзки по уменьшительному имени"
```

---

### Task 4: Цепочки действий — выравнивание строки при переносе, места при смене категории/пола, «отложено»

**Files:**
- Modify: `src/analytics/dq_actions.py` (`move_row`, `_restore_move`, `edit_record`, `DECISIONS`, `_describe`)
- Test: `tests/integration/test_data_quality_undo.py` (дополнить; там фикстура `db`, хелперы `event`, `result`, `lead`, `card`, `owner`)

- [ ] **Step 1: Падающие тесты** — дописать в конец `tests/integration/test_data_quality_undo.py`:

```python
def test_move_with_align_sets_row_fio_bd_of_target_and_undo(db):
    conn, cur = db
    e1 = event(cur, 1.0)
    rid, father = result(cur, e1, 1012, "1980-03-09", name="Александр")
    _, son = result(cur, event(cur, 1.0), 1141, "2013-12-20", name="Саша")
    conn.commit()
    to, aid = dq.move_row(conn, "results", rid, USER, "k", to_client_id=son, align=True)
    cur.execute("SELECT client_id, surname, name, birthday FROM results WHERE id = %s", (rid,))
    assert cur.fetchone() == {"client_id": son, "surname": SUR, "name": "Саша", "birthday": datetime.date(2013, 12, 20)}
    dq.undo_action(conn, aid, USER)
    cur.execute("SELECT client_id, name, birthday FROM results WHERE id = %s", (rid,))
    assert cur.fetchone() == {"client_id": father, "name": "Александр", "birthday": datetime.date(1980, 3, 9)}


def test_category_change_sets_neighbor_rank_and_undo(db):
    conn, cur = db
    ev = event(cur, 5.0)
    rows = []
    for bib, cat, mins in ((1, "М18-29", 20), (2, "М30-39", 21), (3, "М30-39", 23), (4, "М18-29", 22)):
        rid, _ = result(cur, ev, bib, f"1990-01-0{bib}", name=f"Иван{bib}")
        cur.execute("""UPDATE results SET category = %s, time_gun_finish = SEC_TO_TIME(%s), rank_category = %s
                       WHERE id = %s""", (cat, mins * 60, {1: 1, 2: 1, 3: 2, 4: 2}[bib], rid))
        rows.append(rid)
    conn.commit()
    # №4 (22 мин) переводим в М30-39: сосед снизу — №3 (23 мин, место 2) → №4 получает место 2
    _, aid = dq.edit_record(conn, "results", rows[3], {"category": "М30-39"}, USER)
    cur.execute("SELECT category, rank_category FROM results WHERE id = %s", (rows[3],))
    assert cur.fetchone() == {"category": "М30-39", "rank_category": 2}
    cur.execute("SELECT rank_category FROM results WHERE id IN (%s, %s) ORDER BY id", (rows[1], rows[2]))
    assert [r["rank_category"] for r in cur.fetchall()] == [1, 2]            # остальных не трогаем
    dq.undo_action(conn, aid, USER)
    cur.execute("SELECT category, rank_category FROM results WHERE id = %s", (rows[3],))
    assert cur.fetchone() == {"category": "М18-29", "rank_category": 2}


def test_postponed_decision_and_undo(db):
    conn, cur = db
    did = dq.dismiss(conn, "TEST-UNDO::postpone", "postponed", "не знаю ДР", USER)
    assert dq.load_decisions(conn)["TEST-UNDO::postpone"] == "postponed"
    journal = {x["id"]: x for x in dq.recent_actions(conn, 10)}
    assert journal[did]["text"] == "Решение: отложено (не знаю ДР)"
    dq.undo_action(conn, did, USER)
    assert "TEST-UNDO::postpone" not in dq.load_decisions(conn)
```

- [ ] **Step 2: Запустить — падают** (`move_row() got an unexpected keyword argument 'align'`; ранг не меняется; `решение: different_people, keep`).

Run: `C:/Users/podbo/miniconda3/python.exe -m pytest tests/integration/test_data_quality_undo.py -q -p no:warnings`

- [ ] **Step 3: `move_row(..., align=False)`** — в `src/analytics/dq_actions.py`:

Сигнатуру заменить на
`def move_row(conn, table, row_id, user, key="", to_client_id=None, new_card=None, align=False):`
и в docstring добавить строку: `align=True — строка получает ФИ и ДР новой карточки (снимок «до» — в журнале).`

Сразу после `cur.execute(f"UPDATE {table} SET client_id = %s WHERE id = %s", (target, row["id"]))` вставить:

```python
        row_before = None
        if align:
            cur.execute(f"SELECT surname, name, birthday FROM {table} WHERE id = %s", (row["id"],))
            row_before = {k: str(v) for k, v in cur.fetchone().items()}
            cur.execute(f"""UPDATE {table} r JOIN clients c ON c.id = %s
                            SET r.surname = c.surname, r.name = c.name, r.birthday = c.birthday WHERE r.id = %s""",
                        (target, row["id"]))
```

и в словарь `_log_action(cur, "move_result", ...)` добавить ключ `"row_before": row_before`.

В `_restore_move` после `cur.execute(f"UPDATE {table} SET client_id = %s WHERE id = %s", (d["from"], row_id))` вставить:

```python
    if d.get("row_before"):
        b = d["row_before"]
        cur.execute(f"UPDATE {table} SET surname = %s, name = %s, birthday = %s WHERE id = %s",
                    (b["surname"], b["name"], b["birthday"], row_id))
```

- [ ] **Step 4: Места «как у соседа снизу» при смене категории/пола** — в `src/analytics/dq_actions.py` перед `def edit_record` добавить:

```python
RANK_COLS = {"category": ("rank_category", "rank_category_clean"), "sex": ("rank_sex", "rank_sex_clean")}


def _finish_key(t, ms):
    return None if t is None else (int(t.total_seconds()), (ms % 1000) if ms is not None else 0)


def _neighbor_rank(me_key, group, rank_col, time_key):
    """Место первого не быстрее (место на двоих); быстрее всех медленных нет — последнее + 1."""
    others = [r for r in group if r[time_key] is not None and r[rank_col] is not None]
    slower = [r for r in others if r[time_key] >= me_key]
    if slower:
        return min(slower, key=lambda r: (r[time_key], r[rank_col]))[rank_col]
    return max((r[rank_col] for r in others), default=0) + 1


def _neighbor_ranks(cur, row_id, category, sex, fields):
    """Места строки результата в новой категории (и при смене пола — среди пола) по правилу «как у соседа снизу»
    (решение пользователя 2026-10-28): места остальных участников не трогаем. -> {колонка: место}."""
    cur.execute("""SELECT event_id, race_status, time_gun_finish, time_gun_finish_ms, time_clear_finish,
                          time_clear_finish_ms FROM results WHERE id = %s""", (row_id,))
    me = cur.fetchone()
    if not me or me["race_status"] != "Finished" or me["time_gun_finish"] is None:
        return {}
    cur.execute("""SELECT id, sex, category, time_gun_finish, time_gun_finish_ms, time_clear_finish, time_clear_finish_ms,
                          rank_category, rank_category_clean, rank_sex, rank_sex_clean
                   FROM results WHERE event_id = %s AND id <> %s AND race_status = 'Finished'
                     AND time_gun_finish IS NOT NULL""", (me["event_id"], row_id))
    rows = cur.fetchall()
    for r in rows + [me]:
        r["g"] = _finish_key(r["time_gun_finish"], r["time_gun_finish_ms"])
        r["c"] = _finish_key(r["time_clear_finish"], r["time_clear_finish_ms"])
    out = {}
    for field, value in (("category", category), ("sex", sex)):
        if field not in fields:
            continue
        group = [r for r in rows if r[field] == value]
        gun_col, clean_col = RANK_COLS[field]
        out[gun_col] = _neighbor_rank(me["g"], group, gun_col, "g")
        if me["c"] is not None and any(r[clean_col] is not None for r in group):
            out[clean_col] = _neighbor_rank(me["c"], group, clean_col, "c")
    return out
```

В `edit_record`: `cols` для results должен включать колонки мест, чтобы «до» попало в снимок. Заменить строку
`cols = list(EDITABLE[table]) + (["event_id"] if table == "leads" else [])`
на
`cols = list(EDITABLE[table]) + (["event_id"] if table == "leads" else []) + (list(RANK_COLS["category"] + RANK_COLS["sex"]) if table == "results" else [])`

и сразу после блока `_check_category_sex(...)` (там, где проверяется смена пола/категории) добавить:

```python
        if table == "results" and {"sex", "category"} & set(changed):
            ranks = _neighbor_ranks(cur, row_id, changed.get("category", before["category"]),
                                    changed.get("sex", before["sex"]), set(changed))
            changed.update({k: v for k, v in ranks.items() if str(v) != before.get(k)})
```

(`before` хранит строки — `str(row[k])` — поэтому сравнение через `str`. В `UPDATE` и журнал попадут и колонки мест; отмена `_restore_edit` вернёт их вместе с категорией. `_describe` для `edit` пропускает `event_id` — дополнить пропуск колонок мест: в генераторе `diff` условие `if k != "event_id"` заменить на `if k in EDIT_LABELS`.)

- [ ] **Step 5: «Отложено» как решение** — в `src/analytics/dq_actions.py`:

`DECISIONS = ("different_people", "keep")` → `DECISIONS = ("different_people", "keep", "postponed")`

В `_describe` ветку `dismiss` заменить на:

```python
    if action == "dismiss":
        label = {"different_people": "разные люди", "keep": "оставить как есть", "postponed": "отложено"}[d["decision"]]
        return f"Решение: {label}" + (f' ({d["note"]})' if d.get("note") else "")
```

- [ ] **Step 6: Запустить** — `tests/integration/test_data_quality_undo.py` passed; затем `tests/unit/ tests/integration/test_admin_data_quality.py` passed.

- [ ] **Step 7: Commit**

```bash
git add src/analytics/dq_actions.py tests/integration/test_data_quality_undo.py
git commit -m "feat(data-quality): перенос с выравниванием строки, места «как у соседа снизу» при правке, решение «отложено»"
```

---

### Task 5: Вопросы — текст, ответы, рекомендованный ответ

**Files:**
- Modify: `src/analytics/dq_cases.py`
- Test: `tests/unit/test_dq_cases.py` (дополнить)

Вопрос — словарь `{id, code, stage, text, hint, answers: [{id, label, recommended, inputs}]}`, `inputs` — `[{name, label, value, type: "text"|"date"|"select", options?}]`. Ответ `"postpone"` («Не знаю — отложить дело») есть у каждого вопроса последним.

- [ ] **Step 1: Падающие тесты** — дописать в `tests/unit/test_dq_cases.py`:

```python
from src.analytics.dq_cases import build_question


def _q(d, code, **kw):
    f = next(f for f in run_checks(d) if f.code == code and all(getattr(f, k) == v for k, v in kw.items()))
    return build_question(f, d)


def ids(q):
    return [a["id"] for a in q["answers"]]


def test_foreign_question_suggests_namesake_first():
    q = _q(pcarev(), "R-FOREIGN", result_id=101)
    assert q["stage"] == 1 and "Чей это результат" in q["text"] and "36 лет" in q["text"]
    assert ids(q)[0] in ("to:2", "to:3") and q["answers"][0]["recommended"]
    assert ids(q)[-3:] == ["new", "keep", "postpone"]
    assert [i["name"] for i in q["answers"][-3]["inputs"]] == ["surname", "name", "birthday"]


def test_twin_question_prefills_proposal():
    d = data([C(1, "Иванов", "Иван", "1985-07-14"), C(2, "Иванов", "Иван", "1900-01-01")],
             results=[R(1, 1, "Иванов", "Иван", "1985-07-14", 11, 5), R(2, 2, "Иванов", "Иван", "1900-01-01", 10, 6)])
    q = _q(d, "C-TWIN")
    assert "один человек" in q["text"] and ids(q) == ["merge", "different", "postpone"]
    merge = q["answers"][0]
    assert merge["recommended"] and {i["name"]: i["value"] for i in merge["inputs"]}["birthday"] == "1985-07-14"


def test_card_question_recommends_card_bd_for_placeholder_row():
    d = data([C(1, "Ветрова", "Елизавета", "2014-12-12")],
             results=[R(1, 1, "Ветрова", "Елизавета", "2014-01-01", 10, 4102, sex="Женщина")])
    q = _q(d, "R-CARD")
    assert "2014-01-01" in q["text"] and "2014-12-12" in q["text"]
    assert ids(q) == ["row_from_card", "card_from_row", "other", "postpone"] and q["answers"][0]["recommended"]


def test_every_finding_type_has_question_with_postpone():
    d = pcarev()
    for f in run_checks(d):
        q = build_question(f, d)
        assert q["id"] == f.key and q["text"] and ids(q)[-1] == "postpone" and q["stage"] in (1, 2, 3)
        assert sum(a["recommended"] for a in q["answers"]) <= 1
```

- [ ] **Step 2: Запустить — падает** (`ImportError: build_question`).

- [ ] **Step 3: Реализация** — дописать в `src/analytics/dq_cases.py` (импорты — в начало файла):

```python
from src.analytics.dq_actions import propose_final
from src.analytics.dq_checks import KIDS_EVENT, jan1, merge_blockers, real_bd

POSTPONE = {"id": "postpone", "label": "Не знаю — отложить дело", "recommended": False, "inputs": []}


def _a(id_, label, recommended=False, inputs=()):
    return {"id": id_, "label": label, "recommended": recommended, "inputs": list(inputs)}


def _fio_inputs(surname, name, birthday):
    return [{"name": "surname", "label": "Фамилия", "value": surname, "type": "text"},
            {"name": "name", "label": "Имя", "value": name, "type": "text"},
            {"name": "birthday", "label": "ДР", "value": birthday or "", "type": "date"}]


def _card(data, cid):
    c = data.clients.get(cid, {})
    return f'{c.get("surname", "")} {c.get("name", "")} {c.get("birthday", "")}'.strip()


def _age(bd, year):
    return year - int(bd[:4]) if real_bd(bd) and year else None


def _row(data, f):
    if f.result_id:
        return "results", data.result_by_id.get(f.result_id)
    return "leads", data.lead_by_id.get(f.lead_id)


def _q_twin(f, data):
    ids = list(f.client_ids)
    _, s, n, bd = propose_final(ids, data)
    blockers = merge_blockers(ids, data)
    text = f"{_card(data, ids[0])} и {_card(data, ids[1])} — один человек?"
    hint = ("Осторожно: " + "; ".join(blockers)) if blockers else f.message.split(": ", 1)[-1]
    return text, hint, [_a("merge", "Да — одна карточка", not blockers, _fio_inputs(s, n, bd)),
                        _a("different", "Нет, разные люди")]


def _q_lead(f, data):
    _, row = _row(data, f)
    res_card, lead_card = f.client_ids[0], f.client_ids[1]
    same_bib = f.severity == "high"
    text = (f'{data.event_label(f.event_id)} №{row["start_number"]}: результат записан на {_card(data, res_card)}, '
            f"а заявка — на {_card(data, lead_card)}. Это один человек?")
    _, s, n, bd = propose_final([res_card, lead_card], data)
    return text, "Номер в протоколе совпадает с номером заявки" if same_bib else "Совпадают фамилия и имя", [
        _a("merge", "Да — одна карточка", same_bib, _fio_inputs(s, n, bd)),
        _a(f"to:{lead_card}", f"Нет — результат принадлежит {_card(data, lead_card)}"),
        _a("keep", "Нет, всё верно — разные люди")]


def _q_foreign(f, data):
    table, row = _row(data, f)
    owner, others = f.client_ids[0], list(f.client_ids[1:])
    year = data.year(f.event_id)
    age = _age(data.clients[owner]["birthday"], year)
    what = "результат" if table == "results" else "заявка"
    bib = f' №{row["start_number"]}' if table == "results" and row.get("start_number") else ""
    text = (f"{data.event_label(f.event_id)}{bib} записан{'а' if table == 'leads' else ''} на {_card(data, owner)}"
            + (f" — возраст по карточке: {age} лет" if age is not None else "") + f". Чей это {what}?")
    answers = [_a(f"to:{i}", f"{_card(data, i)}", k == 0) for k, i in enumerate(others)]
    answers += [_a("new", "Другой человек — новая карточка", False, _fio_inputs(row["surname"], row["name"], "")),
                _a("keep", "Всё верно — оставить")]
    return text, f.message.split(": ", 1)[-1], answers


def _q_dup(f, data):
    _, row = _row(data, f)
    if f.auto:
        return (f"{_card(data, f.client_ids[0])}: в {data.event_label(f.event_id)} есть «не стартовал» "
                f'№{row["start_number"]} и другой результат. Удалить «не стартовал»?', "Обычно это старый номер",
                [_a("delete", "Да, удалить", True), _a("keep", "Оставить")])
    return (f"{_card(data, f.client_ids[0])}: два финиша в {data.event_label(f.event_id)}. Это два разных человека?",
            f.message, [_a("new", f'Да — вынести №{row["start_number"]} на новую карточку', False,
                           _fio_inputs(row["surname"], row["name"], "")),
                        _a("keep", "Нет, оставить", True)])


def _q_card(f, data):
    _, row = _row(data, f)
    if not f.client_ids:
        return f.message, "", []
    c = data.clients[f.client_ids[0]]
    diff = [k for k in ("surname", "name", "birthday") if str(row[k]) != str(c[k])]
    show = lambda o: " ".join(str(o[k]) for k in diff)
    placeholder = "birthday" in diff and (not real_bd(row["birthday"]) or jan1(row["birthday"]))
    text = (f'{data.event_label(f.event_id)} №{row["start_number"]}: в протоколе «{show(row)}», '
            f"в карточке «{show(c)}». Как правильно?")
    return text, "В протоколе — заглушка ДР" if placeholder else "", [
        _a("row_from_card", f"Как в карточке: {show(c)}", placeholder or "birthday" not in diff),
        _a("card_from_row", f"Как в протоколе: {show(row)}"),
        _a("other", "Другое значение", False, _fio_inputs(row["surname"], row["name"], row["birthday"]))]


def _q_cat(f, data):
    _, row = _row(data, f)
    text = (f'{data.event_label(f.event_id)} №{row["start_number"]}: {row["surname"]} {row["name"]}, '
            f'ДР {row["birthday"]}, пол {row["sex"]} — категория «{row["category"]}». Что неверно?')
    return text, "", [
        _a("birthday", "ДР", False, [{"name": "birthday", "label": "ДР", "value": row["birthday"], "type": "date"}]),
        _a("category", "Категория", False, [{"name": "category", "label": "Категория", "value": row["category"],
                                             "type": "select", "options": "category_options"}]),
        _a("sex", "Пол", False, [{"name": "sex", "label": "Пол", "value": row["sex"], "type": "select",
                                  "options": ["Мужчина", "Женщина"]},
                                 {"name": "category", "label": "Категория", "value": "", "type": "select",
                                  "options": "category_options"}]),
        _a("keep", "Всё верно — оставить")]


def _q_hyg(f, data):
    _, row = _row(data, f)
    s, n = f.fix
    return (f'Записать как «{s} {n}»? В протоколе: «{row["surname"]} {row["name"]}»', "", [
        _a("fix", "Да", True), _a("manual", "Вписать вручную", False, _fio_inputs(s, n, "")[:2]),
        _a("keep", "Оставить как есть")])


def _q_kid(f, data):
    table, row = _row(data, f)
    kids = [i for i in f.client_ids[1:]]
    text = f'Заявка на {data.event_label(f.event_id)}: {row["surname"]} {row["name"]}, ДР {row["birthday"]}. ' \
           f'{f.message.split(" — ", 1)[-1].capitalize()}. Что исправить?'
    return text, "", [
        _a("birthday", "ДР ребёнка", False, [{"name": "birthday", "label": "ДР", "value": "", "type": "date"}]),
        *[_a(f"to:{i}", f"Перенести на {_card(data, i)}") for i in kids],
        _a("distance", "Дистанция", False, [{"name": "event_distance", "label": "Дистанция",
                                             "value": row.get("event_distance", ""), "type": "select",
                                             "options": "distance_options"}]),
        _a("keep", "Всё верно — оставить")]


BUILDERS = {"C-TWIN": _q_twin, "R-LEAD": _q_lead, "R-FOREIGN": _q_foreign, "R-DUP": _q_dup, "R-CARD": _q_card,
            "R-CAT": _q_cat, "HYG": _q_hyg, "L-KID": _q_kid}


def build_question(f, data):
    """Находка -> вопрос человеческим языком с готовыми ответами (★ — recommended, не больше одного)."""
    text, hint, answers = BUILDERS[f.code](f, data)
    return {"id": f.key, "code": f.code, "stage": STAGES[f.code], "text": text, "hint": hint,
            "result_id": f.result_id, "lead_id": f.lead_id, "answers": answers + [dict(POSTPONE)]}
```

(`options: "category_options"` / `"distance_options"` — подставляются в `get_case` из `edit_record_view`, Task 7.)

- [ ] **Step 4: Запустить** `tests/unit/test_dq_cases.py` — passed. Если `test_every_finding_type_has_question_with_postpone` падает на конкретном коде — поправить построитель этого кода (текст не пустой, не более одного ★).

- [ ] **Step 5: Commit**

```bash
git add src/analytics/dq_cases.py tests/unit/test_dq_cases.py
git commit -m "feat(data-quality): вопросы человеческим языком для всех типов находок"
```

---

### Task 6: Применение ответа и откладывание дела

**Files:**
- Modify: `src/analytics/dq_cases.py`
- Test: `tests/integration/test_dq_cases_db.py` (новый)

- [ ] **Step 1: Падающие тесты** — `tests/integration/test_dq_cases_db.py`:

```python
"""Ответы на вопросы дел на локальной БД (.env.local): цепочки, отложить, устаревший вопрос, сквозные проверки.
Тестовые данные — события 2099 года, фамилия «Тестделов», убираются после теста."""
import datetime

import pytest

from src.analytics import dq_cases
from src.analytics import data_quality as dq
from src.analytics.db_pool import get_pooled_connection

EV, SUR, USER = "Тест дел", "Тестделов", "test-cases"


@pytest.fixture
def db():
    conn = get_pooled_connection()
    if not conn:
        pytest.skip("Нет локальной БД")
    cur = conn.cursor(dictionary=True)

    def cleanup():
        # тестовые события: «Тест дел …» и переименованные в «Детский забег» — только 2099 года
        cur.execute("SELECT id FROM events WHERE event_year = 2099 AND (event_name LIKE %s OR event_name = 'Детский забег')",
                    (f"{EV}%",))
        evs = [r["id"] for r in cur.fetchall()]
        if evs:
            ph = ",".join(map(str, evs))
            cur.execute(f"DELETE FROM results WHERE event_id IN ({ph})")
            cur.execute(f"DELETE FROM leads WHERE event_id IN ({ph})")
            cur.execute(f"DELETE FROM events WHERE id IN ({ph})")
        cur.execute("DELETE FROM clients WHERE surname = %s", (SUR,))
        cur.execute("DELETE FROM dq_actions WHERE done_by = %s", (USER,))
        cur.execute("DELETE FROM dq_decisions WHERE decided_by = %s", (USER,))
        conn.commit()

    cleanup()
    yield conn, cur
    cleanup()
    cur.close()
    conn.close()


def event(cur, name, dist, year=2099, date=None):
    cur.execute("INSERT INTO events (event_name, event_distance, event_year, event_date) VALUES (%s, %s, %s, %s)",
                (f"{EV} {name}", dist, year, date))
    return cur.lastrowid


def result(cur, ev, bib, bd, name="Александр", cat="М18-49"):
    cur.execute("""INSERT INTO results (surname, name, birthday, client_id, event_id, sex, start_number, category,
                   race_status) VALUES (%s, %s, %s, 0, %s, 'Мужчина', %s, %s, 'Finished')""", (SUR, name, bd, ev, bib, cat))
    rid = cur.lastrowid
    cur.execute("SELECT client_id FROM results WHERE id = %s", (rid,))
    return rid, cur.fetchone()["client_id"]


def foreign_case(conn, cur):
    """Пцаревы в миниатюре: детский результат на карточке отца, сын — отдельной карточкой."""
    _, father = result(cur, event(cur, "Жара", 21.1), 1, "1980-03-09")
    rid, _ = result(cur, event(cur, "Детский", 1.0), 1012, "1980-03-09", cat="Мальчики 2005 г.р. и младше")
    cur.execute("UPDATE events SET event_name = 'Детский забег' WHERE id = (SELECT event_id FROM results WHERE id = %s)", (rid,))
    _, son = result(cur, event(cur, "Детский 2", 1.0), 1141, "2093-12-20", name="Саша", cat="Мальчики")
    conn.commit()
    return rid, father, son


def test_answer_foreign_moves_and_aligns_then_case_has_no_question(db):
    conn, cur = db
    rid, father, son = foreign_case(conn, cur)
    case = dq_cases.case_for_card(conn, father)
    q = next(q for q in case["questions"] if q["code"] == "R-FOREIGN")
    assert q["answers"][0]["id"] == f"to:{son}"
    out = dq_cases.apply_answer(conn, case["key"], q["id"], f"to:{son}", {}, USER)
    assert out["action_ids"]
    cur.execute("SELECT client_id, name, birthday FROM results WHERE id = %s", (rid,))
    assert cur.fetchone() == {"client_id": son, "name": "Саша", "birthday": datetime.date(2093, 12, 20)}
    assert not [x for x in out["case"]["questions"] if x["code"] == "R-FOREIGN"]


def test_stale_question_raises(db):
    conn, cur = db
    rid, father, son = foreign_case(conn, cur)
    case = dq_cases.case_for_card(conn, father)
    q = next(q for q in case["questions"] if q["code"] == "R-FOREIGN")
    dq_cases.apply_answer(conn, case["key"], q["id"], f"to:{son}", {}, USER)
    with pytest.raises(dq_cases.StaleQuestion):
        dq_cases.apply_answer(conn, case["key"], q["id"], f"to:{son}", {}, USER)


def test_card_from_row_conflict_offers_merge(db):
    conn, cur = db
    ev = event(cur, "Конфликт", 5.0)
    _, a = result(cur, ev, 1, "2093-12-12", name="Елизавета")
    rid, b = result(cur, event(cur, "Конфликт 2", 5.0), 2, "2093-01-01", name="Елизавета")
    cur.execute("UPDATE results SET client_id = %s WHERE id = %s", (a, rid))   # строка 2093-01-01 — на карточке A
    conn.commit()
    case = dq_cases.case_for_card(conn, a)
    q = next(q for q in case["questions"] if q["code"] == "R-CARD" and q["result_id"] == rid)
    out = dq_cases.apply_answer(conn, case["key"], q["id"], "card_from_row", {}, USER)
    assert out["conflict"]["merge_with"] == b and "Склеить" in out["conflict"]["message"]
    out = dq_cases.apply_answer(conn, case["key"], q["id"], f"merge_with:{b}",
                                {"surname": SUR, "name": "Елизавета", "birthday": "2093-12-12"}, USER)
    cur.execute("SELECT COUNT(*) n FROM clients WHERE id IN (%s, %s)", (a, b))
    assert cur.fetchone()["n"] == 1


def test_postpone_case_moves_it_to_postponed_and_back_on_undo(db):
    conn, cur = db
    rid, father, son = foreign_case(conn, cur)
    key = dq_cases.case_for_card(conn, father)["key"]
    ids = dq_cases.postpone_case(conn, key, "не знаю ДР", USER)
    assert ids and key not in {c["key"] for c in dq_cases.list_cases(conn, "open")}
    assert key in {c["key"] for c in dq_cases.list_cases(conn, "postponed")}
    for aid in ids:
        dq.undo_action(conn, aid, USER)
    assert key in {c["key"] for c in dq_cases.list_cases(conn, "open")}
```

- [ ] **Step 2: Запустить — падает** (`AttributeError: case_for_card`).

- [ ] **Step 3: Реализация** — дописать в `src/analytics/dq_cases.py`:

```python
import re

from src.analytics import dq_actions
from src.analytics.dq_checks import load, run_checks


class StaleQuestion(Exception):
    """Вопроса больше нет (дело изменилось в другой вкладке) — 409 «обновите дело»."""


def _state(conn, card_ids=None):
    data = load(conn)
    findings = run_checks(data, card_ids=card_ids)
    decided = dq_actions.load_decisions(conn)
    return data, findings, decided


def _visible(findings, decided):
    """Нерешённые находки и отложенные (для вкладки «Отложено»); «разные люди»/«оставить» — решены."""
    return [f for f in findings if decided.get(f.key) in (None, "postponed")]


def _find_case(cases, key):
    for c in cases:
        if c["key"] == key:
            return c
    return None


def apply_answer(conn, case_key, question_id, answer_id, inputs, user):
    """Выполнить цепочку ответа -> {"action_ids": [...], "case": дело после ответа (или None — дело закрыто)}."""
    data, findings, decided = _state(conn)
    f = next((x for x in findings if x.key == question_id and decided.get(x.key) in (None, "postponed")), None)
    if f is None:
        raise StaleQuestion("Дело изменилось — обновите")
    if answer_id == "postpone":
        return {"action_ids": postpone_case(conn, case_key, inputs.get("reason", ""), user),
                "case": get_case(conn, case_key)}
    table, row = _row(data, f)
    i = {k: (v or "").strip() for k, v in (inputs or {}).items()}
    fio = {k: i[k] for k in ("surname", "name", "birthday") if i.get(k)}
    aid = []
    if answer_id in ("keep", "different"):
        aid.append(dq_actions.dismiss(conn, f.key, "different_people" if answer_id == "different" else "keep", "", user))
    elif answer_id == "merge":
        aid.append(dq_actions.merge_cards(conn, list(f.client_ids), fio["surname"], fio["name"], fio["birthday"],
                                          user, f.key)[1])
    elif answer_id.startswith("to:"):
        aid.append(dq_actions.move_row(conn, table, row["id"], user, f.key, to_client_id=int(answer_id[3:]),
                                       align=True)[1])
    elif answer_id == "new":
        aid.append(dq_actions.move_row(conn, table, row["id"], user, f.key, new_card=fio, align=True)[1])
    elif answer_id == "delete":
        aid.append(dq_actions.delete_result(conn, row["id"], user, f.key))
    elif answer_id == "row_from_card":
        c = data.clients[f.client_ids[0]]
        diff = {k: str(c[k]) for k in ("surname", "name", "birthday") if str(row[k]) != str(c[k])}
        aid.append(dq_actions.edit_record(conn, "results", row["id"], diff, user, f.key)[1])
    elif answer_id in ("card_from_row", "other"):
        c = data.clients[f.client_ids[0]]
        if answer_id == "other":
            aid.append(dq_actions.edit_record(conn, "results", row["id"], fio, user, f.key)[1])
            target = fio
        else:
            target = {k: str(row[k]) for k in ("surname", "name", "birthday") if str(row[k]) != str(c[k])}
        try:
            aid.append(dq_actions.edit_record(conn, "clients", c["id"], target, user, f.key)[1])
        except ValueError as e:
            other = re.search(r"уже у карточки #(\d+)", str(e))
            if not other:
                raise
            # конфликт ФИ+ДР — не ошибка, а предложение склеить (спецификация, «Цепочки»)
            final = {k: target.get(k, str(c[k])) for k in ("surname", "name", "birthday")}
            return {"action_ids": aid, "case": get_case(conn, case_key),
                    "conflict": {"message": f"{final['surname']} {final['name']} {final['birthday']} — уже карточка "
                                            f"#{other[1]}. Склеить с ней?", "merge_with": int(other[1]), **final}}
    elif answer_id.startswith("merge_with:"):
        aid.append(dq_actions.merge_cards(conn, [f.client_ids[0], int(answer_id.split(":")[1])], fio["surname"],
                                          fio["name"], fio["birthday"], user, f.key)[1])
    elif answer_id in ("birthday", "category", "sex", "distance"):
        fields = {k: i[k] for k in ("birthday", "category", "sex", "event_distance") if i.get(k)}
        aid.append(dq_actions.edit_record(conn, table, row["id"], fields, user, f.key)[1])
    elif answer_id == "fix":
        aid.append(dq_actions.fix_fio(conn, row["id"], f.fix[0], f.fix[1], user, f.key)[1])
    elif answer_id == "manual":
        aid.append(dq_actions.fix_fio(conn, row["id"], fio["surname"], fio["name"], user, f.key)[1])
    else:
        raise ValueError(f"неизвестный ответ {answer_id}")
    return {"action_ids": aid, "case": get_case(conn, case_key)}


def postpone_case(conn, case_key, reason, user):
    """Отложить все вопросы дела (решение «postponed» с причиной) -> id записей журнала."""
    case = get_case(conn, case_key)
    if not case:
        raise StaleQuestion("Дело изменилось — обновите")
    note = reason or "не знаю ДР"
    return [dq_actions.dismiss(conn, q["id"], "postponed", note, user)
            for q in case["questions"] if q["state"] != "postponed"]


def list_cases(conn, status="open", event_id=None):
    """Очередь дел: status open — есть нерешённые вопросы; postponed — все вопросы отложены."""
    data, findings, decided = _state(conn)
    out = []
    for c in group_cases(_visible(findings, decided), data):
        open_ = [f for f in c["findings"] if f.key not in decided]
        if (status == "open") != bool(open_):
            continue
        if event_id and not any(f.event_id == event_id for f in c["findings"]):
            continue
        out.append({"key": c["key"], "title": c["title"], "cards": len(c["cards"]),
                    "questions_left": len(open_) if status == "open" else len(c["findings"]),
                    "events": sorted({data.event_label(f.event_id) for f in c["findings"] if f.event_id})})
    return sorted(out, key=lambda c: (c["title"], c["key"]))
```

(`get_case`, `case_for_card` — Task 7; тесты Task 6 проходят после Task 7 — шаги ниже выполнять подряд, коммит один на Task 6+7, см. Task 7 Step 6.)

---

### Task 7: Дело целиком — карточки со строками, вопросы по ступеням, «живой» забег

**Files:**
- Modify: `src/analytics/dq_cases.py`
- Test: `tests/unit/test_dq_cases.py`, `tests/integration/test_dq_cases_db.py`

- [ ] **Step 1: Падающий unit-тест** — дописать в `tests/unit/test_dq_cases.py`:

```python
from src.analytics.dq_cases import case_view, is_live


def test_case_view_rows_by_year_and_locked_stages():
    d = pcarev()
    findings = run_checks(d)
    case = next(c for c in __import__("src.analytics.dq_cases", fromlist=["group_cases"]).group_cases(findings, d)
                if 1 in c["cards"])
    v = case_view(case, d, decided={}, today=datetime.date(2026, 10, 28))
    father = next(c for c in v["cards"] if c["id"] == 1)
    assert [r["year"] for r in father["rows"]] == sorted((r["year"] for r in father["rows"]), reverse=True)
    assert any(r["problem"] for r in father["rows"] if r["id"] == 101)
    stages = [q["stage"] for q in v["questions"]]
    assert stages == sorted(stages)
    first = min(stages)
    assert all(q["state"] == ("current" if q["stage"] == first else "locked") for q in v["questions"])


def test_is_live_today_or_yesterday():
    ev = {"event_date": datetime.date(2026, 10, 27)}
    assert is_live(ev, datetime.date(2026, 10, 27)) and is_live(ev, datetime.date(2026, 10, 28))
    assert not is_live(ev, datetime.date(2026, 10, 29)) and not is_live({"event_date": None}, datetime.date(2026, 10, 28))
```

- [ ] **Step 2: Запустить — падает** (`ImportError: case_view`).

- [ ] **Step 3: Реализация** — дописать в `src/analytics/dq_cases.py`:

```python
import datetime as _dt

from src.analytics.dq_actions import edit_record_view
from src.config.settings import KRASNOYARSK_TZ

FIELD_ANSWERS = {"row_from_card", "card_from_row", "other", "birthday", "category", "sex", "distance", "fix",
                 "manual", "delete"}


def is_live(event, today):
    """Забег «живой» — дата сегодня или вчера (Красноярск): загрузчик Copernico ещё перезаписывает его строки."""
    d = event.get("event_date")
    return bool(d) and 0 <= (today - d).days <= 1


def _rows(data, cid, problems):
    rows = [{"table": "results", "id": r["id"], "year": data.year(r["event_id"]), "event": data.event_label(r["event_id"]),
             "start_number": r["start_number"], "category": r["category"], "status": r["race_status"],
             "birthday": r["birthday"], "problem": r["id"] in problems["results"]} for r in data.res_by_card[cid]]
    rows += [{"table": "leads", "id": l["id"], "year": data.year(l["event_id"]), "event": data.event_label(l["event_id"]),
              "start_number": l["start_number"], "category": "", "status": "заявка", "birthday": l["birthday"],
              "problem": l["id"] in problems["leads"]} for l in data.leads_by_card[cid]]
    return sorted(rows, key=lambda r: (-r["year"], r["event"], r["table"]))


def case_view(case, data, decided, today):
    """Дело для экрана: карточки со строками по годам (проблемные подсвечены), вопросы по ступеням."""
    problems = {"results": {f.result_id for f in case["findings"]}, "leads": {f.lead_id for f in case["findings"]}}
    questions = []
    for f in sorted(case["findings"], key=lambda f: (STAGES[f.code], -data.year(f.event_id) if f.event_id else 0, f.key)):
        q = build_question(f, data)
        rec = edit_record_view(f, data)
        for a in q["answers"]:
            for inp in a["inputs"]:
                if isinstance(inp.get("options"), str):
                    inp["options"] = [o["label"] if isinstance(o, dict) else o for o in (rec or {}).get(inp["options"], [])]
        live = bool(f.event_id) and f.result_id and is_live(data.events.get(f.event_id, {}), today)
        if live:
            q["answers"] = [a for a in q["answers"] if a["id"] not in FIELD_ANSWERS]
            q["hint"] = "Забег ещё загружается из хронометража — поля правьте в Copernico, иначе загрузчик перезапишет"
        q["live"] = live
        q["state"] = "postponed" if decided.get(f.key) == "postponed" else "open"
        questions.append(q)
    open_stages = [q["stage"] for q in questions if q["state"] == "open"]
    current = min(open_stages) if open_stages else None
    for q in questions:
        if q["state"] == "open":
            q["state"] = "current" if q["stage"] == current else "locked"
    cards = [{**{k: data.clients[i][k] for k in ("id", "surname", "name", "birthday")},
              "rows": _rows(data, i, problems)} for i in case["cards"] if i in data.clients]
    return {"key": case["key"], "title": case["title"], "cards": cards, "questions": questions,
            "stage_titles": STAGE_TITLES}


def _today():
    return _dt.datetime.now(KRASNOYARSK_TZ).date()


def get_case(conn, case_key):
    """Дело по ключу (None — дела больше нет: все вопросы решены)."""
    data, findings, decided = _state(conn)
    case = _find_case(group_cases(_visible(findings, decided), data), case_key)
    return case_view(case, data, decided, _today()) if case else None


def case_for_card(conn, client_id):
    """Дело человека по карточке — для поиска по ФИО: его дело с вопросами или карточка и тёзки без вопросов."""
    data, findings, decided = _state(conn)
    for case in group_cases(_visible(findings, decided), data):
        if client_id in case["cards"]:
            return case_view(case, data, decided, _today())
    if client_id not in data.clients:
        return None
    ids = sorted({client_id} | {i for i in data.cards_by_surname[norm(data.clients[client_id]["surname"])]
                                if _namesakes(data, client_id, i)})
    c = data.clients[client_id]
    return case_view({"key": f"c{ids[0]}", "title": f'{c["surname"]} {c["name"]}', "cards": ids, "findings": []},
                     data, decided, _today())
```

- [ ] **Step 4: Запустить** `tests/unit/test_dq_cases.py tests/integration/test_dq_cases_db.py` — passed.

- [ ] **Step 5: Регрессия** — `tests/unit/ tests/integration/` — все passed.

- [ ] **Step 6: Commit** (Task 6 + Task 7)

```bash
git add src/analytics/dq_cases.py tests/unit/test_dq_cases.py tests/integration/test_dq_cases_db.py
git commit -m "feat(data-quality): ответ на вопрос выполняет цепочку, отложить дело, дело со строками и ступенями, «живой» забег"
```

---

### Task 8: API дел

**Files:**
- Modify: `src/krasmarafon/routers/data_quality.py`
- Test: `tests/integration/test_admin_dq_cases.py` (новый)

- [ ] **Step 1: Падающие тесты** — `tests/integration/test_admin_dq_cases.py`:

```python
"""/api/admin/data-quality/cases*, /person/{client_id} — дела (функции dq_cases замоканы)."""
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app import app
from src.core.auth import api_require_auth

R = "src.krasmarafon.routers.data_quality"
client = TestClient(app)


@pytest.fixture(autouse=True)
def _auth():
    app.dependency_overrides[api_require_auth] = lambda: "testuser"
    yield
    app.dependency_overrides.pop(api_require_auth, None)


@pytest.fixture
def conn():
    c = MagicMock()
    with patch(f"{R}.get_pooled_connection", return_value=c):
        yield c


def test_list_and_get_case(conn):
    with patch(f"{R}.dq_cases.list_cases", return_value=[{"key": "c1"}]) as m:
        r = client.get("/api/admin/data-quality/cases?status=postponed&event_id=5")
    assert r.json() == {"cases": [{"key": "c1"}]} and m.call_args.args == (conn, "postponed", 5)
    with patch(f"{R}.dq_cases.get_case", return_value=None):
        assert client.get("/api/admin/data-quality/cases/c1").status_code == 404


def test_answer_passes_user_and_stale_is_409(conn):
    with patch(f"{R}.dq_cases.apply_answer", return_value={"action_ids": [7], "case": None}) as m:
        r = client.post("/api/admin/data-quality/cases/c1/answer",
                        json={"question_id": "R-FOREIGN:r1:1-2", "answer_id": "to:2", "inputs": {}})
    assert r.json() == {"action_ids": [7], "case": None}
    assert m.call_args.args == (conn, "c1", "R-FOREIGN:r1:1-2", "to:2", {}, "testuser")
    from src.analytics.dq_cases import StaleQuestion
    with patch(f"{R}.dq_cases.apply_answer", side_effect=StaleQuestion("Дело изменилось — обновите")):
        r = client.post("/api/admin/data-quality/cases/c1/answer", json={"question_id": "x", "answer_id": "keep"})
    assert r.status_code == 409 and "обновите" in r.json()["detail"]


def test_postpone_and_person(conn):
    with patch(f"{R}.dq_cases.postpone_case", return_value=[3, 4]) as m:
        r = client.post("/api/admin/data-quality/cases/c1/postpone", json={"reason": "не знаю ДР"})
    assert r.json() == {"ok": True, "action_ids": [3, 4]} and m.call_args.args == (conn, "c1", "не знаю ДР", "testuser")
    with patch(f"{R}.dq_cases.case_for_card", return_value={"key": "c9"}):
        assert client.get("/api/admin/data-quality/person/9").json() == {"key": "c9"}


def test_cases_require_auth():
    app.dependency_overrides.pop(api_require_auth, None)
    assert client.get("/api/admin/data-quality/cases").status_code == 401
```

- [ ] **Step 2: Запустить — падает** (404 на новых путях).

- [ ] **Step 3: Эндпоинты** — в `src/krasmarafon/routers/data_quality.py`:

импорт рядом с `from src.analytics import data_quality as dq`:
```python
from src.analytics import dq_cases
```

модели рядом с остальными:
```python
class AnswerBody(BaseModel):
    question_id: str
    answer_id: str
    inputs: dict[str, str] = {}


class PostponeBody(BaseModel):
    reason: str = ""
```

эндпоинты (после `list_findings`):
```python
@router.get("/api/admin/data-quality/cases")
async def list_cases(status: Literal["open", "postponed"] = "open", event_id: Optional[int] = None,
                     user: str = Depends(api_require_auth)) -> dict:
    return {"cases": await run_in_threadpool(_with_conn, dq_cases.list_cases, status, event_id)}


@router.get("/api/admin/data-quality/cases/{key}")
async def get_case(key: str, user: str = Depends(api_require_auth)) -> dict:
    case = await run_in_threadpool(_with_conn, dq_cases.get_case, key)
    if not case:
        raise HTTPException(status_code=404, detail="Дело закрыто или изменилось — обновите список")
    return case


@router.post("/api/admin/data-quality/cases/{key}/answer")
async def answer(key: str, body: AnswerBody, user: str = Depends(api_require_auth)) -> dict:
    try:
        return await run_in_threadpool(_with_conn, dq_cases.apply_answer, key, body.question_id, body.answer_id,
                                       body.inputs, user)
    except dq_cases.StaleQuestion as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post("/api/admin/data-quality/cases/{key}/postpone")
async def postpone(key: str, body: PostponeBody, user: str = Depends(api_require_auth)) -> dict:
    try:
        ids = await run_in_threadpool(_with_conn, dq_cases.postpone_case, key, body.reason, user)
    except dq_cases.StaleQuestion as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"ok": True, "action_ids": ids}


@router.get("/api/admin/data-quality/person/{client_id}")
async def person(client_id: int, user: str = Depends(api_require_auth)) -> dict:
    case = await run_in_threadpool(_with_conn, dq_cases.case_for_card, client_id)
    if not case:
        raise HTTPException(status_code=404, detail=f"Нет карточки #{client_id}")
    return case
```

(`_with_conn` превращает `ValueError` в 400 — ошибки действий (конфликт ФИ+ДР и т.п.) так и вернутся пользователю.)

- [ ] **Step 4: Запустить** `tests/integration/test_admin_dq_cases.py tests/integration/test_admin_data_quality.py` — passed.

- [ ] **Step 5: Commit**

```bash
git add src/krasmarafon/routers/data_quality.py tests/integration/test_admin_dq_cases.py
git commit -m "feat(data-quality): API дел — очередь, дело, ответ, отложить, дело по карточке"
```

---

### Task 9: Сквозные проверки — правки видны там, где их смотрят

**Files:**
- Test: `tests/integration/test_dq_cases_db.py` (дополнить)

- [ ] **Step 1: Тест** — дописать в `tests/integration/test_dq_cases_db.py`:

```python
def test_answer_is_visible_in_results_profile_and_card_counters(db):
    from src.analytics import db_athletes, db_results
    conn, cur = db
    rid, father, son = foreign_case(conn, cur)
    cur.execute("SELECT event_id FROM results WHERE id = %s", (rid,))
    ev = cur.fetchone()["event_id"]
    case = dq_cases.case_for_card(conn, father)
    q = next(q for q in case["questions"] if q["code"] == "R-FOREIGN")
    dq_cases.apply_answer(conn, case["key"], q["id"], f"to:{son}", {}, USER)

    db_results._results_cache.clear()                     # кеш результатов (TTL 5 с) — как после истечения
    row = next(r for r in db_results.get_race_results_by_event_id(ev) if r["start_number"] == 1012)
    assert row["client_id"] == son and row["name"] == "Саша"
    assert [r["start_number"] for r in db_athletes.get_athlete_by_client(son)[1]] .count(1012) == 1
    assert 1012 not in [r["start_number"] for r in db_athletes.get_athlete_by_client(father)[1]]
    cur.execute("SELECT c.last_result_id, (SELECT MAX(id) FROM results r WHERE r.client_id = c.id) AS mx "
                "FROM clients c WHERE c.id = %s", (son,))
    counters = cur.fetchone()
    assert counters["last_result_id"] == counters["mx"]


def test_moved_lead_visible_in_admin_leads_and_duplicates(db):
    from src.analytics import db_results
    conn, cur = db
    ev = event(cur, "Детский заявки", 1.0)
    cur.execute("UPDATE events SET event_name = 'Детский забег', event_year = 2099 WHERE id = %s", (ev,))
    _, kid = result(cur, event(cur, "Детский 3", 1.0), 7, "2093-04-15", name="Алексей", cat="Мальчики")
    cur.execute("""INSERT INTO leads (surname, name, sex, city, birthday, phone, email, event_name, event_distance,
                   event_year, products, amount, client_id, event_id, start_number, created_at)
                   VALUES (%s, 'Алексей', 'Мужчина', '', '2064-06-30', '+70000000002', 'p@test.ru', 'Детский забег',
                           '1 км', 2099, '', 0, 0, %s, NULL, '2026-01-01 10:00:00')""", (SUR, ev))
    lid = cur.lastrowid
    cur.execute("SELECT client_id FROM leads WHERE id = %s", (lid,))
    parent = cur.fetchone()["client_id"]
    conn.commit()
    case = dq_cases.case_for_card(conn, parent)
    q = next(q for q in case["questions"] if q["code"] == "R-FOREIGN" and q["lead_id"] == lid)
    dq_cases.apply_answer(conn, case["key"], q["id"], f"to:{kid}", {}, USER)
    leads = db_results.get_leads_admin(event_id=ev, limit=10)
    assert [(l["id"], l["client_id"], l["is_duplicate"]) for l in leads] == [(lid, kid, 0)]
```

- [ ] **Step 2: Запустить** — passed. Если что-то не видно (кеш, флаг дубля) — это дефект цепочки: чинить в `dq_actions`, не в тесте.

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_dq_cases_db.py
git commit -m "test(data-quality): ответ на вопрос виден в результатах, профиле, заявках и счётчиках карточки"
```

---

### Task 10: Полный прогон, прод (только чтение), деплой

- [ ] **Step 1:** `C:/Users/podbo/miniconda3/python.exe -m pytest tests/unit/ tests/integration/ -q -p no:warnings` — все passed (код возврата сохранить, не маскировать `| tail`).
- [ ] **Step 2: Сухой прогон на данных прода** (только чтение): загрузить ветку `dq_cases.py`/`dq_checks.py`/`dq_actions.py` во временный каталог на VPS и вызвать `list_cases(conn, "open")` + `get_case` для первых 5 дел; проверить: число дел, у каждого вопроса непустой текст, ≤ 1 ★, нет исключений. Ничего не записывать.
- [ ] **Step 3: Деплой** — после подтверждения пользователя: `git push origin main`, `gh run watch … --exit-status`.
- [ ] **Step 4: Прод** — `GET /api/admin/data-quality/cases` под админ-сессией (Playwright, как в прошлых проверках) отдаёт очередь; старая вкладка «Качество данных» работает как раньше.
- [ ] **Step 5:** ревью в `.taskmaster/tasks/todo.md`; план этапа 3 (экран).

---

### Task 11: Скорость дела и ответа (добавлено после сухого прогона на проде 2026-10-29)

Замер на проде: `list_cases` 8.3 с, `get_case` 8.2 с, `apply_answer` ≈ 16 с (два полных `load`) — для экрана этапа 3 неприемлемо. Локально: `load` 1.6 с, `run_checks` 2.3 с, card-scope `run_checks` 0.075 с.

**Цель:** `get_case`, `case_for_card`, `apply_answer`, `postpone_case` — без полной загрузки базы (целевое время на проде < 1.5 с); `list_cases` — полный прогон, но кешируется.

**Files:** `src/analytics/dq_checks.py` (`load_scoped`, кеш `Names`), `src/analytics/dq_cases.py`, тесты `tests/unit/test_dq_cases.py`, `tests/integration/test_dq_cases_db.py`, `tests/integration/test_data_quality_undo.py`.

1. `load_scoped(conn, card_ids)` в `dq_checks.py` → `Data` только с нужными строками:
   - фамилии карточек `card_ids` и их строк; все карточки с этими фамилиями (`clients.surname IN (...)` — колляция `utf8mb4_0900_ai_ci` не различает регистр и ё/е), их заявки и результаты, плюс заявки и результаты с этими фамилиями;
   - плюс строки тех же забегов с теми же стартовыми номерами, что у загруженных (R-LEAD «тот же номер» при опечатке в фамилии), и карточки этих строк;
   - события — все (их ~150);
   - `data.names` — общий справочник имён (`Names` по всей базе) из кеша процесса, TTL 10 мин (строится одним запросом `SELECT surname, name, sex FROM leads UNION ALL ... FROM results`, не через полный `load`).
   Тест-эквивалентность (unit, на данных в памяти через заглушку курсора нельзя — делай integration на локальной БД): для 10 случайных карточек с находками `{f.key for f in run_checks(load_scoped(conn, S), card_ids=S)} == {f.key for f in run_checks(load(conn), card_ids=S)}`.
2. Дело без полной загрузки: `get_case(key)`/`case_for_card(cid)`/`apply_answer`/`postpone_case` строят дело так: стартовый набор карточек (из ключа `c<id>`, из `client_id`, из ключа находки `question_id` — его часть после последнего `:` — список id через `-`), затем расширение до неподвижной точки (не более 4 итераций): `load_scoped` → `run_checks(card_ids=набор)` → `group_cases` → набор ∪ карточки найденных находок и тёзок; затем дело, содержащее стартовую карточку. Ключи `r<id>`/`l<id>` (без карточек) — `load_scoped` по фамилии строки.
   Тест: для каждого дела из полного прогона на локальной БД (`list_cases`) `get_case(key)` (новый) возвращает те же карточки и те же id вопросов, что старый путь через полный прогон (оставь старый путь как приватную функцию для теста или сравнивай с `group_cases(run_checks(load(conn)))`).
3. `list_cases`: результат полного прогона (`data`, находки) кешируется в процессе на 60 с; любой `apply_answer`/`postpone_case`/действие из `dq_actions` в этом процессе сбрасывает кеш (функция `invalidate()` в `dq_cases`, вызывается в конце `apply_answer`/`postpone_case`; роутеры старой вкладки (`/merge`, `/move`, `/edit`, `/dismiss`, `/undo`, `/fix-fio`, `/delete-result`, `/apply-auto`) тоже вызывают `dq_cases.invalidate()` после успеха). Другие процессы сервера увидят изменения не позже чем через 60 с; устаревший вопрос защищён 409.
4. `apply_answer`: не более двух `load_scoped` и ни одного полного `load`. Счётчики в unit-тестах обновить.
5. Тесты на БД: маркеры тестовых данных уникальны для прогона (суффикс `os.getpid()` или `uuid4().hex[:6]` в фамилии и названии события; уборка — по этому суффиксу), чтобы параллельные прогоны не удаляли данные друг друга.
6. Замер: короткий скрипт в `%TEMP%` — время `list_cases` (холодный/из кеша), `get_case`, `apply_answer` (на тестовых данных) на локальной БД — в отчёт.

Коммит: `perf(data-quality): дело и ответ — загрузка только нужных фамилий, кеш очереди и справочника имён`.

### Task 12: Спецификация — фактические решения этапа 2

В `docs/superpowers/specs/2026-10-28-data-quality-cases-design.md` (Этап 2) отразить: вход «дело по человеку» — `GET /api/admin/data-quality/person/{client_id}` (поиск — `/cards?q=`); конфликт ФИ+ДР — поле `conflict` в ответе и ответ `merge_with:<id>` (не новый вопрос C-TWIN); ответ «Другое значение» — два отменяемых действия (карточка, затем строка), не одна транзакция; откладывание дела — по действию на вопрос; ошибки — 400 `detail` / 409; ключи дел `c<id>`/`r<id>`/`l<id>`/`p<id>`; кеш очереди 60 с и загрузка по фамилиям (Task 11); отложенные находки не трогает и ночной `apply_auto`.
Коммит: `docs(spec): этап 2 — фактические решения`.
