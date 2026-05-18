# Server Metrics Dashboard — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Страница `/admin/server-metrics` — дашборд реальной нагрузки на сервер с историей 30 дней: уникальные IP, SSE-соединения, RPS, время ответа, ошибки. Живые обновления каждые 5 секунд.

**Architecture:** Middleware в `app.py` вызывает `MetricsCollector.record()` на каждый HTTP-запрос (неблокирующий). Фоновый asyncio-таск каждые 5 секунд вызывает `flush()`, который атомарно снимает bucket, пишет строку в SQLite и рассылает точку SSE-подписчикам дашборда. Два uvicorn-воркера пишут в одну SQLite-таблицу с разными `worker_id`; при чтении строки суммируются.

**Tech Stack:** Python stdlib `sqlite3`, `asyncio`, `dataclasses`; FastAPI `EventSourceResponse`; Chart.js 4.x (CDN).

---

## Карта файлов

| Файл | Статус | Назначение |
|------|--------|------------|
| `src/monitoring/__init__.py` | Создать | Пустой пакет |
| `src/monitoring/collector.py` | Создать | MetricsCollector: record, flush, query, pub-sub |
| `tests/unit/test_collector.py` | Создать | Unit-тесты collector'а |
| `src/tracker/services/notification_hub.py` | Изменить | Добавить `total_sse_count()` |
| `app.py` | Изменить | Инициализация collector'а, middleware hook, фоновый таск |
| `src/tracker/routers/api.py` | Изменить | Два новых endpoint'а |
| `src/tracker/routers/pages.py` | Изменить | Страница `/admin/server-metrics` |
| `templates/server-metrics.html` | Создать | Chart.js дашборд |
| `data/` | Создать (mkdir) | Директория для SQLite DB |

---

## Task 1: MetricsCollector — ядро сбора метрик

**Files:**
- Create: `src/monitoring/__init__.py`
- Create: `src/monitoring/collector.py`
- Create: `tests/unit/test_collector.py`

- [ ] **Шаг 1.1: Создать пустой пакет**

```python
# src/monitoring/__init__.py
# (пустой файл)
```

- [ ] **Шаг 1.2: Написать тесты**

```python
# tests/unit/test_collector.py
"""Unit-тесты MetricsCollector."""
import asyncio
import sys
import tempfile
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest
from src.monitoring.collector import MetricsCollector


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test_metrics.db")


@pytest.fixture
def collector(db_path):
    c = MetricsCollector(db_path=db_path, retention_days=30)
    return c


class TestRecord:
    def test_record_increments_requests(self, collector):
        collector.record(ip="1.2.3.4", duration_ms=100.0, status=200)
        snap = collector.current_snapshot()
        assert snap["total_requests"] == 1

    def test_record_counts_unique_ips(self, collector):
        collector.record(ip="1.2.3.4", duration_ms=100.0, status=200)
        collector.record(ip="1.2.3.4", duration_ms=100.0, status=200)
        collector.record(ip="5.6.7.8", duration_ms=100.0, status=200)
        snap = collector.current_snapshot()
        assert snap["unique_ips"] == 2

    def test_record_counts_errors(self, collector):
        collector.record(ip="1.2.3.4", duration_ms=50.0, status=200)
        collector.record(ip="1.2.3.4", duration_ms=50.0, status=500)
        collector.record(ip="1.2.3.4", duration_ms=50.0, status=404)
        snap = collector.current_snapshot()
        assert snap["http_errors"] == 2

    def test_record_none_client_skips_ip(self, collector):
        collector.record(ip=None, duration_ms=100.0, status=200)
        snap = collector.current_snapshot()
        assert snap["total_requests"] == 1
        assert snap["unique_ips"] == 0


class TestFlush:
    def test_flush_resets_bucket(self, collector, db_path):
        collector.record(ip="1.2.3.4", duration_ms=100.0, status=200)
        asyncio.run(collector.flush(sse_connections=5))
        snap = collector.current_snapshot()
        assert snap["total_requests"] == 0
        assert snap["unique_ips"] == 0

    def test_flush_writes_to_sqlite(self, collector, db_path):
        collector.record(ip="1.2.3.4", duration_ms=200.0, status=200)
        collector.record(ip="5.6.7.8", duration_ms=400.0, status=500)
        asyncio.run(collector.flush(sse_connections=3))
        import sqlite3
        con = sqlite3.connect(db_path)
        rows = con.execute("SELECT unique_ips, total_requests, http_errors, sse_connections FROM metrics").fetchall()
        con.close()
        assert len(rows) == 1
        unique_ips, total_req, errors, sse = rows[0]
        assert unique_ips == 2
        assert total_req == 2
        assert errors == 1
        assert sse == 3

    def test_flush_no_requests_still_writes(self, collector, db_path):
        asyncio.run(collector.flush(sse_connections=0))
        import sqlite3
        con = sqlite3.connect(db_path)
        rows = con.execute("SELECT total_requests FROM metrics").fetchall()
        con.close()
        assert len(rows) == 1
        assert rows[0][0] == 0


class TestQuery:
    def test_query_returns_empty_for_new_db(self, collector):
        import time
        now = int(time.time())
        result = collector.query(since_ts=now - 3600, until_ts=now, bucket_secs=300)
        assert result == []

    def test_query_returns_flushed_data(self, collector):
        collector.record(ip="1.2.3.4", duration_ms=100.0, status=200)
        asyncio.run(collector.flush(sse_connections=2))
        import time
        now = int(time.time())
        result = collector.query(since_ts=now - 60, until_ts=now + 10, bucket_secs=5)
        assert len(result) == 1
        assert result[0]["total_requests"] == 1
        assert result[0]["sse_connections"] == 2

    def test_query_downsamples_multiple_buckets(self, collector):
        # Записываем 3 flush с интервалом — симулируем через прямую запись в DB
        import sqlite3, time
        now = int(time.time())
        worker_id = os.getpid()
        con = sqlite3.connect(collector._db_path)
        for i in range(3):
            con.execute(
                "INSERT INTO metrics VALUES (?,?,?,?,?,?,?)",
                (now - 30 + i*5, worker_id, 5, 10, 0, 1000.0, 3)
            )
        con.commit()
        con.close()
        # Запрашиваем с bucket 60s — должна вернуть 1 агрегированную точку
        result = collector.query(since_ts=now - 60, until_ts=now + 10, bucket_secs=60)
        assert len(result) == 1
        assert result[0]["total_requests"] == 30  # 3 × 10
        assert result[0]["unique_ips"] == 15       # 3 × 5


class TestSubscribe:
    def test_flush_notifies_subscriber(self, collector):
        async def _run():
            q = collector.subscribe()
            collector.record(ip="1.2.3.4", duration_ms=50.0, status=200)
            await collector.flush(sse_connections=1)
            point = await asyncio.wait_for(q.get(), timeout=1.0)
            collector.unsubscribe(q)
            return point
        point = asyncio.run(_run())
        assert "ts" in point
        assert point["total_requests"] == 1
```

