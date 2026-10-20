"""/medals/stat (localhost; на проде — nginx) и /api/admin/medals-stats[.xlsx]."""
import pytest
from fastapi.testclient import TestClient

from app import app
from src.analytics import medals_stats
from src.core.auth import api_require_auth

client = TestClient(app)


@pytest.fixture
def log(tmp_path, monkeypatch):
    path = tmp_path / "medals_stat.log"
    monkeypatch.setattr(medals_stats, "LOG_PATH", path)
    return path


def test_stat_beacon_is_logged_and_not_blocked_by_static_mount(log):
    r = client.post("/medals/stat?e=download&f=medal-russia")
    assert r.status_code == 204
    assert [(e, f) for _, e, f, _ in medals_stats.read(log)] == [("download", "medal-russia")]


def test_admin_stats_require_auth(log):
    assert client.get("/api/admin/medals-stats").status_code == 401
    assert client.get("/api/admin/medals-stats.xlsx").status_code == 401


def test_admin_stats_json_and_xlsx(log):
    client.post("/medals/stat?e=open")
    client.post("/medals/stat?e=download&f=medal-krasnoyarsk")
    app.dependency_overrides[api_require_auth] = lambda: "testuser"
    try:
        s = client.get("/api/admin/medals-stats").json()
        x = client.get("/api/admin/medals-stats.xlsx")
    finally:
        app.dependency_overrides.pop(api_require_auth, None)
    assert s["totals"] == {"open": 1, "download": 1, "share": 0} and s["conversion"] == 100.0
    assert x.status_code == 200 and x.content[:2] == b"PK"
    assert x.headers["content-disposition"].startswith('attachment; filename="medals-stats-')
