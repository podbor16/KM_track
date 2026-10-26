"""Стартовый список не публикуется (персональные данные, 2026-10-26):
ни страница, ни API с заявками не доступны без входа в админку.

Без TestClient: в CI starlette старый, а httpx новый (TestClient там не создаётся) —
проверяем, что на маршрутах висит зависимость авторизации, и что делает она сама."""

from pathlib import Path

import pytest
from fastapi import HTTPException

from src.core.auth import api_require_auth, require_auth
from src.krasmarafon.routers import api, pages

HEADER = Path(__file__).resolve().parents[2] / "templates" / "krasmarafon" / "header.html"


def _deps(router, path):
    route = next(r for r in router.routes if r.path == path)
    return {d.call for d in route.dependant.dependencies}


def test_page_requires_login():
    assert require_auth in _deps(pages.router, "/start_list")


@pytest.mark.parametrize("path", [
    "/api/registered-runners",
    "/api/registered-runners-years",
    "/api/startlist/{event_id}",
    "/api/export/startlist/{event_id}",
    "/api/export/startlist",
])
def test_leads_api_requires_auth(path):
    assert api_require_auth in _deps(api.router, path)


def test_anonymous_gets_401():
    with pytest.raises(HTTPException) as e:
        api_require_auth(None)
    assert e.value.status_code == 401


def test_nav_has_no_start_list_link():
    assert "/start_list" not in HEADER.read_text(encoding="utf-8")