- [ ] **Шаг 1.3: Запустить тесты — убедиться что FAIL**

```
conda run -n base python -m pytest tests/unit/test_collector.py -v
```
Ожидаем: `ImportError: cannot import name 'MetricsCollector'`

- [ ] **Шаг 1.4: Реализовать collector.py**

```python
# src/monitoring/collector.py
"""
MetricsCollector — сбор прикладных метрик FastAPI-сервера.

record()  — вызывается из middleware на каждый HTTP-запрос (sync, неблокирующий).
flush()   — вызывается фоновым asyncio-таском каждые 5с; пишет в SQLite.
query()   — возвращает downsampled историю для API.
subscribe/unsubscribe — fan-out очередь для live SSE-стрима дашборда.
"""

import asyncio
import os
import sqlite3
import time
import threading
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class _Bucket:
    ips: set = field(default_factory=set)
    requests: int = 0
    errors: int = 0
    total_ms: float = 0.0


_HOURS_TO_BUCKET_SECS = {
    1:   5,
    6:   60,
    24:  300,
    168: 1800,
    720: 7200,
}


def hours_to_bucket_secs(hours: int) -> int:
    """Возвращает гранулярность downsampling по диапазону часов."""
    for h, b in sorted(_HOURS_TO_BUCKET_SECS.items()):
        if hours <= h:
            return b
    return 7200


class MetricsCollector:
    def __init__(self, db_path: str, retention_days: int = 30):
        self._db_path = db_path
        self._retention_secs = retention_days * 86400
        self._worker_id = os.getpid()
        self._lock = threading.Lock()
        self._bucket = _Bucket()
        self._subscribers: set[asyncio.Queue] = set()
        self._last_point: dict = {}
        self._init_db()

    def _init_db(self) -> None:
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        try:
            con = sqlite3.connect(self._db_path)
            con.execute("PRAGMA journal_mode=WAL")
            con.execute("""
                CREATE TABLE IF NOT EXISTS metrics (
                    ts                INTEGER NOT NULL,
                    worker_id         INTEGER NOT NULL,
                    unique_ips        INTEGER NOT NULL,
                    total_requests    INTEGER NOT NULL,
                    http_errors       INTEGER NOT NULL,
                    total_response_ms REAL    NOT NULL,
                    sse_connections   INTEGER NOT NULL,
                    PRIMARY KEY (ts, worker_id)
                )
            """)
            con.execute(
                "CREATE INDEX IF NOT EXISTS idx_metrics_ts ON metrics(ts)"
            )
            con.commit()
            con.close()
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"MetricsCollector: DB init failed: {e}")

    # ── public API ────────────────────────────────────────────────────────────

    def record(self, ip: str | None, duration_ms: float, status: int) -> None:
        """Неблокирующий: вызывается из middleware на каждый запрос."""
        with self._lock:
            if ip:
                self._bucket.ips.add(ip)
            self._bucket.requests += 1
            if status >= 400:
                self._bucket.errors += 1
            self._bucket.total_ms += duration_ms

    async def flush(self, sse_connections: int) -> None:
        """Снимает bucket, пишет в SQLite, уведомляет SSE-подписчиков."""
        with self._lock:
            bucket = self._bucket
            self._bucket = _Bucket()

        ts = int(time.time())
        unique_ips = len(bucket.ips)
        total_req = bucket.requests
        errors = bucket.errors
        total_ms = bucket.total_ms
        avg_ms = (total_ms / total_req) if total_req else 0.0

        try:
            con = sqlite3.connect(self._db_path)
            con.execute("PRAGMA journal_mode=WAL")
            con.execute(
                "INSERT OR REPLACE INTO metrics VALUES (?,?,?,?,?,?,?)",
                (ts, self._worker_id, unique_ips, total_req, errors, total_ms, sse_connections),
            )
            con.execute(
                "DELETE FROM metrics WHERE ts < ?",
                (ts - self._retention_secs,),
            )
            con.commit()
            con.close()
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"MetricsCollector: flush write failed: {e}")

        point = {
            "ts": ts,
            "unique_ips": unique_ips,
            "total_requests": total_req,
            "http_errors": errors,
            "avg_response_ms": round(avg_ms, 1),
            "sse_connections": sse_connections,
        }
        self._last_point = point

        # Уведомляем SSE-подписчиков дашборда
        stale = set()
        for q in self._subscribers:
            try:
                q.put_nowait(point)
            except asyncio.QueueFull:
                stale.add(q)
        self._subscribers -= stale

    def query(self, since_ts: int, until_ts: int, bucket_secs: int) -> list[dict]:
        """Возвращает downsampled точки из SQLite."""
        try:
            con = sqlite3.connect(self._db_path)
            rows = con.execute("""
                SELECT
                    (ts / :b) * :b                        AS period,
                    SUM(unique_ips)                        AS unique_ips,
                    SUM(total_requests)                    AS total_requests,
                    SUM(http_errors)                       AS http_errors,
                    CASE WHEN SUM(total_requests) > 0
                         THEN SUM(total_response_ms) / SUM(total_requests)
                         ELSE 0 END                        AS avg_response_ms,
                    CAST(AVG(sse_connections) AS INTEGER)  AS sse_connections
                FROM metrics
                WHERE ts >= :since AND ts < :until
                GROUP BY period
                ORDER BY period
            """, {"b": bucket_secs, "since": since_ts, "until": until_ts}).fetchall()
            con.close()
            return [
                {
                    "ts": r[0],
                    "unique_ips": r[1] or 0,
                    "total_requests": r[2] or 0,
                    "http_errors": r[3] or 0,
                    "avg_response_ms": round(r[4] or 0.0, 1),
                    "sse_connections": r[5] or 0,
                }
                for r in rows
            ]
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"MetricsCollector: query failed: {e}")
            return []

    def current_snapshot(self) -> dict:
        """Текущий bucket (ещё не сброшенный) — для live KPI-карточек."""
        with self._lock:
            b = self._bucket
            return {
                "unique_ips": len(b.ips),
                "total_requests": b.requests,
                "http_errors": b.errors,
                "avg_response_ms": round(b.total_ms / b.requests, 1) if b.requests else 0.0,
            }

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=10)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subscribers.discard(q)
```

