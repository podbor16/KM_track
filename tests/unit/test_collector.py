"""Unit-тесты MetricsCollector."""
import asyncio
import sys
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
