"""
Отмена действий «Качества данных» на реальной БД (локальный снимок, .env.local) с триггерами:
склейка → отмена (карточка с прежним id, заявки/результаты на местах), порядок отмен,
удалённый «Not started» → обратно с прежним id и карточкой, «Исправить ФИО» и решение → отмена.
Тестовые данные — на событиях 2099 года, убираются после теста.
"""

import datetime

import pytest

from src.analytics import data_quality as dq
from src.analytics.db_pool import get_pooled_connection

EV, SUR, USER = "Тест отмены", "Тестотменов", "test-undo"


@pytest.fixture
def db():
    conn = get_pooled_connection()
    if not conn:
        pytest.skip("Нет локальной БД")
    cur = conn.cursor(dictionary=True)
    cur.execute("SHOW TABLES LIKE 'dq_actions'")
    if not cur.fetchone():
        conn.close()
        pytest.skip("Миграция add_data_quality_tables не применена")

    def cleanup():
        cur.execute("SELECT id FROM events WHERE event_name = %s", (EV,))
        evs = [r["id"] for r in cur.fetchall()]
        if evs:
            ph = ",".join(map(str, evs))
            cur.execute(f"DELETE FROM results WHERE event_id IN ({ph})")
            cur.execute(f"DELETE FROM leads WHERE event_id IN ({ph})")
            cur.execute(f"DELETE FROM events WHERE id IN ({ph})")
        cur.execute("DELETE FROM clients WHERE surname = %s", (SUR,))
        cur.execute("DELETE FROM dq_actions WHERE done_by = %s", (USER,))
        cur.execute("DELETE FROM dq_decisions WHERE decided_by = %s", (USER,))
        conn.commit()

    cleanup()
    yield conn, cur
    cleanup()
    cur.close()
    conn.close()


def event(cur, dist):
    cur.execute("INSERT INTO events (event_name, event_distance, event_year) VALUES (%s, %s, 2099)", (EV, dist))
    return cur.lastrowid


def result(cur, ev, bib, bd, status="Finished", surname=SUR, name="Иван"):
    cur.execute("""INSERT INTO results (surname, name, birthday, client_id, event_id, sex, start_number, race_status)
                   VALUES (%s, %s, %s, 0, %s, 'Мужчина', %s, %s)""", (surname, name, bd, ev, bib, status))
    rid = cur.lastrowid
    cur.execute("SELECT client_id FROM results WHERE id = %s", (rid,))
    return rid, cur.fetchone()["client_id"]


def lead(cur, ev, bd, bib=None, phone="+70000000001"):
    cur.execute("""INSERT INTO leads (surname, name, sex, city, birthday, phone, email, event_name, event_distance,
                   event_year, products, amount, client_id, event_id, start_number, created_at)
                   VALUES (%s, 'Иван', 'Мужчина', '', %s, %s, 'undo@test.ru', %s, '5', 2099, '', 0, 0, %s, %s,
                           '2026-01-01 10:00:00')""", (SUR, bd, phone, EV, ev, bib))
    lid = cur.lastrowid
    cur.execute("SELECT client_id FROM leads WHERE id = %s", (lid,))
    return lid, cur.fetchone()["client_id"]


def card(cur, cid):
    cur.execute("""SELECT id, surname, name, birthday, phone, email, count_leads, last_result_id
                   FROM clients WHERE id = %s""", (cid,))
    return cur.fetchone()


def owner(cur, table, row_id):
    cur.execute(f"SELECT client_id, birthday FROM {table} WHERE id = %s", (row_id,))
    return cur.fetchone()