- [ ] **Шаг 1.5: Запустить тесты — убедиться что PASS**

```
conda run -n base python -m pytest tests/unit/test_collector.py -v
```
Ожидаем: все тесты PASSED.

- [ ] **Шаг 1.6: Коммит**

```bash
git add src/monitoring/__init__.py src/monitoring/collector.py tests/unit/test_collector.py
git commit -m "feat: MetricsCollector — сбор метрик в SQLite с pub-sub"
```

---

## Task 2: total_sse_count() в TrackerHub

**Files:**
- Modify: `src/tracker/services/notification_hub.py`

- [ ] **Шаг 2.1: Добавить метод в TrackerHub**

В файле `src/tracker/services/notification_hub.py` добавить метод после `broadcast()`:

```python
def total_sse_count(self) -> int:
    """Суммарное число активных SSE-подписчиков по всем event_id."""
    return sum(len(queues) for queues in self._subs.values())
```

- [ ] **Шаг 2.2: Проверить вручную**

```
conda run -n base python -c "
from src.tracker.services.notification_hub import tracker_hub
print(tracker_hub.total_sse_count())  # должно быть 0
"
```
Ожидаем: `0`

- [ ] **Шаг 2.3: Коммит**

```bash
git add src/tracker/services/notification_hub.py
git commit -m "feat: TrackerHub.total_sse_count() — суммарный счётчик SSE"
```

