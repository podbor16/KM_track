# Дашборд мониторинга сервера в /admin — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Новая вкладка «Мониторинг» в `/admin` — живой снимок состояния сервера, графики истории и таблица последних алертов, поверх уже существующего и активно работающего в проде `MetricsCollector`. Плюс конкретные предложения по решению проблемы в push-уведомлениях ntfy.

**Architecture:** Backend почти полностью готов — добавляется одна чистая функция (`generate_suggestions()`), два маленьких метода-помощника на `MetricsCollector`, один новый GET-эндпоинт и точечная правка `_send_ntfy_alert()`. Frontend — новая вкладка по образцу уже существующих (`switchTab()`/`_tabLoaded`), один новый JS-файл, Chart.js уже вендорен локально.

**Tech Stack:** Python 3.13/FastAPI (backend), ванильный JS + Chart.js v4 (frontend, без фреймворков — как и весь остальной проект), pytest (Python-тесты), node:vm (JS-тесты, в проекте нет выделенного JS-фреймворка).

**Дизайн:** `docs/superpowers/specs/2026-08-20-krasmarafon-admin-monitoring-dashboard-design.md`

**Найдено при подготовке плана (не в спеке, важно для реализации):**
1. `GET /api/admin/metrics/live` (`src/krasmarafon/routers/api.py:881-902`) — реальный баг: функция определяет `stream()`, но нигде не делает `return EventSourceResponse(stream())`. Эндпоинт прямо сейчас ничего не стримит. Это первая задача плана — без неё живой блок дашборда не может работать.
2. Спека упоминала переиспользование `SSEClient` (`static/js/realtime.js`) для живого потока — не подходит: `SSEClient` ждёt сообщения формата `{type, ...}` и диспетчеризует по `msg.type` (`this._handlers[msg.type]`), а `/api/admin/metrics/live` шлёт голый dict точки метрик без поля `type` — с `SSEClient` НИ ОДИН обработчик никогда бы не сработал. Используем сырой `EventSource` напрямую — тот же приём, что уже применяет `tracker-api.js` для `/api/sse/tracker` (тоже нетипизированный одноцелевой поток).

---

## File Structure

**Backend:**
- Modify: `src/monitoring/collector.py` — новые константы, `generate_suggestions()`, `MetricsCollector._recent_avg_sse()`, `MetricsCollector.get_alerts_path()`, `MetricsCollector.read_recent_alerts()`, правка `_send_ntfy_alert()`
- Modify: `src/krasmarafon/routers/api.py` — фикс `get_server_metrics_live()`, новый `GET /api/admin/metrics/alerts`
- Test: `tests/unit/test_monitoring_collector.py` (новый файл)
- Test: `tests/integration/test_admin_metrics.py` (новый файл)

**Frontend:**
- Modify: `templates/krasmarafon/admin.html` — вкладка «Мониторинг» (кнопка, контент, `_tabLoaded`/`switchTab()`, `<script>`-подключения)
- Modify: `static/css/admin.css` — плитки метрик, цветные бейджи нагрузки, контейнеры графиков, таблица алертов
- Create: `static/js/admin-monitoring.js` — вся логика вкладки (один файл, по прецеденту `krasmarafon-broadcast-posts.js` — одна вкладка/страница = один файл в этом проекте)
- Test: `tests/js/test_admin_monitoring.js` (новый файл, node:vm — как и все остальные JS-тесты проекта)

Один JS-файл на всю вкладку (не разбиваем на подфайлы по тайлам/графикам/таблице) — так устроены все остальные вкладки-с-логикой в этом проекте (`krasmarafon-broadcast-posts.js`, `analytics-start-list.js` и т.д.), внутри организован секциями по комментариям.

---

### Task 1: Фикс `GET /api/admin/metrics/live` — эндпоинт не возвращает поток

**Files:**
- Modify: `src/krasmarafon/routers/api.py:881-902`
- Test: `tests/integration/test_admin_metrics.py` (создать)

- [x] **Step 1: Прочитать текущий код эндпоинта, чтобы убедиться в баге**

Открыть `src/krasmarafon/routers/api.py`, строки 881-902:

```python
@router.get("/api/admin/metrics/live", tags=["Admin"])
async def get_server_metrics_live(
    request: Request,
    user: str = Depends(api_require_auth),
):
    """SSE-стрим: новая точка метрик каждые 5 секунд."""
    collector = _get_metrics_collector()
    queue = collector.subscribe()

    async def stream():
        try:
            yield {"comment": "connected"}
            while True:
                try:
                    point = await asyncio.wait_for(queue.get(), timeout=30)
                    yield {"data": json.dumps(point)}
                except asyncio.TimeoutError:
                    yield {"comment": "heartbeat"}
                if await request.is_disconnected():
                    break
        finally:
            collector.unsubscribe(queue)
```

Убедиться, что после определения `stream()` нет `return EventSourceResponse(stream())` — сравнить с соседним `sse_notify()` (строки 758-777 того же файла), который заканчивается именно этой строкой.

- [x] **Step 2: Написать падающий тест**

Создать `tests/integration/test_admin_metrics.py`:

```python
"""Интеграционные тесты для /api/admin/metrics/* — живой поток и список алертов."""
import asyncio
from unittest.mock import MagicMock, patch

import pytest

from app import app
from src.core.auth import api_require_auth


@pytest.fixture(autouse=True)
def _override_auth():
    app.dependency_overrides[api_require_auth] = lambda: "testuser"
    yield
    app.dependency_overrides.pop(api_require_auth, None)


class TestServerMetricsLive:
    def test_returns_event_source_response(self):
        """Регрессия: get_server_metrics_live() определяла generator
        stream(), но не возвращала EventSourceResponse(stream()) — эндпоинт
        не отдавал SSE-поток вообще. Вызываем корутину напрямую через
        asyncio.run() — SSE live-эндпоинты в проекте не покрыты реальными
        HTTP-стрим-тестами (см. tests/load/sse_test.js, tests/browser_check.py),
        этот тест не меняет конвенцию, просто проверяет тип возвращаемого
        объекта."""
        from sse_starlette.sse import EventSourceResponse
        from src.krasmarafon.routers.api import get_server_metrics_live

        request = MagicMock()
        result = asyncio.run(get_server_metrics_live(request=request, user="testuser"))
        assert isinstance(result, EventSourceResponse)

    def test_requires_auth(self, client):
        app.dependency_overrides.pop(api_require_auth, None)
        r = client.get("/api/admin/metrics/live")
        assert r.status_code == 401
```

- [x] **Step 3: Запустить тест, убедиться что первый кейс падает**

Run: `conda run -n base python -m pytest tests/integration/test_admin_metrics.py::TestServerMetricsLive::test_returns_event_source_response -v`
Expected: FAIL — `assert isinstance(None, EventSourceResponse)` (функция вернула `None`)

- [x] **Step 4: Добавить недостающий `return`**

В `src/krasmarafon/routers/api.py`, сразу после блока `async def stream(): ... finally: collector.unsubscribe(queue)` (конец функции `get_server_metrics_live`), добавить:

```python
        finally:
            collector.unsubscribe(queue)

    return EventSourceResponse(stream())
```

- [x] **Step 5: Запустить тесты, убедиться что оба проходят**

Run: `conda run -n base python -m pytest tests/integration/test_admin_metrics.py -v`
Expected: `2 passed`

- [x] **Step 6: Коммит**

```bash
git add src/krasmarafon/routers/api.py tests/integration/test_admin_metrics.py
git commit -m "fix(krasmarafon): /api/admin/metrics/live не возвращала SSE-поток вообще

get_server_metrics_live() определяла async-генератор stream(), но нигде
не делала return EventSourceResponse(stream()) — эндпоинт молча отдавал
None вместо живого потока метрик. Найдено при подготовке дашборда
мониторинга в /admin."
```

---

### Task 2: `generate_suggestions()` — предложения по решению проблемы

**Files:**
- Modify: `src/monitoring/collector.py`
- Test: `tests/unit/test_monitoring_collector.py` (создать)

- [x] **Step 1: Написать падающие тесты**

Создать `tests/unit/test_monitoring_collector.py`:

```python
"""Тесты для src/monitoring/collector.py — generate_suggestions() и связанные
методы MetricsCollector (baseline SSE, чтение алертов)."""
import csv
import time
from unittest.mock import patch

import pytest

from src.monitoring.collector import MetricsCollector, generate_suggestions


def _base_point(**overrides):
    base = {
        "ram_used_mb": 500, "ram_total_mb": 2972,
        "avg_response_ms": 100, "total_requests": 100, "http_errors": 0,
        "sse_connections": 5,
    }
    base.update(overrides)
    return base


# --- generate_suggestions() ---------------------------------------------

def test_ram_high_triggers_suggestion():
    point = _base_point(ram_used_mb=2400)  # 80.8% из 2972 MB
    suggestions = generate_suggestions(point, recent_avg_sse=5.0)
    assert len(suggestions) == 1
    assert "RAM" in suggestions[0]
    assert "systemctl restart km_track" in suggestions[0]


def test_response_time_high_triggers_suggestion():
    point = _base_point(avg_response_ms=5000)
    suggestions = generate_suggestions(point, recent_avg_sse=5.0)
    assert len(suggestions) == 1
    assert "Среднее время ответа" in suggestions[0]


def test_error_rate_high_triggers_suggestion():
    point = _base_point(http_errors=10)  # 10% от 100 запросов
    suggestions = generate_suggestions(point, recent_avg_sse=5.0)
    assert len(suggestions) == 1
    assert "Ошибок" in suggestions[0]


def test_sse_anomaly_triggers_suggestion():
    point = _base_point(sse_connections=60)
    suggestions = generate_suggestions(point, recent_avg_sse=10.0)  # 60 > 10*2 и 60 > 20
    assert len(suggestions) == 1
    assert "SSE-подключений" in suggestions[0]


def test_sse_anomaly_requires_absolute_floor_not_just_multiplier():
    """Мультипликатор формально сработал бы (5 > 1*2), но абсолютный порог
    (20 соединений) — нет: не шумим на переходе с 1 до 5 при почти нулевом
    трафике."""
    point = _base_point(sse_connections=5)
    assert generate_suggestions(point, recent_avg_sse=1.0) == []


def test_sse_check_skipped_when_no_baseline():
    point = _base_point(sse_connections=100)
    assert generate_suggestions(point, recent_avg_sse=None) == []


def test_multiple_factors_produce_multiple_suggestions():
    point = _base_point(ram_used_mb=2600, http_errors=20)  # RAM ~87.5%, ошибок 20%
    suggestions = generate_suggestions(point, recent_avg_sse=5.0)
    assert len(suggestions) == 2


def test_nothing_over_threshold_returns_empty_list():
    assert generate_suggestions(_base_point(), recent_avg_sse=5.0) == []


def test_empty_point_does_not_raise():
    """point без ожидаемых ключей — не падает, просто не добавляет советы
    по недостающим показателям (используется .get() с дефолтами)."""
    assert generate_suggestions({}, recent_avg_sse=None) == []


def test_zero_total_requests_does_not_divide_by_zero():
    point = _base_point(total_requests=0, http_errors=0)
    assert generate_suggestions(point, recent_avg_sse=5.0) == []
```

- [x] **Step 2: Запустить тесты, убедиться что падают**

Run: `conda run -n base python -m pytest tests/unit/test_monitoring_collector.py -v`
Expected: FAIL — `ImportError: cannot import name 'generate_suggestions'`

- [x] **Step 3: Добавить константы и функцию в `collector.py`**

Открыть `src/monitoring/collector.py`, найти существующий блок констант (строки 88-92):

```python
_ALERT_CPU_THRESHOLD = 70.0
_ALERT_LOAD_LABELS = {"Высокая", "Критическая"}
_EMAIL_CPU_THRESHOLD = 90.0
_EMAIL_LOAD_LABELS = {"Критическая"}
_EMAIL_COOLDOWN_S = 900
```

Сразу после них добавить:

```python
# Пороги для generate_suggestions() — какой конкретно фактор считается
# "виновником" высокой нагрузки. Из них только _SUGGEST_RT_MS_THRESHOLD
# совпадает с уже существующим порогом _load_score() (там же rt=35 с
# 1500мс) — RAM/ошибки/SSE-аномалия здесь заводятся впервые, для них в
# коде раньше не было отдельных констант (_ALERT_CPU_THRESHOLD/
# _EMAIL_CPU_THRESHOLD относятся только к CPU).
_SUGGEST_RAM_PCT_THRESHOLD = 80.0
_SUGGEST_RT_MS_THRESHOLD = 1500.0
_SUGGEST_ERROR_RATE_THRESHOLD = 5.0
_SUGGEST_SSE_MULTIPLIER = 2.0
_SUGGEST_SSE_MIN_ABSOLUTE = 20


def generate_suggestions(point: dict, recent_avg_sse: float | None) -> list[str]:
    """Готовые русские советы по решению проблемы для точки метрик — 0, 1
    или несколько сразу (проблема может быть многофакторной). Чистая
    функция: без обращений к БД/сети, полностью определяется аргументами —
    used и в _send_ntfy_alert() (свежая точка), и в read_recent_alerts()
    (исторические строки CSV, пересчитывается на лету при каждом чтении,
    не хранится).

    recent_avg_sse — baseline для сравнения "аномально много SSE" (среднее
    число соединений за последний час, см. MetricsCollector._recent_avg_sse());
    вычисляется ВЫЗЫВАЮЩЕЙ стороной, не этой функцией — единственная
    внешняя зависимость, оставлена снаружи ради тестируемости в изоляции."""
    suggestions: list[str] = []

    ram_used = point.get("ram_used_mb") or 0
    ram_total = point.get("ram_total_mb") or 0
    if ram_total > 0 and (ram_used / ram_total) >= _SUGGEST_RAM_PCT_THRESHOLD / 100:
        ram_pct = ram_used / ram_total * 100
        suggestions.append(
            f"RAM {ram_pct:.0f}% ({ram_used} из {ram_total} MB). "
            "ps aux --sort=-%mem | head -5 — какой процесс тянет. "
            "Если один gunicorn-воркер сильно больше других — похоже на утечку, "
            "сброс: systemctl restart km_track. "
            "Если равномерно у всех — это реальный трафик, рассмотреть апгрейд VPS до 4 ГБ."
        )

    avg_ms = point.get("avg_response_ms") or 0
    if avg_ms >= _SUGGEST_RT_MS_THRESHOLD:
        suggestions.append(
            f"Среднее время ответа {avg_ms:.0f} мс. "
            "Проверьте, не идёт ли сейчас bulk-импорт заявок в /admin — это тяжёлая "
            "синхронная операция. Если нет — возможен «thundering herd» на "
            "/api/registered-runners после истечения 5-минутного кеша: много "
            "одновременных запросов бьют в «холодную» БД одновременно."
        )

    total_req = point.get("total_requests") or 0
    http_errors = point.get("http_errors") or 0
    if total_req > 0 and (http_errors / total_req) >= _SUGGEST_ERROR_RATE_THRESHOLD / 100:
        err_rate = http_errors / total_req * 100
        suggestions.append(
            f"Ошибок {err_rate:.0f}% от {total_req} запросов. "
            "journalctl -u km_track --since '15 min ago' | grep -iE \"error|traceback\" "
            "— конкретные исключения. systemctl status mysql redis-server — не легла "
            "ли база/очереди SSE."
        )

    sse = point.get("sse_connections") or 0
    if (recent_avg_sse is not None
            and sse > recent_avg_sse * _SUGGEST_SSE_MULTIPLIER
            and sse > _SUGGEST_SSE_MIN_ABSOLUTE):
        suggestions.append(
            f"Открыто {sse} SSE-подключений (обычно ~{recent_avg_sse:.0f}). "
            "Проверьте, не держит ли один IP непропорционально много соединений "
            "(бот/зависший клиент в цикле переподключения) — nginx уже режет по 50 "
            "на IP. Проверьте также, не лёг ли Redis (без него SSE не рассылает "
            "уведомления, но клиенты всё равно держат соединение)."
        )

    return suggestions
```

- [x] **Step 4: Запустить тесты, убедиться что проходят**

Run: `conda run -n base python -m pytest tests/unit/test_monitoring_collector.py -v`
Expected: `10 passed`

- [x] **Step 5: Коммит**

```bash
git add src/monitoring/collector.py tests/unit/test_monitoring_collector.py
git commit -m "feat(krasmarafon): generate_suggestions() — советы по решению при высокой нагрузке"
```

---

### Task 3: `MetricsCollector._recent_avg_sse()` и `get_alerts_path()`

**Files:**
- Modify: `src/monitoring/collector.py`
- Test: `tests/unit/test_monitoring_collector.py`

- [x] **Step 1: Написать падающие тесты**

Добавить в конец `tests/unit/test_monitoring_collector.py`:

```python
# --- MetricsCollector._recent_avg_sse() ----------------------------------

@patch.object(MetricsCollector, "query")
def test_recent_avg_sse_averages_query_points(mock_query, tmp_path):
    mock_query.return_value = [
        {"sse_connections": 10}, {"sse_connections": 20}, {"sse_connections": 30},
    ]
    collector = MetricsCollector(db_path=str(tmp_path / "metrics.db"))
    assert collector._recent_avg_sse() == 20.0


@patch.object(MetricsCollector, "query")
def test_recent_avg_sse_returns_none_when_no_history(mock_query, tmp_path):
    mock_query.return_value = []
    collector = MetricsCollector(db_path=str(tmp_path / "metrics.db"))
    assert collector._recent_avg_sse() is None


# --- MetricsCollector.get_alerts_path() ----------------------------------

def test_get_alerts_path_matches_db_path_parent(tmp_path):
    collector = MetricsCollector(db_path=str(tmp_path / "metrics.db"))
    assert collector.get_alerts_path() == tmp_path / "high_load_alerts.csv"
```

- [x] **Step 2: Запустить тесты, убедиться что падают**