def test_merge_undo_restores_cards_leads_and_results(db):
    conn, cur = db
    e1, e2 = event(cur, 21.1), event(cur, 1.0)
    lid, a = lead(cur, e1, "1980-03-09")
    r1, a2 = result(cur, e1, 501, "1980-03-09")
    r2, b = result(cur, e2, 1012, "1900-01-01")
    conn.commit()
    assert a == a2 and a != b
    before = {i: card(cur, i) for i in (a, b)}

    surv, aid = dq.merge_cards(conn, [a, b], SUR, "Иван", "1980-03-09", USER, "TEST-UNDO::merge")
    assert surv == a and card(cur, b) is None and owner(cur, "results", r2)["client_id"] == a

    dq.undo_action(conn, aid, USER)
    assert {i: card(cur, i) for i in (a, b)} == before
    assert owner(cur, "results", r2) == {"client_id": b, "birthday": datetime.date(1900, 1, 1)}
    assert owner(cur, "results", r1)["client_id"] == a and owner(cur, "leads", lid)["client_id"] == a
    with pytest.raises(ValueError, match="уже отменено"):
        dq.undo_action(conn, aid, USER)


def test_undo_order_later_action_first(db):
    conn, cur = db
    e1, e2, e3 = event(cur, 21.1), event(cur, 10.0), event(cur, 5.0)
    _, a = result(cur, e1, 1, "1980-03-09")
    _, b = result(cur, e2, 2, "1900-01-01")
    _, c = result(cur, e3, 3, "1980-01-01")
    conn.commit()
    _, first = dq.merge_cards(conn, [a, b], SUR, "Иван", "1980-03-09", USER)
    _, second = dq.merge_cards(conn, [a, c], SUR, "Иван", "1980-03-09", USER)

    with pytest.raises(ValueError, match=f"#{second}"):
        dq.undo_action(conn, first, USER)
    journal = {x["id"]: x for x in dq.recent_actions(conn, 10)}
    assert journal[second]["can_undo"] and not journal[first]["can_undo"]

    dq.undo_action(conn, second, USER)
    dq.undo_action(conn, first, USER)
    assert all(card(cur, i) for i in (a, b, c))
    journal = {x["id"]: x for x in dq.recent_actions(conn, 10)}
    assert journal[first]["undone"] and journal[second]["undone"]


def test_delete_result_undo_returns_row_with_same_id_and_card(db):
    conn, cur = db
    e1 = event(cur, 5.0)
    r_fin, a = result(cur, e1, 10, "1985-02-02")
    r_dns, a2 = result(cur, e1, 11, "1985-02-02", status="Not started")
    conn.commit()
    assert a == a2
    aid = dq.delete_result(conn, r_dns, USER, "TEST-UNDO::dup")
    assert owner(cur, "results", r_dns) is None

    dq.undo_action(conn, aid, USER)
    cur.execute("SELECT client_id, race_status, start_number FROM results WHERE id = %s", (r_dns,))
    assert cur.fetchone() == {"client_id": a, "race_status": "Not started", "start_number": 11}
    cur.execute("SELECT COUNT(*) n FROM clients WHERE surname = %s", (SUR,))
    assert cur.fetchone()["n"] == 1                      # триггер вставки не оставил лишней карточки


def test_fix_fio_result_only_and_dismiss_undo(db):
    conn, cur = db
    e1 = event(cur, 5.0)
    lead(cur, e1, "1985-02-02", bib=77)
    rid, cid = result(cur, e1, 77, "1985-02-02", surname="Иван", name=SUR)    # имя и фамилия переставлены
    conn.commit()
    _, aid = dq.fix_fio(conn, rid, SUR, "Иван", USER, "TEST-UNDO::hyg")
    cur.execute("SELECT surname, name FROM results WHERE id = %s", (rid,))
    assert cur.fetchone() == {"surname": SUR, "name": "Иван"}
    dq.undo_action(conn, aid, USER)
    cur.execute("SELECT surname, name FROM results WHERE id = %s", (rid,))
    assert cur.fetchone() == {"surname": "Иван", "name": SUR}

    did = dq.dismiss(conn, "TEST-UNDO::keep", "keep", "", USER)
    assert "TEST-UNDO::keep" in dq.load_decisions(conn)
    dq.undo_action(conn, did, USER)
    assert "TEST-UNDO::keep" not in dq.load_decisions(conn)