---

## Task 3: Интеграция в app.py

**Files:**
- Modify: `app.py` (строки: imports ~1-22, lifespan startup ~84-166, middleware ~201-214)

- [ ] **Шаг 3.1: Добавить импорт и создание collector'а в app.py**

После строки `from src.analytics.db_connection_optimized import initialize_connection_pool` (строка 21) добавить:

```python
from src.monitoring.collector import MetricsCollector

# Глобальный экземпляр — создаётся до lifespan, доступен из middleware
DATA_DIR = Path(__file__).resolve().parent / "data"
DATA_DIR.mkdir(exist_ok=True)
metrics_collector = MetricsCollector(db_path=str(DATA_DIR / "server_metrics.db"))
```

- [ ] **Шаг 3.2: Добавить фоновый таск в lifespan**

В блоке `_sse_tasks` в lifespan (рядом со строками `asyncio.create_task(_tracker_broadcast())` и т.д.) добавить таск `_metrics_flusher`. Найти блок:

```python
    _sse_tasks = [
        asyncio.create_task(_tracker_broadcast()),
        asyncio.create_task(_results_watcher()),
        asyncio.create_task(_startlist_watcher()),
    ]
```

Заменить на:

```python
    async def _metrics_flusher():
        """Каждые 5с снимает bucket метрик и пишет в SQLite."""
        while True:
            await asyncio.sleep(5)
            sse_count = tracker_hub.total_sse_count()
            await metrics_collector.flush(sse_connections=sse_count)

    _sse_tasks = [
        asyncio.create_task(_tracker_broadcast()),
        asyncio.create_task(_results_watcher()),
        asyncio.create_task(_startlist_watcher()),
        asyncio.create_task(_metrics_flusher()),
    ]
```

- [ ] **Шаг 3.3: Добавить hook в middleware**

Найти в middleware `log_request_duration` строку:

```python
    return response
```

Заменить блок внутри middleware (полный, чтобы было точно):

```python
@app.middleware("http")
async def log_request_duration(request: Request, call_next):
    # BaseHTTPMiddleware несовместим с SSE-стримингом — пропускаем без обработки
    if request.url.path.startswith("/api/sse"):
        return await call_next(request)
    start = _time.time()
    response = await call_next(request)
    duration = _time.time() - start
    response.headers["X-Process-Time"] = f"{duration:.3f}"
    if duration > 0.5:
        _perf_logger.warning(f"SLOW {request.method} {request.url.path} {duration:.3f}s")
    else:
        _perf_logger.debug(f"{request.method} {request.url.path} {duration:.3f}s {response.status_code}")
    # Запись метрики (неблокирующая)
    metrics_collector.record(
        ip=request.client.host if request.client else None,
        duration_ms=duration * 1000,
        status=response.status_code,
    )
    return response
```

- [ ] **Шаг 3.4: Проверить что приложение стартует**

```
conda run -n base python -c "import app; print('OK')"
```
Ожидаем: `OK` без ошибок.

- [ ] **Шаг 3.5: Коммит**

```bash
git add app.py
git commit -m "feat: подключение MetricsCollector — middleware + фоновый таск flush"
```

---

## Task 4: API endpoints

**Files:**
- Modify: `src/tracker/routers/api.py` (добавить в конец файла, после строки 680)

- [ ] **Шаг 4.1: Добавить импорт MetricsCollector в начало api.py**

После строки `from src.core.auth import require_auth` добавить:

```python
from src.monitoring.collector import MetricsCollector, hours_to_bucket_secs
```

- [ ] **Шаг 4.2: Добавить endpoints в конец api.py**

