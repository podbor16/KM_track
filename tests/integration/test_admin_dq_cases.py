"""/api/admin/data-quality/cases*, /person/{client_id} — дела (функции dq_cases замоканы)."""
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app import app
from src.core.auth import api_require_auth

R = "src.krasmarafon.routers.data_quality"
client = TestClient(app)


@pytest.fixture(autouse=True)
def _auth():
    app.dependency_overrides[api_require_auth] = lambda: "testuser"
    yield
    app.dependency_overrides.pop(api_require_auth, None)


@pytest.fixture
def conn():
    c = MagicMock()
    with patch(f"{R}.get_pooled_connection", return_value=c):
        yield c


def test_list_and_get_case(conn):
    with patch(f"{R}.dq_cases.list_cases", return_value=[{"key": "c1"}]) as m:
        r = client.get("/api/admin/data-quality/cases?status=postponed&event_id=5")
    assert r.json() == {"cases": [{"key": "c1"}]} and m.call_args.args == (conn, "postponed", 5)
    with patch(f"{R}.dq_cases.get_case", return_value=None):
        assert client.get("/api/admin/data-quality/cases/c1").status_code == 404


def test_answer_passes_user_and_stale_is_409(conn):
    with patch(f"{R}.dq_cases.apply_answer", return_value={"action_ids": [7], "case": None}) as m:
        r = client.post("/api/admin/data-quality/cases/c1/answer",
                        json={"question_id": "R-FOREIGN:r1:1-2", "answer_id": "to:2", "inputs": {}})
    assert r.json() == {"action_ids": [7], "case": None}
    assert m.call_args.args == (conn, "c1", "R-FOREIGN:r1:1-2", "to:2", {}, "testuser", [])
    from src.analytics.dq_cases import StaleQuestion
    with patch(f"{R}.dq_cases.apply_answer", side_effect=StaleQuestion("Дело изменилось — обновите")):
        r = client.post("/api/admin/data-quality/cases/c1/answer", json={"question_id": "x", "answer_id": "keep"})
    assert r.status_code == 409 and "обновите" in r.json()["detail"]


def test_answer_returns_conflict_as_is_and_value_error_is_400(conn):
    out = {"action_ids": [], "case": {"key": "c1"}, "conflict": {"merge_with": 14}}
    with patch(f"{R}.dq_cases.apply_answer", return_value=out):
        r = client.post("/api/admin/data-quality/cases/c1/answer", json={"question_id": "x", "answer_id": "other"})
    assert r.json() == out
    with patch(f"{R}.dq_cases.apply_answer", side_effect=ValueError("значения не изменились")):
        r = client.post("/api/admin/data-quality/cases/c1/answer", json={"question_id": "x", "answer_id": "other"})
    assert r.status_code == 400 and "не изменились" in r.json()["detail"]


def test_postpone_and_person(conn):
    with patch(f"{R}.dq_cases.postpone_case", return_value=[3, 4]) as m:
        r = client.post("/api/admin/data-quality/cases/c1/postpone", json={"reason": "не знаю ДР"})
    assert r.json() == {"ok": True, "action_ids": [3, 4]} and m.call_args.args == (conn, "c1", "не знаю ДР", "testuser")
    with patch(f"{R}.dq_cases.case_for_card", return_value={"key": "c9"}):
        assert client.get("/api/admin/data-quality/person/9").json() == {"key": "c9"}
    with patch(f"{R}.dq_cases.case_for_card", return_value=None):
        assert client.get("/api/admin/data-quality/person/9").status_code == 404


def test_cases_require_auth():
    app.dependency_overrides.pop(api_require_auth, None)
    assert client.get("/api/admin/data-quality/cases").status_code == 401


def test_answer_passes_extra_cards(conn):
    with patch(f"{R}.dq_cases.apply_answer", return_value={"action_ids": [], "case": None}) as m:
        client.post("/api/admin/data-quality/cases/c1/answer",
                    json={"question_id": "x", "answer_id": "keep", "extra_cards": [9]})
    assert m.call_args.args[-1] == [9]
