"""Интеграционные тесты: раздел «История участия» скрыт/доступен по
флагу get_history_enabled() — роуты /history, /athlete-profile и API
/api/search-athletes, /api/athlete/{surname}/{name}."""
from unittest.mock import patch

import pytest

from app import app
from src.core.auth import api_require_auth


@pytest.fixture(autouse=True)
def _override_auth():
    app.dependency_overrides[api_require_auth] = lambda: "testuser"
    yield
    app.dependency_overrides.pop(api_require_auth, None)


def test_history_page_redirects_when_disabled(client):
    with patch("src.krasmarafon.routers.pages.get_history_enabled", return_value=False):
        r = client.get("/history", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "/"


def test_athlete_profile_page_redirects_when_disabled(client):
    with patch("src.krasmarafon.routers.pages.get_history_enabled", return_value=False):
        r = client.get("/athlete-profile", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "/"


def test_history_page_renders_when_enabled(client):
    with patch("src.krasmarafon.routers.pages.get_history_enabled", return_value=True):
        r = client.get("/history", follow_redirects=False)
    assert r.status_code == 200
    assert "История" in r.text


def test_history_nav_link_hidden_when_disabled(client, tmp_path, monkeypatch):
    # templates.env.globals['history_enabled'] хранит ссылку на функцию,
    # захваченную один раз при импорте pages.py — патчить имя в модуле
    # бесполезно (Jinja всё равно дёргает исходный объект). Единственный
    # способ реально повлиять — подменить файл, который эта функция читает
    # при каждом вызове (тот же механизм, что и в проде).
    f = tmp_path / "history_enabled.local"
    f.write_text("false", encoding="utf-8")
    monkeypatch.setattr("src.config.event_loader._HISTORY_ENABLED_FILE", f)
    r = client.get("/results", follow_redirects=False)
    assert r.status_code == 200
    assert 'href="/history"' not in r.text


def test_history_nav_link_shown_when_enabled(client, tmp_path, monkeypatch):
    monkeypatch.setattr("src.config.event_loader._HISTORY_ENABLED_FILE", tmp_path / "history_enabled.local")
    r = client.get("/results", follow_redirects=False)
    assert r.status_code == 200
    assert 'href="/history"' in r.text


def test_search_athletes_404_when_disabled(client):
    with patch("src.krasmarafon.routers.api.get_history_enabled", return_value=False):
        r = client.get("/api/search-athletes?q=Иван")
    assert r.status_code == 404


def test_search_athletes_ok_when_enabled(client):
    with patch("src.krasmarafon.routers.api.get_history_enabled", return_value=True), \
         patch("src.analytics.db_connection_optimized.search_clients_optimized", return_value=[]):
        r = client.get("/api/search-athletes?q=Иван")
    assert r.status_code == 200


def test_athlete_profile_api_404_when_disabled(client):
    with patch("src.krasmarafon.routers.api.get_history_enabled", return_value=False):
        r = client.get("/api/athlete/Иванов/Иван")
    assert r.status_code == 404


def test_admin_history_status_reflects_flag(client):
    with patch("src.krasmarafon.routers.admin.get_history_enabled", return_value=False):
        r = client.get("/api/admin/history-status")
    assert r.status_code == 200
    assert r.json() == {"enabled": False}


def test_admin_history_toggle_calls_setter(client):
    with patch("src.krasmarafon.routers.admin.set_history_enabled") as mock_set:
        r = client.post("/api/admin/history-toggle?enabled=false")
    assert r.status_code == 200
    assert r.json() == {"enabled": False}
    mock_set.assert_called_once_with(False)


def test_admin_history_toggle_requires_auth(client):
    app.dependency_overrides.pop(api_require_auth, None)
    r = client.post("/api/admin/history-toggle?enabled=false")
    assert r.status_code in (401, 403)