```python
# ============================================================================
# ADMIN: SERVER METRICS
# ============================================================================

def _get_metrics_collector() -> MetricsCollector:
    """Ленивый импорт чтобы не создавать circular import."""
    import app as _app
    return _app.metrics_collector


@router.get("/api/admin/metrics", tags=["Admin"])
async def get_server_metrics(
    hours: int = Query(default=24, description="Диапазон: 1,6,24,168,720"),
    user=Depends(require_auth),
):
    """История метрик сервера с downsampling по диапазону."""
    import time
    if isinstance(user, RedirectResponse):
        return user
    allowed = {1, 6, 24, 168, 720}
    if hours not in allowed:
        hours = 24
    bucket_secs = hours_to_bucket_secs(hours)
    now = int(time.time())
    since = now - hours * 3600
    collector = _get_metrics_collector()
    points = await asyncio.get_event_loop().run_in_executor(
        None, collector.query, since, now, bucket_secs
    )
    return {
        "points": points,
        "meta": {
            "from_ts": since,
            "to_ts": now,
            "bucket_secs": bucket_secs,
            "hours": hours,
        },
    }


@router.get("/api/admin/metrics/live", tags=["Admin"])
async def get_server_metrics_live(
    request: Request,
    user=Depends(require_auth),
):
    """SSE-стрим: новая точка метрик каждые 5 секунд."""
    if isinstance(user, RedirectResponse):
        return user
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

    return EventSourceResponse(stream())
```

- [ ] **Шаг 4.3: Проверить синтаксис**

```
conda run -n base python -c "from src.tracker.routers.api import router; print('OK')"
```
Ожидаем: `OK`

- [ ] **Шаг 4.4: Коммит**

```bash
git add src/tracker/routers/api.py
git commit -m "feat: GET /api/admin/metrics + /api/admin/metrics/live (SSE)"
```

---

## Task 5: Страница /admin/server-metrics

**Files:**
- Modify: `src/tracker/routers/pages.py` (добавить в конец)

- [ ] **Шаг 5.1: Добавить route в pages.py**

В конец файла `src/tracker/routers/pages.py` добавить:

```python
@router.get("/admin/server-metrics", response_class=HTMLResponse)
async def server_metrics_page(
    request: Request,
    user=Depends(require_auth),
):
    """Дашборд реальной нагрузки на сервер."""
    if isinstance(user, RedirectResponse):
        return user
    return templates.TemplateResponse("server-metrics.html", {"request": request})
```

- [ ] **Шаг 5.2: Проверить синтаксис**

```
conda run -n base python -c "from src.tracker.routers.pages import router; print('OK')"
```
Ожидаем: `OK`

- [ ] **Шаг 5.3: Коммит**

```bash
git add src/tracker/routers/pages.py
git commit -m "feat: страница /admin/server-metrics (за авторизацией)"
```

---

## Task 6: Dashboard template

**Files:**
- Create: `templates/server-metrics.html`

- [ ] **Шаг 6.1: Создать шаблон**

