"""Unit-тесты MetricsCollector."""
import asyncio
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest
from src.monitoring.collector import MetricsCollector, _load_score, hours_to_bucket_secs


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
        import sqlite3, time
        now = int(time.time())
        worker_id = os.getpid()
        con = sqlite3.connect(collector._db_path)
        for i in range(3):
            con.execute(
                """INSERT INTO metrics
                   (ts, worker_id, unique_ips, total_requests, http_errors,
                    total_response_ms, sse_connections)
                   VALUES (?,?,?,?,?,?,?)""",
                (now - 30 + i*5, worker_id, 5, 10, 0, 1000.0, 3)
            )
        con.commit()
        con.close()
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
        con.execute("INSERT INTO metrics VALUES (1000,1,5,10,0,500.0,2)")
        con.commit()
        con.close()
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
