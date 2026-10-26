"""Стартовый список не публикуется (персональные данные, 2026-10-26):
ни страница, ни API с заявками не доступны без входа в админку."""

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from src.krasmarafon.routers import api, pages


@pytest.fixture
def anon():
    app = FastAPI()
    app.include_router(pages.router)
    app.include_router(api.router)
    return TestClient(app)


def test_page_redirects_to_login(anon):
    r = anon.get("/start_list")
    assert [h.status_code for h in r.history] == [302]
    assert r.history[0].headers["location"].startswith("/login")


@pytest.mark.parametrize("url", [
    "/api/registered-runners",
    "/api/registered-runners?event_name=Жара&event_year=2026",
    "/api/registered-runners-years?event_name=Жара",
    "/api/startlist/104",
    "/api/export/startlist/104",
    "/api/export/startlist?event_name=Жара",
])
def test_leads_api_requires_auth(anon, url):
    assert anon.get(url).status_code == 401


def test_nav_has_no_start_list_link(anon):
    r = anon.get("/results")
    assert r.status_code == 200
    assert "/start_list" not in r.text
