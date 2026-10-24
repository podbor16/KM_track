"""/api/admin/age-groups — режим расчёта возраста в ответе и PUT /api/admin/age-groups/mode."""
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import app
from src.core.auth import api_require_auth

client = TestClient(app)
DB = "src.analytics.db_results"


def setup_function():
    app.dependency_overrides[api_require_auth] = lambda: "testuser"


def teardown_function():
    app.dependency_overrides.pop(api_require_auth, None)


def test_list_returns_mode_for_event_and_distance():
    with patch(f"{DB}.list_age_groups", return_value=[]), patch(f"{DB}.get_age_group_mode", return_value="event_date") as m:
        r = client.get("/api/admin/age-groups?event_name=Жара&event_distance=5 км")
    assert r.json() == {"items": [], "mode": "event_date"}
    assert m.call_args.args == ("Жара", "5 км")


def test_set_mode_and_reject_unknown():
    with patch(f"{DB}.set_age_group_mode", return_value="event_date") as s:
        r = client.put("/api/admin/age-groups/mode", json={"event_name": "Жара", "event_distance": "5 км", "mode": "event_date"})
    assert r.json() == {"ok": True, "mode": "event_date"} and s.call_args.args == ("Жара", "5 км", "event_date")
    r = client.put("/api/admin/age-groups/mode", json={"event_name": "Жара", "event_distance": "5 км", "mode": "today"})
    assert r.status_code == 422


def test_set_mode_requires_auth():
    app.dependency_overrides.pop(api_require_auth, None)
    r = client.put("/api/admin/age-groups/mode", json={"event_name": "Жара", "event_distance": "5 км", "mode": "birth_year"})
    assert r.status_code == 401
