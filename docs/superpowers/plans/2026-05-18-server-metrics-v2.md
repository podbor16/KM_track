# Server Metrics Dashboard v2 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Расширить `/admin/server-metrics` — добавить CPU/RAM историю в SQLite, комбинированный индикатор нагрузки, 8 диапазонов (до 12 месяцев), flush 60с, авто-обновление раз в минуту.

**Architecture:** `collector.py` расширяется системными метриками (читает `/proc` на Linux), схема SQLite мигрируется через `ALTER TABLE ADD COLUMN` без потери данных. Flush-интервал меняется 5с → 60с во всём стеке. Frontend полностью переписывается: 8 KPI-карточек, 4 графика, countdown-таймер.

**Tech Stack:** Python stdlib `sqlite3`, `platform`, `/proc` filesystem; FastAPI; Chart.js 4.x (CDN); Vanilla JS.

---

## Карта файлов

| Файл | Статус | Что меняется |
|------|--------|-------------|
| `src/monitoring/collector.py` | Изменить | CPU/RAM чтение, load_score, новый downsampling, миграция схемы, flush retention 365д |
| `tests/unit/test_collector.py` | Изменить | Новые тесты + фикс INSERT в test_query_downsamples_multiple_buckets |
| `app.py` | Изменить | `sleep(5)` → `sleep(60)` в `_metrics_flusher` |
| `src/tracker/routers/api.py` | Изменить | Новые hours, uptime_secs в meta |
| `templates/server-metrics.html` | Перезаписать | 8 KPI, 4 графика, countdown, 8 кнопок |

---

## Task 1: Обновить collector.py — системные метрики, load_score, новая схема

**Files:**
- Modify: `src/monitoring/collector.py`
- Modify: `tests/unit/test_collector.py`

- [ ] **Шаг 1.1: Добавить новые тесты (перед изменением кода)**

Добавить в конец `tests/unit/test_collector.py`:

```python
from src.monitoring.collector import MetricsCollector, _load_score, hours_to_bucket_secs


class TestLoadScore:
    def test_low_score(self):
        score, label = _load_score(ram_pct=10.0, avg_ms=200.0, err_rate=0.0)
        assert label == "Низкая"
        assert score < 25

    def test_moderate_score(self):
        score, label = _load_score(ram_pct=50.0, avg_ms=800.0, err_rate=5.0)
        assert label == "Умеренная"

    def test_high_score(self):
        score, label = _load_score(ram_pct=70.0, avg_ms=2000.0, err_rate=10.0)
        assert label == "Высокая"

    def test_critical_score(self):
        score, label = _load_score(ram_pct=95.0, avg_ms=4000.0, err_rate=50.0)
        assert label == "Критическая"
        assert score >= 80

    def test_zero_inputs(self):
        score, label = _load_score(ram_pct=0.0, avg_ms=0.0, err_rate=0.0)
        assert score == 0.0
        assert label == "Низкая"


class TestHoursToBucketSecsV2:
    def test_1h(self):   assert hours_to_bucket_secs(1)    == 60
    def test_6h(self):   assert hours_to_bucket_secs(6)    == 300
    def test_24h(self):  assert hours_to_bucket_secs(24)   == 600
    def test_7d(self):   assert hours_to_bucket_secs(168)  == 3600
    def test_30d(self):  assert hours_to_bucket_secs(720)  == 7200
    def test_3m(self):   assert hours_to_bucket_secs(2160) == 21600
    def test_6m(self):   assert hours_to_bucket_secs(4320) == 43200
    def test_12m(self):  assert hours_to_bucket_secs(8760) == 86400


class TestSchemaMigration:
    def test_migration_adds_columns_to_existing_table(self, tmp_path):
        import sqlite3
        db_path = str(tmp_path / "old_metrics.db")
        con = sqlite3.connect(db_path)
        con.execute("""
            CREATE TABLE metrics (
                ts INTEGER NOT NULL, worker_id INTEGER NOT NULL,
                unique_ips INTEGER NOT NULL, total_requests INTEGER NOT NULL,
                http_errors INTEGER NOT NULL, total_response_ms REAL NOT NULL,
                sse_connections INTEGER NOT NULL,
                PRIMARY KEY (ts, worker_id)
            )
        """)
        con.execute(
            "INSERT INTO metrics VALUES (1000,1,5,10,0,500.0,2)"
        )
        con.commit()
        con.close()
        # Создание collector должно добавить столбцы
        MetricsCollector(db_path=db_path)
        con = sqlite3.connect(db_path)
        cols = [r[1] for r in con.execute("PRAGMA table_info(metrics)").fetchall()]
        con.close()
        assert "cpu_percent" in cols
        assert "ram_used_mb" in cols
        assert "ram_total_mb" in cols


class TestFlushSysMetrics:
    def test_flush_writes_sys_columns(self, collector, db_path):
        import sqlite3
        asyncio.run(collector.flush(sse_connections=0))
        con = sqlite3.connect(db_path)
        row = con.execute(
            "SELECT cpu_percent, ram_used_mb, ram_total_mb FROM metrics"
        ).fetchone()
        con.close()
        assert row is not None
        cpu, ram_used, ram_total = row
        assert isinstance(cpu, (int, float))
        assert isinstance(ram_used, int)
        assert isinstance(ram_total, int)

    def test_flush_point_has_load_fields(self, collector):
        async def _run():
            q = collector.subscribe()
            await collector.flush(sse_connections=0)
            point = await asyncio.wait_for(q.get(), timeout=1.0)
            collector.unsubscribe(q)
            return point
        point = asyncio.run(_run())
        assert "load_score" in point
        assert "load_label" in point
        assert "cpu_percent" in point
        assert "ram_used_mb" in point
        assert "ram_total_mb" in point


class TestQuerySysMetrics:
    def test_query_returns_sys_fields(self, collector):
        asyncio.run(collector.flush(sse_connections=0))
        import time
        now = int(time.time())
        result = collector.query(since_ts=now - 120, until_ts=now + 10, bucket_secs=60)
        assert len(result) == 1
        assert "cpu_percent" in result[0]
        assert "ram_used_mb" in result[0]
        assert "ram_total_mb" in result[0]
```

