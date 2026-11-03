"""Флаг «не согласен на ПД» на реальной БД (локальный снимок): set_lead_pd_refused ставит/снимает
флаг и пишет в журнал dq_actions. Тестовые записи — событие «Тест ПД» 2099 года, убираются."""
import json

import pytest

from src.analytics.db_pool import get_pooled_connection
from src.analytics.db_results import set_lead_pd_refused

EV = "Тест ПД"


@pytest.fixture
def db():
    conn = get_pooled_connection()
    if not conn:
        pytest.skip("Нет локальной БД")
    cur = conn.cursor(dictionary=True)
    cur.execute("SHOW COLUMNS FROM leads LIKE 'pd_refused'")
    if not cur.fetchone():
        conn.close()
        pytest.skip("Миграция lead_pd_refused не применена")

    def cleanup():
        cur.execute("SELECT id, client_id FROM leads WHERE event_name = %s", (EV,))
        rows = cur.fetchall()
        if rows:
            ids = ",".join(str(r["id"]) for r in rows)
            keys = ",".join(f"'lead:{r['id']}'" for r in rows)
            cur.execute(f"DELETE FROM dq_actions WHERE finding_key IN ({keys})")
            cur.execute(f"DELETE FROM leads WHERE id IN ({ids})")
            cards = ",".join(str(r["client_id"]) for r in rows if r["client_id"])
            if cards:
                cur.execute(f"DELETE FROM clients WHERE id IN ({cards})")
        conn.commit()

    cleanup()
    yield conn, cur
    cleanup()
    cur.close()
    conn.close()


def add_lead(cur):
    cur.execute("""INSERT INTO leads (surname, name, sex, city, club, birthday, email, phone, event_name, event_distance,
                   event_year, products, amount, client_id, event_id, is_duplicate, status, is_new, is_new_event,
                   is_name_suspicious, created_at)
                   VALUES ('Тестпд', 'Иван', 'Мужчина', '', '', '1990-01-01', 'pd@test.ru', '', %s, '5 км', 2099,
                           '', 0, 0, 0, 0, 0, 0, 0, 0, NOW())""", (EV,))
    return cur.lastrowid


def test_set_and_clear_pd_refused_with_journal(db):
    conn, cur = db
    lead = add_lead(cur)
    conn.commit()

    assert set_lead_pd_refused(lead, True, "tester")
    cur.execute("SELECT pd_refused FROM leads WHERE id = %s", (lead,))
    assert cur.fetchone()["pd_refused"] == 1

    assert set_lead_pd_refused(lead, False, "tester")
    cur.execute("SELECT pd_refused FROM leads WHERE id = %s", (lead,))
    assert cur.fetchone()["pd_refused"] == 0

    cur.execute("SELECT action, details, done_by FROM dq_actions WHERE finding_key = %s ORDER BY id", (f"lead:{lead}",))
    log = cur.fetchall()
    assert [r["action"] for r in log] == ["pd_refused", "pd_refused"]
    assert [json.loads(r["details"])["pd_refused"] for r in log] == [1, 0]
    assert {r["done_by"] for r in log} == {"tester"}


def test_unknown_lead_returns_false(db):
    assert not set_lead_pd_refused(10 ** 12, True, "tester")
