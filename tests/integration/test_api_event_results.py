"""
Интеграционные тесты /api/event-results — источник трекера и страницы результатов
(static/js/tracker-api.js). Заменяют тесты удалённого /api/runners.
Идут по локальной БД (.env.local, снимок прода); нет событий с результатами — skip.
"""

import pytest

from src.analytics.db_pool import get_pooled_connection
from src.krasmarafon.services import results_service

RESULT_FIELDS = ("id", "full_name", "status", "race_status", "distance", "checkpoints",
                 "speed", "current_distance", "time_gun_finish", "rank_absolute")


@pytest.fixture(scope="module")
def event():
    """Последнее по дате событие-дистанция с результатами."""
    conn = get_pooled_connection()
    if not conn:
        pytest.skip("Нет локальной БД")
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("""SELECT e.id, e.event_name, e.event_year, COUNT(r.id) AS n
                       FROM events e JOIN results r ON r.event_id = e.id
                       GROUP BY e.id ORDER BY e.event_date DESC, e.id DESC LIMIT 1""")
        row = cur.fetchone()
        cur.close()
    finally:
        conn.close()
    if not row:
        pytest.skip("В БД нет событий с результатами")
    return row


@pytest.fixture(scope="module")
def data(client, event):
    r = client.get(f"/api/event-results?event_id={event['id']}")
    assert r.status_code == 200
    return r.json()


def started(results):
    return [x for x in results if x["status"] != "Not started"]


def test_top_level_fields(data, event):
    for field in ("event", "total_results", "results", "timestamp", "server_time_unix", "total_distance_km"):
        assert field in data, f"нет поля {field}"
    assert data["event"] == event["event_name"]
    assert data["total_results"] == len(data["results"]) == event["n"]


def test_each_result_has_tracker_fields(data):
    for x in data["results"]:
        for field in RESULT_FIELDS:
            assert field in x, f"нет поля {field} у {x.get('full_name')}"
        assert isinstance(x["checkpoints"], dict)


def test_distance_within_route(data):
    total = data["total_distance_km"]
    assert total and total > 0
    for x in data["results"]:
        assert 0.0 <= x["current_distance"] <= total + 1e-6, f"{x['full_name']}: {x['current_distance']} из {total}"


def test_finished_have_time_rank_and_reach_finish(data):
    finished = [x for x in data["results"] if x["status"] == "Finished"]
    if not finished:
        pytest.skip("Нет финишировавших")
    for x in finished:
        assert x["time_gun_finish"], f"{x['full_name']}: финишировал без времени"
        assert x["rank_absolute"], f"{x['full_name']}: финишировал без места"
        assert x["current_distance"] == pytest.approx(data["total_distance_km"])


def test_runners_have_individual_speeds(data):
    """Маркеры двигаются с разной скоростью — личный/категорийный темп, не одна константа."""
    speeds = {x["speed"] for x in started(data["results"]) if x["speed"]}
    assert len(speeds) > 1, f"у всех одна скорость: {speeds}"


def test_cached_response_is_identical(client, event, data):
    """Второй запрос в пределах TTL отдаётся из готового JSON (быстрый путь) — тот же состав."""
    again = client.get(f"/api/event-results?event_id={event['id']}").json()
    assert [x["id"] for x in again["results"]] == [x["id"] for x in data["results"]]


def test_cold_start_without_cache(client, event, data):
    """Холодный старт: кеш пуст — ответ строится заново и совпадает по составу."""
    results_service._json_cache.clear()
    results_service._response_cache_ts.clear()
    cold = client.get(f"/api/event-results?event_id={event['id']}")
    assert cold.status_code == 200
    assert sorted(x["id"] for x in cold.json()["results"]) == sorted(x["id"] for x in data["results"])


def test_by_event_name_and_year_includes_event(client, event, data):
    r = client.get("/api/event-results", params={"event_name": event["event_name"], "year": event["event_year"]})
    assert r.status_code == 200
    ids = {x["id"] for x in r.json()["results"]}
    assert {x["id"] for x in data["results"]} <= ids


def test_unknown_event_returns_no_results(client):
    r = client.get("/api/event-results?event_id=99999999")
    assert r.status_code in (200, 404)
    if r.status_code == 200:
        assert r.json()["results"] == []