- [ ] **Шаг 1.2: Зафиксировать падающий тест `test_query_downsamples_multiple_buckets`**

Существующий тест использует `INSERT INTO metrics VALUES (?,?,?,?,?,?,?)` — 7 значений. После добавления 3 новых столбцов тест упадёт. Заменить в `test_collector.py` строку INSERT:

```python
# БЫЛО (строка 108-110):
        for i in range(3):
            con.execute(
                "INSERT INTO metrics VALUES (?,?,?,?,?,?,?)",
                (now - 30 + i*5, worker_id, 5, 10, 0, 1000.0, 3)
            )

# СТАЛО:
        for i in range(3):
            con.execute(
                """INSERT INTO metrics
                   (ts, worker_id, unique_ips, total_requests, http_errors,
                    total_response_ms, sse_connections)
                   VALUES (?,?,?,?,?,?,?)""",
                (now - 30 + i*5, worker_id, 5, 10, 0, 1000.0, 3)
            )
```

- [ ] **Шаг 1.3: Запустить тесты — убедиться что новые FAIL, старые PASS**

```
conda run -n base python -m pytest tests/unit/test_collector.py -v
```
Ожидаем: старые 11 тестов PASS, новые классы (`TestLoadScore`, `TestHoursToBucketSecsV2`, `TestSchemaMigration`, `TestFlushSysMetrics`, `TestQuerySysMetrics`) — FAIL с `ImportError: cannot import name '_load_score'`.

- [ ] **Шаг 1.4: Полностью переписать `src/monitoring/collector.py`**

