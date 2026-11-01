# Демо «Повтор гонки» (часть 1: ядро + Жара) — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** статический сайт `podbor16.github.io/race-tracker-demo/`, где Жара 21,1 км и Жара 5 км проигрываются в настоящем трекере Красмарафона с перемоткой и ускорением.

**Architecture:** скрипт на Python заранее «проигрывает» гонку шагом 5 с через серверную функцию сборки ответа трекера (вынесенную из `_do_build`) и пишет сжатую запись `initial + changes + distance`. Браузерный модуль `demo-replay.js` подменяет часы (`Date`), `fetch` и `EventSource` и кормит неизменённый `tracker-*.js` из записи. Сборка рендерит `tracker.html` тем же Jinja-шаблоном, подменяя три include-шаблона (шапка, Метрика, футер) демо-версиями.

**Tech Stack:** Python 3.13, Jinja2, mysql-connector (локальная БД), pytest; ванильный JS (DecompressionStream), GitHub Pages.

**Спека:** `docs/superpowers/specs/2026-11-01-race-replay-demo-design.md`

**Запуск тестов:** `conda run -n base python -m pytest tests/unit/ -v` (conftest грузит `.env.local` → локальная БД :3308).

---

## Структура файлов

| Файл | Ответственность |
|---|---|
| `src/krasmarafon/services/runners_service.py` (изм.) | `calculate_live_position(..., now=None)` |
| `src/krasmarafon/services/results_service.py` (изм.) | `load_hist_data()`, `assemble_event_results()` — чистая сборка; `_do_build()` = загрузка + вызов |
| `src/krasmarafon/routers/api.py` (изм.) | `build_current_event_response(event)` |
| `tools/demo/__init__.py` | пакет |
| `tools/demo/races.py` | реестр демо-гонок |
| `tools/demo/anonymize.py` | фейковые ФИО, перемешивание номеров, перенумерация id |
| `tools/demo/timeline.py` | «строки результатов на момент T»: обрезка времён, статусы, места |
| `tools/demo/record.py` | проигрывание → запись; сжатие `current_distance`; `state_at()` для тестов |
| `tools/demo/source.py` | загрузка входных данных из локальной БД и конфига |
| `tools/demo/site.py` | рендер страниц, копирование статики, переписывание путей |
| `tools/demo/checks.py` | проверки ПДн / ссылок / `/api/` |
| `tools/demo/build.py` | CLI сборки |
| `tools/demo/publish.py` | публикация в `podbor16/race-tracker-demo` |
| `tools/demo/templates/krasmarafon/{header,analytics,krasmarafon_footer}.html` | демо-подмены include-шаблонов |
| `tools/demo/templates/demo/{index,404}.html` | витрина, 404 |
| `tools/demo/static/demo-replay.js`, `demo-replay.css` | часы, подмена источников, панель |
| `tools/demo/README.md` | как собрать, опубликовать, добавить гонку |
| `tests/unit/test_demo_*.py` | тесты |

Константа базового пути — `BASE = "/race-tracker-demo/"`; сайт собирается в `dist/race-tracker-demo/`, чтобы локальный `python -m http.server -d dist` повторял адреса Pages.

---

### Task 1: `calculate_live_position(now=...)`

**Files:**
- Modify: `src/krasmarafon/services/runners_service.py:76-109`
- Test: `tests/unit/test_runners_service.py`

- [ ] **Step 1: Падающий тест** — дописать в конец `tests/unit/test_runners_service.py`:

```python
def test_calculate_live_position_uses_explicit_now():
    from datetime import datetime, date, timedelta
    from src.krasmarafon.services.runners_service import calculate_live_position
    gun = datetime(2026, 8, 23, 9, 0, 0)
    runner = {'time_gun_start': timedelta(0), 'category': ''}
    speed, dist, _ = calculate_live_position(
        runner, [0.0, 5.0, 21.1], date(2026, 8, 23), {},
        hist_speed=12.0, gun_start_dt=gun, now=gun + timedelta(minutes=30),
    )
    assert speed == 12.0
    assert abs(dist - 6.0) < 1e-9
```

- [ ] **Step 2:** `conda run -n base python -m pytest tests/unit/test_runners_service.py::test_calculate_live_position_uses_explicit_now -v` → FAIL (`unexpected keyword argument 'now'`).

- [ ] **Step 3:** в сигнатуре `calculate_live_position` после `gun_start_dt: Optional[datetime] = None,` добавить `now: Optional[datetime] = None,`; строку `now = datetime.now()` заменить на:

```python
    now = now or datetime.now()
```

В docstring в блок Args добавить строку: `now: момент расчёта (по умолчанию datetime.now(); демо-сборка передаёт время гонки)`.

- [ ] **Step 4:** тот же запуск → PASS; затем весь файл `tests/unit/test_runners_service.py` → PASS.

- [ ] **Step 5: Commit**

```bash
git add src/krasmarafon/services/runners_service.py tests/unit/test_runners_service.py
git commit -m "refactor(tracker): calculate_live_position принимает now — для демо-повтора"
```

---

### Task 2: вынести чистую сборку из `_do_build`

**Files:**
- Modify: `src/krasmarafon/services/results_service.py:155-407`
- Test: `tests/unit/test_results_assemble.py` (новый)

- [ ] **Step 1: Падающий тест** `tests/unit/test_results_assemble.py`:

```python
from datetime import datetime, timedelta, timezone

from src.krasmarafon.services.results_service import assemble_event_results

GUN_UTC = "2026-08-23T02:00:00Z"   # 09:00 Красноярск


def _ev_info():
    return {'event_name': 'Жара', 'event_distance': 21.1, 'event_year': 2026,
            'event_date': datetime(2026, 8, 23).date(), 'gun_time_utc': GUN_UTC,
            'checkpoint_distances': [0, 5.0, 21.1]}


def _gun_local_naive():
    return datetime(2026, 8, 23, 2, 0, tzinfo=timezone.utc).astimezone().replace(tzinfo=None)


def test_assemble_is_pure_and_uses_now():
    rows = [{'id': 1, 'surname': 'Тестов', 'name': 'Тест', 'sex': 'Мужчина', 'category': 'М18-29',
             'birthday': None, 'race_status': 'Running', 'time_gun_start': timedelta(0)}]
    hist = {'personal': {'ТЕСТОВ|ТЕСТ|': 10.0}, 'category_avg': {}, 'prev_year': 2025}
    now = _gun_local_naive() + timedelta(hours=1)
    res = assemble_event_results(rows, _ev_info(), {}, {}, hist, event_id=116, now=now)
    r = res.results[0]
    assert r['speed'] == 10.0
    assert r['current_distance'] == 10.0
    assert r['pace_source'] == 'personal'
    assert res.server_time_unix == int(now.timestamp() * 1000)
    assert res.race_gun_unix_ms == int(datetime(2026, 8, 23, 2, tzinfo=timezone.utc).timestamp() * 1000)
    assert res.total_distance_km == 21.1


def test_assemble_last_kt_unix_ms():
    rows = [{'id': 2, 'surname': 'А', 'name': 'Б', 'sex': 'Женщина', 'category': '',
             'race_status': 'Running', 'time_gun_start': timedelta(0),
             'time_clear_kt1': timedelta(minutes=25)}]
    res = assemble_event_results(rows, _ev_info(), {}, {},
                                 {'personal': {}, 'category_avg': {}, 'prev_year': 2025},
                                 event_id=116, now=_gun_local_naive() + timedelta(minutes=30))
    gun_ms = res.race_gun_unix_ms
    assert res.results[0]['last_kt_unix_ms'] == gun_ms + 25 * 60 * 1000
    assert res.results[0]['current_distance'] == 5.0
```

- [ ] **Step 2:** `conda run -n base python -m pytest tests/unit/test_results_assemble.py -v` → FAIL (`cannot import name 'assemble_event_results'`).

- [ ] **Step 3: Реализация.** В `results_service.py`:

(a) Вынести блок «Исторический кеш (предыдущий год)» (от `cache_key = ...` до `hist_data = _hist_cache[cache_key]`) в функцию над `_do_build`:

```python
def load_hist_data(ev_name: str, ev_distance, ev_year: int) -> dict:
    """{'personal', 'category_avg', 'prev_year'} по результатам прошлого года, с TTL-кешем."""
    from datetime import timedelta as _td
    from src.analytics.db_connection_optimized import get_prev_year_results
    from src.krasmarafon.services.pace_calculator import parse_pace_to_kmh

    cache_key = f"{ev_name}|{ev_distance}|{ev_year}"
    _now_ts = time.time()
    # ... тело блока БЕЗ изменений (prev_year = ev_year - 1, цикл по prev_rows, prune, запись в _hist_cache, logger.info) ...
    return _hist_cache[cache_key]
```

В перенесённом коде `(ev_year or current_year) - 1` заменить на `ev_year - 1` (вызывающий гарантирует `ev_year`).

(b) Всё от `race_date = ev_info.get('event_date') ...` до `return RaceResultsResponse(...)` перенести в новую функцию:

```python
def assemble_event_results(
    results_data: list,
    ev_info: dict,
    events: dict,
    category_speeds: dict,
    hist_data: dict,
    event_id: Optional[int] = None,
    event_name: Optional[str] = None,
    now: Optional[datetime] = None,
) -> RaceResultsResponse:
    """Чистая сборка ответа трекера из строк results (без обращений к БД).
    now — момент расчёта (naive local); None → текущее время (прод)."""
    import json as _json
    from datetime import timedelta as _td
    from src.krasmarafon.services.runners_service import calculate_live_position

    _now_dt = now or datetime.now()
    server_time_unix = int(_now_dt.timestamp() * 1000)
    current_year = _now_dt.year
    race_date = ev_info.get('event_date') or _now_dt.date()
    ev_name = ev_info.get('event_name', event_name or '')
    ev_distance = ev_info.get('event_distance')
    ev_year = ev_info.get('event_year', current_year)
    # ... gun_start_dt, checkpoint_distances, num_laps, цикл по results_data — БЕЗ изменений,
    #     кроме: в вызове calculate_live_position(...) добавить аргумент now=now ...
    return RaceResultsResponse(
        event=ev_name or f"event_{event_id}",
        total_results=len(results_data),
        results=results,
        timestamp=_now_dt.isoformat(),
        server_time_unix=server_time_unix,
        race_gun_unix_ms=race_gun_unix_ms,
        total_distance_km=float(checkpoint_distances[-1]) if checkpoint_distances else None,
    )
```

Строку `category_speeds = _get_cached_category_speeds(...)` и весь блок hist в `assemble_event_results` НЕ переносить — они приходят аргументами. Таймеры `_t_loop`/`logger.info(build_event_results: ...)` оставить в `_do_build` (лог total/db/ev/hist) — в `assemble` только сама сборка.

(c) `_do_build` становится:

```python
def _do_build(event_id, event_name, year, events) -> "RaceResultsResponse":
    """Загрузка данных из БД + assemble_event_results. Без кеш-логики."""
    from src.analytics.db_connection_optimized import (
        get_race_results_by_event_id,
        get_race_results_by_event_id_and_year,
        get_event_info_by_id,
        get_event_info,
    )
    from fastapi import HTTPException

    _t0 = time.time()
    current_year = datetime.now().year
    if event_id:
        results_data = get_race_results_by_event_id(event_id)
        ev_info = get_event_info_by_id(event_id) or {}
    elif event_name and year:
        results_data = get_race_results_by_event_id_and_year(event_name, year)
        ev_info = get_event_info(event_name, year or current_year) or {}
    else:
        raise HTTPException(status_code=400, detail="Укажите event_id или event_name + year")

    ev_name = ev_info.get('event_name', event_name or '')
    ev_distance = ev_info.get('event_distance')
    ev_year = ev_info.get('event_year', current_year)
    category_speeds = _get_cached_category_speeds(ev_name, ev_distance, ev_year)
    hist_data = load_hist_data(ev_name, ev_distance, ev_year)
    result = assemble_event_results(results_data, ev_info, events, category_speeds, hist_data,
                                    event_id=event_id, event_name=event_name)
    logger.info(f"build_event_results: total={time.time() - _t0:.2f}s runners={len(results_data)}")
    return result
```

Важно: порядок «сначала results, потом ev_info» сохраняется; импорты функций БД остаются внутри функций (существующие тесты патчат `src.analytics.db_connection_optimized.*`). Если ev_name пустой — `load_hist_data` вызывать как раньше нельзя (был `if ev_name else []`): в `load_hist_data` оставить `get_prev_year_results(...) if ev_name else []` из исходного кода.

- [ ] **Step 4:** `conda run -n base python -m pytest tests/unit/test_results_assemble.py tests/unit/test_results_service_client_id.py -v` → PASS. Затем весь `tests/unit/` → столько же passed, сколько до правки (запомнить число до начала задачи: `conda run -n base python -m pytest tests/unit/ -q | tail -1`).

- [ ] **Step 5: Commit**

```bash
git add src/krasmarafon/services/results_service.py tests/unit/test_results_assemble.py
git commit -m "refactor(tracker): assemble_event_results — чистая сборка ответа трекера без БД"
```

---

### Task 3: `build_current_event_response(event)`

**Files:**
- Modify: `src/krasmarafon/routers/api.py:56-103`
- Test: `tests/unit/test_current_event_payload.py` (новый)

- [ ] **Step 1: Падающий тест:**

```python
from pathlib import Path

from src.config.event_loader import load_all_events
from src.krasmarafon.routers.api import build_current_event_response


def test_payload_for_zhara_has_both_distances():
    events = load_all_events(Path("config/events"))
    p = build_current_event_response(events["zhara"])
    assert p.event == "zhara"
    ids = {d.db_event_id for d in p.distances}
    assert ids == {115, 116}
    d21 = next(d for d in p.distances if d.db_event_id == 116)
    assert d21.gpx_file == "static/map/2026/zhara_21.gpx"
    assert len(d21.checkpoints) == 8
```

- [ ] **Step 2:** запуск → FAIL (import error).

- [ ] **Step 3:** в `api.py` перед `@router.get("/api/current-event"...)` создать функцию `build_current_event_response(event: EventConfig) -> CurrentEventResponse`, перенеся в неё всё от `tracked = event.get_tracked()` до `return CurrentEventResponse(...)` с `event=event.code` вместо `event=code`. Эндпоинт:

```python
@router.get("/api/current-event", response_model=CurrentEventResponse)
async def get_current_event() -> CurrentEventResponse:
    """Текущее активное событие. Перечитывает YAML с TTL-кешем 30 сек."""
    events = load_events_cached()
    active = get_active_event(events)
    code = active.code if active else settings.CURRENT_EVENT
    event = events.get(code)
    if not event:
        raise HTTPException(status_code=404, detail=f"Event {code} not configured")
    return build_current_event_response(event)
```

Импорт `EventConfig` из `src.config.event_loader`, если его ещё нет в api.py.

- [ ] **Step 4:** тест → PASS; `conda run -n base python -m pytest tests/unit/ -q -k "current_event or api"` → PASS.

- [ ] **Step 5: Commit** `refactor(api): build_current_event_response — для демо-сборки`.

---

### Task 4: реестр гонок и обезличивание

**Files:**
- Create: `tools/demo/__init__.py` (пустой; `tools/` остаётся namespace-пакетом — корень проекта в `sys.path` ставят conftest и `build.py`), `tools/demo/races.py`, `tools/demo/anonymize.py`
- Test: `tests/unit/test_demo_anonymize.py`

- [ ] **Step 1:** `tools/demo/races.py`:

```python
"""Реестр демо-гонок. Добавить гонку Красмарафона = добавить запись сюда и пересобрать."""

BASE = "/race-tracker-demo/"

RACES = {
    "zhara_21": {
        "slug": "zhara-21",
        "config_code": "zhara",
        "db_event_id": 116,
        "title": "Жара, 21,1 км",
        "caption": "Жара, Красноярск, 23.08.2026 — запись реальной гонки",
        "kind": "Трекер на карте",
    },
    "zhara_5": {
        "slug": "zhara-5",
        "config_code": "zhara",
        "db_event_id": 115,
        "title": "Жара, 5 км",
        "caption": "Жара, Красноярск, 22.08.2026 — запись реальной гонки",
        "kind": "Трекер на карте",
    },
}

LOOP_START_S = 30 * 60      # круг повтора начинается с 30-й минуты
TAIL_S = 5 * 60             # хвост после «массового финиша» / последнего финиша
STEP_S = 5                  # шаг записи = темп прод-загрузчика
```

- [ ] **Step 2: Падающий тест** `tests/unit/test_demo_anonymize.py`:

```python
from tools.demo.anonymize import anonymize


def _rows():
    return [
        {'id': 10, 'client_id': 5, 'surname': 'Петров', 'name': 'Иван', 'sex': 'Мужчина',
         'birthday': '1990-01-01', 'start_number': 101, 'category': 'М30-39'},
        {'id': 11, 'client_id': 6, 'surname': 'Сидорова', 'name': 'Анна', 'sex': 'Женщина',
         'birthday': '1992-02-02', 'start_number': 102, 'category': 'Ж30-39'},
        {'id': 12, 'client_id': 7, 'surname': 'Кузнецов', 'name': 'Пётр', 'sex': 'Мужчина',
         'birthday': None, 'start_number': 103, 'category': 'М18-29'},
    ]


def test_removes_pii_and_keeps_sex_category():
    out, key_map = anonymize(_rows(), seed=1)
    real_surnames = {'Петров', 'Сидорова', 'Кузнецов'}
    for r in out:
        assert r['surname'] not in real_surnames
        assert r['birthday'] is None and r['client_id'] is None
    assert [r['sex'] for r in out] == ['Мужчина', 'Женщина', 'Мужчина']
    assert [r['category'] for r in out] == ['М30-39', 'Ж30-39', 'М18-29']
    assert out[1]['surname'].endswith('а')


def test_ids_renumbered_bibs_permuted_names_unique():
    out, _ = anonymize(_rows(), seed=1)
    assert [r['id'] for r in out] == [1, 2, 3]
    assert sorted(r['start_number'] for r in out) == [101, 102, 103]
    assert len({(r['surname'], r['name']) for r in out}) == 3


def test_deterministic():
    assert anonymize(_rows(), seed=1) == anonymize(_rows(), seed=1)


def test_key_map_translates_hist_keys():
    out, key_map = anonymize(_rows(), seed=1)
    assert key_map['ПЕТРОВ|ИВАН|1990-01-01'] == f"{out[0]['surname']}|{out[0]['name']}|".upper()
```

