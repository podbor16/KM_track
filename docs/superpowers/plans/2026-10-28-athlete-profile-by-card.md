# Профиль участника по карточке — план реализации (этап 1 из 3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** «История участия» и профиль участника строятся по карточке (`clients.id`), а не по совпадению ФИО в строках результатов — тёзки разделены, правки «Качества данных» (переносы, склейки) видны на сайте.

**Architecture:** `src/analytics/db_athletes.py` получает две функции на фиксированных колонках: поиск карточек (с `client_id`, годом рождения, числом забегов) и профиль по `client_id` (карточка + её результаты). API `GET /api/athlete/{client_id}` заменяет `/api/athlete/{surname}/{name}`. Три места фронтенда (поиск `/history`, страница профиля, кнопка «Профиль» в `/results`) передают `client_id`.

**Tech Stack:** Python 3.13, FastAPI, mysql-connector (без ORM), pytest; vanilla JS в шаблонах.

Спецификация: `docs/superpowers/specs/2026-10-28-data-quality-cases-design.md` → «Этап 1».

---

## Файлы

| Файл | Что меняется |
|---|---|
| `src/analytics/db_athletes.py` | переписать целиком: `search_clients_optimized(q, limit)` → `[{client_id, surname, name, birth_year, events_count}]`; `get_athlete_by_client(client_id)` → `(athlete, results)`; удалить `get_athlete_results_optimized` |
| `src/analytics/db_connection_optimized.py:17-60` | реэкспорт: убрать `get_athlete_results_optimized`, `get_athlete_results`; добавить `get_athlete_by_client` |
| `src/krasmarafon/routers/api.py:163-213` | `GET /api/athlete/{client_id}` вместо `/{surname}/{name}` |
| `src/krasmarafon/services/results_service.py:339` | в строке бегуна — `client_id` |
| `static/js/history.js:95-115` | `data-client-id`, переход `/athlete-profile?id=…` |
| `templates/krasmarafon/athlete-profile.html:164-170, 303-318` | `getUrlParams` → `id`; fetch `/api/athlete/{id}` |
| `static/js/analytics-results.js:1297` | `profileUrl` по `runner.client_id` |
| `tests/integration/test_athletes_by_card_db.py` | новый: поиск и профиль на локальной БД |
| `tests/integration/test_history_toggle_routes.py:74-78` | путь API |
| `tests/integration/test_athlete_api.py` | новый: API с замоканной БД |

Запуск тестов: `conda run -n base python -m pytest <путь> -q -p no:warnings` (интеграционные на локальной БД берут `.env.local` через `tests/conftest.py`).

---

### Task 1: Поиск карточек и профиль по `client_id` (БД)

**Files:**
- Modify: `src/analytics/db_athletes.py` (весь файл)
- Modify: `src/analytics/db_connection_optimized.py:17-60`
- Test: `tests/integration/test_athletes_by_card_db.py`

- [ ] **Step 1: Написать падающий тест**

`tests/integration/test_athletes_by_card_db.py`:

```python
"""Поиск карточек и профиль по client_id на локальной БД (.env.local): тёзки — раздельно.
Тестовые данные — на событиях 2099 года, убираются после теста."""
import pytest

from src.analytics import db_athletes
from src.analytics.db_pool import get_pooled_connection

EV, SUR = "Тест профиля", "Тестпрофилев"


@pytest.fixture
def db():
    conn = get_pooled_connection()
    if not conn:
        pytest.skip("Нет локальной БД")
    cur = conn.cursor(dictionary=True)

    def cleanup():
        cur.execute("SELECT id FROM events WHERE event_name = %s", (EV,))
        ids = [r["id"] for r in cur.fetchall()]
        if ids:
            ph = ",".join(map(str, ids))
            cur.execute(f"DELETE FROM results WHERE event_id IN ({ph})")
            cur.execute(f"DELETE FROM events WHERE id IN ({ph})")
        cur.execute("DELETE FROM clients WHERE surname = %s", (SUR,))
        conn.commit()

    cleanup()
    yield conn, cur
    cleanup()
    cur.close()
    conn.close()


def add_result(cur, dist, bib, bd, name="Александр"):
    cur.execute("INSERT INTO events (event_name, event_distance, event_year) VALUES (%s, %s, 2099)", (EV, dist))
    cur.execute("""INSERT INTO results (surname, name, birthday, client_id, event_id, sex, start_number, category,
                   race_status) VALUES (%s, %s, %s, 0, %s, 'Мужчина', %s, 'М18-49', 'Finished')""",
                (SUR, name, bd, cur.lastrowid, bib))
    cur.execute("SELECT client_id FROM results WHERE id = %s", (cur.lastrowid,))
    return cur.fetchone()["client_id"]


def test_namesakes_are_separate_cards_with_birth_year(db):
    conn, cur = db
    father = add_result(cur, 21.1, 1, "1980-03-09")
    add_result(cur, 10.0, 2, "1980-03-09")
    son = add_result(cur, 1.0, 3, "2013-12-20")
    conn.commit()

    found = {c["client_id"]: c for c in db_athletes.search_clients_optimized(SUR)}
    assert set(found) == {father, son}
    assert found[father] == {"client_id": father, "surname": SUR, "name": "Александр",
                             "birth_year": "1980", "events_count": 2}
    assert found[son]["birth_year"] == "2013" and found[son]["events_count"] == 1


def test_profile_by_card_has_only_its_results(db):
    conn, cur = db
    father = add_result(cur, 21.1, 1, "1980-03-09")
    son = add_result(cur, 1.0, 3, "2013-12-20")
    conn.commit()

    athlete, results = db_athletes.get_athlete_by_client(son)
    assert athlete["client_id"] == son and athlete["surname"] == SUR and str(athlete["birthday"]) == "2013-12-20"
    assert [r["start_number"] for r in results] == [3]
    assert results[0]["event_name"] == EV and float(results[0]["event_distance"]) == 1.0
    assert athlete["category"] == "М18-49"                       # пол/категория — из последнего результата

    assert db_athletes.get_athlete_by_client(father)[1][0]["start_number"] == 1
    assert db_athletes.get_athlete_by_client(999_999_999) == ({}, [])
```

- [ ] **Step 2: Запустить — тест падает**

Run: `conda run -n base python -m pytest tests/integration/test_athletes_by_card_db.py -q -p no:warnings`
Expected: FAIL — `KeyError: 'client_id'` (поиск сейчас без `client_id`) и `AttributeError: ... get_athlete_by_client`.

- [ ] **Step 3: Переписать `src/analytics/db_athletes.py`**

Весь файл:

```python
"""
Поиск участников и профиль для «Истории участия» (/history, /athlete-profile).

Профиль строится по карточке (clients.id), а не по совпадению ФИО в строках результатов:
тёзки (отец и сын «Пцарев Александр») — разные профили, правки «Качества данных»
(перенос строки, склейка карточек) сразу видны на сайте.
"""

import logging
from typing import Any, Dict, List, Tuple

from src.analytics.db_pool import get_pooled_connection

logger = logging.getLogger(__name__)


def search_clients_optimized(search_query: str, limit: int = 20) -> List[Dict[str, Any]]:
    """Карточки по началу фамилии или имени -> [{client_id, surname, name, birth_year, events_count}]."""
    connection = get_pooled_connection()
    if not connection:
        logger.error("❌ Не удалось получить соединение")
        return []
    try:
        cursor = connection.cursor(dictionary=True)
        term = f"{search_query.strip()}%"
        cursor.execute(
            """SELECT c.id AS client_id, c.surname, c.name, c.birthday,
                      (SELECT COUNT(*) FROM results r WHERE r.client_id = c.id) AS events_count
               FROM clients c
               WHERE c.id <> 0 AND (c.surname LIKE %s OR c.name LIKE %s)
               ORDER BY c.surname, c.name, c.birthday
               LIMIT %s""",
            (term, term, int(limit)),
        )
        rows = cursor.fetchall()
        cursor.close()
        for row in rows:
            bd = row.pop("birthday")
            row["birth_year"] = str(bd.year) if bd else "Неизвестно"
        return rows
    except Exception as e:
        logger.error(f"❌ Ошибка поиска: {e}")
        return []
    finally:
        if connection.is_connected():
            connection.close()


def get_athlete_by_client(client_id: int) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Карточка и её результаты -> (athlete, results). Нет карточки -> ({}, []).
    athlete: поля последнего результата (пол, категория…) + ФИО и ДР карточки + client_id."""
    connection = get_pooled_connection()
    if not connection:
        logger.error("❌ Не удалось установить соединение")
        return {}, []
    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT id, surname, name, birthday FROM clients WHERE id = %s AND id <> 0", (int(client_id),))
        card = cursor.fetchone()
        if not card:
            cursor.close()
            return {}, []
        cursor.execute(
            """SELECT r.*, e.event_name, e.event_distance, e.event_year, e.event_date
               FROM results r
               LEFT JOIN events e ON r.event_id = e.id
               WHERE r.client_id = %s
               ORDER BY e.event_year DESC, e.event_date DESC, r.id DESC""",
            (card["id"],),
        )
        results = [dict(r) for r in cursor.fetchall()]
        cursor.close()
        athlete = dict(results[0]) if results else {}
        athlete.update(client_id=card["id"], surname=card["surname"], name=card["name"], birthday=card["birthday"])
        return athlete, results
    except Exception as e:
        logger.error(f"❌ Ошибка при получении профиля #{client_id}: {e}")
        return {}, []
    finally:
        if connection.is_connected():
            connection.close()


search_clients = search_clients_optimized
```

- [ ] **Step 4: Поправить реэкспорт в `src/analytics/db_connection_optimized.py`**

Прочитать строки 15–60. В импорте из `db_athletes` заменить

```python
    search_clients_optimized,
    get_athlete_results_optimized,
    get_athlete_results,
    search_clients,
```

на

```python
    search_clients_optimized,
    get_athlete_by_client,
    search_clients,
```

и в `__all__` заменить

```python
    "search_clients_optimized",
    "get_athlete_results_optimized",
    "get_athlete_results",
    "search_clients",
```

на

```python
    "search_clients_optimized",
    "get_athlete_by_client",
    "search_clients",
```

- [ ] **Step 5: Запустить — тест проходит**

Run: `conda run -n base python -m pytest tests/integration/test_athletes_by_card_db.py -q -p no:warnings`
Expected: `2 passed`

- [ ] **Step 6: Commit**

```bash
git add src/analytics/db_athletes.py src/analytics/db_connection_optimized.py tests/integration/test_athletes_by_card_db.py
git commit -m "feat(history): поиск и профиль участника по карточке, тёзки раздельно"
```

---

### Task 2: API `GET /api/athlete/{client_id}`

**Files:**
- Modify: `src/krasmarafon/routers/api.py:181-213`
- Modify: `tests/integration/test_history_toggle_routes.py:74-78`
- Test: `tests/integration/test_athlete_api.py`

- [ ] **Step 1: Написать падающий тест**

`tests/integration/test_athlete_api.py`:

```python
"""/api/athlete/{client_id} и /api/search-athletes — профиль по карточке (БД замокана)."""
import datetime
from unittest.mock import patch

DB = "src.analytics.db_connection_optimized"
ON = patch("src.krasmarafon.routers.api.get_history_enabled", return_value=True)


def test_profile_by_client_id(client):
    athlete = {"client_id": 40803, "surname": "Пцарев", "name": "Александр", "birthday": datetime.date(2013, 12, 20)}
    rows = [{"id": 1, "start_number": 1012, "event_name": "Детский забег", "event_date": datetime.date(2016, 8, 28)}]
    with ON, patch(f"{DB}.get_athlete_by_client", return_value=(athlete, rows)) as m:
        r = client.get("/api/athlete/40803")
    assert r.status_code == 200 and m.call_args.args == (40803,)
    body = r.json()
    assert body["athlete"]["birthday"] == "2013-12-20" and body["athlete"]["client_id"] == 40803
    assert body["results"][0]["event_date"] == "2016-08-28" and body["total_races"] == 1


def test_profile_unknown_card_404_and_old_path_gone(client):
    with ON, patch(f"{DB}.get_athlete_by_client", return_value=({}, [])):
        assert client.get("/api/athlete/999").status_code == 404
    with ON:
        assert client.get("/api/athlete/Пцарев/Александр").status_code == 404


def test_search_returns_client_ids(client):
    found = [{"client_id": 43759, "surname": "Пцарев", "name": "Александр", "birth_year": "1980", "events_count": 9},
             {"client_id": 40803, "surname": "Пцарев", "name": "Александр", "birth_year": "2013", "events_count": 3}]
    with ON, patch(f"{DB}.search_clients_optimized", return_value=found):
        r = client.get("/api/search-athletes?q=Пцарев")
    assert [x["client_id"] for x in r.json()["results"]] == [43759, 40803]
```

- [ ] **Step 2: Запустить — тест падает**

Run: `conda run -n base python -m pytest tests/integration/test_athlete_api.py -q -p no:warnings`
Expected: FAIL — `/api/athlete/40803` попадает в старый роут `{surname}/{name}` не может (один сегмент) → 404; `test_profile_by_client_id` падает на `assert r.status_code == 200`.

- [ ] **Step 3: Заменить роут в `src/krasmarafon/routers/api.py`**

Прочитать строки 181–213 и заменить функцию `get_athlete_profile` целиком на:

```python
@router.get("/api/athlete/{client_id}")
async def get_athlete_profile(client_id: int = PathParam(..., description="Номер карточки участника")):
    """Профиль участника по карточке и все его результаты."""
    if not get_history_enabled():
        raise HTTPException(status_code=404, detail="Not Found")
    try:
        from src.analytics.db_connection_optimized import get_athlete_by_client

        athlete_info, results = await asyncio.get_event_loop().run_in_executor(None, get_athlete_by_client, client_id)
        if not athlete_info:
            raise HTTPException(status_code=404, detail=f"Участник #{client_id} не найден")

        def _format(d: dict) -> dict:
            return {k: v.isoformat() if hasattr(v, 'isoformat') else v for k, v in d.items()}

        return {
            'athlete': _format(athlete_info),
            'results': [_format(r) for r in results],
            'total_races': len(results),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"get_athlete_profile error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
```

- [ ] **Step 4: Поправить старый тест-переключатель**

В `tests/integration/test_history_toggle_routes.py` в `test_athlete_profile_api_404_when_disabled` заменить

```python
        r = client.get("/api/athlete/Иванов/Иван")
```

на

```python
        r = client.get("/api/athlete/1")
```

и в docstring файла (строка 3) `/api/athlete/{surname}/{name}` → `/api/athlete/{client_id}`.

- [ ] **Step 5: Запустить — тесты проходят**

Run: `conda run -n base python -m pytest tests/integration/test_athlete_api.py tests/integration/test_history_toggle_routes.py -q -p no:warnings`
Expected: все passed (3 новых + 9 существующих).

- [ ] **Step 6: Commit**

```bash
git add src/krasmarafon/routers/api.py tests/integration/test_athlete_api.py tests/integration/test_history_toggle_routes.py
git commit -m "feat(history): GET /api/athlete/{client_id} вместо поиска по ФИО"
```

---

### Task 3: `client_id` в строке бегуна на странице результатов

