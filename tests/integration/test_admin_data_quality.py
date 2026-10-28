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
    with patch(f"{R}.dq.merge_cards", return_value=(7, 501)) as m:
        r = client.post("/api/admin/data-quality/merge",
                        json={"client_ids": [7, 9], "surname": "Иванов", "name": "Иван", "birthday": "1990-01-02", "key": "k"})
    assert r.json() == {"ok": True, "client_id": 7, "action_id": 501}
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



def test_fix_fio_passes_user_and_returns_card(conn):
    with patch(f"{R}.dq.fix_fio", return_value=(53428, 502)) as m:
        r = client.post("/api/admin/data-quality/fix-fio",
                        json={"result_id": 7, "surname": "Цимис", "name": "Егор", "key": "k"})
    assert r.json() == {"ok": True, "client_id": 53428, "action_id": 502}
    assert m.call_args.args == (conn, 7, "Цимис", "Егор", "testuser", "k")


def test_edit_passes_user_and_rejects_unknown_table(conn):
    with patch(f"{R}.dq.edit_record", return_value=(23881, 610)) as m:
        r = client.post("/api/admin/data-quality/edit",
                        json={"table": "results", "id": 5, "fields": {"birthday": "2014-12-12"}, "key": "k"})
    assert r.json() == {"ok": True, "client_id": 23881, "action_id": 610}
    assert m.call_args.args == (conn, "results", 5, {"birthday": "2014-12-12"}, "testuser", "k")
    r = client.post("/api/admin/data-quality/edit", json={"table": "events", "id": 1, "fields": {}})
    assert r.status_code == 422


def test_undo_passes_user_and_maps_refusal_to_400(conn):
    with patch(f"{R}.dq.undo_action", return_value=900) as m:
        r = client.post("/api/admin/data-quality/undo", json={"action_id": 501})
    assert r.json() == {"ok": True, "undo_id": 900}
    assert m.call_args.args == (conn, 501, "testuser")
    with patch(f"{R}.dq.undo_action", side_effect=ValueError("уже отменено")):
        r = client.post("/api/admin/data-quality/undo", json={"action_id": 501})
    assert r.status_code == 400 and r.json()["detail"] == "уже отменено"


def test_actions_journal_limit_clamped(conn):
    with patch(f"{R}.dq.recent_actions", return_value=[{"id": 1}]) as m:
        r = client.get("/api/admin/data-quality/actions?limit=100000")
    assert r.json() == {"actions": [{"id": 1}]}
    assert m.call_args.args == (conn, 500)


def test_move_requires_exactly_one_target(conn):
    with patch(f"{R}.dq.move_row", return_value=(49463, 1656)) as m:
        r = client.post("/api/admin/data-quality/move", json={"table": "leads", "row_id": 7, "to_client_id": 49463, "key": "k"})
    assert r.json() == {"ok": True, "client_id": 49463, "action_id": 1656}
    assert m.call_args.args == (conn, "leads", 7, "testuser", "k", 49463, None)
    assert client.post("/api/admin/data-quality/move", json={"row_id": 1}).status_code == 422
    both = {"row_id": 1, "to_client_id": 2, "new_card": {"surname": "А", "name": "Б", "birthday": "2000-01-01"}}
    assert client.post("/api/admin/data-quality/move", json=both).status_code == 422
    assert client.post("/api/admin/data-quality/move", json={"table": "clients", "row_id": 1, "to_client_id": 2}).status_code == 422


def test_cards_search(conn):
    with patch(f"{R}.dq.search_cards", return_value=[{"id": 1}]) as m:
        r = client.get("/api/admin/data-quality/cards?q=Чернова Соф")
    assert r.json() == {"cards": [{"id": 1}]} and m.call_args.args == (conn, "Чернова Соф")