```python
import asyncio
import os
import platform
import sqlite3
import time
import threading
from dataclasses import dataclass, field
from pathlib import Path

_IS_LINUX = platform.system() == "Linux"


@dataclass
class _Bucket:
    ips: set = field(default_factory=set)
    requests: int = 0
    errors: int = 0
    total_ms: float = 0.0


_HOURS_TO_BUCKET_SECS = {
    1:    60,
    6:    300,
    24:   600,
    168:  3600,
    720:  7200,
    2160: 21600,
    4320: 43200,
    8760: 86400,
}


def hours_to_bucket_secs(hours: int) -> int:
    for h, b in sorted(_HOURS_TO_BUCKET_SECS.items()):
        if hours <= h:
            return b
    return 86400


def _read_ram() -> tuple[int, int]:
    """Возвращает (used_mb, total_mb) из /proc/meminfo."""
    info: dict[str, int] = {}
    with open("/proc/meminfo") as f:
        for line in f:
            parts = line.split(":")
            if len(parts) == 2:
                info[parts[0].strip()] = int(parts[1].split()[0])
    total = info.get("MemTotal", 0)
    available = info.get("MemAvailable", info.get("MemFree", 0))
    return (total - available) // 1024, total // 1024


def _read_cpu_stat() -> tuple[int, int]:
    """Возвращает (idle_jiffies, total_jiffies) из /proc/stat."""
    with open("/proc/stat") as f:
        line = f.readline()
    vals = [int(x) for x in line.split()[1:8]]
    idle = vals[3] + vals[4]   # idle + iowait
    return idle, sum(vals)


def _read_uptime_secs() -> int:
    with open("/proc/uptime") as f:
        return int(float(f.read().split()[0]))


def _load_score(ram_pct: float, avg_ms: float, err_rate: float) -> tuple[float, str]:
    """Возвращает (score 0-100, label). Вес: RAM 40%, RT 40%, ошибки 20%."""
    if avg_ms < 500:      rt = 0.0
    elif avg_ms < 1500:   rt = 35.0
    elif avg_ms < 3000:   rt = 70.0
    else:                 rt = 100.0
    score = ram_pct * 0.4 + rt * 0.4 + err_rate * 0.2
    if score < 25:    label = "Низкая"
    elif score < 55:  label = "Умеренная"
    elif score < 80:  label = "Высокая"
    else:             label = "Критическая"
    return round(score, 1), label


class MetricsCollector:
    def __init__(self, db_path: str, retention_days: int = 365):
        self._db_path = db_path
        self._retention_secs = retention_days * 86400
        self._worker_id = os.getpid()
        self._lock = threading.Lock()
        self._bucket = _Bucket()
        self._subscribers: set[asyncio.Queue] = set()
        self._last_point: dict = {}
        self._prev_cpu: tuple[int, int] | None = None
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
                    cpu_percent       REAL    DEFAULT 0,
                    ram_used_mb       INTEGER DEFAULT 0,
                    ram_total_mb      INTEGER DEFAULT 0,
                    PRIMARY KEY (ts, worker_id)
                )
            """)
            con.execute("CREATE INDEX IF NOT EXISTS idx_metrics_ts ON metrics(ts)")
            # Миграция существующих таблиц без новых столбцов
            for col, typedef in [
                ("cpu_percent", "REAL DEFAULT 0"),
                ("ram_used_mb", "INTEGER DEFAULT 0"),
                ("ram_total_mb", "INTEGER DEFAULT 0"),
            ]:
                try:
                    con.execute(f"ALTER TABLE metrics ADD COLUMN {col} {typedef}")
                except sqlite3.OperationalError:
                    pass  # столбец уже существует
            con.commit()
            con.close()
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"MetricsCollector: DB init failed: {e}")

    def record(self, ip: str | None, duration_ms: float, status: int) -> None:
        with self._lock:
            if ip:
                self._bucket.ips.add(ip)
            self._bucket.requests += 1
            if status >= 400:
                self._bucket.errors += 1
            self._bucket.total_ms += duration_ms

    async def flush(self, sse_connections: int) -> None:
        with self._lock:
            bucket = self._bucket
            self._bucket = _Bucket()

        ts = int(time.time())
        unique_ips = len(bucket.ips)
        total_req = bucket.requests
        errors = bucket.errors
        total_ms = bucket.total_ms
        avg_ms = (total_ms / total_req) if total_req else 0.0

        # Системные метрики (только Linux)
        cpu_pct = 0.0
        ram_used_mb = 0
        ram_total_mb = 0
        if _IS_LINUX:
            try:
                idle_now, total_now = _read_cpu_stat()
                if self._prev_cpu:
                    idle_prev, total_prev = self._prev_cpu
                    dt = total_now - total_prev
                    cpu_pct = (1 - (idle_now - idle_prev) / dt) * 100 if dt else 0.0
                self._prev_cpu = (idle_now, total_now)
            except Exception:
                pass
            try:
                ram_used_mb, ram_total_mb = _read_ram()
            except Exception:
                pass

        try:
            con = sqlite3.connect(self._db_path)
            con.execute("PRAGMA journal_mode=WAL")
            con.execute(
                "INSERT OR REPLACE INTO metrics VALUES (?,?,?,?,?,?,?,?,?,?)",
                (ts, self._worker_id, unique_ips, total_req, errors, total_ms,
                 sse_connections, round(cpu_pct, 2), ram_used_mb, ram_total_mb),
            )
            con.execute("DELETE FROM metrics WHERE ts < ?", (ts - self._retention_secs,))
            con.commit()
            con.close()
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"MetricsCollector: flush write failed: {e}")

        ram_pct = (ram_used_mb / ram_total_mb * 100) if ram_total_mb else 0.0
        err_rate = (errors / total_req * 100) if total_req else 0.0
        load_score, load_label = _load_score(ram_pct, avg_ms, err_rate)

        point = {
            "ts": ts,
            "unique_ips": unique_ips,
            "total_requests": total_req,
            "http_errors": errors,
            "avg_response_ms": round(avg_ms, 1),
            "sse_connections": sse_connections,
            "cpu_percent": round(cpu_pct, 1),
            "ram_used_mb": ram_used_mb,
            "ram_total_mb": ram_total_mb,
            "load_score": load_score,
            "load_label": load_label,
        }
        self._last_point = point

        stale = set()
        for q in self._subscribers:
            try:
                q.put_nowait(point)
            except asyncio.QueueFull:
                stale.add(q)
        self._subscribers -= stale

    def query(self, since_ts: int, until_ts: int, bucket_secs: int) -> list[dict]:
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
                    CAST(AVG(sse_connections) AS INTEGER)  AS sse_connections,
                    ROUND(AVG(cpu_percent), 1)             AS cpu_percent,
                    CAST(AVG(ram_used_mb) AS INTEGER)      AS ram_used_mb,
                    CAST(AVG(ram_total_mb) AS INTEGER)     AS ram_total_mb
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
                    "cpu_percent": r[6] or 0.0,
                    "ram_used_mb": r[7] or 0,
                    "ram_total_mb": r[8] or 0,
                }
                for r in rows
            ]
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"MetricsCollector: query failed: {e}")
            return []

    def current_snapshot(self) -> dict:
        with self._lock:
            b = self._bucket
            snap = {
                "unique_ips": len(b.ips),
                "total_requests": b.requests,
                "http_errors": b.errors,
                "avg_response_ms": round(b.total_ms / b.requests, 1) if b.requests else 0.0,
            }
        lp = self._last_point
        snap["cpu_percent"] = lp.get("cpu_percent", 0.0)
        snap["ram_used_mb"] = lp.get("ram_used_mb", 0)
        snap["ram_total_mb"] = lp.get("ram_total_mb", 0)
        ram_pct = (snap["ram_used_mb"] / snap["ram_total_mb"] * 100) if snap["ram_total_mb"] else 0.0
        err_rate = (snap["http_errors"] / snap["total_requests"] * 100) if snap["total_requests"] else 0.0
        snap["load_score"], snap["load_label"] = _load_score(ram_pct, snap["avg_response_ms"], err_rate)
        return snap

    def get_uptime_secs(self) -> int:
        if not _IS_LINUX:
            return 0
        try:
            return _read_uptime_secs()
        except Exception:
            return 0

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=10)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subscribers.discard(q)
```

