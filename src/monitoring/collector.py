import asyncio
import csv
import logging
import os
import platform
import sqlite3
import time
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

_log = logging.getLogger(__name__)

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


_ALERT_CPU_THRESHOLD = 70.0   # % CPU → пишем в файл тревог
_ALERT_LOAD_LABELS = {"Высокая", "Критическая"}


class MetricsCollector:
    def __init__(self, db_path: str, retention_days: int = 365):
        self._db_path = db_path
        self._alerts_path = Path(db_path).parent / "high_load_alerts.csv"
        self._retention_secs = retention_days * 86400
        self._worker_id = os.getpid()
        self._lock = threading.Lock()
        self._file_lock = threading.Lock()
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

        if load_label in _ALERT_LOAD_LABELS or cpu_pct >= _ALERT_CPU_THRESHOLD:
            self._write_alert(point, ram_pct)

        stale = set()
        for q in self._subscribers:
            try:
                q.put_nowait(point)
            except asyncio.QueueFull:
                stale.add(q)
        self._subscribers -= stale

    def _write_alert(self, point: dict, ram_pct: float) -> None:
        need_header = not self._alerts_path.exists() or self._alerts_path.stat().st_size == 0
        try:
            with self._file_lock:
                with open(self._alerts_path, "a", newline="", encoding="utf-8") as f:
                    w = csv.writer(f)
                    if need_header:
                        w.writerow([
                            "datetime", "ts", "worker_id",
                            "load_label", "load_score",
                            "cpu_pct", "ram_pct", "ram_used_mb", "ram_total_mb",
                            "sse_connections", "unique_ips",
                            "requests", "http_errors", "avg_ms",
                        ])
                    w.writerow([
                        datetime.fromtimestamp(point["ts"]).strftime("%Y-%m-%d %H:%M:%S"),
                        point["ts"],
                        self._worker_id,
                        point["load_label"],
                        point["load_score"],
                        point["cpu_percent"],
                        round(ram_pct, 1),
                        point["ram_used_mb"],
                        point["ram_total_mb"],
                        point["sse_connections"],
                        point["unique_ips"],
                        point["total_requests"],
                        point["http_errors"],
                        point["avg_response_ms"],
                    ])
        except Exception as e:
            _log.warning(f"MetricsCollector: alert write failed: {e}")

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
                    SUM(sse_connections)                   AS sse_connections,
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