```html
<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Мониторинг сервера · KM_track</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
:root{
  --bg:#0f1117;--surface:#181c27;--surface2:#1e2235;--border:#262b3d;
  --text:#e2e8f0;--muted:#7c87a0;--accent:#6366f1;
  --green:#22c55e;--red:#ef4444;--yellow:#f59e0b;--blue:#38bdf8;
}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);font-family:'Segoe UI',system-ui,sans-serif;font-size:13px}

.header{background:var(--surface);border-bottom:1px solid var(--border);padding:14px 24px;
  display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}
.header-left{display:flex;align-items:center;gap:12px}
.header-title{font-size:16px;font-weight:700}
.live-dot{width:8px;height:8px;border-radius:50%;background:var(--green);
  display:inline-block;margin-right:4px;animation:pulse 2s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}
.live-dot.dead{background:var(--muted);animation:none}
.live-label{font-size:11px;color:var(--muted)}
.btn-link{background:none;border:1px solid var(--border);color:var(--muted);
  padding:4px 12px;border-radius:5px;cursor:pointer;font-size:11px;text-decoration:none}
.btn-link:hover{color:var(--text);border-color:var(--muted)}

.main{padding:20px 24px;max-width:1400px;margin:0 auto}

/* KPI */
.kpi-row{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px;margin-bottom:20px}
.kpi{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:14px 16px}
.kpi .lbl{color:var(--muted);font-size:10px;text-transform:uppercase;letter-spacing:.06em;margin-bottom:4px}
.kpi .val{font-size:26px;font-weight:800;line-height:1.1}
.kpi .sub{color:var(--muted);font-size:11px;margin-top:3px}
.kpi.green .val{color:var(--green)}
.kpi.red .val{color:var(--red)}
.kpi.blue .val{color:var(--blue)}
.kpi.yellow .val{color:var(--yellow)}

/* Range controls */
.controls{display:flex;align-items:center;gap:8px;margin-bottom:16px;flex-wrap:wrap}
.controls label{color:var(--muted);font-size:11px}
.range-btn{background:var(--surface2);border:1px solid var(--border);color:var(--muted);
  padding:5px 14px;border-radius:5px;cursor:pointer;font-size:11px;font-weight:600;transition:.15s}
.range-btn:hover,.range-btn.active{background:var(--accent);border-color:var(--accent);color:#fff}

/* Charts */
.chart-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:20px}
@media(max-width:860px){.chart-grid{grid-template-columns:1fr}}
.chart-card{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:14px}
.chart-card h3{font-size:11px;font-weight:700;color:var(--muted);text-transform:uppercase;
  letter-spacing:.06em;margin-bottom:10px}
.chart-card.wide{grid-column:1/-1}

.footer-note{color:var(--muted);font-size:11px;text-align:center;padding:12px 0}
</style>
</head>
<body>

<div class="header">
  <div class="header-left">
    <div class="header-title">Мониторинг сервера · KM_track</div>
    <div>
      <span class="live-dot" id="liveDot"></span>
      <span class="live-label" id="liveLabel">live</span>
    </div>
  </div>
  <a class="btn-link" href="/logout">Выйти</a>
</div>

<div class="main">

  <!-- KPI -->
  <div class="kpi-row">
    <div class="kpi blue"><div class="lbl">IP сейчас</div><div class="val" id="kpiIp">—</div><div class="sub">уникальных адресов</div></div>
    <div class="kpi green"><div class="lbl">SSE соединений</div><div class="val" id="kpiSse">—</div><div class="sub">живых подключений</div></div>
    <div class="kpi"><div class="lbl">RPS (5с)</div><div class="val" id="kpiRps">—</div><div class="sub">запросов/сек</div></div>
    <div class="kpi"><div class="lbl">Среднее время</div><div class="val" id="kpiRt">—</div><div class="sub">мс</div></div>
    <div class="kpi" id="kpiErrCard"><div class="lbl">Ошибки (5с)</div><div class="val" id="kpiErr">—</div><div class="sub">4xx + 5xx</div></div>
  </div>

  <!-- Range selector -->
  <div class="controls">
    <label>Диапазон:</label>
    <button class="range-btn" data-h="1">1ч</button>
    <button class="range-btn" data-h="6">6ч</button>
    <button class="range-btn active" data-h="24">24ч</button>
    <button class="range-btn" data-h="168">7д</button>
    <button class="range-btn" data-h="720">30д</button>
  </div>

  <!-- Charts -->
  <div class="chart-grid">
    <div class="chart-card wide">
      <h3>Пользователи на сервере</h3>
      <canvas id="chartUsers" height="130"></canvas>
    </div>
    <div class="chart-card">
      <h3>Запросы в секунду (RPS) и ошибки</h3>
      <canvas id="chartRps" height="180"></canvas>
    </div>
    <div class="chart-card">
      <h3>Среднее время ответа сервера (мс)</h3>
      <canvas id="chartRt" height="180"></canvas>
    </div>
  </div>

  <div class="footer-note">Данные обновляются каждые 5 секунд · История 30 дней</div>
</div>

<script>
// ── конфиг Chart.js ────────────────────────────────────────────────────────
const SCALE_X = { ticks:{color:'#4a5568',maxTicksLimit:10,font:{size:10}}, grid:{color:'#1a1f30'} };
const SCALE_Y = lbl => ({
  ticks:{color:'#4a5568',font:{size:10}}, grid:{color:'#1a1f30'},
  title:{display:!!lbl,text:lbl,color:'#4a5568',font:{size:10}}, min:0
});

function mkChart(id, datasets, yLabel) {
  return new Chart(document.getElementById(id), {
    type:'line',
    data:{ labels:[], datasets },
    options:{
      responsive:true, animation:false,
      interaction:{mode:'index',intersect:false},
      plugins:{
        legend:{labels:{color:'#7c87a0',boxWidth:12,font:{size:10}}},
        tooltip:{
          callbacks:{
            title: items => {
              const d = new Date(items[0].label * 1000);
              return d.toLocaleString('ru-RU');
            }
          }
        }
      },
      scales:{ x:{...SCALE_X, ticks:{...SCALE_X.ticks, callback:(_,i,ticks)=>{
        const ts = ticks[i]?.value;
        if (!ts) return '';
        const d = new Date(ts*1000);
        return d.toLocaleTimeString('ru-RU',{hour:'2-digit',minute:'2-digit'});
      }}}, y:SCALE_Y(yLabel) }
    }
  });
}

// ── инициализация графиков ─────────────────────────────────────────────────
const chartUsers = mkChart('chartUsers', [
  {label:'Уникальные IP', data:[], borderColor:'#6366f1', backgroundColor:'rgba(99,102,241,.1)', fill:true, tension:.3, pointRadius:0},
  {label:'SSE соединения', data:[], borderColor:'#22c55e', backgroundColor:'rgba(34,197,94,.08)', fill:true, tension:.3, pointRadius:0},
], 'Пользователей');

const chartRps = mkChart('chartRps', [
  {label:'RPS', data:[], borderColor:'#38bdf8', backgroundColor:'rgba(56,189,248,.08)', fill:true, tension:.3, pointRadius:0},
  {label:'Ошибки/с', data:[], borderColor:'#ef4444', backgroundColor:'rgba(239,68,68,.08)', fill:true, tension:.3, pointRadius:0},
], 'Запросов / сек');

const chartRt = mkChart('chartRt', [
  {label:'Среднее время (мс)', data:[], borderColor:'#f59e0b', tension:.3, pointRadius:0, borderWidth:2},
], 'Мс');

// ── загрузка исторических данных ──────────────────────────────────────────
let currentHours = 24;

function setData(points) {
  const labels = points.map(p => p.ts);
  // bucket_secs для RPS
  const meta = window._lastMeta || {};
  const bSec = meta.bucket_secs || 5;

  chartUsers.data.labels = labels;
  chartUsers.data.datasets[0].data = points.map(p => p.unique_ips);
  chartUsers.data.datasets[1].data = points.map(p => p.sse_connections);
  chartUsers.update('none');

  chartRps.data.labels = labels;
  chartRps.data.datasets[0].data = points.map(p => +(p.total_requests / bSec).toFixed(2));
  chartRps.data.datasets[1].data = points.map(p => +(p.http_errors / bSec).toFixed(3));
  chartRps.update('none');

  chartRt.data.labels = labels;
  chartRt.data.datasets[0].data = points.map(p => p.avg_response_ms);
  chartRt.update('none');
}

function appendPoint(point) {
  const bSec = 5;
  const maxPoints = currentHours === 1 ? 720 : 500;

  [chartUsers, chartRps, chartRt].forEach(c => {
    c.data.labels.push(point.ts);
    if (c.data.labels.length > maxPoints) c.data.labels.shift();
  });

  const rps = +(point.total_requests / bSec).toFixed(2);
  const errS = +(point.http_errors / bSec).toFixed(3);

  chartUsers.data.datasets[0].data.push(point.unique_ips);
  chartUsers.data.datasets[1].data.push(point.sse_connections);
  chartRps.data.datasets[0].data.push(rps);
  chartRps.data.datasets[1].data.push(errS);
  chartRt.data.datasets[0].data.push(point.avg_response_ms);

  [chartUsers, chartRps, chartRt].forEach(c => {
    c.data.datasets.forEach(d => { if (d.data.length > maxPoints) d.data.shift(); });
    c.update('none');
  });
}

async function loadHistory(hours) {
  try {
    const res = await fetch(`/api/admin/metrics?hours=${hours}`);
    if (!res.ok) return;
    const json = await res.json();
    window._lastMeta = json.meta;
    setData(json.points);
  } catch(e) { console.error('loadHistory:', e); }
}

// ── range buttons ─────────────────────────────────────────────────────────
document.querySelectorAll('.range-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.range-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    currentHours = parseInt(btn.dataset.h);
    loadHistory(currentHours);
  });
});

// ── KPI обновление ────────────────────────────────────────────────────────
function updateKpi(point) {
  document.getElementById('kpiIp').textContent = point.unique_ips ?? '—';
  document.getElementById('kpiSse').textContent = point.sse_connections ?? '—';
  const bSec = 5;
  document.getElementById('kpiRps').textContent = point.total_requests
    ? (point.total_requests / bSec).toFixed(1) : '0';
  document.getElementById('kpiRt').textContent = point.avg_response_ms ?? '—';
  const err = point.http_errors || 0;
  document.getElementById('kpiErr').textContent = err;
  document.getElementById('kpiErrCard').className = 'kpi ' + (err > 0 ? 'red' : '');
}

// ── Live SSE ──────────────────────────────────────────────────────────────
function connectLive() {
  const dot = document.getElementById('liveDot');
  const label = document.getElementById('liveLabel');
  const es = new EventSource('/api/admin/metrics/live');

  es.onopen = () => {
    dot.classList.remove('dead');
    label.textContent = 'live';
  };
  es.onmessage = e => {
    try {
      const point = JSON.parse(e.data);
      appendPoint(point);
      updateKpi(point);
    } catch(_) {}
  };
  es.onerror = () => {
    dot.classList.add('dead');
    label.textContent = 'переподключение...';
    es.close();
    setTimeout(connectLive, 3000);
  };
}

// ── Старт ─────────────────────────────────────────────────────────────────
loadHistory(24);
connectLive();
</script>
</body>
</html>
```

