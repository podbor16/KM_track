"""Поиск карточек и профиль по client_id на локальной БД (.env.local): тёзки — раздельно.
Тестовые данные — на событиях 2099 года, убираются после теста."""
import pytest

from src.analytics import db_athletes
from src.analytics.db_pool import get_pooled_connection

EV, SUR = "Тест профиля", "Тестпрофилев"


@pytest.fixture
def db():
    conn = get_pooled_connection()
    if not conn:
        pytest.skip("Нет локальной БД")
    cur = conn.cursor(dictionary=True)

    def cleanup():
        cur.execute("SELECT id FROM events WHERE event_name = %s", (EV,))
        ids = [r["id"] for r in cur.fetchall()]
        if ids:
            ph = ",".join(map(str, ids))
            cur.execute(f"DELETE FROM results WHERE event_id IN ({ph})")
            cur.execute(f"DELETE FROM events WHERE id IN ({ph})")
        cur.execute("DELETE FROM clients WHERE surname = %s", (SUR,))
        conn.commit()

    cleanup()
    yield conn, cur
    cleanup()
    cur.close()
    conn.close()


def add_result(cur, dist, bib, bd, name="Александр"):
    cur.execute("INSERT INTO events (event_name, event_distance, event_year) VALUES (%s, %s, 2099)", (EV, dist))
    cur.execute("""INSERT INTO results (surname, name, birthday, client_id, event_id, sex, start_number, category,
                   race_status) VALUES (%s, %s, %s, 0, %s, 'Мужчина', %s, 'М18-49', 'Finished')""",
                (SUR, name, bd, cur.lastrowid, bib))
    cur.execute("SELECT client_id FROM results WHERE id = %s", (cur.lastrowid,))
    return cur.fetchone()["client_id"]


def test_namesakes_are_separate_cards_with_birth_year(db):
    conn, cur = db
    father = add_result(cur, 21.1, 1, "1980-03-09")
    add_result(cur, 10.0, 2, "1980-03-09")
    son = add_result(cur, 1.0, 3, "2013-12-20")
    conn.commit()

    found = {c["client_id"]: c for c in db_athletes.search_clients_optimized(SUR)}
    assert set(found) == {father, son}
    assert found[father] == {"client_id": father, "surname": SUR, "name": "Александр",
                             "birth_year": "1980", "events_count": 2}
    assert found[son]["birth_year"] == "2013" and found[son]["events_count"] == 1


def test_profile_by_card_has_only_its_results(db):
    conn, cur = db
    father = add_result(cur, 21.1, 1, "1980-03-09")
    son = add_result(cur, 1.0, 3, "2013-12-20")
    conn.commit()

    athlete, results = db_athletes.get_athlete_by_client(son)
    assert athlete["client_id"] == son and athlete["surname"] == SUR and str(athlete["birthday"]) == "2013-12-20"
    assert [r["start_number"] for r in results] == [3]
    assert results[0]["event_name"] == EV and float(results[0]["event_distance"]) == 1.0
    assert athlete["category"] == "М18-49"                       # пол/категория — из последнего результата

    assert db_athletes.get_athlete_by_client(father)[1][0]["start_number"] == 1
    assert db_athletes.get_athlete_by_client(999_999_999) == ({}, [])
