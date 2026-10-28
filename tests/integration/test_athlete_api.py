"""/api/athlete/{client_id} и /api/search-athletes — профиль по карточке (БД замокана)."""
import datetime
from unittest.mock import patch

DB = "src.analytics.db_connection_optimized"
ON = patch("src.krasmarafon.routers.api.get_history_enabled", return_value=True)


def test_profile_by_client_id(client):
    athlete = {"client_id": 40803, "surname": "Пцарев", "name": "Александр", "birthday": datetime.date(2013, 12, 20)}
    rows = [{"id": 1, "start_number": 1012, "event_name": "Детский забег", "event_date": datetime.date(2016, 8, 28)}]
    with ON, patch(f"{DB}.get_athlete_by_client", return_value=(athlete, rows)) as m:
        r = client.get("/api/athlete/40803")
    assert r.status_code == 200 and m.call_args.args == (40803,)
    body = r.json()
    assert body["athlete"]["birthday"] == "2013-12-20" and body["athlete"]["client_id"] == 40803
    assert body["results"][0]["event_date"] == "2016-08-28" and body["total_races"] == 1


def test_profile_unknown_card_404_and_old_path_gone(client):
    with ON, patch(f"{DB}.get_athlete_by_client", return_value=({}, [])):
        assert client.get("/api/athlete/999").status_code == 404
    with ON:
        assert client.get("/api/athlete/Пцарев/Александр").status_code == 404


def test_search_returns_client_ids(client):
    found = [{"client_id": 43759, "surname": "Пцарев", "name": "Александр", "birth_year": "1980", "events_count": 9},
             {"client_id": 40803, "surname": "Пцарев", "name": "Александр", "birth_year": "2013", "events_count": 3}]
    with ON, patch(f"{DB}.search_clients_optimized", return_value=found):
        r = client.get("/api/search-athletes?q=Пцарев")
    assert [x["client_id"] for x in r.json()["results"]] == [43759, 40803]