**Files:**
- Modify: `src/krasmarafon/services/results_service.py:339-341`
- Test: `tests/unit/test_results_service_client_id.py`

- [ ] **Step 1: Написать падающий тест**

`tests/unit/test_results_service_client_id.py` (`_do_build` — сборка ответа без кеша; БД замокана):

```python
"""Строка бегуна на /results несёт client_id — кнопка «Профиль» ведёт на профиль по карточке."""
from datetime import date, timedelta
from unittest.mock import patch

DB = "src.analytics.db_connection_optimized"


def test_runner_row_has_client_id():
    from src.krasmarafon.services import results_service as rs
    runner = {"id": 7, "client_id": 40803, "surname": "Пцарев", "name": "Александр", "start_number": 1012,
              "race_status": "Finished", "time_gun_finish": timedelta(minutes=9), "sex": "Мужчина", "category": "М"}
    ev = {"event_name": "Детский забег", "event_distance": 1.0, "event_year": 2016, "event_date": date(2016, 8, 28)}
    with patch(f"{DB}.get_race_results_by_event_id", return_value=[runner]), \
            patch(f"{DB}.get_event_info_by_id", return_value=ev), \
            patch(f"{DB}.get_category_avg_paces", return_value={}), \
            patch(f"{DB}.get_prev_year_results", return_value=[]):
        resp = rs._do_build(150, None, None, {})
    row = resp.results[0]
    assert row["client_id"] == 40803 and row["id"] == 7
```

- [ ] **Step 2: Запустить — тест падает**

Run: `conda run -n base python -m pytest tests/unit/test_results_service_client_id.py -q -p no:warnings`
Expected: FAIL — `KeyError: 'client_id'` (проверено при составлении плана).

- [ ] **Step 3: Добавить поле**

В `src/krasmarafon/services/results_service.py` после строки

```python
            'id': runner.get('id') or runner.get('client_id'),
```

добавить

```python
            'client_id': runner.get('client_id'),
```

- [ ] **Step 4: Запустить — проходит**, затем весь `tests/unit/` (кеши/ответы результатов не должны сломаться)

Run: `conda run -n base python -m pytest tests/unit/ -q -p no:warnings`
Expected: все passed.

- [ ] **Step 5: Commit**

```bash
git add src/krasmarafon/services/results_service.py tests/unit/test_results_service_client_id.py
git commit -m "feat(results): client_id в строке бегуна — ссылка на профиль по карточке"
```

---

### Task 4: Фронтенд — поиск, профиль, кнопка «Профиль»

**Files:**
- Modify: `static/js/history.js:95-115`
- Modify: `templates/krasmarafon/athlete-profile.html:164-170, 303-318`
- Modify: `static/js/analytics-results.js:1297`

- [ ] **Step 1: `static/js/history.js` — элемент списка несёт `client_id`**

В `displayResults` заменить

```js
            html += `
                <div class="autocomplete-item" data-index="${index}" data-surname="${surname}" data-name="${name}">
                    <div class="athlete-info">${surname} ${name}, ${birth_year} г.р.</div>
                </div>
            `;
```

на

```js
            const races = athlete.events_count ? ` · забегов: ${athlete.events_count}` : '';
            html += `
                <div class="autocomplete-item" data-index="${index}" data-client-id="${Number(athlete.client_id)}"
                     data-surname="${surname}" data-name="${name}">
                    <div class="athlete-info">${surname} ${name}, ${birth_year} г.р.${races}</div>
                </div>
            `;
```

В `selectAthlete` заменить

```js
        window.location.href = `/athlete-profile?surname=${encodeURIComponent(surname)}&name=${encodeURIComponent(name)}`;
```

на

```js
        window.location.href = `/athlete-profile?id=${encodeURIComponent(element.dataset.clientId)}`;
```

- [ ] **Step 2: `templates/krasmarafon/athlete-profile.html` — параметр `id`**