- [ ] **Step 3:** `conda run -n base python -m pytest tests/unit/test_demo_anonymize.py -v` → FAIL (module not found).

- [ ] **Step 4:** `tools/demo/anonymize.py`:

```python
"""Обезличивание строк results для публичного демо (спека, п. 4)."""
import random

_SURNAMES = [
    "Абрамов", "Белов", "Блинов", "Борисов", "Быков", "Веселов", "Виноградов", "Воронов",
    "Гаврилов", "Голубев", "Горбунов", "Громов", "Гусев", "Давыдов", "Денисов", "Дроздов",
    "Ершов", "Жуков", "Зайцев", "Зимин", "Зуев", "Игнатов", "Калинин", "Карпов", "Киселев",
    "Клюев", "Комаров", "Кондратьев", "Королев", "Крылов", "Лаптев", "Лебедев", "Ларин",
    "Лукин", "Макаров", "Медведев", "Мельников", "Миронов", "Назаров", "Никитин", "Носов",
    "Орлов", "Осипов", "Панов", "Пестов", "Поляков", "Прохоров", "Родионов", "Рябов",
    "Савельев", "Соболев", "Соколов", "Суханов", "Тарасов", "Титов", "Уваров", "Федотов",
    "Фомин", "Чернов", "Шилов",
]
_MALE = [
    "Александр", "Алексей", "Андрей", "Антон", "Артём", "Борис", "Вадим", "Василий",
    "Виктор", "Виталий", "Владимир", "Глеб", "Григорий", "Даниил", "Денис", "Дмитрий",
    "Евгений", "Егор", "Иван", "Игорь", "Илья", "Кирилл", "Константин", "Лев", "Максим",
    "Марк", "Матвей", "Михаил", "Никита", "Николай", "Олег", "Павел", "Роман", "Семён",
    "Сергей", "Станислав", "Степан", "Тимофей", "Фёдор", "Юрий",
]
_FEMALE = [
    "Алина", "Алёна", "Анастасия", "Анна", "Арина", "Валентина", "Валерия", "Вера",
    "Виктория", "Галина", "Дарья", "Диана", "Ева", "Екатерина", "Елена", "Елизавета",
    "Жанна", "Злата", "Инна", "Ирина", "Кира", "Ксения", "Лариса", "Лидия", "Любовь",
    "Людмила", "Маргарита", "Марина", "Мария", "Надежда", "Наталья", "Нина", "Ольга",
    "Полина", "Светлана", "София", "Таисия", "Татьяна", "Ульяна", "Юлия",
]


def _hist_key(surname, name, birthday) -> str:
    bday = birthday.isoformat() if hasattr(birthday, 'isoformat') else str(birthday or '')
    return f"{(surname or '').strip()}|{(name or '').strip()}|{bday}".upper()


def anonymize(rows: list[dict], seed: int) -> tuple[list[dict], dict]:
    """Копии строк с фейковыми ФИО (пол сохранён, уникальны, не совпадают с реальными
    фамилиями гонки), без ДР/client_id, с перемешанными номерами и id 1..N.
    Возвращает (строки, {реальный_ключ_hist: фейковый_ключ_hist}) — ключ как в results_service."""
    rnd = random.Random(seed)
    real = {(r.get('surname') or '').strip() for r in rows}
    surnames = [s for s in _SURNAMES if s not in real and s + 'а' not in real]
    pools = {
        'Ж': [(s + 'а', n) for s in surnames for n in _FEMALE],
        'М': [(s, n) for s in surnames for n in _MALE],
    }
    for pool in pools.values():
        rnd.shuffle(pool)
    bibs = [r.get('start_number') for r in rows]
    rnd.shuffle(bibs)

    out, key_map = [], {}
    for i, r in enumerate(rows):
        sex_key = 'Ж' if r.get('sex') == 'Женщина' else 'М'
        surname, name = pools[sex_key].pop()
        a = dict(r)
        a.update(id=i + 1, client_id=None, birthday=None, surname=surname, name=name,
                 start_number=bibs[i])
        out.append(a)
        key_map[_hist_key(r.get('surname'), r.get('name'), r.get('birthday'))] = _hist_key(surname, name, None)
    return out, key_map
```

- [ ] **Step 5:** тест → PASS.
- [ ] **Step 6: Commit** `feat(demo): реестр гонок и обезличивание`.

---

### Task 5: «результаты на момент T»

**Files:**
- Create: `tools/demo/timeline.py`
- Test: `tests/unit/test_demo_timeline.py`

Абсолютный момент (секунды от выстрела): старт = `time_gun_start`; КТ N = `time_clear_ktN` (несмотря на имя, это **official-время от выстрела**: во всех пресетах `config/copernico/km_*.yaml` `checkpoint_fields` → `times.official_*`; так же его трактует прод в `_calc_last_kt_unix_ms`); финиш = `time_gun_finish`. Поля группы скрываются (→ `None`), если момент > T.

- [ ] **Step 1: Падающий тест:**

```python
from datetime import timedelta as td

from tools.demo.timeline import rows_at

ROWS = [
    {'id': 1, 'sex': 'Мужчина', 'category': 'М', 'race_status': 'Finished',
     'time_gun_start': td(seconds=10), 'time_clear_start': td(0),
     'time_clear_kt1': td(minutes=20), 'pace_avg_kt1': '4:00',
     'time_gun_finish': td(minutes=90), 'time_clear_finish': td(minutes=89, seconds=50),
     'finish_pace_avg': '4:15', 'rank_absolute': 1},
    {'id': 2, 'sex': 'Женщина', 'category': 'Ж', 'race_status': 'DNF',
     'time_gun_start': td(seconds=30), 'time_clear_kt1': td(minutes=30)},
    {'id': 3, 'sex': 'Мужчина', 'category': 'М', 'race_status': 'Not started'},
    {'id': 4, 'sex': 'Мужчина', 'category': 'М', 'race_status': 'Finished',
     'time_gun_start': td(seconds=5), 'time_gun_finish': td(minutes=80),
     'time_clear_finish': td(minutes=79, seconds=55)},
]
END = 100 * 60


def by_id(rows):
    return {r['id']: r for r in rows}


def test_before_start_everyone_not_started():
    r = by_id(rows_at(ROWS, 0, END))
    assert all(x['race_status'] == 'Not started' for x in r.values())
    assert r[1]['time_gun_start'] is None and r[1]['time_clear_kt1'] is None


def test_mid_race():
    r = by_id(rows_at(ROWS, 25 * 60, END))
    assert r[1]['race_status'] == 'Running'
    assert r[1]['time_clear_kt1'] == td(minutes=20) and r[1]['pace_avg_kt1'] == '4:00'
    assert r[1]['time_gun_finish'] is None and r[1]['finish_pace_avg'] is None
    assert r[1]['rank_absolute'] is None
    assert r[2]['race_status'] == 'Running' and r[2]['time_clear_kt1'] is None


def test_ranks_among_finished_so_far():
    r = by_id(rows_at(ROWS, 85 * 60, END))
    assert r[4]['race_status'] == 'Finished' and r[4]['rank_absolute'] == 1
    assert r[4]['rank_absolute_clean'] == 1 and r[4]['rank_sex'] == 1
    r = by_id(rows_at(ROWS, 95 * 60, END))
    assert r[4]['rank_absolute'] == 1 and r[1]['rank_absolute'] == 2


def test_dnf_visible_only_at_end():
    assert by_id(rows_at(ROWS, 95 * 60, END))[2]['race_status'] == 'Running'
    assert by_id(rows_at(ROWS, END, END))[2]['race_status'] == 'DNF'
    assert by_id(rows_at(ROWS, END, END))[3]['race_status'] == 'Not started'
```

- [ ] **Step 2:** запуск → FAIL.

- [ ] **Step 3:** `tools/demo/timeline.py`:

```python
"""Строки results «как в момент T» (секунды от выстрела) — спека, п. 5."""
import re
from datetime import timedelta

from load_race_results import RaceLoader

_KT_RE = re.compile(r'^(?:time_(?:gun|clear)|pace_avg)_kt(\d)(?:_ms)?$')
_RANK_FIELDS = ('rank_absolute', 'rank_sex', 'rank_category',
                'rank_absolute_clean', 'rank_sex_clean', 'rank_category_clean')
_FINAL_ONLY = ('DNF', 'DSQ', 'Withdrawn')


def _s(v) -> float | None:
    return v.total_seconds() if isinstance(v, timedelta) else None


def _finish_field(k: str) -> bool:
    return k.startswith(('time_gun_finish', 'time_clear_finish', 'finish_pace'))


def _start_field(k: str) -> bool:
    return k.startswith(('time_gun_start', 'time_clear_start'))


def _row_at(r: dict, t: float, end_s: float) -> dict:
    start = _s(r.get('time_gun_start'))
    finish = _s(r.get('time_gun_finish'))
    a = dict(r)
    for k in r:
        m = _KT_RE.match(k)
        if m:
            kt = _s(r.get(f'time_clear_kt{m.group(1)}'))   # official: от выстрела
            if kt is None or kt > t:
                a[k] = None
        elif _finish_field(k) and (finish is None or finish > t):
            a[k] = None
        elif _start_field(k) and (start is None or start > t):
            a[k] = None
    for k in _RANK_FIELDS:
        a[k] = None
    final = r.get('race_status')
    if final in _FINAL_ONLY and t >= end_s:
        a['race_status'] = final
    elif a.get('time_gun_finish') is not None and final == 'Finished':
        a['race_status'] = 'Finished'
    elif a.get('time_gun_start') is not None:
        a['race_status'] = 'Running'
    else:
        a['race_status'] = 'Not started'
    return a


def _key(r: dict, time_key: str):
    return (r[time_key].total_seconds(), (r.get(f'{time_key}_ms') or 0) % 1000)


def _assign(rows: list[dict], time_key: str, field: str) -> None:
    for r in rows:
        r['_k'] = _key(r, time_key)
    groups = {field: [rows]}
    for g_field, attr in ((field.replace('absolute', 'sex'), 'sex'),
                          (field.replace('absolute', 'category'), 'category')):
        by = {}
        for r in rows:
            if r.get(attr):
                by.setdefault(r[attr], []).append(r)
        groups[g_field] = list(by.values())
    for f, lists in groups.items():
        for group in lists:
            ranks = RaceLoader._assign_ranks(group, '_k')
            for r in group:
                r[f] = ranks.get(r['id'])
    for r in rows:
        del r['_k']


def rows_at(rows: list[dict], t: float, end_s: float) -> list[dict]:
    """t, end_s — секунды от выстрела. end_s — момент, с которого видны DNF/DSQ."""
    out = [_row_at(r, t, end_s) for r in rows]
    finished = [r for r in out if r['race_status'] == 'Finished' and r.get('time_gun_finish')]
    _assign(finished, 'time_gun_finish', 'rank_absolute')
    _assign([r for r in finished if r.get('time_clear_finish')], 'time_clear_finish', 'rank_absolute_clean')
    return out
```

Проверить имена полей с суффиксом `_clean`: `'rank_absolute_clean'.replace('absolute', 'sex')` → `'rank_sex_clean'` ✔.

- [ ] **Step 4:** тест → PASS. Если импорт `load_race_results` тянет `.env` — в тестах conftest уже загрузил `.env.local` с override, это безопасно (модуль только читает переменные).
- [ ] **Step 5: Commit** `feat(demo): строки результатов на момент T`.

---

### Task 6: запись гонки и восстановление состояния

**Files:**
- Create: `tools/demo/record.py`
- Test: `tests/unit/test_demo_record.py`

- [ ] **Step 1: Падающий тест** (синтетическая гонка, без БД):

```python
from datetime import timedelta as td

from tools.demo.record import build_record, state_at, compress_series
from tools.demo.timeline import rows_at
from src.krasmarafon.services.results_service import assemble_event_results
from tests.unit.test_results_assemble import _ev_info, _gun_local_naive

HIST = {'personal': {}, 'category_avg': {}, 'prev_year': 2025}
ROWS = [
    {'id': i, 'surname': f'Ф{i}', 'name': 'И', 'sex': 'Мужчина', 'category': 'М18-29',
     'race_status': 'Finished', 'time_gun_start': td(seconds=i * 7),
     'time_clear_kt1': td(minutes=20 + i), 'time_gun_finish': td(minutes=95 + i * 2, seconds=i * 7),
     'time_clear_finish': td(minutes=95 + i * 2)}
    for i in range(1, 6)
] + [{'id': 6, 'surname': 'Ф6', 'name': 'И', 'sex': 'Женщина', 'category': 'Ж',
      'race_status': 'DNF', 'time_gun_start': td(seconds=3)}]


def _build():
    return build_record(ROWS, _ev_info(), {}, {}, HIST, event_id=116,
                        t_from=-300, t_to=120 * 60, end_s=110 * 60, step_s=5)


def test_state_at_every_step_matches_server_code():
    rec = _build()
    gun = _gun_local_naive()
    for t in range(-300, 120 * 60 + 1, 5):
        expect = assemble_event_results(rows_at(ROWS, t, 110 * 60), _ev_info(), {}, {}, HIST,
                                        event_id=116, now=gun + td(seconds=t))
        expect = {r['id']: r for r in rec['_normalize'](expect.results)}
        got = {r['id']: r for r in state_at(rec, t)}
        assert got.keys() == expect.keys()
        for i, e in expect.items():
            g = dict(got[i])
            assert abs(g.pop('current_distance') - e.pop('current_distance')) <= 0.001, (t, i)
            assert g == e, (t, i)


def test_compress_series_linear_and_steps():
    pts = [[t, round(min(t * 0.003, 5.0), 3)] for t in range(0, 4000, 5)]
    c = compress_series(pts)
    assert len(c) <= 4
    assert c[0] == pts[0] and c[-1] == pts[-1]


def test_meta_fields():
    rec = _build()
    assert rec['meta']['step_s'] == 5
    assert rec['meta']['gun_unix_ms'] > 0
    assert rec['meta']['t_from'] == -300 and rec['meta']['t_to'] == 120 * 60
```

- [ ] **Step 2:** запуск → FAIL.

- [ ] **Step 3:** `tools/demo/record.py`:

```python
"""Проигрывание гонки серверным кодом → запись {meta, initial, changes, distance} (спека, п. 5)."""
import json
from datetime import datetime, timedelta

from src.krasmarafon.services.results_service import assemble_event_results
from tools.demo.timeline import rows_at

_TOL_KM = 0.0015   # шум округления current_distance до 0.001 км


def _normalize(results: list[dict]) -> list[dict]:
    """Тот же JSON, что уходит клиенту по SSE (json.dumps(default=str))."""
    return json.loads(json.dumps(results, default=str))


def compress_series(pts: list[list]) -> list[list]:
    """Оставить точки излома ломаной [[t, km], ...]; между ними — линейная интерполяция."""
    if len(pts) <= 2:
        return [list(p) for p in pts]
    keep = [list(pts[0])]
    for i in range(1, len(pts) - 1):
        (t0, d0), (t1, d1), (t2, d2) = pts[i - 1], pts[i], pts[i + 1]
        slope_in = (d1 - d0) / (t1 - t0)
        slope_out = (d2 - d1) / (t2 - t1)
        if abs(slope_out - slope_in) * (t2 - t1) > _TOL_KM:
            keep.append(list(pts[i]))
    keep.append(list(pts[-1]))
    return keep


def build_record(rows, ev_info, events, category_speeds, hist_data, *, event_id,
                 t_from: int, t_to: int, end_s: int, step_s: int) -> dict:
    """rows — уже обезличенные строки; t_* — секунды от выстрела."""
    gun_dt = None
    initial, changes, series, prev = None, [], {}, {}
    for t in range(t_from, t_to + 1, step_s):
        if gun_dt is None:
            probe = assemble_event_results(rows_at(rows, t, end_s), ev_info, events,
                                           category_speeds, hist_data, event_id=event_id)
            gun_ms = probe.race_gun_unix_ms
            gun_dt = datetime.fromtimestamp(gun_ms / 1000)
        res = assemble_event_results(rows_at(rows, t, end_s), ev_info, events, category_speeds,
                                     hist_data, event_id=event_id, now=gun_dt + timedelta(seconds=t))
        results = _normalize(res.results)
        changed = []
        for r in results:
            rid = str(r['id'])
            series.setdefault(rid, []).append([t, r['current_distance']])
            body = {k: v for k, v in r.items() if k != 'current_distance'}
            if prev.get(rid) != body:
                changed.append(body)
            prev[rid] = body
        if initial is None:
            initial = {'total_distance_km': res.total_distance_km,
                       'total_results': res.total_results, 'results': results}
        elif changed:
            changes.append({'t_s': t, 'results': changed})
    return {
        'meta': {'gun_unix_ms': gun_ms, 'step_s': step_s, 't_from': t_from, 't_to': t_to},
        'initial': initial,
        'changes': changes,
        'distance': {rid: compress_series(p) for rid, p in series.items()},
        '_normalize': _normalize,
    }


def _interp(s: list, t: float) -> float:
    if t <= s[0][0]:
        return s[0][1]
    for (t0, d0), (t1, d1) in zip(s, s[1:]):
        if t <= t1:
            return d0 + (d1 - d0) * (t - t0) / (t1 - t0)
    return s[-1][1]


def state_at(rec: dict, t: float) -> list[dict]:
    """Python-эталон того, что делает demo-replay.js: initial + changes ≤ t + ломаная."""
    by_id = {str(r['id']): dict(r) for r in rec['initial']['results']}
    for ch in rec['changes']:
        if ch['t_s'] > t:
            break
        for r in ch['results']:
            by_id[str(r['id'])].update(r)
    for rid, r in by_id.items():
        r['current_distance'] = round(_interp(rec['distance'][rid], t), 3)
    return list(by_id.values())
```

