import mysql.connector
import pytest

from src.siberman.hall import service


@pytest.fixture
def clock(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(service.time, "monotonic", lambda: now[0])
    service.clear_cache()
    yield now
    service.clear_cache()


def test_db_failure_serves_old_snapshot_and_retries_not_before_retry_s(clock, monkeypatch):
    calls = []

    def build():
        calls.append(clock[0])
        if len(calls) > 1:
            raise mysql.connector.Error("down")
        return {"rating": "old", "records": {}}

    monkeypatch.setattr(service, "_build", build)
    assert service.rating() == "old"
    clock[0] += service.CACHE_TTL_S
    assert service.rating() == "old" and len(calls) == 2          # попытка была, отдали прошлый снимок
    clock[0] += service.RETRY_S - 1
    assert service.rating() == "old" and len(calls) == 2          # в БД не ходим до RETRY_S
    clock[0] += 1
    assert service.rating() == "old" and len(calls) == 3


def test_no_snapshot_fails_fast_until_retry_s(clock, monkeypatch):
    calls = []

    def build():
        calls.append(clock[0])
        raise service.HallUnavailable("x")

    monkeypatch.setattr(service, "_build", build)
    for _ in range(3):
        with pytest.raises(service.HallUnavailable):
            service.rating()
    assert len(calls) == 1
    clock[0] += service.RETRY_S
    with pytest.raises(service.HallUnavailable):
        service.rating()
    assert len(calls) == 2