Заменить `getUrlParams`:

```js
        function getUrlParams() {
            const params = new URLSearchParams(window.location.search);
            return { id: params.get('id') };
        }
```

В `loadAthleteProfile` заменить

```js
            if (!params.surname || !params.name) {
                showError('Параметры спортсмена не найдены');
                return;
            }

            try {
                const response = await fetch(`/api/athlete/${encodeURIComponent(params.surname)}/${encodeURIComponent(params.name)}`);
```

на

```js
            if (!/^\d+$/.test(params.id || '')) {
                showError('Участник не указан — найдите его на странице «История участия»');
                return;
            }

            try {
                const response = await fetch(`/api/athlete/${params.id}`);
```

Проверить, что больше нигде в файле нет `params.surname` / `params.name`:
Run: `grep -n "params\.\(surname\|name\)" templates/krasmarafon/athlete-profile.html` → пусто.

- [ ] **Step 3: `static/js/analytics-results.js` — кнопка «Профиль»**

Заменить строку 1297

```js
    const profileUrl = `/athlete-profile?surname=${encodeURIComponent(runner.surname || '')}&name=${encodeURIComponent(runner.name || '')}`;
```

на

```js
    const profileUrl = `/athlete-profile?id=${encodeURIComponent(runner.client_id || '')}`;
```

- [ ] **Step 4: Синтаксис JS и JS-тесты**

Run: `node --check static/js/history.js && node --check static/js/analytics-results.js && echo OK`
Expected: `OK`
Run: `node tests/js/test_analytics_athlete_profile_view_toggle.js`
Expected: без ошибок (тест читает шаблон профиля).

- [ ] **Step 5: Commit**

```bash
git add static/js/history.js templates/krasmarafon/athlete-profile.html static/js/analytics-results.js
git commit -m "feat(history): поиск, профиль и кнопка «Профиль» — по номеру карточки"
```

---

### Task 5: Проверка в браузере, полный прогон, деплой

**Files:** нет изменений кода.

- [ ] **Step 1: Полный прогон тестов**

Run: `conda run -n base python -m pytest tests/unit/ tests/integration/ -q -p no:warnings`
Expected: все passed (сохранить код возврата: не маскировать `| tail`).

- [ ] **Step 2: Локальный сервер на `.env.local` и включённая история**

Запустить локальный сервер (порт, не занятый чужими сессиями: проверить `netstat -ano | grep LISTEN`), на нём временно включить «Историю участия» в /admin (переключатель; локальный файл `config/history_enabled.local`, на прод не уходит).

- [ ] **Step 3: Браузер (Playwright), компьютер и телефон 390 px**

1. `/history`: ввести «Пцарев» → в списке отдельные строки с разными годами рождения и «забегов: N».
2. Клик по строке → `/athlete-profile?id=<число>` — в профиле только результаты этой карточки.
3. `/results` события с результатами → кнопка «Профиль» (если включена `PROFILE_BUTTON_ENABLED`) ведёт на `?id=`.
4. `/athlete-profile` без `id` → сообщение «Участник не указан…».
5. Нет горизонтальной прокрутки на 390 px.

- [ ] **Step 4: Вернуть переключатель истории локально как был, остановить сервер**

- [ ] **Step 5: Пуш и деплой** (после подтверждения пользователя)

```bash
git push origin main
gh run watch $(gh run list --limit 1 --json databaseId -q '.[0].databaseId') --exit-status
```
Expected: `Deploy to VPS` — success.

- [ ] **Step 6: Прод (только чтение)**

История на проде выключена — проверить через API под админ-сессией нельзя (роуты отдают 404 при выключенной истории). Проверка: `/api/athlete/40803` → 404 (выключено, как и раньше), `/history` → редирект на `/`. Включение — решение пользователя (бэклог в Obsidian).

- [ ] **Step 7: Ревью в `.taskmaster/tasks/todo.md`** — что сделано, чем проверено.