`'_normalize'` в записи нужен только тестам; `build.py` удаляет ключ перед сохранением (Task 9).

- [ ] **Step 4:** тест → PASS. Если `test_state_at_every_step_matches_server_code` падает на `current_distance` — уменьшить `_TOL_KM` до 0.001 и перепроверить; поля кроме `current_distance` должны совпадать точно (`server_time_unix` в results не входит).
- [ ] **Step 5: Commit** `feat(demo): запись гонки initial+changes+ломаная дистанции`.

---

### Task 7: входные данные из локальной БД и сборка записи гонки

**Files:**
- Create: `tools/demo/source.py`
- Test: `tests/unit/test_demo_source.py` (интеграционный, пропускается без локальной БД)

- [ ] **Step 1:** `tools/demo/source.py`:

```python
"""Входные данные демо-гонки: локальная БД (.env.local) + YAML-конфиг."""
from pathlib import Path

from src.analytics.db_connection_optimized import (
    get_race_results_by_event_id, get_event_info_by_id, get_category_avg_paces,
)
from src.config.event_loader import load_all_events
from src.krasmarafon.routers.api import build_current_event_response
from src.krasmarafon.services.results_service import load_hist_data
from tools.demo.anonymize import anonymize
from tools.demo.record import build_record
from tools.demo.races import RACES, LOOP_START_S, TAIL_S, STEP_S

ROOT = Path(__file__).resolve().parents[2]


def _finish_s(r):
    v = r.get('time_gun_finish')
    return v.total_seconds() if v is not None and r.get('race_status') == 'Finished' else None


def build_race(key: str) -> dict:
    race = RACES[key]
    events = load_all_events(ROOT / "config" / "events")
    event = events[race["config_code"]]
    rows = get_race_results_by_event_id(race["db_event_id"])
    ev_info = get_event_info_by_id(race["db_event_id"]) or {}
    ev_name, ev_dist, ev_year = ev_info['event_name'], ev_info.get('event_distance'), ev_info['event_year']
    cat_speeds = get_category_avg_paces(ev_name, ev_dist, ev_year) if ev_name else {}
    hist = load_hist_data(ev_name, ev_dist, ev_year)

    anon, key_map = anonymize(rows, seed=race["db_event_id"])
    hist = {**hist, 'personal': {key_map[k]: v for k, v in hist['personal'].items() if k in key_map}}

    finishes = sorted(f for f in map(_finish_s, rows) if f is not None)
    if not finishes:
        raise RuntimeError(f"{key}: нет финишировавших — нечего проигрывать")
    mass = finishes[int(len(finishes) * 0.95) - 1]
    end_s = int(finishes[-1]) + TAIL_S
    rec = build_record(anon, ev_info, events, cat_speeds, hist, event_id=race["db_event_id"],
                       t_from=-TAIL_S, t_to=end_s, end_s=end_s, step_s=STEP_S)

    payload = build_current_event_response(event).model_dump()
    payload['distances'] = [d for d in payload['distances'] if d['db_event_id'] == race["db_event_id"]]
    d = payload['distances'][0]
    payload.update(db_event_id=race["db_event_id"], gpx_file=d['gpx_file'],
                   display_name=race["title"], title=race["title"])
    rec['meta'].update(
        race=key, title=race["title"], caption=race["caption"], current_event=payload,
        gpx=d['gpx_file'], loop_start_s=LOOP_START_S, loop_end_s=int(mass) + TAIL_S,
        marks=[{'label': 'Старт', 't_s': 0},
               {'label': 'Первый финиш', 't_s': int(finishes[0])},
               {'label': 'Массовый финиш', 't_s': int(mass)}],
        participants=len(rows), event_date=d['event_date'],
    )
    return rec, rows
```

`build_race` возвращает и исходные `rows` — они нужны проверке ПДн (Task 9) и тесту точности; в файл не пишутся.

- [ ] **Step 2: Интеграционный тест** `tests/unit/test_demo_source.py`:

```python
import pytest

from src.analytics.db_connection_optimized import get_pooled_connection


def _db_ok():
    try:
        c = get_pooled_connection()
        c.close()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _db_ok(), reason="нет локальной БД (.env.local)")


def test_final_state_matches_protocol():
    from tools.demo.source import build_race
    from tools.demo.record import state_at
    rec, rows = build_race("zhara_5")
    final = {r['id']: r for r in state_at(rec, rec['meta']['t_to'])}
    # id в записи = позиция строки + 1 (anonymize перенумеровывает по порядку)
    for i, real in enumerate(rows):
        got = final[i + 1]
        assert got['race_status'] == real['race_status']
        if real['race_status'] == 'Finished':
            assert got['rank_absolute'] == real['rank_absolute'], real['id']
            assert got['time_gun_finish'] == str(real['time_gun_finish'])
```

- [ ] **Step 3:** `conda run -n base python -m pytest tests/unit/test_demo_source.py -v` → PASS (или SKIP без БД — тогда запустить локальный MySQL80 и повторить; SKIP не считается выполнением задачи). Если места расходятся у единиц участников — вывести их и сравнить `time_gun_finish_ms`: расхождение по тай-брейку внутри секунды допустимо только если в БД нет `_ms`; иначе — баг в `timeline._key`.
- [ ] **Step 4: Commit** `feat(demo): сборка записи гонки из локальной БД`.

---

### Task 8: браузерный модуль `demo-replay.js` и стили

**Files:**
- Create: `tools/demo/static/demo-replay.js`, `tools/demo/static/demo-replay.css`

- [ ] **Step 1:** `tools/demo/static/demo-replay.js`:

```javascript
// Демо «Повтор гонки»: виртуальные часы + подмена fetch/EventSource поверх tracker-*.js.
// Подключается в <head> ДО скриптов трекера (через демо-версию krasmarafon/analytics.html).
(function () {
    'use strict';
    const me = document.currentScript;
    const BASE = me.dataset.base;        // '/race-tracker-demo/'
    const RACE = me.dataset.race;        // 'zhara_21'
    const RealDate = Date;
    const realFetch = window.fetch.bind(window);
    const RealES = window.EventSource;

    // ---------- виртуальные часы ----------
    const clock = { v: RealDate.now(), r: performance.now(), speed: 1 };
    const vnow = () => clock.v + (performance.now() - clock.r) * clock.speed;
    function setClock(v, speed) {
        clock.v = v; clock.r = performance.now();
        if (speed !== undefined) clock.speed = speed;
    }
    class VDate extends RealDate {
        constructor(...a) { if (a.length === 0) super(vnow()); else super(...a); }
        static now() { return vnow(); }
    }
    window.Date = VDate;

    // ---------- запись ----------
    let rec = null;
    const recReady = realFetch(`${BASE}data/${RACE}.json.gz`)
        .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r; })
        .then(r => new Response(r.body.pipeThrough(new DecompressionStream('gzip'))).json())
        .then(j => { rec = j; start(); return j; });
    recReady.catch(showError);

    const tRace = () => (vnow() - rec.meta.gun_unix_ms) / 1000;
    const st = { byId: new Map(), cursor: 0, lastStep: null, sentDist: new Map() };

    function distAt(id, t) {
        const s = rec.distance[id];
        if (t <= s[0][0]) return s[0][1];
        for (let i = 1; i < s.length; i++) {
            if (t <= s[i][0]) {
                const [t0, d0] = s[i - 1], [t1, d1] = s[i];
                return d0 + (d1 - d0) * (t - t0) / (t1 - t0);
            }
        }
        return s[s.length - 1][1];
    }
    function advanceTo(t) {
        const changed = new Set();
        const ch = rec.changes;
        while (st.cursor < ch.length && ch[st.cursor].t_s <= t) {
            for (const r of ch[st.cursor].results) {
                const id = String(r.id);
                st.byId.set(id, Object.assign({}, st.byId.get(id), r));
                changed.add(id);
            }
            st.cursor++;
        }
        return changed;
    }
    function resetTo(t) {
        st.byId = new Map(rec.initial.results.map(r => [String(r.id), Object.assign({}, r)]));
        st.cursor = 0;
        st.sentDist = new Map();
        advanceTo(t);
    }
    function withDist(id, t) {
        const d = Math.round(distAt(id, t) * 1000) / 1000;
        st.sentDist.set(id, d);
        return Object.assign({}, st.byId.get(id), { current_distance: d });
    }
    function payload(results, initial) {
        const p = {
            server_time_unix: Math.round(vnow()),
            race_gun_unix_ms: initial === false ? null : rec.meta.gun_unix_ms,
            total_distance_km: initial === false ? null : rec.initial.total_distance_km,
            total_results: rec.initial.total_results,
            results,
        };
        if (initial !== undefined) p.initial = initial;
        return p;
    }
    function snapshot(initial) {
        const t = tRace();
        return payload([...st.byId.keys()].map(id => withDist(id, t)), initial);
    }
    function delta(t) {
        const ids = advanceTo(t);
        for (const id of st.byId.keys()) {
            const d = Math.round(distAt(id, t) * 1000) / 1000;
            if (st.sentDist.get(id) !== d) ids.add(id);
        }
        return payload([...ids].map(id => withDist(id, t)), false);
    }

    // ---------- подмена fetch ----------
    const json = obj => new Response(JSON.stringify(obj), { headers: { 'Content-Type': 'application/json' } });
    window.fetch = function (input, init) {
        const u = new URL(typeof input === 'string' ? input : input.url, location.href);
        if (u.origin === location.origin) {
            if (u.pathname === '/api/current-event') return recReady.then(r => json(r.meta.current_event));
            if (u.pathname === '/api/event-results') return recReady.then(() => json(snapshot(undefined)));
            if (u.pathname.startsWith('/static/')) return realFetch(BASE + u.pathname.slice(1) + u.search, init);
            if (u.pathname.startsWith('/api/')) {
                console.warn('[demo] неперехваченный запрос', u.pathname);
                return Promise.resolve(new Response('{}', { status: 404 }));
            }
        }
        return realFetch(input, init);
    };

    // ---------- подмена EventSource ----------
    const sources = new Set();
    class FakeEventSource {
        constructor(url) {
            this.url = url; this.readyState = 0; this.onmessage = null; this.onerror = null; this.onopen = null;
            this._listeners = [];
            sources.add(this);
            recReady.then(() => { this.readyState = 1; if (this.onopen) this.onopen(); this._send(snapshot(true)); });
        }
        addEventListener(type, fn) { if (type === 'message') this._listeners.push(fn); }
        removeEventListener(type, fn) { this._listeners = this._listeners.filter(f => f !== fn); }
        close() { this.readyState = 2; sources.delete(this); }
        _send(obj) {
            const ev = { data: JSON.stringify(obj) };
            if (this.onmessage) this.onmessage(ev);
            this._listeners.forEach(fn => fn(ev));
        }
    }
    window.EventSource = function (url, opts) {
        return String(url).includes('/api/sse/tracker') ? new FakeEventSource(url) : new RealES(url, opts);
    };

    // ---------- управление ----------
    function seek(t) {
        setClock(rec.meta.gun_unix_ms + t * 1000);
        resetTo(t);
        st.lastStep = Math.floor(t / rec.meta.step_s);
        sources.forEach(s => s._send(snapshot(true)));
        renderPanel();
    }
    function parseT(v) {
        if (!v) return null;
        const m = /^(\d+)(m?)$/.exec(v);
        return m ? Number(m[1]) * (m[2] ? 60 : 1) : null;
    }
    function start() {
        const q = new URLSearchParams(location.search);
        const t0 = parseT(q.get('t')) ?? rec.meta.loop_start_s;
        const speed = [1, 2, 5, 10].includes(Number(q.get('speed'))) ? Number(q.get('speed')) : 1;
        setClock(rec.meta.gun_unix_ms + t0 * 1000, speed);
        resetTo(t0);
        st.lastStep = Math.floor(t0 / rec.meta.step_s);
        buildPanel();
        setInterval(tick, 250);
    }
    function tick() {
        const t = tRace();
        if (clock.speed > 0 && t >= rec.meta.loop_end_s) { seek(rec.meta.loop_start_s); return; }
        const step = Math.floor(t / rec.meta.step_s);
        if (step !== st.lastStep) {
            st.lastStep = step;
            const d = delta(t);
            if (d.results.length) sources.forEach(s => s._send(d));
        }
        renderPanel();
    }

    // ---------- панель ----------
    const el = {};
    const fmt = s => {
        const sign = s < 0 ? '−' : ''; s = Math.abs(Math.floor(s));
        return `${sign}${Math.floor(s / 3600)}:${String(Math.floor(s / 60) % 60).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;
    };
    function buildPanel() {
        const m = rec.meta;
        const p = document.createElement('div');
        p.className = 'demo-panel';
        p.innerHTML = `
            <button class="demo-panel__toggle" type="button" aria-label="Панель повтора">⏱</button>
            <div class="demo-panel__body">
              <div class="demo-panel__caption">${m.caption}</div>
              <div class="demo-panel__row">
                <button class="demo-panel__play" type="button"></button>
                <span class="demo-panel__time"></span>
                <div class="demo-panel__speeds">${[1, 2, 5, 10].map(s => `<button type="button" data-speed="${s}">${s}×</button>`).join('')}</div>
              </div>
              <input class="demo-panel__range" type="range" min="${m.t_from}" max="${m.t_to}" step="1">
              <div class="demo-panel__marks">${m.marks.map(k => `<button type="button" data-t="${k.t_s}">${k.label}</button>`).join('')}</div>
            </div>`;
        document.body.appendChild(p);
        el.panel = p;
        el.play = p.querySelector('.demo-panel__play');
        el.time = p.querySelector('.demo-panel__time');
        el.range = p.querySelector('.demo-panel__range');
        el.speeds = [...p.querySelectorAll('[data-speed]')];
        el.lastSpeed = clock.speed || 1;
        p.querySelector('.demo-panel__toggle').onclick = () => p.classList.toggle('demo-panel--open');
        el.play.onclick = () => {
            if (clock.speed > 0) { el.lastSpeed = clock.speed; setClock(vnow(), 0); }
            else setClock(vnow(), el.lastSpeed);
            renderPanel();
        };
        el.speeds.forEach(b => b.onclick = () => { setClock(vnow(), Number(b.dataset.speed)); renderPanel(); });
        el.range.oninput = () => { el.dragging = true; el.time.textContent = fmt(Number(el.range.value)); };
        el.range.onchange = () => { el.dragging = false; seek(Number(el.range.value)); };
        p.querySelectorAll('[data-t]').forEach(b => b.onclick = () => seek(Number(b.dataset.t)));
        renderPanel();
    }
    function renderPanel() {
        if (!el.panel) return;
        const t = tRace();
        el.play.textContent = clock.speed > 0 ? '⏸' : '▶';
        el.speeds.forEach(b => b.classList.toggle('active', Number(b.dataset.speed) === clock.speed));
        if (!el.dragging) { el.range.value = Math.round(t); el.time.textContent = fmt(t); }
    }
    function showError() {
        const box = document.createElement('div');
        box.className = 'demo-error';
        box.innerHTML = 'Не удалось загрузить запись гонки <button type="button">Повторить</button>';
        box.querySelector('button').onclick = () => location.reload();
        (document.body ? Promise.resolve() : new Promise(r => document.addEventListener('DOMContentLoaded', r)))
            .then(() => document.body.appendChild(box));
    }
})();
```

- [ ] **Step 2:** `tools/demo/static/demo-replay.css`:

```css
.demo-panel { position: fixed; left: 50%; bottom: 12px; transform: translateX(-50%); z-index: 2000;
  width: min(720px, calc(100vw - 32px)); background: rgba(20, 24, 31, .92); color: #fff;
  border-radius: 12px; padding: 10px 14px; font: 14px/1.3 system-ui, sans-serif; box-shadow: 0 6px 24px rgba(0,0,0,.3); }
.demo-panel button { font: inherit; color: inherit; background: rgba(255,255,255,.12); border: 0;
  border-radius: 6px; padding: 4px 8px; cursor: pointer; }
