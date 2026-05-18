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
