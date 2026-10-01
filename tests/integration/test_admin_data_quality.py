"""/api/admin/data-quality/* — роуты вкладки «Качество данных» (БД и проверки замоканы)."""
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app import app
from src.analytics.data_quality import Finding
from src.core.auth import api_require_auth

R = "src.krasmarafon.routers.data_quality"


@pytest.fixture(autouse=True)
def _override_auth():
    app.dependency_overrides[api_require_auth] = lambda: "testuser"
    yield
    app.dependency_overrides.pop(api_require_auth, None)


@pytest.fixture
def conn():
    c = MagicMock()
    with patch(f"{R}.get_pooled_connection", return_value=c):
        yield c


client = TestClient(app)


def test_list_sorted_by_severity_and_connection_closed(conn):
    low = Finding("R-DUP", "low", "б", (1,), 10, 5)
    high = Finding("C-TWIN", "high", "а", (2, 3))
    with patch(f"{R}.dq.pending_findings", return_value=([low, high], "data")) as pf, \
            patch(f"{R}.dq.finding_view", side_effect=lambda f, d: {"key": f.key}):
        r = client.get("/api/admin/data-quality?event_id=5")
    assert r.status_code == 200
    assert [f["key"] for f in r.json()["findings"]] == [high.key, low.key]
    assert pf.call_args.args[1] == {5}
    conn.close.assert_called_once()


def test_merge_passes_user_and_returns_survivor(conn):
    with patch(f"{R}.dq.merge_cards", return_value=7) as m:
        r = client.post("/api/admin/data-quality/merge",
                        json={"client_ids": [7, 9], "surname": "Иванов", "name": "Иван", "birthday": "1990-01-02", "key": "k"})
    assert r.json() == {"ok": True, "client_id": 7}
    assert m.call_args.args == (conn, [7, 9], "Иванов", "Иван", "1990-01-02", "testuser", "k")


def test_validation_error_is_400(conn):
    with patch(f"{R}.dq.delete_result", side_effect=ValueError("удаляется только «Not started»")):
        r = client.post("/api/admin/data-quality/delete-result", json={"result_id": 1})
    assert r.status_code == 400
    assert "Not started" in r.json()["detail"]
    conn.close.assert_called_once()


def test_dismiss_rejects_unknown_decision(conn):
    r = client.post("/api/admin/data-quality/dismiss", json={"key": "k", "decision": "merge"})
    assert r.status_code == 422


def test_no_db_connection_is_503():
    with patch(f"{R}.get_pooled_connection", return_value=None):
        r = client.get("/api/admin/data-quality")
    assert r.status_code == 503