.demo-panel button.active { background: #f57c00; }
.demo-panel__toggle { display: none; }
.demo-panel__caption { opacity: .8; font-size: 12px; margin-bottom: 6px; }
.demo-panel__row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.demo-panel__time { font-variant-numeric: tabular-nums; min-width: 70px; }
.demo-panel__speeds { display: flex; gap: 4px; margin-left: auto; }
.demo-panel__range { width: 100%; margin: 8px 0 4px; accent-color: #f57c00; }
.demo-panel__marks { display: flex; gap: 6px; flex-wrap: wrap; font-size: 12px; }
.demo-error { position: fixed; inset: auto 16px 16px 16px; z-index: 2001; background: #b71c1c; color: #fff;
  padding: 12px 16px; border-radius: 10px; font: 14px system-ui, sans-serif; }
.demo-error button { margin-left: 8px; }
@media (max-width: 600px) {
  .demo-panel { width: auto; left: auto; right: 16px; transform: none; padding: 0; background: none; box-shadow: none; }
  .demo-panel__toggle { display: block; width: 48px; height: 48px; border-radius: 50% !important;
    background: rgba(20, 24, 31, .92) !important; font-size: 20px !important; margin-left: auto; }
  .demo-panel__body { display: none; }
  .demo-panel--open { left: 16px; background: rgba(20, 24, 31, .92); padding: 10px 14px; border-radius: 12px; }
  .demo-panel--open .demo-panel__body { display: block; }
}
```

- [ ] **Step 3:** `node --check tools/demo/static/demo-replay.js` → без ошибок (если node нет — проверка откладывается до браузера, Task 10).
- [ ] **Step 4: Commit** `feat(demo): demo-replay.js — виртуальные часы, подмена fetch/SSE, панель`.

---

### Task 9: шаблоны, сайт, проверки, сборка

**Files:**
- Create: `tools/demo/templates/krasmarafon/header.html`, `analytics.html`, `krasmarafon_footer.html`; `tools/demo/templates/demo/index.html`, `404.html`; `tools/demo/site.py`, `tools/demo/checks.py`, `tools/demo/build.py`
- Modify: `.gitignore` (+ `dist/`)
- Test: `tests/unit/test_demo_site.py`

- [ ] **Step 1: Шаблоны.**

`tools/demo/templates/krasmarafon/analytics.html` (подключается в `<head>` tracker.html — сюда ставим модуль повтора):

```html
<link rel="stylesheet" href="/static/demo/demo-replay.css">
<script src="/static/demo/demo-replay.js" data-base="{{ base }}" data-race="{{ race_key }}"></script>
```

`tools/demo/templates/krasmarafon/header.html`:

```html
<header style="display:flex;align-items:center;gap:16px;padding:12px 16px;background:#14181f;color:#fff;font:15px system-ui,sans-serif">
  <a href="{{ base }}" style="color:#fff;text-decoration:none;opacity:.85">← Все демо</a>
  <strong>{{ race_title }}</strong>
</header>
```

`tools/demo/templates/krasmarafon/krasmarafon_footer.html` — пустой файл.

`tools/demo/templates/demo/index.html`:

```html
<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="robots" content="noindex">
  <title>Демо: трекер забегов</title>
  <style>
    body { margin: 0; font: 16px/1.4 system-ui, sans-serif; background: #f4f5f7; color: #14181f; }
    main { max-width: 960px; margin: 0 auto; padding: 32px 16px; }
    .cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 16px; }
    .card { background: #fff; border-radius: 12px; padding: 20px; box-shadow: 0 2px 8px rgba(0,0,0,.06); }
    .card h2 { margin: 0 0 6px; font-size: 20px; }
    .card p { margin: 4px 0; color: #555; }
    .card a { display: inline-block; margin-top: 12px; padding: 8px 16px; background: #f57c00; color: #fff;
              border-radius: 8px; text-decoration: none; }
  </style>
</head>
<body>
<main>
  <h1>Трекер забегов — демо</h1>
  <p>Записи реальных гонок, воспроизводятся так, будто идут прямо сейчас. Можно перематывать и ускорять.</p>
  <div class="cards">
    {% for r in races %}
    <div class="card">
      <h2>{{ r.title }}</h2>
      <p>{{ r.kind }} · {{ r.event_date }}</p>
      <p>Участников: {{ r.participants }}</p>
      <a href="{{ base }}{{ r.slug }}/">Открыть</a>
    </div>
    {% endfor %}
  </div>
</main>
</body>
</html>
```

`tools/demo/templates/demo/404.html`:

```html
<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="0; url={{ base }}"><title>Демо</title>
```

- [ ] **Step 2: Падающий тест** `tests/unit/test_demo_site.py`:

```python
import gzip
import json

from tools.demo.checks import check_pii, check_links, check_api
from tools.demo.site import rewrite_static


def test_rewrite_static():
    assert rewrite_static("url('/static/fonts/a.woff')", "/race-tracker-demo/") == \
        "url('/race-tracker-demo/static/fonts/a.woff')"
    assert rewrite_static("/race-tracker-demo/static/x", "/race-tracker-demo/") == "/race-tracker-demo/static/x"


def test_check_pii_finds_surname_in_gz(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "r.json.gz").write_bytes(gzip.compress(json.dumps({"s": "Петров"}).encode()))
    assert check_pii(tmp_path, {"Петров"}) == ["data/r.json.gz: Петров"]
    assert check_pii(tmp_path, {"Сидоров"}) == []


def test_check_links(tmp_path):
    (tmp_path / "static").mkdir()
    (tmp_path / "static" / "a.css").write_text("x")
    (tmp_path / "index.html").write_text('<link href="/race-tracker-demo/static/a.css"><script src="/race-tracker-demo/static/b.js">')
    assert check_links(tmp_path, "/race-tracker-demo/") == ["index.html: /race-tracker-demo/static/b.js"]


def test_check_api(tmp_path):
    (tmp_path / "a.js").write_text("fetch('/api/current-event'); fetch('/api/secret/x')")
    assert check_api(tmp_path) == ["a.js: /api/secret/x"]
```

- [ ] **Step 3:** запуск → FAIL.

- [ ] **Step 4:** `tools/demo/checks.py`:

```python
"""Проверки собранного сайта: ПДн, битые ссылки, неперехваченные /api/ (спека, п. 7)."""
import gzip
import re
from pathlib import Path

from tools.demo.anonymize import _SURNAMES

_TEXT = {'.html', '.js', '.css', '.json'}
_ALLOWED_API = ('/api/current-event', '/api/event-results', '/api/sse/tracker')


def _texts(root: Path):
    for p in sorted(root.rglob('*')):
        if p.suffix in _TEXT:
            yield p, p.read_text(encoding='utf-8', errors='replace')
        elif p.name.endswith('.json.gz'):
            yield p, gzip.decompress(p.read_bytes()).decode('utf-8')


def check_pii(root: Path, surnames: set[str]) -> list[str]:
    """Реальные фамилии (≥ 4 букв) целым словом в любом файле сайта. Фамилии из словаря
    генератора пропускаются: фейковая «Соколова» в демо ничего не раскрывает, а реальные
    фамилии разных гонок пересекаются со словарём (иначе ложные срабатывания)."""
    found = []
    fake = set(_SURNAMES) | {s + 'а' for s in _SURNAMES}
    words = sorted(s for s in surnames if s and len(s) >= 4 and s not in fake)
    for p, text in _texts(root):
        for s in words:
            if re.search(rf'(?<![\w-]){re.escape(s)}(?![\w-])', text):
                found.append(f"{p.relative_to(root).as_posix()}: {s}")
    return found


def check_links(root: Path, base: str) -> list[str]:
    bad = []
    for p, text in _texts(root):
        if p.suffix not in ('.html', '.css'):
            continue
        for ref in re.findall(rf'{re.escape(base)}static/[\w./-]+', text):
            if not (root / ref[len(base):]).exists():
                bad.append(f"{p.relative_to(root).as_posix()}: {ref}")
    return bad


def check_api(root: Path) -> list[str]:
    bad = []
    for p, text in _texts(root):
        if p.suffix not in ('.html', '.js'):
            continue
        for ref in re.findall(r"/api/[\w/-]+", text):
            if not ref.startswith(_ALLOWED_API):
                bad.append(f"{p.relative_to(root).as_posix()}: {ref}")
    return bad
```

`tools/demo/site.py`:

```python
"""Рендер страниц демо и копирование статики (спека, пп. 6–7)."""
import gzip
import json
import shutil
from pathlib import Path

from jinja2 import ChoiceLoader, Environment, FileSystemLoader

ROOT = Path(__file__).resolve().parents[2]
DEMO = Path(__file__).resolve().parent

STATIC_FILES = [
    "lib/leaflet-1.9.4", "css/km-design-tokens.css", "css/krasmarafon-header.css",
    "css/navigation.css", "css/tracker.css", "css/krasmarafon-footer.css",
    "js/utils.js", "js/realtime.js", "js/tracker-api.js", "js/tracker-search.js", "js/tracker-map.js",
    "fonts/HouschkaRoundedAlt-Bold.woff", "fonts/HouschkaRoundedAlt-Medium.woff",
    "fonts/HouschkaPro-DemiBold.otf", "images/krasmarafon",
]


def rewrite_static(text: str, base: str) -> str:
    return text.replace("/static/", f"{base}static/").replace(f"{base}{base[1:]}static/", f"{base}static/")


def _env() -> Environment:
    return Environment(loader=ChoiceLoader([FileSystemLoader(DEMO / "templates"),
                                            FileSystemLoader(ROOT / "templates")]))


def _copy(src: Path, dst: Path, base: str) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.suffix in (".css", ".js"):
        dst.write_text(rewrite_static(src.read_text(encoding="utf-8"), base), encoding="utf-8")
    else:
        shutil.copyfile(src, dst)


def copy_static(out: Path, base: str, gpx_files: list[str]) -> None:
    items = [ROOT / "static" / s for s in STATIC_FILES] + [ROOT / g for g in gpx_files]
    for src in items:
        files = [p for p in src.rglob("*") if p.is_file()] if src.is_dir() else [src]
        for f in files:
            _copy(f, out / f.relative_to(ROOT), base)
    for f in (DEMO / "static").iterdir():
        _copy(f, out / "static" / "demo" / f.name, base)


def write_record(out: Path, key: str, rec: dict) -> None:
    (out / "data").mkdir(parents=True, exist_ok=True)
    body = {k: v for k, v in rec.items() if not k.startswith("_")}
    raw = json.dumps(body, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8")
    (out / "data" / f"{key}.json.gz").write_bytes(gzip.compress(raw, 9))


def render_tracker(out: Path, base: str, key: str, slug: str, rec: dict) -> None:
    m = rec["meta"]
    ce = m["current_event"]
    event_config = {"id": ce["db_event_id"], "code": ce["event"], "name": m["title"],
                    "year": ce["year"], "distance": ce["distances"][0]["distance"],
                    "title": m["title"], "description": m["caption"],
                    "coordinates": [56.0075, 92.7246]}
    html = _env().get_template("krasmarafon/tracker.html").render(
        event_title=f"{m['title']} — демо трекера", event_config=event_config, events=[],
        v="demo", base=base, race_key=key, race_title=m["title"])
    page = out / slug / "index.html"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(rewrite_static(html, base), encoding="utf-8")


def render_index(out: Path, base: str, races: list[dict]) -> None:
    env = _env()
    (out / "index.html").write_text(env.get_template("demo/index.html").render(base=base, races=races), encoding="utf-8")
    (out / "404.html").write_text(env.get_template("demo/404.html").render(base=base), encoding="utf-8")
    (out / ".nojekyll").write_text("")
```

`rewrite_static` второй `.replace` убирает удвоение для уже переписанных путей (`/race-tracker-demo/static/` → после первой замены `/race-tracker-demo/race-tracker-demo/static/` → обратно).

`tools/demo/build.py`:

```python
"""Сборка демо: python tools/demo/build.py zhara_21 zhara_5 → dist/race-tracker-demo/"""
import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv  # noqa: E402
load_dotenv(ROOT / ".env.local", override=True)   # только локальная БД, никогда прод

from tools.demo import checks, site  # noqa: E402
from tools.demo.races import BASE, RACES  # noqa: E402
from tools.demo.source import build_race  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("races", nargs="+", choices=sorted(RACES))
    args = ap.parse_args()
    out = ROOT / "dist" / BASE.strip("/")
    shutil.rmtree(out, ignore_errors=True)

    cards, surnames, gpx = [], set(), []
    for key in args.races:
        print(f"[{key}] проигрываю гонку…", flush=True)
        rec, rows = build_race(key)
        surnames |= {(r.get("surname") or "").strip() for r in rows}
        site.write_record(out, key, rec)
        site.render_tracker(out, BASE, key, RACES[key]["slug"], rec)
        gpx.append(rec["meta"]["gpx"])
        cards.append({**RACES[key], "participants": rec["meta"]["participants"],
                      "event_date": rec["meta"]["event_date"]})
        size = (out / "data" / f"{key}.json.gz").stat().st_size
        print(f"[{key}] шагов с изменениями: {len(rec['changes'])}, запись {size / 1e6:.2f} МБ")
    site.copy_static(out, BASE, gpx)
    site.render_index(out, BASE, cards)

    problems = (checks.check_pii(out, surnames) + checks.check_links(out, BASE) + checks.check_api(out))
    for p in problems:
        print("✗", p)
    if problems:
        print("Сборка НЕ прошла проверки")
        return 1
    print(f"Готово: {out}\nПросмотр: python -m http.server -d dist 8765 → http://localhost:8765{BASE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

В `.gitignore` добавить строку `dist/`.

- [ ] **Step 5:** `conda run -n base python -m pytest tests/unit/test_demo_site.py -v` → PASS.
- [ ] **Step 6: Сборка:** `conda run -n base python tools/demo/build.py zhara_21 zhara_5` → «Готово», размер каждой записи ≤ 3 МБ. Если `check_api` ругается на строки в `tracker-api.js` (например, комментарий с `/api/...`) — добавить конкретный путь в `_ALLOWED_API` только если запрос действительно перехватывается в `demo-replay.js`; иначе — перехватить его там.
- [ ] **Step 7: Commit** `feat(demo): сборка сайта — шаблоны, статика, проверки, CLI`.

---

### Task 10: проверка в браузере

**Files:** без новых (правки по итогам — в `demo-replay.js`)

- [ ] **Step 1:** `conda run -n base python -m http.server -d dist 8765` (в фоне).
- [ ] **Step 2:** через навык `agent-browser` открыть `http://localhost:8765/race-tracker-demo/` (десктоп 1280×800):
  - витрина: 2 карточки, «Открыть» ведёт на `/race-tracker-demo/zhara-21/`;
  - трекер: через ≤ 10 с маркеры есть и двигаются (два скриншота с интервалом 5 с);
  - консоль: нет ошибок; сеть: ни одного запроса к `/api/`, `data/zhara_21.json.gz` — 200;
  - ⏸ останавливает маркеры; 10× ускоряет; «Массовый финиш» перематывает вперёд, «Старт» — назад; после перемотки назад маркеры стоят на правильных местах (не «улетают»);
  - `?t=170m` → через ≤ 20 с повтор возвращается на 30-ю минуту (круг);
  - поиск по фамилии из записи → карточка участника открывается, видны КТ.
- [ ] **Step 3:** то же на 390×844: карта видна, панель свёрнута в кнопку ⏱, раскрывается.
- [ ] **Step 4:** если анимация при перемотке назад сбивается — в `seek()` заменить отправку снимка на `location.search = '?t=' + Math.round(t) + '&speed=' + (clock.speed || 1)` (запасной вариант спеки) и повторить Step 2.
- [ ] **Step 5: Commit** (если были правки) `fix(demo): …` с описанием найденного.

---

### Task 11: публикация

**Files:**
- Create: `tools/demo/publish.py`, `tools/demo/README.md`

- [ ] **Step 1:** `tools/demo/publish.py`:

```python
"""Публикация dist/race-tracker-demo/ в репозиторий podbor16/race-tracker-demo (GitHub Pages, ветка main)."""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "dist" / "race-tracker-demo"
REPO = "https://github.com/podbor16/race-tracker-demo.git"


def run(*cmd, cwd=None):
    print("$", " ".join(cmd))
    subprocess.run(cmd, cwd=cwd, check=True)


def main() -> int:
    if not (SRC / "index.html").exists():
        print("Нет сборки: сначала python tools/demo/build.py …")
        return 1
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp) / "site"
        run("git", "clone", "--depth", "1", REPO, str(work))
        for p in work.iterdir():
            if p.name != ".git":
                shutil.rmtree(p) if p.is_dir() else p.unlink()
        shutil.copytree(SRC, work, dirs_exist_ok=True)
        run("git", "add", "-A", cwd=work)
        if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=work).returncode == 0:
            print("Изменений нет")
            return 0
        run("git", "commit", "-m", "Обновление демо", cwd=work)
        run("git", "push", "origin", "HEAD:main", cwd=work)
    print("Опубликовано: https://podbor16.github.io/race-tracker-demo/ (Pages обновится за 1–2 мин)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2:** `tools/demo/README.md` — разделы: «Собрать» (команда build + просмотр через http.server), «Опубликовать» (publish.py), «Добавить гонку Красмарафона» (запись в `races.py`: slug, config_code, db_event_id, title, caption, kind; в локальной БД должны быть итоговые результаты; пересобрать), «Обновить локальную БД» (ссылка на память `reference-local-db`: снимок прода), «Как устроено» (3 абзаца из спеки п. 3).
- [ ] **Step 3: ПОДТВЕРЖДЕНИЕ ЗАКАЗЧИКА**, затем один раз: `gh repo create podbor16/race-tracker-demo --public --description "Демо трекера забегов"` → `conda run -n base python tools/demo/publish.py` → `gh api -X POST repos/podbor16/race-tracker-demo/pages -f "source[branch]=main" -f "source[path]=/"`.
- [ ] **Step 4:** через 2 мин открыть `https://podbor16.github.io/race-tracker-demo/zhara-21/` в браузере → те же проверки, что Task 10 Step 2 (кратко: маркеры движутся, нет `/api/`, нет ошибок).
- [ ] **Step 5: Commit** `feat(demo): публикация на GitHub Pages + README`.

---

### Task 12: финал

- [ ] **Step 1:** `conda run -n base python -m pytest tests/unit/ -q` → всё зелёное, число тестов = исходное + новые.
- [ ] **Step 2:** `.taskmaster/tasks/todo.md` — отметить пункты, дописать «Ревью»: ссылка на демо, размеры записей, что проверено, отклонения от спеки (если были).
- [ ] **Step 3:** Commit `docs(todo): демо «Повтор гонки» часть 1 — ревью`.