Run: `conda run -n base python -m pytest tests/unit/test_monitoring_collector.py -k "recent_avg_sse or alerts_path" -v`
Expected: FAIL — `AttributeError: 'MetricsCollector' object has no attribute '_recent_avg_sse'`

- [x] **Step 3: Добавить методы в `MetricsCollector`**

В `src/monitoring/collector.py`, найти метод `get_uptime_secs()` (после `query()`, перед `subscribe()`):

```python
    def get_uptime_secs(self) -> int:
        if not _IS_LINUX:
            return 0
        try:
            return _read_uptime_secs()
        except Exception:
            return 0
```

Сразу после него добавить:

```python
    def get_alerts_path(self) -> Path:
        return self._alerts_path

    def _recent_avg_sse(self, hours: int = 1) -> float | None:
        """Среднее число SSE-соединений за последние `hours` часов —
        baseline для generate_suggestions(), чтобы отличить "аномально
        много" от обычного уровня. None, если истории ещё нет (свежий
        деплой, БД метрик пустая)."""
        now = int(time.time())
        since = now - hours * 3600
        points = self.query(since, now, hours_to_bucket_secs(hours))
        if not points:
            return None
        return sum(p["sse_connections"] for p in points) / len(points)
```

- [x] **Step 4: Запустить тесты, убедиться что проходят**

Run: `conda run -n base python -m pytest tests/unit/test_monitoring_collector.py -k "recent_avg_sse or alerts_path" -v`
Expected: `3 passed`

- [x] **Step 5: Коммит**

```bash
git add src/monitoring/collector.py tests/unit/test_monitoring_collector.py
git commit -m "feat(krasmarafon): MetricsCollector._recent_avg_sse()/get_alerts_path()"
```

---

### Task 4: `MetricsCollector.read_recent_alerts()`

**Files:**
- Modify: `src/monitoring/collector.py`
- Test: `tests/unit/test_monitoring_collector.py`

**Важно:** колонки CSV (`_write_alert()`, уже существующий код) называются НЕ так, как ключи `point`-словаря, которые ждёт `generate_suggestions()` — `cpu_pct` (не `cpu_percent`), `ram_pct`/`ram_used_mb`/`ram_total_mb`, `requests` (не `total_requests`), `avg_ms` (не `avg_response_ms`). Без явного маппинга `generate_suggestions()` тихо получит на входе `{}`-подобный объект (через `.get()`) и всегда будет возвращать пустой список — не упадёт, но советы никогда не появятся.

- [x] **Step 1: Написать падающие тесты**

Добавить в конец `tests/unit/test_monitoring_collector.py`:

```python
# --- MetricsCollector.read_recent_alerts() -------------------------------

_CSV_HEADER = [
    "datetime", "ts", "worker_id", "load_label", "load_score",
    "cpu_pct", "ram_pct", "ram_used_mb", "ram_total_mb",
    "sse_connections", "unique_ips", "requests", "http_errors", "avg_ms",
]


def _write_alerts_csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(_CSV_HEADER)
        for r in rows:
            w.writerow(r)


def test_read_recent_alerts_missing_file_returns_empty_list(tmp_path):
    collector = MetricsCollector(db_path=str(tmp_path / "metrics.db"))
    assert collector.read_recent_alerts() == []


@patch.object(MetricsCollector, "_recent_avg_sse", return_value=5.0)
def test_read_recent_alerts_maps_csv_columns_to_point_shape(mock_avg, tmp_path):
    """cpu_pct/ram_used_mb/requests/avg_ms в CSV должны превратиться в
    cpu_percent/total_requests/avg_response_ms и т.д. для generate_suggestions()
    — иначе советы никогда не появятся (см. примечание к задаче)."""
    collector = MetricsCollector(db_path=str(tmp_path / "metrics.db"))
    _write_alerts_csv(collector.get_alerts_path(), [
        ["2026-08-19 16:49:02", "1787147342", "332942", "Критическая", "85.0",
         "2.4", "80.8", "2400", "2972", "5", "10", "100", "1", "17991.2"],
    ])

    alerts = collector.read_recent_alerts(limit=50)

    assert len(alerts) == 1
    assert alerts[0]["load_label"] == "Критическая"
    suggestions = alerts[0]["suggestions"]
    assert any("RAM" in s for s in suggestions), suggestions
    assert any("Среднее время ответа" in s for s in suggestions), suggestions


def test_read_recent_alerts_respects_limit_and_newest_first(tmp_path):
    collector = MetricsCollector(db_path=str(tmp_path / "metrics.db"))
    rows = [
        [f"2026-08-19 16:{i:02d}:00", str(1787147000 + i), "1", "Высокая", "60.0",
         "10.0", "50.0", "1000", "2972", "5", "10", "100", "0", "500.0"]
        for i in range(5)
    ]
    _write_alerts_csv(collector.get_alerts_path(), rows)

    alerts = collector.read_recent_alerts(limit=2)

    assert len(alerts) == 2
    assert alerts[0]["datetime"] == "2026-08-19 16:04:00"  # самая новая строка первая
    assert alerts[1]["datetime"] == "2026-08-19 16:03:00"


def test_read_recent_alerts_empty_csv_returns_empty_list(tmp_path):
    collector = MetricsCollector(db_path=str(tmp_path / "metrics.db"))
    collector.get_alerts_path().touch()  # существует, но пуст (0 байт)
    assert collector.read_recent_alerts() == []
```

- [x] **Step 2: Запустить тесты, убедиться что падают**

Run: `conda run -n base python -m pytest tests/unit/test_monitoring_collector.py -k read_recent_alerts -v`
Expected: FAIL — `AttributeError: 'MetricsCollector' object has no attribute 'read_recent_alerts'`

- [x] **Step 3: Добавить метод**

В `src/monitoring/collector.py`, сразу после `_recent_avg_sse()` (добавлен в Task 3), добавить:

```python
    def read_recent_alerts(self, limit: int = 50) -> list[dict]:
        """Последние `limit` строк high_load_alerts.csv, самые новые первыми,
        каждая дополнена suggestions (generate_suggestions()) — советы
        считаются на лету при каждом чтении, не хранятся в CSV, чтобы
        будущие улучшения логики сразу применялись и к старым алертам."""
        if not self._alerts_path.exists() or self._alerts_path.stat().st_size == 0:
            return []
        try:
            with self._file_lock:
                with open(self._alerts_path, "r", encoding="utf-8", newline="") as f:
                    rows = list(csv.DictReader(f))
        except Exception as e:
            _log.warning(f"MetricsCollector: read_recent_alerts failed: {e}")
            return []

        recent_avg_sse = self._recent_avg_sse()
        result = []
        for row in reversed(rows[-limit:]):
            point = {
                "cpu_percent": float(row.get("cpu_pct") or 0),
                "ram_used_mb": int(float(row.get("ram_used_mb") or 0)),
                "ram_total_mb": int(float(row.get("ram_total_mb") or 0)),
                "avg_response_ms": float(row.get("avg_ms") or 0),
                "total_requests": int(float(row.get("requests") or 0)),
                "http_errors": int(float(row.get("http_errors") or 0)),
                "sse_connections": int(float(row.get("sse_connections") or 0)),
            }
            result.append({**row, "suggestions": generate_suggestions(point, recent_avg_sse)})
        return result
```

- [x] **Step 4: Запустить тесты, убедиться что проходят**

Run: `conda run -n base python -m pytest tests/unit/test_monitoring_collector.py -v`
Expected: `17 passed` (все тесты файла — из Task 2/3/4 суммарно)

- [x] **Step 5: Коммит**

```bash
git add src/monitoring/collector.py tests/unit/test_monitoring_collector.py
git commit -m "feat(krasmarafon): MetricsCollector.read_recent_alerts() — история алертов с советами"
```

---

### Task 5: Обогатить `_send_ntfy_alert()` советами

**Files:**
- Modify: `src/monitoring/collector.py:265-294`
- Test: `tests/unit/test_monitoring_collector.py`

- [x] **Step 1: Написать падающий тест**

Добавить в конец `tests/unit/test_monitoring_collector.py`:

```python
# --- MetricsCollector._send_ntfy_alert() ---------------------------------

@patch("src.monitoring.collector.urllib.request.urlopen")
def test_send_ntfy_alert_includes_suggestions_in_body(mock_urlopen, tmp_path):
    collector = MetricsCollector(db_path=str(tmp_path / "metrics.db"))
    collector._ntfy_url = "https://ntfy.sh/test-topic"
    point = {
        "ts": int(time.time()), "load_score": 85.0, "load_label": "Критическая",
        "cpu_percent": 10.0, "ram_used_mb": 2400, "ram_total_mb": 2972,
        "sse_connections": 5, "unique_ips": 10, "total_requests": 100,
        "http_errors": 0, "avg_response_ms": 100,
    }

    collector._send_ntfy_alert(point, ram_pct=80.8)

    sent_request = mock_urlopen.call_args_list[0].args[0]
    body_text = sent_request.data.decode("utf-8")
    assert "Рекомендации:" in body_text
    assert "RAM" in body_text


@patch("src.monitoring.collector.urllib.request.urlopen")
def test_send_ntfy_alert_omits_recommendations_block_when_no_suggestions(mock_urlopen, tmp_path):
    collector = MetricsCollector(db_path=str(tmp_path / "metrics.db"))
    collector._ntfy_url = "https://ntfy.sh/test-topic"
    point = {
        "ts": int(time.time()), "load_score": 85.0, "load_label": "Критическая",
        "cpu_percent": 95.0, "ram_used_mb": 500, "ram_total_mb": 2972,
        "sse_connections": 5, "unique_ips": 10, "total_requests": 100,
        "http_errors": 0, "avg_response_ms": 100,
    }  # только CPU высокий (не входит в generate_suggestions()) — советов нет

    collector._send_ntfy_alert(point, ram_pct=16.8)

    sent_request = mock_urlopen.call_args_list[0].args[0]
    body_text = sent_request.data.decode("utf-8")
    assert "Рекомендации:" not in body_text
```

