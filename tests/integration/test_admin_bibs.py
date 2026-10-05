"""/api/admin/bibs/* — роуты присвоения номеров (БД и правила замоканы)."""
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app import app
from src.core.auth import api_require_auth

R = "src.krasmarafon.routers.bibs"
BODY = {"event_name": "Снежная семерка", "event_year": 2026,
        "ranges": [{"distance": "7 км", "key": "", "start": 1, "end": 500}, {"distance": "2 км", "start": None}]}


@pytest.fixture(autouse=True)
def _auth_and_conn():
    app.dependency_overrides[api_require_auth] = lambda: "testuser"
    conn = MagicMock()
    with patch(f"{R}.get_pooled_connection", return_value=conn):
        yield conn
    app.dependency_overrides.pop(api_require_auth, None)


client = TestClient(app)


def test_overview_passes_event_and_year(_auth_and_conn):
    with patch(f"{R}.bibs.overview", return_value={"groups": [], "skipped": [], "taken": 0}) as ov:
        r = client.get("/api/admin/bibs?event_name=Снежная семерка&event_year=2026")
    assert r.status_code == 200 and ov.call_args.args[1:] == ("Снежная семерка", 2026)
    _auth_and_conn.close.assert_called_once()


def test_preview_converts_ranges_to_group_keys():
    with patch(f"{R}.bibs.preview", return_value={"groups": [], "ok": True, "to_assign": 0}) as pv:
        client.post("/api/admin/bibs/preview", json=BODY)
    assert pv.call_args.args[3] == {("7 км", ""): (1, 500), ("2 км", ""): (None, None)}


def test_assign_with_errors_is_400_and_returns_groups():
    groups = [{"label": "2 км", "error": "не задан диапазон"}]
    with patch(f"{R}.bibs.assign", return_value={"groups": groups, "ok": False, "assigned": 0}):
        r = client.post("/api/admin/bibs/assign", json=BODY)
    assert r.status_code == 400 and r.json()["detail"]["groups"] == groups


def test_assign_passes_user():
    with patch(f"{R}.bibs.assign", return_value={"groups": [], "ok": True, "assigned": 3}) as a:
        r = client.post("/api/admin/bibs/assign", json=BODY)
    assert r.json()["assigned"] == 3 and a.call_args.args[4] == "testuser"


def test_export_csv_one_row_per_person_with_bib():
    from datetime import datetime
    rows = [{"id": 1, "client_id": 10, "event_id": 5, "created_at": datetime(2026, 10, 5), "start_number": None,
             "surname": "Дубль", "name": "Поздний", "birthday": None, "sex": "", "event_distance": "7 км", "category": ""},
            {"id": 2, "client_id": 10, "event_id": 5, "created_at": datetime(2026, 10, 1), "start_number": 12,
             "surname": "Дубль", "name": "Ранний", "birthday": None, "sex": "", "event_distance": "7 км", "category": ""}]
    with patch("src.analytics.db_results.get_leads_admin", return_value=rows) as gl:
        r = client.get("/api/export/startlist?event_name=Снежная семерка&event_year=2026")
    lines = r.text.strip().splitlines()
    assert gl.call_args.kwargs["is_duplicate"] is None
    assert len(lines) == 2 and lines[1].startswith("12,,Дубль,Ранний")
    assert "filename*=UTF-8" in r.headers["content-disposition"]