- [ ] **Шаг 1.5: Запустить все тесты — убедиться что PASS**

```
conda run -n base python -m pytest tests/unit/test_collector.py -v
```
Ожидаем: все тесты PASSED (11 старых + ~14 новых).

- [ ] **Шаг 1.6: Коммит**

```bash
git add src/monitoring/collector.py tests/unit/test_collector.py
git commit -m "feat: collector v2 — CPU/RAM /proc, load_score, 365д retention, 8 диапазонов"
```

---

## Task 2: app.py — изменить интервал flush 5с → 60с

**Files:**
- Modify: `app.py` (строка с `await asyncio.sleep(5)` внутри `_metrics_flusher`)

- [ ] **Шаг 2.1: Изменить sleep в `_metrics_flusher`**

Найти в `app.py`:
```python
    async def _metrics_flusher():
        """Каждые 5с снимает bucket метрик и пишет в SQLite."""
        while True:
            await asyncio.sleep(5)
            sse_count = tracker_hub.total_sse_count()
            await metrics_collector.flush(sse_connections=sse_count)
```

Заменить на:
```python
    async def _metrics_flusher():
        """Каждые 60с снимает bucket метрик и пишет в SQLite."""
        while True:
            await asyncio.sleep(60)
            sse_count = tracker_hub.total_sse_count()
            await metrics_collector.flush(sse_connections=sse_count)
```

- [ ] **Шаг 2.2: Проверить синтаксис**

```
conda run -n base python -c "import app; print('OK')"
```
Ожидаем: `OK`

- [ ] **Шаг 2.3: Коммит**

```bash
git add app.py
git commit -m "feat: flush interval 5s → 60s"
```

---

## Task 3: api.py — новые диапазоны и uptime в ответе

**Files:**
- Modify: `src/tracker/routers/api.py` (функция `get_server_metrics` в разделе ADMIN: SERVER METRICS)

- [ ] **Шаг 3.1: Обновить endpoint `get_server_metrics`**

Найти в `src/tracker/routers/api.py`:

```python
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
```

Заменить на:

```python
@router.get("/api/admin/metrics", tags=["Admin"])
async def get_server_metrics(
    hours: int = Query(default=24, description="Диапазон: 1,6,24,168,720,2160,4320,8760"),
    user=Depends(require_auth),
):
    """История метрик сервера с downsampling по диапазону."""
    import time
    if isinstance(user, RedirectResponse):
        return user
    allowed = {1, 6, 24, 168, 720, 2160, 4320, 8760}
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
            "uptime_secs": collector.get_uptime_secs(),
        },
    }
```

- [ ] **Шаг 3.2: Проверить синтаксис**

```
conda run -n base python -c "from src.tracker.routers.api import router; print('OK')"
```
Ожидаем: `OK`

- [ ] **Шаг 3.3: Коммит**

```bash
git add src/tracker/routers/api.py
git commit -m "feat: /api/admin/metrics — 8 диапазонов + uptime_secs в meta"
```

---

## Task 4: Переписать templates/server-metrics.html

**Files:**
- Overwrite: `templates/server-metrics.html`

- [ ] **Шаг 4.1: Перезаписать шаблон**

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
  --green:#22c55e;--red:#ef4444;--yellow:#f59e0b;--blue:#38bdf8;--orange:#f97316;
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
.live-status{font-size:11px;color:var(--muted)}
.btn-link{background:none;border:1px solid var(--border);color:var(--muted);
  padding:4px 12px;border-radius:5px;cursor:pointer;font-size:11px;text-decoration:none}
.btn-link:hover{color:var(--text);border-color:var(--muted)}

.main{padding:20px 24px;max-width:1400px;margin:0 auto}