- [x] **Step 2: Запустить тесты, убедиться что падают**

Run: `conda run -n base python -m pytest tests/unit/test_monitoring_collector.py -k send_ntfy_alert -v`
Expected: FAIL — первый тест: `assert "Рекомендации:" in body_text` → AssertionError (блока сейчас нет вообще)

- [x] **Step 3: Переписать сборку `body` в `_send_ntfy_alert()`**

В `src/monitoring/collector.py` найти текущий блок (внутри `_send_ntfy_alert`):

```python
        dt = datetime.fromtimestamp(point["ts"]).strftime("%Y-%m-%d %H:%M:%S")
        body = (
            f"Время: {dt}\n"
            f"Score: {point['load_score']} / 100\n"
            f"CPU: {point['cpu_percent']}%\n"
            f"RAM: {ram_pct:.1f}% ({point['ram_used_mb']} / {point['ram_total_mb']} MB)\n"
            f"SSE: {point['sse_connections']} соединений\n"
            f"IP: {point['unique_ips']} уникальных\n"
            f"Запросов: {point['total_requests']} | Ошибок: {point['http_errors']}\n"
            f"Среднее время: {point['avg_response_ms']} мс"
        ).encode("utf-8")
```

Заменить на:

```python
        dt = datetime.fromtimestamp(point["ts"]).strftime("%Y-%m-%d %H:%M:%S")
        suggestions = generate_suggestions(point, self._recent_avg_sse())
        body_lines = [
            f"Время: {dt}",
            f"Score: {point['load_score']} / 100",
            f"CPU: {point['cpu_percent']}%",
            f"RAM: {ram_pct:.1f}% ({point['ram_used_mb']} / {point['ram_total_mb']} MB)",
            f"SSE: {point['sse_connections']} соединений",
            f"IP: {point['unique_ips']} уникальных",
            f"Запросов: {point['total_requests']} | Ошибок: {point['http_errors']}",
            f"Среднее время: {point['avg_response_ms']} мс",
        ]
        if suggestions:
            body_lines.append("")
            body_lines.append("Рекомендации:")
            body_lines.extend(f"• {s}" for s in suggestions)
        body = "\n".join(body_lines).encode("utf-8")
```

- [x] **Step 4: Запустить тесты, убедиться что проходят**

Run: `conda run -n base python -m pytest tests/unit/test_monitoring_collector.py -v`
Expected: `19 passed`

- [x] **Step 5: Коммит**

```bash
git add src/monitoring/collector.py tests/unit/test_monitoring_collector.py
git commit -m "feat(krasmarafon): push-уведомления ntfy дополнены советами по решению"
```

---

### Task 6: Новый эндпоинт `GET /api/admin/metrics/alerts`

**Files:**
- Modify: `src/krasmarafon/routers/api.py`
- Test: `tests/integration/test_admin_metrics.py`

- [x] **Step 1: Написать падающие тесты**

Добавить в `tests/integration/test_admin_metrics.py` (после класса `TestServerMetricsLive`):

```python
class TestServerMetricsAlerts:
    def test_returns_alerts_from_collector(self, client):
        fake_alerts = [{
            "datetime": "2026-08-19 16:49:02", "load_label": "Критическая",
            "suggestions": ["RAM 80% ..."],
        }]
        with patch("src.krasmarafon.routers.api._get_metrics_collector") as mock_get:
            mock_collector = MagicMock()
            mock_collector.read_recent_alerts.return_value = fake_alerts
            mock_get.return_value = mock_collector
            r = client.get("/api/admin/metrics/alerts")
        assert r.status_code == 200
        assert r.json() == {"alerts": fake_alerts}

    def test_passes_limit_to_collector(self, client):
        with patch("src.krasmarafon.routers.api._get_metrics_collector") as mock_get:
            mock_collector = MagicMock()
            mock_collector.read_recent_alerts.return_value = []
            mock_get.return_value = mock_collector
            client.get("/api/admin/metrics/alerts?limit=10")
        mock_collector.read_recent_alerts.assert_called_once_with(10)

    def test_default_limit_is_50(self, client):
        with patch("src.krasmarafon.routers.api._get_metrics_collector") as mock_get:
            mock_collector = MagicMock()
            mock_collector.read_recent_alerts.return_value = []
            mock_get.return_value = mock_collector
            client.get("/api/admin/metrics/alerts")
        mock_collector.read_recent_alerts.assert_called_once_with(50)

    def test_limit_over_200_returns_422(self, client):
        r = client.get("/api/admin/metrics/alerts?limit=500")
        assert r.status_code == 422

    def test_requires_auth(self, client):
        app.dependency_overrides.pop(api_require_auth, None)
        r = client.get("/api/admin/metrics/alerts")
        assert r.status_code == 401
```

- [x] **Step 2: Запустить тесты, убедиться что падают**

Run: `conda run -n base python -m pytest tests/integration/test_admin_metrics.py::TestServerMetricsAlerts -v`
Expected: FAIL — `404 Not Found` (эндпоинта ещё нет)

- [x] **Step 3: Добавить эндпоинт**

В `src/krasmarafon/routers/api.py`, сразу после `get_server_metrics_live()` (после строки с `return EventSourceResponse(stream())`, добавленной в Task 1), добавить:

```python
@router.get("/api/admin/metrics/alerts", tags=["Admin"])
async def get_server_metrics_alerts(
    limit: int = Query(default=50, le=200),
    user: str = Depends(api_require_auth),
):
    """Последние алерты высокой нагрузки — каждый дополнен советами по
    решению (generate_suggestions(), считаются на лету, не хранятся в CSV)."""
    collector = _get_metrics_collector()
    alerts = await asyncio.get_event_loop().run_in_executor(
        None, collector.read_recent_alerts, limit
    )
    return {"alerts": alerts}
```

- [x] **Step 4: Запустить тесты, убедиться что проходят**

Run: `conda run -n base python -m pytest tests/integration/test_admin_metrics.py -v`
Expected: `7 passed` (Task 1 + Task 6 тесты суммарно)

- [x] **Step 5: Коммит**

```bash
git add src/krasmarafon/routers/api.py tests/integration/test_admin_metrics.py
git commit -m "feat(krasmarafon): GET /api/admin/metrics/alerts — история алертов для дашборда"
```

---

### Task 7: Вкладка «Мониторинг» — разметка в `admin.html`

**Files:**
- Modify: `templates/krasmarafon/admin.html`

- [x] **Step 1: Добавить кнопку вкладки**

Найти (строка 48):

```html
            <button class="admin-tab" onclick="switchTab('broadcast', this)">Трансляция</button>
        </div>
```

Заменить на:

```html
            <button class="admin-tab" onclick="switchTab('broadcast', this)">Трансляция</button>
            <button class="admin-tab" onclick="switchTab('monitoring', this)">Мониторинг</button>
        </div>
```

- [x] **Step 2: Добавить контент вкладки**

Найти конец блока `tab-broadcast` (после закрывающего `</div>` вкладки «Трансляция», перед закрывающим `</div>` контейнера `.admin-page` — строки 240-242 в исходном файле):

```html
            </div>
        </div>
    </div>

    <!-- ШАБЛОН КАРТОЧКИ СОБЫТИЯ (JS-клонирование) -->
```

Заменить на (добавляя новый блок ПЕРЕД закрывающим `</div>` контейнера страницы):

