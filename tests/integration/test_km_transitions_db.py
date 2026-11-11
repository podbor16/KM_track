"""km_transitions (migrations/km_transitions.sql) на локальной БД (.env.local): пары «тот же забег» и «любой забег».
Тестовые данные — события 2097–2099 «Тест переходов <суффикс> …», фамилия «Тестпереходов<суффикс>», убираются после теста.
Тест 3 создаёт события с реальным именем «Детский забег» 2097–2098 (убираются фикстурой по заявкам прогона)."""
import uuid

import pytest

from src.analytics.db_pool import get_pooled_connection

RUN = uuid.uuid4().hex[:6].translate(str.maketrans("0123456789abcdef", "бвгджзклмнпрстфх"))
EV, SUR = f"Тест переходов {RUN}", f"Тестпереходов{RUN}"


@pytest.fixture
def db():
    conn = get_pooled_connection()
    if not conn:
        pytest.skip("Нет локальной БД")
    cur = conn.cursor(dictionary=True)
    cur.execute("SHOW PROCEDURE STATUS WHERE Db = DATABASE() AND Name = 'refresh_km_transitions'")
    if not cur.fetchall():
        pytest.fail("Нет процедуры refresh_km_transitions — примените migrations/km_transitions.sql к локальной БД")

    def cleanup():
        cur.execute("SELECT id FROM events WHERE event_name LIKE %s OR id IN (SELECT event_id FROM leads WHERE surname = %s)",
                    (f"{EV}%", SUR))
        evs = [r["id"] for r in cur.fetchall()]
        if evs:
            ph = ",".join(map(str, evs))
            cur.execute(f"DELETE FROM leads WHERE event_id IN ({ph})")
            cur.execute(f"DELETE FROM events WHERE id IN ({ph})")
        cur.execute("DELETE FROM clients WHERE surname = %s", (SUR,))
        conn.commit()

    cleanup()
    yield cur
    cur.execute("DELETE t FROM km_transitions t JOIN clients c ON c.id = t.client_id WHERE c.surname = %s", (SUR,))
    conn.commit()
    cleanup()
    conn.close()


def _event(cur, name, dist, year, date):
    cur.execute("INSERT INTO events (event_name, event_distance, event_year, event_date) VALUES (%s, %s, %s, %s)",
                (name, dist, year, date))
    return cur.lastrowid


def _lead(cur, ev, event_name, dist_str, year, refund=0):
    cur.execute("""INSERT INTO leads (surname, name, sex, city, birthday, phone, email, event_name, event_distance,
                   event_year, products, amount, client_id, event_id, start_number, created_at, refund)
                   VALUES (%s, 'Иван', 'Мужчина', '', '1990-01-01', '+70000000099', 'tr@test.ru', %s, %s,
                           %s, '', 0, 0, %s, NULL, '2026-01-01 10:00:00', %s)""",
                (SUR, event_name, dist_str, year, ev, refund))


def _rows(cur):
    cur.execute("CALL refresh_km_transitions()")
    cur.execute("""SELECT t.* FROM km_transitions t JOIN clients c ON c.id = t.client_id
                   WHERE c.surname = %s ORDER BY t.event_year, t.event_name""", (SUR,))
    return cur.fetchall()


def test_same_event_pairs_take_longest_distance_and_skip_refunds(db):
    a = f"{EV} A"
    a97_2, a97_7 = _event(db, a, "2", 2097, "2097-12-06"), _event(db, a, "7", 2097, "2097-12-06")
    a98_2 = _event(db, a, "2", 2098, "2098-12-06")
    a99_7 = _event(db, a, "7", 2099, "2099-12-06")
    _lead(db, a97_2, a, "2 км", 2097)
    _lead(db, a97_7, a, "7 км", 2097)            # две дистанции в 2097 → берётся 7
    _lead(db, a98_2, a, "2 км", 2098)
    _lead(db, a99_7, a, "7 км", 2099, refund=1)  # возврат — участия нет
    rows = _rows(db)
    assert [(r["event_year"], float(r["dist"]), r["event_distance"]) for r in rows] == [(2097, 7.0, "7 км"), (2098, 2.0, "2 км")]
    first, second = rows
    assert first["same_direction"] == "Впервые на забеге" and first["same_prev_year"] is None
    assert second["same_prev_year"] == 2097 and float(second["same_prev_dist"]) == 7.0
    assert second["same_direction"] == "Сократили"


def test_any_event_pair_crosses_events(db):
    kids, b = f"{EV} Детский забег", f"{EV} B"
    k = _event(db, kids, "1", 2097, "2097-06-01")
    b1 = _event(db, b, "2", 2097, "2097-08-01")
    b2 = _event(db, b, "5", 2098, "2098-08-01")
    _lead(db, k, kids, "1 км", 2097)
    _lead(db, b1, b, "2 км", 2097)
    _lead(db, b2, b, "5 км", 2098)
    rows = {(r["event_name"], r["event_year"]): r for r in _rows(db)}
    b97, b98 = rows[(b, 2097)], rows[(b, 2098)]
    assert (b97["any_prev_event"], b97["any_prev_year"], float(b97["any_prev_dist"])) == (kids, 2097, 1.0)
    assert b98["same_direction"] == "Выросли" and b98["any_prev_event"] == b


def test_kids_race_has_no_same_event_pair(db):
    kids = "Детский забег"
    # реальное название забега: правило «Детский забег → пары тот же забег нет» привязано к нему
    k1 = _event(db, kids, "0.5", 2097, "2097-06-01")
    k2 = _event(db, kids, "1", 2098, "2098-06-01")
    _lead(db, k1, kids, "500 м", 2097)
    _lead(db, k2, kids, "1 км", 2098)
    rows = [r for r in _rows(db) if r["event_name"] == kids]
    assert [r["same_direction"] for r in rows] == [None, None]
    assert all(r["same_prev_year"] is None and r["same_prev_dist"] is None for r in rows)
    assert rows[1]["any_prev_event"] == kids          # пара «любой забег» есть


def test_multi_distance_count_and_list_per_year(db):
    """Мультидистанции (2026-11-11): сколько разных дистанций человек бежал на забеге в году и какие — по возрастанию."""
    c = f"{EV} C"
    c2, c10, c5 = _event(db, c, "2", 2097, "2097-12-06"), _event(db, c, "10", 2097, "2097-12-06"), _event(db, c, "5", 2097, "2097-12-06")
    c98 = _event(db, c, "5", 2098, "2098-12-06")
    _lead(db, c10, c, "10 км", 2097)
    _lead(db, c2, c, "2 км", 2097)
    _lead(db, c5, c, "5 км", 2097, refund=1)     # возврат — не считается
    _lead(db, c98, c, "5 км", 2098)
    rows = _rows(db)
    assert [(r["event_year"], r["n_dist"], r["distances"]) for r in rows] == [(2097, 2, "2 км + 10 км"), (2098, 1, "5 км")]
