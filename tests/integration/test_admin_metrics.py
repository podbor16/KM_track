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