```html
            </div>
        </div>

        <!-- ================================================================ -->
        <!-- ВКЛАДКА: МОНИТОРИНГ (живое состояние сервера + история + алерты) -->
        <!-- ================================================================ -->
        <div id="tab-monitoring" class="admin-tab-content" style="display:none">
            <div class="admin-section-note">
                Живое состояние сервера, графики истории и последние алерты высокой
                нагрузки — данные собирает MetricsCollector (src/monitoring/collector.py),
                уже работает в фоне каждую минуту.
            </div>

            <div class="admin-metric-tiles">
                <div class="admin-metric-tile">
                    <div class="admin-metric-tile__label">Индекс нагрузки</div>
                    <div class="admin-metric-tile__value" id="mon-tile-load-score">—</div>
                    <span class="admin-badge" id="mon-tile-load-badge">—</span>
                </div>
                <div class="admin-metric-tile">
                    <div class="admin-metric-tile__label">CPU</div>
                    <div class="admin-metric-tile__value" id="mon-tile-cpu">—</div>
                </div>
                <div class="admin-metric-tile">
                    <div class="admin-metric-tile__label">RAM</div>
                    <div class="admin-metric-tile__value" id="mon-tile-ram">—</div>
                </div>
                <div class="admin-metric-tile">
                    <div class="admin-metric-tile__label">Среднее время ответа</div>
                    <div class="admin-metric-tile__value" id="mon-tile-response">—</div>
                </div>
                <div class="admin-metric-tile">
                    <div class="admin-metric-tile__label">Запросы / ошибки</div>
                    <div class="admin-metric-tile__value" id="mon-tile-requests">—</div>
                </div>
                <div class="admin-metric-tile">
                    <div class="admin-metric-tile__label">SSE-соединения</div>
                    <div class="admin-metric-tile__value" id="mon-tile-sse">—</div>
                </div>
                <div class="admin-metric-tile">
                    <div class="admin-metric-tile__label">Уникальные IP</div>
                    <div class="admin-metric-tile__value" id="mon-tile-ips">—</div>
                </div>
                <div class="admin-metric-tile">
                    <div class="admin-metric-tile__label">Аптайм</div>
                    <div class="admin-metric-tile__value" id="mon-tile-uptime">—</div>
                </div>
            </div>

            <div class="admin-leads-toolbar" style="margin-top:24px">
                <label class="km-label" for="mon-range">Диапазон:</label>
                <select id="mon-range" class="admin-select" onchange="monOnRangeChange()">
                    <option value="1h">1 час</option>
                    <option value="6h">6 часов</option>
                    <option value="24h" selected>24 часа</option>
                    <option value="7d">7 дней</option>
                    <option value="30d">30 дней</option>
                    <option value="90d">90 дней</option>
                    <option value="6m">Полгода</option>
                    <option value="1y">Год</option>
                </select>
            </div>

            <div class="admin-monitoring-charts">
                <div class="admin-monitoring-chart-box"><canvas id="mon-chart-cpu"></canvas></div>
                <div class="admin-monitoring-chart-box"><canvas id="mon-chart-ram"></canvas></div>
                <div class="admin-monitoring-chart-box"><canvas id="mon-chart-response"></canvas></div>
                <div class="admin-monitoring-chart-box"><canvas id="mon-chart-errors"></canvas></div>
            </div>

            <h3 style="margin-top:24px">Последние алерты</h3>
            <table class="admin-alerts-table">
                <thead>
                    <tr><th>Время</th><th>Нагрузка</th><th>CPU/RAM</th><th>Время ответа</th><th>Советы</th></tr>
                </thead>
                <tbody id="mon-alerts-body">
                    <tr><td colspan="5">Загрузка...</td></tr>
                </tbody>
            </table>
        </div>
    </div>

    <!-- ШАБЛОН КАРТОЧКИ СОБЫТИЯ (JS-клонирование) -->
```

- [x] **Step 3: Подключить Chart.js и новый JS-файл**

Найти строку 1587:

```html
    <script src="/static/js/krasmarafon-broadcast-posts.js"></script>
```

Заменить на:

```html
    <script src="/static/lib/chart4/chart.umd.min.js"></script>
    <script src="/static/js/krasmarafon-broadcast-posts.js"></script>
    <script src="/static/js/admin-monitoring.js"></script>
```

- [x] **Step 4: Подключить вкладку к диспетчеру `switchTab()`**

Найти (строка 293):

```javascript
    const _tabLoaded = { events: false, presets: false, loader: false, leads: false, analytics: false };
```

Заменить на:

```javascript
    const _tabLoaded = { events: false, presets: false, loader: false, leads: false, analytics: false, monitoring: false };
```

Найти блок диспетчеризации внутри `switchTab()` (строки 306-315):

```javascript
        if (!_tabLoaded[name]) {
            _tabLoaded[name] = true;
            if (name === 'events') loadEvents();
            if (name === 'presets') loadPresets();
            if (name === 'loader') loadLoader();
            if (name === 'leads') loadLeadsTab();
            if (name === 'age-groups') loadAgeGroupsTab();
            if (name === 'photos') loadPhotosTab();
            if (name === 'analytics') loadAnalyticsTab();
        }
```

Заменить на:

```javascript
        if (!_tabLoaded[name]) {
            _tabLoaded[name] = true;
            if (name === 'events') loadEvents();
            if (name === 'presets') loadPresets();
            if (name === 'loader') loadLoader();
            if (name === 'leads') loadLeadsTab();
            if (name === 'age-groups') loadAgeGroupsTab();
            if (name === 'photos') loadPhotosTab();
            if (name === 'analytics') loadAnalyticsTab();
            if (name === 'monitoring') loadMonitoringTab();
        }
```

- [x] **Step 5: Коммит**

Файл `static/js/admin-monitoring.js` ещё не создан (Task 9-11) — `loadMonitoringTab()` пока не определена, страница будет падать в консоли при клике на вкладку. Это нормально для промежуточного коммита в рамках плана (следующие задачи создают файл), но чтобы не оставлять репозиторий в ломаном состоянии дольше одного коммита, объединяем со следующей задачей:

```bash
git add templates/krasmarafon/admin.html
git commit -m "feat(krasmarafon): вкладка «Мониторинг» — разметка в /admin

Логика (loadMonitoringTab() и т.д.) добавляется следующим коммитом —
static/js/admin-monitoring.js."
```

---

### Task 8: CSS для вкладки «Мониторинг»

**Files:**
- Modify: `static/css/admin.css`

- [x] **Step 1: Добавить стили**

В конец `static/css/admin.css` добавить:

```css
/* ------- Monitoring tab ------- */

.admin-metric-tiles {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
    gap: 12px;
    margin-bottom: 16px;
}
.admin-metric-tile {
    background: var(--km-bg-card);
    border: 1px solid var(--km-border-light);
    border-radius: var(--km-radius-card);
    padding: 12px 16px;
    box-shadow: var(--km-shadow);
}
.admin-metric-tile__label {
    font-size: 0.72rem;
    color: var(--km-text-secondary);
    text-transform: uppercase;
    margin-bottom: 4px;
}
.admin-metric-tile__value {
    font-family: var(--km-font-brand);
    font-size: 1.3rem;
    font-weight: 600;
    color: var(--km-dark);
}

.admin-badge--load-low { background: #d4edda; color: #155724; }
.admin-badge--load-medium { background: #fff3cd; color: #856404; }
.admin-badge--load-high { background: #ffe5d0; color: #a34e00; }
.admin-badge--load-critical { background: #f8d7da; color: #721c24; }

.admin-monitoring-charts {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
    gap: 16px;
    margin-bottom: 16px;
}
.admin-monitoring-chart-box {
    background: var(--km-bg-card);
    border: 1px solid var(--km-border-light);
    border-radius: var(--km-radius-card);
    padding: 12px;
    height: 220px;
}
.admin-monitoring-chart-box canvas { max-height: 196px; }

.admin-alerts-table {
    width: 100%;
    font-size: 0.8rem;
    border-collapse: collapse;
}
.admin-alerts-table th, .admin-alerts-table td {
    padding: 8px;
    text-align: left;
    border-bottom: 1px solid var(--km-border-light);
    vertical-align: top;
}
.admin-alerts-suggestions {
    margin: 0;
    padding-left: 18px;
}
.admin-alerts-suggestions li {
    margin-bottom: 4px;
}
```

- [x] **Step 2: Коммит**

```bash
git add static/css/admin.css
git commit -m "feat(krasmarafon): стили вкладки «Мониторинг» — плитки, бейджи, графики, таблица алертов"
```

---

### Task 9: `admin-monitoring.js` — живые плитки и подписка на SSE

**Files:**
- Create: `static/js/admin-monitoring.js`
- Test: `tests/js/test_admin_monitoring.js` (создать)

- [ ] **Step 1: Написать падающий тест**

Создать `tests/js/test_admin_monitoring.js`:

