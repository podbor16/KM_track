"""club_names (migrations/club_names.sql) на локальной БД (.env.local): написание клуба → клуб для DataLens.
Тестовые данные — событие 2099 «Тест клубов <суффикс>», фамилия «Тестклубов<суффикс>», убираются после теста."""
import uuid

import pytest

from src.analytics.db_pool import get_pooled_connection

RUN = uuid.uuid4().hex[:6].translate(str.maketrans("0123456789abcdef", "бвгджзклмнпрстфх"))
EV, SUR = f"Тест клубов {RUN}", f"Тестклубов{RUN}"


@pytest.fixture
def db():
    conn = get_pooled_connection()
    if not conn:
        pytest.skip("Нет локальной БД")
    cur = conn.cursor(dictionary=True)
    cur.execute("SHOW PROCEDURE STATUS WHERE Db = DATABASE() AND Name = 'refresh_club_names'")
    if not cur.fetchall():
        pytest.fail("Нет процедуры refresh_club_names — примените migrations/club_names.sql к локальной БД")

    def cleanup():
        cur.execute("SELECT id FROM events WHERE event_name = %s", (EV,))
        evs = [r["id"] for r in cur.fetchall()]
        if evs:
            ph = ",".join(map(str, evs))
            cur.execute(f"DELETE FROM leads WHERE event_id IN ({ph})")
            cur.execute(f"DELETE FROM events WHERE id IN ({ph})")
        cur.execute("DELETE FROM clients WHERE surname = %s", (SUR,))
        conn.commit()

    cleanup()
    cur.execute("INSERT INTO events (event_name, event_distance, event_year, event_date) VALUES (%s, 5, 2099, '2099-06-01')", (EV,))
    ev = cur.lastrowid

    def lead(name, club):
        cur.execute("""INSERT INTO leads (surname, name, sex, city, birthday, phone, email, event_name, event_distance,
                       event_year, products, amount, client_id, event_id, start_number, created_at, club)
                       VALUES (%s, %s, 'Мужчина', '', '1990-01-01', '+70000000098', 'cl@test.ru', %s, '5 км',
                               2099, '', 0, 0, %s, NULL, '2026-01-01 10:00:00', %s)""", (SUR, name, EV, ev, club))
    yield cur, lead
    cleanup()
    cur.execute("CALL refresh_club_names()")
    conn.commit()
    conn.close()


def _name(cur, club):
    cur.execute("CALL refresh_club_names()")
    cur.execute("SELECT club_name FROM club_names WHERE club = %s", (club,))
    row = cur.fetchone()
    assert row is not None, f"нет строки для {club!r}"
    return row["club_name"]


def test_spelling_variants_get_most_common_spelling(db):
    cur, lead = db
    for i in range(3):
        lead(f"Иван{i}", f"Тест Клуб {RUN}")
    lead("Петр", f"тестклуб{RUN}")
    lead("Олег", f"Тест-Клуб {RUN}!")
    assert _name(cur, f"тестклуб{RUN}") == f"Тест Клуб {RUN}"
    assert _name(cur, f"Тест-Клуб {RUN}!") == f"Тест Клуб {RUN}"


def test_merge_rules_and_not_a_club(db):
    cur, lead = db
    lead("Анна", f"Supersport {RUN}")
    lead("Мария", f"I Love Triathlon {RUN}")
    lead("Ольга", f"Полюс Магадан {RUN}")
    lead("Ирина", f"Профсоюз РН-Ванкор {RUN}")
    assert _name(cur, f"Supersport {RUN}") == "I Love Supersport"
    assert _name(cur, f"I Love Triathlon {RUN}") == "I Love Supersport"
    assert _name(cur, f"Полюс Магадан {RUN}") == "Полюс"
    assert _name(cur, f"Профсоюз РН-Ванкор {RUN}") == "РН-Ванкор"


def test_not_a_club_values_map_to_null(db):
    cur, lead = db
    cur.execute("CALL refresh_club_names()")
    cur.execute("""SELECT club, club_name FROM club_names
                   WHERE club_key IN ('noclub', 'лично', 'красноярск', 'нет', 'безклуба', '')""")
    rows = cur.fetchall()
    assert rows, "в снимке БД должны быть служебные значения клуба"
    assert all(r["club_name"] is None for r in rows)