- [ ] **Шаг 6.2: Коммит**

```bash
git add templates/server-metrics.html
git commit -m "feat: дашборд /admin/server-metrics — Chart.js + live SSE"
```

---

## Task 7: Деплой и smoke-проверка

- [ ] **Шаг 7.1: Запушить ветку**

```bash
git push origin Map
```

- [ ] **Шаг 7.2: Подождать деплой (≈70 сек), проверить статус**

```bash
python -c "
import paramiko, sys, time
client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect('89.108.88.104', username='root', password='shsfzw5fHiQY8v6g', timeout=15)
time.sleep(70)
stdin, stdout, stderr = client.exec_command('systemctl is-active km_track && git -C /opt/km_track log --oneline -1')
sys.stdout.buffer.write(stdout.read())
client.close()
"
```
Ожидаем: `active` + последний commit.

- [ ] **Шаг 7.3: Smoke-проверка endpoints**

```bash
python -c "
import paramiko, sys
client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect('89.108.88.104', username='root', password='shsfzw5fHiQY8v6g', timeout=15)
# Проверяем что API отвечает (без авторизации должно вернуть redirect)
stdin, stdout, stderr = client.exec_command(
    'curl -s -o /dev/null -w \"%{http_code}\" http://127.0.0.1:8000/api/admin/metrics'
)
code = stdout.read().decode().strip()
print('GET /api/admin/metrics без auth:', code)  # ожидаем 307 или 401
stdin, stdout, stderr = client.exec_command(
    'curl -s -o /dev/null -w \"%{http_code}\" http://127.0.0.1:8000/admin/server-metrics'
)
code = stdout.read().decode().strip()
print('GET /admin/server-metrics без auth:', code)  # ожидаем 307 или 200 (редирект на login)
client.close()
"
```

