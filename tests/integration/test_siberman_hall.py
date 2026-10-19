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
from src.siberman.hall import geo as hgeo
from src.siberman.hall import service
from src.siberman.hall.athlete import build_athletes
from src.siberman.hall.rating import build_rating
from src.siberman.hall.records import build_records
from src.siberman.hall.stats import build_stats
from src.siberman.persons.linking import norm_city

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
        persons, applicants = hdata.load_people(conn)
    finally:
        conn.close()
    if not any(e.year == 2016 for e in entries):
        pytest.skip("В локальной БД нет архива 2016–2025")
    teams = hdata.build_teams(entries)
    records = build_records(entries, teams)
    places = hgeo.resolve_places(entries, persons, applicants, hgeo.load_cities())
    geo = hgeo.build_geo(entries, places)
    return {"entries": entries, "teams": teams, "records": records,
            "rating": build_rating(entries, teams, records), "geo": geo,
            "athletes": build_athletes(entries, teams, records, places, persons)}


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


def test_stats_match_site(archive):
    s = build_stats(archive["entries"], archive["teams"], archive["geo"])
    i = s["individual"]
    got = (i["starts"], i["finishes"], i["people"], i["people_finished"], i["people_men"], i["people_women"],
           i["starts_men"], i["finishes_men"], i["starts_women"], i["finishes_women"],
           s["relay"]["teams"], s["relay"]["finished"], s["people_total"])
    assert got == (204, 196, 170, 165, 156, 14, 189, 184, 15, 12, 73, 71, 337), f"наше: {got}"
    assert (s["first_year"], s["last_year"], len(s["years"])) == (2016, 2025, 10)


def test_geo_on_archive(archive):
    g = archive["geo"]
    assert g["total"] == 337 and 168 <= g["known"] < g["total"]
    assert sum(c["count"] for c in g["cities"]) == g["known"] == sum(c["count"] for c in g["countries"])
    assert all(c["name"] for c in g["countries"])
    assert len({norm_city(c["name"]) for c in g["cities"]}) == len(g["cities"])


def test_athlete_pages_on_archive(archive):
    pages, holder = archive["athletes"], archive["records"]["current"]["race:individual:M"]["holder"]
    assert len(pages) == 337
    p = pages[holder["person_id"]]
    assert p["person"]["bib"] == holder["bib"] and p["summary"]["records"] >= 1
    assert any(r["cell"] == "race:individual:M" and r["current"] for r in p["records"])
    assert sorted(x["rating"]["position"] for x in pages.values() if x["rating"]) == list(range(1, 166))
    assert sum(len(x["medals"]) for x in pages.values()) == 196


def test_athlete_finish_numbers_match_rating(archive):
    want = {(r["year"], r["bib"]): (r["person_id"], r["finish_no"], r["medal"]["key"])
            for r in archive["rating"]["individual"] if r["status"] == "finished"}
    got = {(row["year"], row["bib"]): (pid, row["finish_no"], p["medals"][row["finish_no"] - 1]["medal"]["key"])
           for pid, p in archive["athletes"].items() for row in p["participations"] if row.get("finish_no")}
    assert got == want


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
    stats = client.get("/api/siberman/hall/stats").json()
    assert {"individual", "relay", "years", "people_total", "countries", "cities"} <= set(stats)
    geo = client.get("/api/siberman/hall/geo")
    assert geo.status_code == 200 and {"total", "known", "countries", "cities"} <= set(geo.json())
    assert "birthdate" not in geo.text
    assert client.get("/hall/rating", headers=SIBERMAN).status_code == 200
    assert client.get("/hall/records", headers=SIBERMAN).status_code == 200
    assert client.get("/hall/rating").status_code == 404
    assert client.get("/hall/records").status_code == 404
    for page in ("/hall/stats", "/hall/geo"):
        assert client.get(page, headers=SIBERMAN).status_code == 200
        assert client.get(page).status_code == 404
    holder = records["current"]["race:individual:M"]["holder"]
    slug, pid = holder["slug"], holder["person_id"]
    assert slug == holder["bib"]                                           # адрес — личный стартовый номер
    a = client.get(f"/api/siberman/athlete/{slug}")
    assert a.status_code == 200 and a.json()["person"]["id"] == pid and a.json()["person"]["slug"] == slug
    assert "birthdate" not in a.text
    assert client.get("/api/siberman/athlete/999999").status_code == 404
    assert client.get(f"/athlete/{slug}", headers=SIBERMAN).status_code == 200
    r = client.get(f"/athlete/r{pid}", headers=SIBERMAN, follow_redirects=False)   # r{id} у личника → номер
    assert r.status_code == 301 and r.headers["location"] == f"/athlete/{slug}"
    rating = client.get("/api/siberman/hall/rating").json()
    relay_only = next(m["slug"] for t in rating["relay"] for m in t["members"] if (m["slug"] or "").startswith("r"))
    assert client.get(f"/athlete/{relay_only}", headers=SIBERMAN).status_code == 200
    assert all(r["slug"] == r["bib"] for r in rating["individual"] if r["person_id"])
    for bad in ("/athlete/999999", "/athlete/abc", "/athlete/%C2%B2", "/athlete/r999999"):
        r = client.get(bad, headers=SIBERMAN)
        assert r.status_code == 404 and "Спортсмен не найден" in r.text
    assert client.get(f"/athlete/{slug}").status_code == 404