```javascript
// Тесты для static/js/admin-monitoring.js — вкладка «Мониторинг» в /admin.
// В проекте нет JS-тест-фреймворка — используется node:vm.
// Запуск: node tests/js/test_admin_monitoring.js
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert');

const ROOT = path.resolve(__dirname, '..', '..');
const scriptJs = fs.readFileSync(path.join(ROOT, 'static/js/admin-monitoring.js'), 'utf-8');

function makeElement(tag) {
    const children = [];
    const classes = new Set();
    const el = {
        tagName: (tag || 'DIV').toUpperCase(),
        value: '', textContent: '', innerHTML: '',
        style: {},
        dataset: {},
        parentElement: null,
        _children: children,
        appendChild(child) { children.push(child); child.parentElement = el; return child; },
        get className() { return Array.from(classes).join(' '); },
        set className(v) { classes.clear(); String(v).split(/\s+/).filter(Boolean).forEach(c => classes.add(c)); },
        classList: {
            add: (c) => classes.add(c),
            remove: (c) => classes.delete(c),
            contains: (c) => classes.has(c),
        },
    };
    return el;
}

const elementsById = {};
function domStub(id) {
    if (!elementsById[id]) elementsById[id] = makeElement('DIV');
    return elementsById[id];
}
function resetDom() {
    for (const k of Object.keys(elementsById)) delete elementsById[k];
}

class FakeEventSource {
    constructor(url) { this.url = url; this.onmessage = null; }
    close() {}
}

const sandbox = {
    console,
    fetch: () => Promise.resolve({ ok: true, json: () => Promise.resolve({}) }),
    document: { getElementById: domStub, createElement: (tag) => makeElement(tag) },
    EventSource: FakeEventSource,
    window: {},
};
sandbox.window = sandbox;
vm.createContext(sandbox);
vm.runInContext(scriptJs, sandbox);

let failures = 0;
function check(name, fn) {
    try { fn(); console.log(`OK   ${name}`); }
    catch (e) { failures++; console.log(`FAIL ${name}: ${e.message}`); }
}

check('loadLabelBadgeClass() — маппит русские метки на CSS-классы', () => {
    assert.strictEqual(sandbox.loadLabelBadgeClass('Низкая'), 'admin-badge--load-low');
    assert.strictEqual(sandbox.loadLabelBadgeClass('Умеренная'), 'admin-badge--load-medium');
    assert.strictEqual(sandbox.loadLabelBadgeClass('Высокая'), 'admin-badge--load-high');
    assert.strictEqual(sandbox.loadLabelBadgeClass('Критическая'), 'admin-badge--load-critical');
});

check('loadLabelBadgeClass() — неизвестная метка не падает, возвращает дефолт', () => {
    assert.strictEqual(sandbox.loadLabelBadgeClass('бред'), 'admin-badge--inactive');
    assert.strictEqual(sandbox.loadLabelBadgeClass(undefined), 'admin-badge--inactive');
});

check('formatRamLabel() — форматирует used/total MB с процентом', () => {
    assert.strictEqual(sandbox.formatRamLabel(1755, 2972), '1755 / 2972 MB (59%)');
});

check('formatRamLabel() — total=0 не делит на ноль', () => {
    assert.strictEqual(sandbox.formatRamLabel(0, 0), '—');
});

check('formatUptime() — дни+часы при аптайме больше суток', () => {
    assert.strictEqual(sandbox.formatUptime(90000), '1 д 1 ч'); // 25ч = 1д1ч
});

check('formatUptime() — только часы, если меньше суток', () => {
    assert.strictEqual(sandbox.formatUptime(7200), '2 ч');
});

check('renderLiveTiles() — заполняет все плитки из точки метрик', () => {
    resetDom();
    const point = {
        cpu_percent: 42.5, ram_used_mb: 1755, ram_total_mb: 2972,
        avg_response_ms: 320, total_requests: 500, http_errors: 3,
        sse_connections: 12, unique_ips: 80,
        load_score: 55.2, load_label: 'Умеренная',
    };
    sandbox.renderLiveTiles(point);
    assert.strictEqual(domStub('mon-tile-cpu').textContent, '42.5%');
    assert.strictEqual(domStub('mon-tile-ram').textContent, '1755 / 2972 MB (59%)');
    assert.strictEqual(domStub('mon-tile-response').textContent, '320 мс');
    assert.strictEqual(domStub('mon-tile-requests').textContent, '500 (ошибок: 3)');
    assert.strictEqual(domStub('mon-tile-sse').textContent, '12');
    assert.strictEqual(domStub('mon-tile-ips').textContent, '80');
    assert.strictEqual(domStub('mon-tile-load-score').textContent, '55.2 / 100');
    assert.strictEqual(domStub('mon-tile-load-badge').textContent, 'Умеренная');
    assert.ok(domStub('mon-tile-load-badge').classList.contains('admin-badge--load-medium'));
});

console.log(failures === 0 ? '\nALL PASSED' : `\n${failures} FAILED`);
process.exit(failures === 0 ? 0 : 1);
```

- [ ] **Step 2: Запустить тест, убедиться что падает**

Run: `node tests/js/test_admin_monitoring.js`
Expected: FAIL — `static/js/admin-monitoring.js` ещё не существует (`ENOENT`)

- [ ] **Step 3: Создать `static/js/admin-monitoring.js`**

```javascript
// static/js/admin-monitoring.js
// Вкладка "Мониторинг" в /admin — живой снимок состояния сервера, графики
// истории и таблица последних алертов. Backend полностью готов и уже
// активно собирает данные в проде — src/monitoring/collector.py
// (MetricsCollector) + src/krasmarafon/routers/api.py (/api/admin/metrics,
// /api/admin/metrics/live, /api/admin/metrics/alerts).
// Дизайн: docs/superpowers/specs/2026-08-20-krasmarafon-admin-monitoring-dashboard-design.md
//
// Живой поток — сырой EventSource, НЕ через SSEClient (static/js/realtime.js):
// SSEClient диспетчеризует сообщения по полю msg.type, а
// /api/admin/metrics/live шлёт голый dict точки метрик без этого поля —
// с SSEClient ни один обработчик никогда бы не сработал. Тот же приём, что
// уже использует tracker-api.js для /api/sse/tracker (тоже нетипизированный
// одноцелевой поток).

// ---- Русские метки нагрузки → CSS-модификатор бейджа ----
const MON_LOAD_BADGE_CLASS = {
    'Низкая': 'admin-badge--load-low',
    'Умеренная': 'admin-badge--load-medium',
    'Высокая': 'admin-badge--load-high',
    'Критическая': 'admin-badge--load-critical',
};
function loadLabelBadgeClass(label) {
    return MON_LOAD_BADGE_CLASS[label] || 'admin-badge--inactive';
}

// ---- Форматирование ----
function formatRamLabel(usedMb, totalMb) {
    if (!totalMb) return '—';
    const pct = Math.round((usedMb / totalMb) * 100);
    return `${usedMb} / ${totalMb} MB (${pct}%)`;
}

function formatUptime(secs) {
    if (!secs) return '—';
    const days = Math.floor(secs / 86400);
    const hours = Math.floor((secs % 86400) / 3600);
    return days > 0 ? `${days} д ${hours} ч` : `${hours} ч`;
}

// ---- Живые плитки ----
function renderLiveTiles(point) {
    domSet('mon-tile-cpu', `${point.cpu_percent ?? 0}%`);
    domSet('mon-tile-ram', formatRamLabel(point.ram_used_mb, point.ram_total_mb));
    domSet('mon-tile-response', `${point.avg_response_ms ?? 0} мс`);
    domSet('mon-tile-requests', `${point.total_requests ?? 0} (ошибок: ${point.http_errors ?? 0})`);
    domSet('mon-tile-sse', `${point.sse_connections ?? 0}`);
    domSet('mon-tile-ips', `${point.unique_ips ?? 0}`);
    domSet('mon-tile-load-score', `${point.load_score ?? 0} / 100`);

    const badgeEl = document.getElementById('mon-tile-load-badge');
    if (badgeEl) {
        badgeEl.textContent = point.load_label || '—';
        badgeEl.className = 'admin-badge ' + loadLabelBadgeClass(point.load_label);
    }
}

function domSet(id, text) {
    const el = document.getElementById(id);
    if (el) el.textContent = text;
}

// ---- Живой SSE-поток ----
let monSSE = null;
let monLastLoadLabel = null;
const MON_HIGH_LOAD_LABELS = ['Высокая', 'Критическая'];

function monOnLivePoint(point) {
    renderLiveTiles(point);
    // Новый алерт (метка стала "Высокая"/"Критическая", раньше не была) —
    // обновляем таблицу последних алертов, не дожидаясь ручного обновления.
    if (MON_HIGH_LOAD_LABELS.includes(point.load_label) && point.load_label !== monLastLoadLabel) {
        monLoadAlerts();
    }
    monLastLoadLabel = point.load_label;
}

function monSubscribeLive() {
    if (monSSE) return;
    monSSE = new EventSource('/api/admin/metrics/live');
    monSSE.onmessage = (e) => {
        try {
            monOnLivePoint(JSON.parse(e.data));
        } catch {}
    };
}

// ---- Инициализация вкладки (вызывается из switchTab() в admin.html) ----
function loadMonitoringTab() {
    monLoadHistory(24);
    monLoadAlerts();
    monSubscribeLive();
}
```

Функции `monLoadHistory`/`monLoadAlerts`/`monOnRangeChange`/`renderHistoryCharts`/`renderAlertsTable` определяются в Task 10/11 — пока оставляем вызовы как есть (браузер выдаст `ReferenceError` в консоли при реальном открытии вкладки до завершения этих задач; для текущего теста это не проблема — тест не вызывает `loadMonitoringTab()`).

- [ ] **Step 4: Запустить тест, убедиться что проходит**

Run: `node tests/js/test_admin_monitoring.js`
Expected: `ALL PASSED`

- [ ] **Step 5: Коммит**

```bash
git add static/js/admin-monitoring.js tests/js/test_admin_monitoring.js
git commit -m "feat(krasmarafon): admin-monitoring.js — живые плитки + подписка на SSE"
```