.kpi-row{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:10px}
@media(max-width:900px){.kpi-row{grid-template-columns:repeat(2,1fr)}}
.kpi{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:14px 16px;
  transition:border-color .4s,box-shadow .4s}
.kpi .lbl{color:var(--muted);font-size:10px;text-transform:uppercase;letter-spacing:.06em;margin-bottom:4px}
.kpi .val{font-size:26px;font-weight:800;line-height:1.1}
.kpi .sub{color:var(--muted);font-size:11px;margin-top:3px}
.kpi.blue .val{color:var(--blue)}
.kpi.green .val{color:var(--green)}
.kpi.orange .val{color:var(--orange)}

#kpiLoad{border-width:2px}
#kpiLoadVal{font-size:20px;font-weight:800}

.controls{display:flex;align-items:center;gap:6px;margin:14px 0;flex-wrap:wrap}
.controls label{color:var(--muted);font-size:11px}
.range-btn{background:var(--surface2);border:1px solid var(--border);color:var(--muted);
  padding:5px 11px;border-radius:5px;cursor:pointer;font-size:11px;font-weight:600;transition:.15s}
.range-btn:hover,.range-btn.active{background:var(--accent);border-color:var(--accent);color:#fff}

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
      <span class="live-status">
        <span id="liveLabel">live</span>
        · <span id="countdownLabel">обновление через 60с</span>
      </span>
    </div>
  </div>
  <a class="btn-link" href="/logout">Выйти</a>
</div>

<div class="main">

  <!-- KPI ряд 1 -->
  <div class="kpi-row">
    <div class="kpi" id="kpiLoad">
      <div class="lbl">Нагрузка</div>
      <div class="val" id="kpiLoadVal">—</div>
      <div class="sub" id="kpiLoadSub">score: —</div>
    </div>
    <div class="kpi blue">
      <div class="lbl">IP сейчас</div>
      <div class="val" id="kpiIp">—</div>
      <div class="sub">уникальных адресов</div>
    </div>
    <div class="kpi green">
      <div class="lbl">SSE соединений</div>
      <div class="val" id="kpiSse">—</div>
      <div class="sub">живых подключений</div>
    </div>
    <div class="kpi">
      <div class="lbl">RPS (1мин)</div>
      <div class="val" id="kpiRps">—</div>
      <div class="sub">запросов/сек</div>
    </div>
  </div>

  <!-- KPI ряд 2 -->
  <div class="kpi-row">
    <div class="kpi orange">
      <div class="lbl">RAM</div>
      <div class="val" id="kpiRam">—</div>
      <div class="sub" id="kpiRamSub">МБ / —</div>
    </div>
    <div class="kpi blue">
      <div class="lbl">CPU</div>
      <div class="val" id="kpiCpu">—</div>
      <div class="sub">загрузка ядра</div>
    </div>
    <div class="kpi">
      <div class="lbl">Среднее время</div>
      <div class="val" id="kpiRt">—</div>
      <div class="sub">мс</div>
    </div>
    <div class="kpi" id="kpiErrCard">
      <div class="lbl">Ошибки (1мин)</div>
      <div class="val" id="kpiErr">—</div>
      <div class="sub">4xx + 5xx</div>
    </div>
  </div>

  <!-- Диапазон -->
  <div class="controls">
    <label>Диапазон:</label>
    <button class="range-btn" data-h="1">1ч</button>
    <button class="range-btn" data-h="6">6ч</button>
    <button class="range-btn active" data-h="24">24ч</button>
    <button class="range-btn" data-h="168">7д</button>
    <button class="range-btn" data-h="720">30д</button>
    <button class="range-btn" data-h="2160">3м</button>
    <button class="range-btn" data-h="4320">6м</button>
    <button class="range-btn" data-h="8760">12м</button>
  </div>

  <!-- Графики -->
  <div class="chart-grid">
    <div class="chart-card wide">
      <h3>Пользователи на сервере</h3>
      <canvas id="chartUsers" height="110"></canvas>
    </div>
    <div class="chart-card">
      <h3>RAM % и CPU %</h3>
      <canvas id="chartSys" height="180"></canvas>
    </div>
    <div class="chart-card">
      <h3>Запросы в секунду (RPS) и ошибки</h3>
      <canvas id="chartRps" height="180"></canvas>
    </div>
    <div class="chart-card wide">
      <h3>Среднее время ответа сервера (мс)</h3>
      <canvas id="chartRt" height="110"></canvas>
    </div>
  </div>

  <div class="footer-note" id="footerNote">
    Данные обновляются каждую минуту · История 1 год
  </div>
</div>

<script>
// ── Chart.js helpers ──────────────────────────────────────────────────────────
const SCALE_X = {
  ticks:{color:'#4a5568',maxTicksLimit:10,font:{size:10}},
  grid:{color:'#1a1f30'}
};
const mkY = (lbl, max) => ({
  ticks:{color:'#4a5568',font:{size:10}},
  grid:{color:'#1a1f30'},
  title:{display:!!lbl,text:lbl,color:'#4a5568',font:{size:10}},
  min:0,
  ...(max != null ? {max} : {}),
});

function mkChart(id, datasets, yLabel, yMax) {
  return new Chart(document.getElementById(id), {
    type:'line',
    data:{labels:[], datasets},
    options:{
      responsive:true, animation:false,
      interaction:{mode:'index',intersect:false},
      plugins:{
        legend:{labels:{color:'#7c87a0',boxWidth:12,font:{size:10}}},
        tooltip:{callbacks:{title: items => {
          return new Date(items[0].label * 1000).toLocaleString('ru-RU');
        }}},
      },
      scales:{
        x:{...SCALE_X, ticks:{...SCALE_X.ticks, callback:(_,i,ticks)=>{
          const ts = ticks[i]?.value;
          if (!ts) return '';
          return new Date(ts*1000).toLocaleTimeString('ru-RU',{hour:'2-digit',minute:'2-digit'});
        }}},
        y: mkY(yLabel, yMax),
      },
    },
  });
}

// ── Chart instances ───────────────────────────────────────────────────────────
const chartUsers = mkChart('chartUsers', [
  {label:'Уникальные IP',  data:[], borderColor:'#6366f1', backgroundColor:'rgba(99,102,241,.1)', fill:true, tension:.3, pointRadius:0},
  {label:'SSE соединения', data:[], borderColor:'#22c55e', backgroundColor:'rgba(34,197,94,.08)', fill:true, tension:.3, pointRadius:0},
], 'Пользователей');

const chartSys = mkChart('chartSys', [
  {label:'RAM %', data:[], borderColor:'#f97316', tension:.3, pointRadius:0, borderWidth:2},
  {label:'CPU %', data:[], borderColor:'#38bdf8', tension:.3, pointRadius:0, borderWidth:2},
], '%', 100);

const chartRps = mkChart('chartRps', [
  {label:'RPS',       data:[], borderColor:'#38bdf8', backgroundColor:'rgba(56,189,248,.08)', fill:true, tension:.3, pointRadius:0},
  {label:'Ошибки/с', data:[], borderColor:'#ef4444', backgroundColor:'rgba(239,68,68,.08)',   fill:true, tension:.3, pointRadius:0},
], 'Запросов / сек');

const chartRt = mkChart('chartRt', [
  {label:'Среднее время (мс)', data:[], borderColor:'#f59e0b', tension:.3, pointRadius:0, borderWidth:2},
], 'Мс');

const ALL_CHARTS = [chartUsers, chartSys, chartRps, chartRt];

// ── State ─────────────────────────────────────────────────────────────────────
let currentHours = 24;
let countdown = 60;
let countdownInterval = null;

// ── Load badge ────────────────────────────────────────────────────────────────
const LOAD_COLORS = {
  'Низкая':      '#22c55e',
  'Умеренная':   '#f59e0b',
  'Высокая':     '#f97316',
  'Критическая': '#ef4444',
};

function updateLoadBadge(label, score) {
  const color = LOAD_COLORS[label] || '#7c87a0';
  const card = document.getElementById('kpiLoad');
  card.style.borderColor = color;
  card.style.boxShadow = `0 0 12px ${color}33`;
  document.getElementById('kpiLoadVal').style.color = color;
  document.getElementById('kpiLoadVal').textContent = label || '—';
  document.getElementById('kpiLoadSub').textContent =
    score != null ? `score: ${score}%` : 'score: —';
}

// ── Client-side load score (для исторических точек без load_label) ────────────
function computeLoad(ramPct, avgMs, errRate) {
  const rt = avgMs < 500 ? 0 : avgMs < 1500 ? 35 : avgMs < 3000 ? 70 : 100;
  const s = ramPct * 0.4 + rt * 0.4 + errRate * 0.2;
  const label = s < 25 ? 'Низкая' : s < 55 ? 'Умеренная' : s < 80 ? 'Высокая' : 'Критическая';
  return {score: Math.round(s * 10) / 10, label};
}

function ramPct(used, total) {
  return total > 0 ? Math.round(used / total * 100) : 0;
}

// ── KPI update ────────────────────────────────────────────────────────────────
function updateKpi(point, bucketSecs) {
  const b = bucketSecs || 60;
  const rp = ramPct(point.ram_used_mb, point.ram_total_mb);
  const errRate = point.total_requests > 0
    ? (point.http_errors / point.total_requests * 100) : 0;

  if (point.load_label != null) {
    updateLoadBadge(point.load_label, point.load_score);
  } else {
    const {score, label} = computeLoad(rp, point.avg_response_ms || 0, errRate);
    updateLoadBadge(label, score);
  }

  document.getElementById('kpiIp').textContent  = point.unique_ips ?? '—';
  document.getElementById('kpiSse').textContent = point.sse_connections ?? '—';
  document.getElementById('kpiRps').textContent = point.total_requests
    ? (point.total_requests / b).toFixed(1) : '0';
  document.getElementById('kpiRam').textContent    = rp ? `${rp}%` : '—';
  document.getElementById('kpiRamSub').textContent = point.ram_total_mb
    ? `${point.ram_used_mb} / ${point.ram_total_mb} МБ` : 'МБ / —';
  document.getElementById('kpiCpu').textContent = point.cpu_percent != null
    ? `${(+point.cpu_percent).toFixed(1)}%` : '—';
  document.getElementById('kpiRt').textContent = point.avg_response_ms ?? '—';
  const err = point.http_errors || 0;
  document.getElementById('kpiErr').textContent = err;
  document.getElementById('kpiErrCard').style.setProperty(
    '--err-color', err > 0 ? 'var(--red)' : ''
  );
  document.getElementById('kpiErr').style.color = err > 0 ? 'var(--red)' : '';
}

// ── Chart data ────────────────────────────────────────────────────────────────
function setData(points, bucketSecs) {
  const b = bucketSecs || 60;
  const labels = points.map(p => p.ts);

  chartUsers.data.labels = labels;
  chartUsers.data.datasets[0].data = points.map(p => p.unique_ips);
  chartUsers.data.datasets[1].data = points.map(p => p.sse_connections);

  chartSys.data.labels = labels;
  chartSys.data.datasets[0].data = points.map(p => ramPct(p.ram_used_mb, p.ram_total_mb));
  chartSys.data.datasets[1].data = points.map(p => p.cpu_percent ?? 0);

  chartRps.data.labels = labels;
  chartRps.data.datasets[0].data = points.map(p => +(p.total_requests / b).toFixed(2));
  chartRps.data.datasets[1].data = points.map(p => +(p.http_errors / b).toFixed(3));

  chartRt.data.labels = labels;
  chartRt.data.datasets[0].data = points.map(p => p.avg_response_ms);

  ALL_CHARTS.forEach(c => c.update('none'));
}

function appendPoint(point) {
  const b = 60;
  const maxPts = 500;

  ALL_CHARTS.forEach(c => {
    c.data.labels.push(point.ts);
    if (c.data.labels.length > maxPts) c.data.labels.shift();
  });

  chartUsers.data.datasets[0].data.push(point.unique_ips);
  chartUsers.data.datasets[1].data.push(point.sse_connections);
  chartSys.data.datasets[0].data.push(ramPct(point.ram_used_mb, point.ram_total_mb));
  chartSys.data.datasets[1].data.push(point.cpu_percent ?? 0);
  chartRps.data.datasets[0].data.push(+(point.total_requests / b).toFixed(2));
  chartRps.data.datasets[1].data.push(+(point.http_errors / b).toFixed(3));
  chartRt.data.datasets[0].data.push(point.avg_response_ms);

  ALL_CHARTS.forEach(c => {
    c.data.datasets.forEach(d => { if (d.data.length > maxPts) d.data.shift(); });
    c.update('none');
  });
}

// ── History ───────────────────────────────────────────────────────────────────
function formatUptime(secs) {
  const d = Math.floor(secs / 86400);
  const h = Math.floor((secs % 86400) / 3600);
  const m = Math.floor((secs % 3600) / 60);
  if (d > 0) return `${d}д ${h}ч ${m}м`;
  if (h > 0) return `${h}ч ${m}м`;
  return `${m}м`;
}

async function loadHistory(hours) {
  try {
    const res = await fetch(`/api/admin/metrics?hours=${hours}`);
    if (!res.ok) return;
    const json = await res.json();
    setData(json.points, json.meta.bucket_secs);
    if (json.points.length > 0) {
      updateKpi(json.points[json.points.length - 1], json.meta.bucket_secs);
    }
    if (json.meta.uptime_secs) {
      document.getElementById('footerNote').textContent =
        `Данные обновляются каждую минуту · Аптайм: ${formatUptime(json.meta.uptime_secs)} · История 1 год`;
    }
  } catch(e) { console.error('loadHistory:', e); }
}

// ── Range buttons ─────────────────────────────────────────────────────────────
document.querySelectorAll('.range-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.range-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    currentHours = parseInt(btn.dataset.h);
    startCountdown();
    loadHistory(currentHours);
  });
});

