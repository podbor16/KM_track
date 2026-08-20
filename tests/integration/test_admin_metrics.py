"""Интеграционные тесты для /api/admin/metrics/* — живой поток и список алертов."""
import asyncio
from unittest.mock import MagicMock, patch

import pytest

from app import app
from src.core.auth import api_require_auth


@pytest.fixture(autouse=True)
def _override_auth():
    app.dependency_overrides[api_require_auth] = lambda: "testuser"
    yield
    app.dependency_overrides.pop(api_require_auth, None)


class TestServerMetricsLive:
    def test_returns_event_source_response(self):
        """Регрессия: get_server_metrics_live() определяла generator
        stream(), но не возвращала EventSourceResponse(stream()) — эндпоинт
        не отдавал SSE-поток вообще. Вызываем корутину напрямую через
        asyncio.run() — SSE live-эндпоинты в проекте не покрыты реальными
        HTTP-стрим-тестами (см. tests/load/sse_test.js, tests/browser_check.py),
        этот тест не меняет конвенцию, просто проверяет тип возвращаемого
        объекта."""
        from sse_starlette.sse import EventSourceResponse
        from src.krasmarafon.routers.api import get_server_metrics_live

        request = MagicMock()
        result = asyncio.run(get_server_metrics_live(request=request, user="testuser"))
        assert isinstance(result, EventSourceResponse)

    def test_requires_auth(self, client):
        app.dependency_overrides.pop(api_require_auth, None)
        r = client.get("/api/admin/metrics/live")
        assert r.status_code == 401


class TestServerMetricsAlerts:
    def test_returns_alerts_from_collector(self, client):
        fake_alerts = [{
            "datetime": "2026-08-19 16:49:02", "load_label": "Критическая",
            "suggestions": ["RAM 80% ..."],
        }]
        with patch("src.krasmarafon.routers.api._get_metrics_collector") as mock_get:
            mock_collector = MagicMock()
            mock_collector.read_recent_alerts.return_value = fake_alerts
            mock_get.return_value = mock_collector
            r = client.get("/api/admin/metrics/alerts")
        assert r.status_code == 200
        assert r.json() == {"alerts": fake_alerts}

    def test_passes_limit_to_collector(self, client):
        with patch("src.krasmarafon.routers.api._get_metrics_collector") as mock_get:
            mock_collector = MagicMock()
            mock_collector.read_recent_alerts.return_value = []
            mock_get.return_value = mock_collector
            client.get("/api/admin/metrics/alerts?limit=10")
        mock_collector.read_recent_alerts.assert_called_once_with(10)

    def test_default_limit_is_50(self, client):
        with patch("src.krasmarafon.routers.api._get_metrics_collector") as mock_get:
            mock_collector = MagicMock()
            mock_collector.read_recent_alerts.return_value = []
            mock_get.return_value = mock_collector
            client.get("/api/admin/metrics/alerts")
        mock_collector.read_recent_alerts.assert_called_once_with(50)

    def test_limit_over_200_returns_422(self, client):
        r = client.get("/api/admin/metrics/alerts?limit=500")
        assert r.status_code == 422

    def test_requires_auth(self, client):
        app.dependency_overrides.pop(api_require_auth, None)
        r = client.get("/api/admin/metrics/alerts")
        assert r.status_code == 401