---

### Task 10: `admin-monitoring.js` — графики истории (Chart.js)

**Files:**
- Modify: `static/js/admin-monitoring.js`
- Modify: `tests/js/test_admin_monitoring.js`

- [ ] **Step 1: Написать падающие тесты**

Добавить в `tests/js/test_admin_monitoring.js` перед финальным `console.log(...)`:

```javascript
// ---- Chart.js стаб ----
class FakeChart {
    constructor(canvas, config) { this.canvas = canvas; this.config = config; this._destroyed = false; }
    destroy() { this._destroyed = true; }
}
sandbox.Chart = FakeChart;
vm.runInContext('void 0', sandbox); // no-op — Chart уже доступен глобально в sandbox без повторной загрузки скрипта

check('hoursForRange() — маппит ключ диапазона на часы для API', () => {
    assert.strictEqual(sandbox.hoursForRange('1h'), 1);
    assert.strictEqual(sandbox.hoursForRange('6h'), 6);
    assert.strictEqual(sandbox.hoursForRange('24h'), 24);
    assert.strictEqual(sandbox.hoursForRange('7d'), 168);
    assert.strictEqual(sandbox.hoursForRange('30d'), 720);
    assert.strictEqual(sandbox.hoursForRange('90d'), 2160);
    assert.strictEqual(sandbox.hoursForRange('6m'), 4320);
    assert.strictEqual(sandbox.hoursForRange('1y'), 8760);
});

check('hoursForRange() — неизвестный ключ по умолчанию 24 часа', () => {
    assert.strictEqual(sandbox.hoursForRange('bogus'), 24);
});

check('renderHistoryCharts() — строит 4 графика с данными из точек истории', () => {
    resetDom();
    const points = [
        { ts: 1755000000, cpu_percent: 10, ram_used_mb: 1000, ram_total_mb: 2000, avg_response_ms: 200, http_errors: 1 },
        { ts: 1755003600, cpu_percent: 20, ram_used_mb: 1500, ram_total_mb: 2000, avg_response_ms: 300, http_errors: 2 },
    ];
    sandbox.renderHistoryCharts(points);
    const cpuChart = vm.runInContext('monCharts["mon-chart-cpu"]', sandbox);
    const ramChart = vm.runInContext('monCharts["mon-chart-ram"]', sandbox);
    assert.deepStrictEqual(cpuChart.config.data.datasets[0].data, [10, 20]);
    assert.deepStrictEqual(ramChart.config.data.datasets[0].data, [50, 75]); // RAM% = used/total*100
});

check('renderHistoryCharts() — второй вызов уничтожает предыдущие графики (нет утечки)', () => {
    resetDom();
    sandbox.renderHistoryCharts([{ ts: 1755000000, cpu_percent: 5, ram_used_mb: 100, ram_total_mb: 200, avg_response_ms: 50, http_errors: 0 }]);
    const first = vm.runInContext('monCharts["mon-chart-cpu"]', sandbox);
    sandbox.renderHistoryCharts([{ ts: 1755000000, cpu_percent: 5, ram_used_mb: 100, ram_total_mb: 200, avg_response_ms: 50, http_errors: 0 }]);
    assert.strictEqual(first._destroyed, true);
});
```

- [ ] **Step 2: Запустить тесты, убедиться что падают**

Run: `node tests/js/test_admin_monitoring.js`
Expected: FAIL — `sandbox.hoursForRange is not a function`

- [ ] **Step 3: Добавить графики в `static/js/admin-monitoring.js`**

Найти текущее определение (добавлено в Task 9):

```javascript
// ---- Инициализация вкладки (вызывается из switchTab() в admin.html) ----
function loadMonitoringTab() {
    monLoadHistory(24);
    monLoadAlerts();
    monSubscribeLive();
}
```

Заменить на (новый блок графиков ВСТАВЛЕН ПЕРЕД `loadMonitoringTab()`, сама функция инициализации остаётся текстуально той же — `monLoadAlerts`/`monSubscribeLive` по-прежнему определяются в Task 9/11, здесь только добавляется `monLoadHistory`, которую `loadMonitoringTab()` уже вызывает):

```javascript
// ---- Диапазон графиков истории: ключ UI → часы для /api/admin/metrics ----
const MON_RANGE_HOURS = {
    '1h': 1, '6h': 6, '24h': 24, '7d': 168, '30d': 720,
    '90d': 2160, '6m': 4320, '1y': 8760,
};
function hoursForRange(rangeKey) {
    return MON_RANGE_HOURS[rangeKey] || 24;
}

// ---- Графики истории (Chart.js v4, static/lib/chart4/) ----
let monCharts = {}; // canvasId → Chart instance, для destroy() перед перерисовкой

function renderHistoryCharts(points) {
    if (!points.length) {
        // Пустая история (свежий деплой, БД метрик ещё не наполнилась) —
        // явное сообщение вместо пустого канваса без каких-либо данных.
        Object.keys(MON_CHART_LABELS).forEach(canvasId => {
            if (monCharts[canvasId]) { monCharts[canvasId].destroy(); monCharts[canvasId] = null; }
            const canvas = document.getElementById(canvasId);
            const box = canvas && canvas.parentElement;
            if (box) box.textContent = 'Нет данных за выбранный период';
        });
        return;
    }

    const labels = points.map(p => new Date(p.ts * 1000).toLocaleString('ru-RU', {
        day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit',
    }));

    monRenderLineChart('mon-chart-cpu', labels, points.map(p => p.cpu_percent), 'CPU %', 'rgba(238,45,98,0.9)');
    monRenderLineChart('mon-chart-ram', labels, points.map(p => p.ram_total_mb ? Math.round(p.ram_used_mb / p.ram_total_mb * 100) : 0), 'RAM %', 'rgba(39,174,96,0.9)');
    monRenderLineChart('mon-chart-response', labels, points.map(p => p.avg_response_ms), 'Время ответа, мс', 'rgba(52,152,219,0.9)');
    monRenderLineChart('mon-chart-errors', labels, points.map(p => p.http_errors), 'Ошибки', 'rgba(230,126,34,0.9)');
}

const MON_CHART_LABELS = {
    'mon-chart-cpu': 'CPU %', 'mon-chart-ram': 'RAM %',
    'mon-chart-response': 'Время ответа, мс', 'mon-chart-errors': 'Ошибки',
};

function monRenderLineChart(canvasId, labels, data, label, color) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    if (monCharts[canvasId]) monCharts[canvasId].destroy();
    monCharts[canvasId] = new Chart(canvas, {
        type: 'line',
        data: {
            labels,
            datasets: [{ label, data, borderColor: color, backgroundColor: color, tension: 0.2, pointRadius: 0 }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: { x: { ticks: { maxTicksLimit: 8 } } },
            plugins: { legend: { display: true } },
        },
    });
}

async function monLoadHistory(hours) {
    const resp = await fetch(`/api/admin/metrics?hours=${hours}`);
    if (!resp.ok) return;
    const data = await resp.json();
    renderHistoryCharts(data.points || []);
    domSet('mon-tile-uptime', formatUptime(data.meta && data.meta.uptime_secs));
}

function monOnRangeChange() {
    const sel = document.getElementById('mon-range');
    monLoadHistory(hoursForRange(sel.value));
}

// ---- Инициализация вкладки (вызывается из switchTab() в admin.html) ----
function loadMonitoringTab() {
    monLoadHistory(24);
    monLoadAlerts();
    monSubscribeLive();
}
```

- [ ] **Step 4: Дополнить тест на пустую историю**

`makeElement()` (Task 9 Step 1) уже проставляет `parentElement` в `appendChild` — ничего в тестовом хелпере менять не нужно. Добавить в `tests/js/test_admin_monitoring.js`, в блок с `FakeChart` (после `sandbox.Chart = FakeChart;`), тест на пустое состояние:

```javascript
check('renderHistoryCharts() — пустой массив точек показывает "Нет данных", не пустой график', () => {
    resetDom();
    const box = makeElement('DIV');
    const canvas = makeElement('CANVAS');
    box.appendChild(canvas);
    elementsById['mon-chart-cpu'] = canvas;
    sandbox.renderHistoryCharts([]);
    assert.ok(box.textContent.includes('Нет данных'));
});
```

- [ ] **Step 5: Запустить тесты, убедиться что проходят**

Run: `node tests/js/test_admin_monitoring.js`
Expected: `ALL PASSED`

- [ ] **Step 6: Коммит**

```bash
git add static/js/admin-monitoring.js tests/js/test_admin_monitoring.js
git commit -m "feat(krasmarafon): admin-monitoring.js — графики истории (Chart.js)"
```

---

### Task 11: `admin-monitoring.js` — таблица последних алертов

**Files:**
- Modify: `static/js/admin-monitoring.js`
- Modify: `tests/js/test_admin_monitoring.js`

- [ ] **Step 1: Написать падающие тесты**

Добавить в `tests/js/test_admin_monitoring.js` перед финальным `console.log(...)`:

