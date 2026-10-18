"""
Рейтинг и рекорды на локальном архиве siberman 2016–2025 (.env.local): сверка рекордов с таблицей
организаторов (лист «Рекорды», Online results Siberman.xlsx) и рейтинга — с цифрами сайта
siberman515.com/results; API и страницы блоков. Расхождения — сообщить, тест не подгонять.
"""
import pytest
from fastapi.testclient import TestClient

from app import app
from src.siberman.db import get_siberman_connection
from src.siberman.hall import data as hdata
from src.siberman.hall import service
from src.siberman.hall.rating import build_rating
from src.siberman.hall.records import build_records

SIBERMAN = {"host": "siberman.localhost"}

# Рекорды организаторов на 2025 год, секунды (времена — с листа «Рекорды»).
ORGANIZERS = {
    "race:individual:M": 71429, "race:individual:F": 95387, "race:relay:X": 76811,
    "race:absolute:M": 71429, "race:absolute:F": 95387,
    "swim:individual:M": 8647, "swim:individual:F": 12570, "swim:relay:M": 7588, "swim:relay:F": 9330,
    "swim:absolute:M": 7588, "swim:absolute:F": 9330,
    "bike:individual:M": 38943, "bike:individual:F": 51112, "bike:relay:M": 41071, "bike:relay:F": 47671,
    "bike:absolute:M": 38943, "bike:absolute:F": 47671,
    "bike1:individual:M": 13541, "bike1:individual:F": 17334, "bike1:relay:M": 13960, "bike1:relay:F": 15764,
    "bike1:absolute:M": 13541, "bike1:absolute:F": 15764,
    "bike2:individual:M": 25402, "bike2:individual:F": 33778, "bike2:relay:M": 27111, "bike2:relay:F": 31828,
    "bike2:absolute:M": 25402, "bike2:absolute:F": 31828,
    "run:individual:M": 22793, "run:individual:F": 29795, "run:relay:M": 21852, "run:relay:F": 28115,
    "run:absolute:M": 21852, "run:absolute:F": 28115,
}


@pytest.fixture(scope="module")
def archive():
    conn = get_siberman_connection()
    if conn is None:
        pytest.skip("Нет локальной БД siberman")
    try:
        entries = [e for e in hdata.load_entries(conn) if e.year <= 2025]
    finally:
        conn.close()
    if not any(e.year == 2016 for e in entries):
        pytest.skip("В локальной БД нет архива 2016–2025")
    teams = hdata.build_teams(entries)
    records = build_records(entries, teams)
    return {"entries": entries, "teams": teams, "records": records,
            "rating": build_rating(entries, teams, records)}


def test_records_match_organizers_table(archive):
    current = archive["records"]["current"]
    diffs = {k: ((current[k] or {}).get("time_s"), v) for k, v in ORGANIZERS.items()
             if (current[k] or {}).get("time_s") != v}
    assert diffs == {}, f"расхождения (наше, организаторы): {diffs}"


def test_history_ends_with_current_and_only_improves(archive):
    history, current = archive["records"]["history"], archive["records"]["current"]
    for key, h in history.items():
        assert h, key
        assert h[-1]["time_s"] == current[key]["time_s"]
        assert all(a["time_s"] > b["time_s"] for a, b in zip(h, h[1:])), key


def test_rating_counts_match_site(archive):
    rating = archive["rating"]
    finished = [r for r in rating["individual"] if r["status"] == "finished"]
    assert len(finished) == 196
    assert sum(r["gender"] == "M" for r in finished) == 184 and sum(r["gender"] == "F" for r in finished) == 12
    assert len(archive["teams"]) == 73
    assert sum(r["status"] == "finished" for r in rating["relay"]) == 71


def test_rating_marks_current_records(archive):
    rating = archive["rating"]
    assert sum(1 for r in rating["individual"] if r["record"]) == 2
    assert sum(1 for r in rating["relay"] if r["record"]) == 1


def test_api_and_pages():
    service.clear_cache()
    client = TestClient(app)
    r = client.get("/api/siberman/hall/rating")
    if r.status_code == 503:
        pytest.skip("Нет локальной БД siberman")
    assert r.status_code == 200 and {"individual", "relay", "years"} <= set(r.json())
    assert "birthdate" not in r.text
    records = client.get("/api/siberman/hall/records").json()
    assert "race:relay:X" in records["current"] and "history" not in records
    assert client.get("/api/siberman/hall/records/history", params={"cell": "run:absolute:M"}).status_code == 200
    assert client.get("/api/siberman/hall/records/history", params={"cell": "nope"}).status_code == 404
    assert client.get("/hall/rating", headers=SIBERMAN).status_code == 200
    assert client.get("/hall/records", headers=SIBERMAN).status_code == 200
    assert client.get("/hall/rating").status_code == 404
    assert client.get("/hall/records").status_code == 404
