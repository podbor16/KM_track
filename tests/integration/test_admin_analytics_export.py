"""/api/admin/analytics-export* — панель «Скачать Excel» во вкладке «Аналитика»."""
from unittest.mock import patch
from urllib.parse import unquote

from fastapi.testclient import TestClient

from app import app
from src.core.auth import api_require_auth

client = TestClient(app)
DE = "src.analytics.dash_export"


def setup_function():
    app.dependency_overrides[api_require_auth] = lambda: "testuser"


def teardown_function():
    app.dependency_overrides.pop(api_require_auth, None)


def test_xlsx_passes_filters_and_returns_file():
    with patch(f"{DE}.build_xlsx", return_value=(b"PK..", "analytics_Динамика_20261026-1200.xlsx")) as b:
        r = client.get("/api/admin/analytics-export.xlsx?tab=XbA&event_year_jr76=2025&event_name_2iel=Жара"
                       "&event_name_2iel=Весна&event_distance_6efj=")
    assert r.status_code == 200 and r.content == b"PK.."
    assert b.call_args.args == ("XbA", {"event_year_jr76": "2025", "event_name_2iel": ["Жара", "Весна"]})
    assert "analytics_Динамика_20261026-1200.xlsx" in unquote(r.headers["content-disposition"])


def test_xlsx_errors():
    with patch(f"{DE}.build_xlsx", side_effect=ValueError("экспорт этой вкладки ещё не включён")):
        assert client.get("/api/admin/analytics-export.xlsx?tab=nA").status_code == 400
    with patch(f"{DE}.build_xlsx", side_effect=OSError("timeout")):
        r = client.get("/api/admin/analytics-export.xlsx?tab=XbA")
    assert r.status_code == 502 and "DataLens" in r.json()["detail"]


def test_filters():
    with patch(f"{DE}.tabs", return_value=[{"id": "XbA", "title": "Д", "export": True}]), \
            patch(f"{DE}.filters", return_value=[{"param": "p", "title": "Год", "multiselect": False, "options": ["2025"]}]) as f:
        r = client.get("/api/admin/analytics-export/filters?tab=XbA")
    assert r.json()["filters"][0]["options"] == ["2025"] and f.call_args.args == ("XbA",)


def test_requires_auth():
    app.dependency_overrides.pop(api_require_auth, None)
    assert client.get("/api/admin/analytics-export.xlsx?tab=XbA").status_code == 401
    assert client.get("/api/admin/analytics-export/filters?tab=XbA").status_code == 401