```javascript
check('renderAlertsTable() — пустой список показывает заглушку', () => {
    resetDom();
    sandbox.renderAlertsTable([]);
    assert.ok(domStub('mon-alerts-body').innerHTML.includes('Алертов нет'));
});

check('renderAlertsTable() — строит строки с бейджем и советами', () => {
    resetDom();
    const alerts = [
        {
            datetime: '2026-08-19 16:49:02', load_label: 'Критическая',
            cpu_pct: '2.4', ram_pct: '80.8', avg_ms: '17991.2',
            suggestions: ['RAM 80% ...', 'Среднее время ответа 17991 мс ...'],
        },
    ];
    sandbox.renderAlertsTable(alerts);
    const html = domStub('mon-alerts-body').innerHTML;
    assert.ok(html.includes('2026-08-19 16:49:02'));
    assert.ok(html.includes('Критическая'));
    assert.ok(html.includes('admin-badge--load-critical'));
    assert.ok(html.includes('RAM 80%'));
    assert.ok(html.includes('Среднее время ответа 17991 мс'));
});

check('renderAlertsTable() — алерт без советов показывает прочерк, не пустой <ul>', () => {
    resetDom();
    sandbox.renderAlertsTable([{ datetime: '2026-08-19 16:49:02', load_label: 'Высокая', cpu_pct: '90', ram_pct: '10', avg_ms: '100', suggestions: [] }]);
    const html = domStub('mon-alerts-body').innerHTML;
    assert.ok(html.includes('—'));
    assert.ok(!html.includes('<ul'));
});
```

- [ ] **Step 2: Запустить тесты, убедиться что падают**

Run: `node tests/js/test_admin_monitoring.js`
Expected: FAIL — `sandbox.renderAlertsTable is not a function`

- [ ] **Step 3: Добавить рендер таблицы и `loadMonitoringTab()`**

В `static/js/admin-monitoring.js` найти текущее определение (добавлено в Task 9):

```javascript
// ---- Инициализация вкладки (вызывается из switchTab() в admin.html) ----
function loadMonitoringTab() {
    monLoadHistory(24);
    monLoadAlerts();
    monSubscribeLive();
}
```

Заменить весь этот блок на (добавляя таблицу алертов ПЕРЕД инициализацией):

```javascript
// ---- Таблица последних алертов ----
function renderAlertsTable(alerts) {
    const tbody = document.getElementById('mon-alerts-body');
    if (!tbody) return;
    if (!alerts.length) {
        tbody.innerHTML = '<tr><td colspan="5">Алертов нет</td></tr>';
        return;
    }
    tbody.innerHTML = alerts.map(a => {
        const suggestionsHtml = (a.suggestions && a.suggestions.length)
            ? `<ul class="admin-alerts-suggestions">${a.suggestions.map(s => `<li>${s}</li>`).join('')}</ul>`
            : '—';
        return `
            <tr>
                <td>${a.datetime || ''}</td>
                <td><span class="admin-badge ${loadLabelBadgeClass(a.load_label)}">${a.load_label || ''}</span></td>
                <td>CPU ${a.cpu_pct || 0}% / RAM ${a.ram_pct || 0}%</td>
                <td>${a.avg_ms || 0} мс</td>
                <td>${suggestionsHtml}</td>
            </tr>
        `;
    }).join('');
}

async function monLoadAlerts() {
    const resp = await fetch('/api/admin/metrics/alerts?limit=50');
    if (!resp.ok) return;
    const data = await resp.json();
    renderAlertsTable(data.alerts || []);
}

// ---- Инициализация вкладки (вызывается из switchTab() в admin.html) ----
function loadMonitoringTab() {
    monLoadHistory(24);
    monLoadAlerts();
    monSubscribeLive();
}
```

Обратить внимание: `monOnLivePoint()` (Task 9) уже вызывает `monLoadAlerts()` при появлении нового алерта — эта функция теперь определена, `ReferenceError` из Task 9 больше не актуален.

- [ ] **Step 4: Запустить тесты, убедиться что проходят**

Run: `node tests/js/test_admin_monitoring.js`
Expected: `ALL PASSED`

- [ ] **Step 5: Коммит**

```bash
git add static/js/admin-monitoring.js tests/js/test_admin_monitoring.js
git commit -m "feat(krasmarafon): admin-monitoring.js — таблица последних алертов"
```

---

### Task 12: Живая проверка в браузере

**Files:** нет изменений кода — только проверка.

- [ ] **Step 1: Прогнать полный набор тестов перед живой проверкой**

Run: `conda run -n base python -m pytest tests/unit/ tests/integration/test_admin_metrics.py -v`
Expected: все тесты зелёные (никаких новых падений сверх уже известных предсуществующих — если интеграционные тесты в этом окружении требуют локальный MySQL, которого может не быть, см. заметку ниже)

Run (для каждого JS-тест файла проекта, не только нового):
```bash
node tests/js/test_admin_monitoring.js
```
Expected: `ALL PASSED`

- [ ] **Step 2: Поднять локальный dev-сервер**

Run: `conda run -n base python -m uvicorn app:app --host 127.0.0.1 --port 8010`

Подождать строку в логе `Application startup complete` — фоновая задача `_metrics_flusher()` уже начнёт писать точки метрик в `data/server_metrics.db` каждую минуту (реальные данные с локальной машины: CPU/RAM хоста, на котором запущен dev-сервер).

- [ ] **Step 3: Открыть /admin и проверить вкладку «Мониторинг» через agent-browser**

Использовать skill `agent-browser`: открыть `http://127.0.0.1:8010/admin` (потребуется логин — использовать реальные админ-креды из `.env`, НЕ выводить пароль в текст отчёта агента, см. `.claude/memory/feedback_no_credentials_in_subagent_reports.md`), кликнуть вкладку «Мониторинг», убедиться:
- плитки живого состояния отображают числа (не «—» после первого SSE-сообщения — может потребоваться подождать до 5 секунд на первое сообщение потока)
- 4 графика истории отрисовались (можно не иметь много точек за 24ч на свежем dev-сервере — график может быть почти пустым, это ожидаемо, главное что не падает JS-ошибкой)
- таблица алертов показывает «Алертов нет» (на свежей локальной БД метрик — это правильное поведение, не баг)
- переключение диапазона (`1ч`/`7д`/...) не роняет страницу

- [ ] **Step 4: Проверить обработку ошибок — до появления данных**

Через несколько секунд после старта сервера (пока в `data/server_metrics.db` ещё 0 или 1 точка) убедиться, что графики не показывают JS-исключение в консоли браузера при пустом/почти пустом массиве точек.

- [ ] **Step 5: Остановить dev-сервер**

Run: `pkill -f "uvicorn app:app.*8010"` (или закрыть терминал, где сервер запущен)

---

### Task 13: Финальная проверка и пуш

**Files:** нет изменений кода.

- [ ] **Step 1: Полный прогон Python-тестов**

Run: `conda run -n base python -m pytest tests/unit/ -v`
Expected: все тесты проходят (в т.ч. новые из Task 2-6)

- [ ] **Step 2: Полный прогон JS-тестов проекта**

```bash
for f in tests/js/*.js; do node "$f" >/tmp/o.log 2>&1; ec=$?; echo "$f: exit=$ec"; done
```
Expected: только уже известные предсуществующие падения (`test_analytics_results_event_banner.js`, `test_analytics_start_list_event_banner.js`, `test_siberman_results_merge.js` — не связаны с этой задачей, см. историю проекта), новый `test_admin_monitoring.js` — `exit=0`

- [ ] **Step 3: Проверить git-статус — не осталось ли незакоммиченных изменений**

Run: `git status --short`
Expected: чисто относительно всех файлов этого плана (`src/monitoring/collector.py`, `src/krasmarafon/routers/api.py`, `templates/krasmarafon/admin.html`, `static/css/admin.css`, `static/js/admin-monitoring.js`, `tests/unit/test_monitoring_collector.py`, `tests/integration/test_admin_metrics.py`, `tests/js/test_admin_monitoring.js`)

- [ ] **Step 4: Push**

```bash
git push
```

- [ ] **Step 5: Дождаться деплоя и проверить на проде**

Run: `gh run list --limit 1` → `gh run watch <id> --exit-status`

После успешного деплоя — зайти на `https://results.krasmarafon.ru/admin` → вкладка «Мониторинг», убедиться, что живой блок показывает РЕАЛЬНЫЕ данные прод-сервера (не пустые/нулевые — `data/server_metrics.db` на проде уже несколько дней накапливает историю), таблица алертов показывает реальные алерты 18-19.08 с содержательными советами (RAM/время ответа — судя по найденным в этой же сессии числам, оба фактора должны сработать для этих конкретных исторических алертов).

---

## Итог

13 задач, каждая с собственным коммитом. Backend — 6 задач (Task 1-6), фронтенд — 5 задач (Task 7-11), живая проверка — 2 задачи (Task 12-13). По ходу плана исправлен один реальный существовавший баг (Task 1, отсутствующий `return` в live-эндпоинте) и одно отклонение от буквального текста спеки, обоснованное найденной несовместимостью (сырой `EventSource` вместо `SSEClient` в Task 9 — причина явно объяснена в шапке плана и в комментарии кода).