// ── Countdown ─────────────────────────────────────────────────────────────────
function startCountdown() {
  clearInterval(countdownInterval);
  countdown = 60;
  document.getElementById('countdownLabel').textContent = `обновление через ${countdown}с`;
  countdownInterval = setInterval(() => {
    countdown--;
    document.getElementById('countdownLabel').textContent = `обновление через ${countdown}с`;
    if (countdown <= 0) {
      countdown = 60;
      loadHistory(currentHours);
    }
  }, 1000);
}

// ── Live SSE ──────────────────────────────────────────────────────────────────
function connectLive() {
  const dot   = document.getElementById('liveDot');
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
      updateKpi(point, 60);
      countdown = 60;  // синхронизируем countdown с сервером
    } catch(_) {}
  };
  es.onerror = () => {
    dot.classList.add('dead');
    label.textContent = 'переподключение...';
    es.close();
    setTimeout(connectLive, 3000);
  };
}

// ── Init ──────────────────────────────────────────────────────────────────────
loadHistory(24);
startCountdown();
connectLive();
</script>
</body>
</html>
```

- [ ] **Шаг 4.2: Проверить синтаксис приложения**

```
conda run -n base python -c "import app; print('OK')"
```
Ожидаем: `OK`

- [ ] **Шаг 4.3: Прогнать все тесты**

```
conda run -n base python -m pytest tests/unit/test_collector.py -v
```
Ожидаем: все тесты PASSED.

- [ ] **Шаг 4.4: Коммит**

```bash
git add templates/server-metrics.html
git commit -m "feat: server-metrics dashboard v2 — 8 KPI, 4 графика, countdown, load badge"
```

---

## Task 5: Деплой и проверка

- [ ] **Шаг 5.1: Запушить**

```bash
git push origin Map
```

- [ ] **Шаг 5.2: Деплой на VPS**

```bash
python deploy/ssh_update.py
```

- [ ] **Шаг 5.3: Подождать первый flush (60с) и проверить данные в SQLite**

```python
import paramiko, time
client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect('89.108.88.104', username='root', password='shsfzw5fHiQY8v6g', timeout=15)
time.sleep(75)  # ждём первый flush
_, stdout, _ = client.exec_command(
    'python3 -c "import sqlite3; c=sqlite3.connect(\'/opt/km_track/data/server_metrics.db\'); '
    'r=c.execute(\'SELECT ts, cpu_percent, ram_used_mb, ram_total_mb FROM metrics ORDER BY ts DESC LIMIT 3\').fetchall(); print(r)"'
)
print(stdout.read().decode())
client.close()
```
Ожидаем: 3 строки с ненулевыми `ram_used_mb` и `ram_total_mb`.

- [ ] **Шаг 5.4: Проверить endpoint через curl**

```python
import paramiko
client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect('89.108.88.104', username='root', password='shsfzw5fHiQY8v6g', timeout=15)
_, stdout, _ = client.exec_command(
    'curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/api/admin/metrics?hours=8760'
)
print('hours=8760 без auth:', stdout.read().decode())
_, stdout, _ = client.exec_command(
    'curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/admin/server-metrics'
)
print('page без auth:', stdout.read().decode())
client.close()
```
Ожидаем: оба `302` (редирект на логин).

---

## Self-review

**Spec coverage:**
- ✅ CPU % из `/proc/stat` — `_read_cpu_stat()`, дельта в `flush()`
- ✅ RAM % из `/proc/meminfo` — `_read_ram()`
- ✅ Fallback для не-Linux — `_IS_LINUX` + `platform.system()`
- ✅ Load score (RAM 40% + RT 40% + err 20%) — `_load_score()`
- ✅ 4 уровня нагрузки — "Низкая" / "Умеренная" / "Высокая" / "Критическая"
- ✅ Retention 365 дней — `retention_days=365` default
- ✅ Flush 60с — Task 2 меняет `sleep(5)` → `sleep(60)` в `app.py`
- ✅ 8 диапазонов — `_HOURS_TO_BUCKET_SECS` + `allowed` set в API
- ✅ Countdown 60с — `startCountdown()` с `setInterval(1000)`
- ✅ Авто-ребилд при countdown=0 — `loadHistory(currentHours)`
- ✅ SSE синхронизирует countdown — `countdown = 60` в `es.onmessage`
- ✅ Миграция существующей таблицы — `ALTER TABLE ADD COLUMN` с try/except
- ✅ Аптайм в footer — `get_uptime_secs()` → `meta.uptime_secs` → `formatUptime()`
- ✅ load_score вычисляется на клиенте для исторических точек — `computeLoad()`
- ✅ RAM% для исторических точек — `ramPct(used, total)` из `ram_used_mb / ram_total_mb`
- ✅ 4 графика: Users, Sys (RAM/CPU), RPS, RT

**Type consistency:**
- `_load_score(ram_pct, avg_ms, err_rate)` → Task 1 defines, tests call ✅
- `hours_to_bucket_secs(hours)` → Task 1 redefines, Task 3 uses (через import) ✅
- `collector.get_uptime_secs()` → Task 1 defines, Task 3 calls ✅
- `flush()` → `(ts, worker_id, ..., cpu_percent, ram_used_mb, ram_total_mb)` 10 полей = 10 `?` в INSERT ✅
- `query()` → возвращает 9 полей в dict, включая `cpu_percent`, `ram_used_mb`, `ram_total_mb` ✅
- Frontend `updateKpi(point, bucketSecs)` → принимает как SSE-точки (с `load_label`), так и исторические (без) ✅

**Placeholder scan:** нет TBD, TODO или незавершённых шагов — весь код приведён полностью.