- [ ] **Шаг 7.4: Проверить SQLite создался на VPS**

```bash
python -c "
import paramiko, sys
client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect('89.108.88.104', username='root', password='shsfzw5fHiQY8v6g', timeout=15)
stdin, stdout, stderr = client.exec_command(
    'ls -lh /opt/km_track/data/server_metrics.db 2>/dev/null || echo NOT_FOUND'
)
sys.stdout.buffer.write(stdout.read())
# Подождать 10 секунд и проверить что появились строки
import time; time.sleep(10)
stdin, stdout, stderr = client.exec_command(
    'sqlite3 /opt/km_track/data/server_metrics.db \"SELECT COUNT(*) FROM metrics\"'
)
sys.stdout.buffer.write(stdout.read())
client.close()
"
```
Ожидаем: файл существует, COUNT > 0.

- [ ] **Шаг 7.5: Финальный коммит если всё OK**

```bash
git add .
git commit -m "chore: smoke-проверка пройдена — server metrics dashboard в проде"
```

---

## Self-review

**Spec coverage:**
- ✅ Уникальные IP — `record(ip=...)`, `_Bucket.ips: set`
- ✅ SSE-соединения — `tracker_hub.total_sse_count()` → `flush(sse_connections=...)`
- ✅ RPS и ошибки — `_Bucket.requests`, `_Bucket.errors`
- ✅ Время ответа — `_Bucket.total_ms`, weighted avg в SQL
- ✅ История 30 дней — `retention_days=30`, DELETE в flush
- ✅ Живые обновления — pub-sub очередь, `/api/admin/metrics/live` SSE
- ✅ Downsampling — `hours_to_bucket_secs()`, GROUP BY в `query()`
- ✅ Диапазоны 1ч/6ч/24ч/7д/30д — кнопки в HTML, параметр `hours` в API
- ✅ Авторизация — `Depends(require_auth)` на обоих endpoints и странице
- ✅ SQLite WAL — `PRAGMA journal_mode=WAL` в `_init_db`
- ✅ Multi-worker — `PRIMARY KEY (ts, worker_id)`, SUM в GROUP BY
- ✅ Ошибка SQLite не крашит приложение — try/except в `flush()` и `query()`
- ✅ `request.client is None` — `ip=request.client.host if request.client else None`

**Type consistency:**
- `MetricsCollector.flush(sse_connections: int)` — Task 1 defines, Task 3 calls ✅
- `MetricsCollector.subscribe() -> asyncio.Queue` — Task 1 defines, Task 4 calls ✅
- `MetricsCollector.unsubscribe(q)` — Task 1 defines, Task 4 calls ✅
- `hours_to_bucket_secs(hours: int) -> int` — Task 1 defines, Task 4 imports ✅
- `tracker_hub.total_sse_count()` — Task 2 defines, Task 3 calls ✅
- `collector._db_path` — используется в тестах Task 1 (атрибут задан в `__init__`) ✅

**Placeholder scan:** нет TBD, TODO, "implement later" — все шаги содержат готовый код.
