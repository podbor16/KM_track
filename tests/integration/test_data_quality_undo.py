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


def test_edit_result_and_card_then_undo(db):
    conn, cur = db
    e1 = event(cur, 1.0)
    r_ok, cid = result(cur, e1, 466, "2014-12-12")
    e2 = event(cur, 0.5)
    rid, cid2 = result(cur, e2, 4102, "2014-01-01")
    conn.commit()
    assert cid != cid2
    cur.execute("SELECT category FROM results WHERE id = %s", (rid,))
    category = cur.fetchone()["category"]
    # R-CARD «в результат — как в карточке»: правится только строка результата
    _, aid = dq.edit_record(conn, "results", rid, {"birthday": "2014-12-12", "category": "Д7"}, USER, "TEST-UNDO::card")
    cur.execute("SELECT birthday, category, client_id FROM results WHERE id = %s", (rid,))
    assert cur.fetchone() == {"birthday": datetime.date(2014, 12, 12), "category": "Д7", "client_id": cid2}
    with pytest.raises(ValueError, match="не изменились"):
        dq.edit_record(conn, "results", rid, {"birthday": "2014-12-12"}, USER)
    journal = {x["id"]: x for x in dq.recent_actions(conn, 10)}
    assert "ДР 2014-01-01 → 2014-12-12" in journal[aid]["text"]
    dq.undo_action(conn, aid, USER)
    cur.execute("SELECT birthday, category FROM results WHERE id = %s", (rid,))
    assert cur.fetchone() == {"birthday": datetime.date(2014, 1, 1), "category": category}

    # карточка: ФИ+ДР другой карточки — нельзя (это склейка); своя правка — отменяется
    with pytest.raises(ValueError, match=f"#{cid}"):
        dq.edit_record(conn, "clients", cid2, {"birthday": "2014-12-12"}, USER)
    _, cid_aid = dq.edit_record(conn, "clients", cid2, {"birthday": "2014-12-13"}, USER)
    assert card(cur, cid2)["birthday"] == datetime.date(2014, 12, 13)
    dq.undo_action(conn, cid_aid, USER)
    assert card(cur, cid2)["birthday"] == datetime.date(2014, 1, 1)


def test_edit_lead_distance_moves_to_same_race_event_and_undo(db):
    conn, cur = db
    e5, e10 = event(cur, 5.0), event(cur, 10.0)
    lid, cid = lead(cur, e5, "2018-05-05")
    conn.commit()
    _, aid = dq.edit_record(conn, "leads", lid, {"event_distance": "10 км", "birthday": "2019-05-05"}, USER)
    cur.execute("SELECT event_id, event_distance, birthday FROM leads WHERE id = %s", (lid,))
    assert cur.fetchone() == {"event_id": e10, "event_distance": "10 км", "birthday": datetime.date(2019, 5, 5)}
    with pytest.raises(ValueError, match="нет дистанции"):
        dq.edit_record(conn, "leads", lid, {"event_distance": "42.2"}, USER)
    dq.undo_action(conn, aid, USER)
    cur.execute("SELECT event_id, event_distance, birthday FROM leads WHERE id = %s", (lid,))
    assert cur.fetchone() == {"event_id": e5, "event_distance": "5", "birthday": datetime.date(2018, 5, 5)}


def test_edit_validation(db):
    conn, cur = db
    rid, _ = result(cur, event(cur, 5.0), 1, "1990-01-01")
    conn.commit()
    for fields, msg in (({"birthday": "01.01.1990"}, "ГГГГ-ММ-ДД"), ({"sex": "М"}, "пол"),
                        ({"surname": " "}, "пустыми"), ({"race_status": "Finished"}, "не правятся"), ({}, "нет полей")):
        with pytest.raises(ValueError, match=msg):
            dq.edit_record(conn, "results", rid, fields, USER)
    cur.execute("UPDATE results SET category = 'М18-29' WHERE id = %s", (rid,))
    conn.commit()
    with pytest.raises(ValueError, match="для пола «Мужчина»"):
        dq.edit_record(conn, "results", rid, {"sex": "Женщина"}, USER)
    with pytest.raises(ValueError, match="для пола «Женщина»"):
        dq.edit_record(conn, "results", rid, {"category": "Ж18-29"}, USER)
    dq.edit_record(conn, "results", rid, {"sex": "Женщина", "category": "Ж18-29"}, USER)
    with pytest.raises(ValueError, match="не поддерживается"):
        dq.edit_record(conn, "events", 1, {"name": "x"}, USER)


def test_move_result_to_existing_card_deletes_empty_source_and_undo(db):
    conn, cur = db
    e1, e2 = event(cur, 1.0), event(cur, 0.5)
    r_own, girl = result(cur, e1, 686, "2016-08-02", name="София")
    r_moved, wrong = result(cur, e2, 6020, "1900-01-01", name="София")       # заглушка ДР — своя карточка
    conn.commit()
    assert girl != wrong
    wrong_before = card(cur, wrong)

    to, aid = dq.move_result(conn, r_moved, USER, "TEST-UNDO::move", to_client_id=girl)
    assert to == girl and owner(cur, "results", r_moved) == {"client_id": girl, "birthday": datetime.date(1900, 1, 1)}
    assert card(cur, wrong) is None                                          # опустела — удалена
    assert card(cur, girl)["last_result_id"] == max(r_own, r_moved)
    journal = {x["id"]: x for x in dq.recent_actions(conn, 10)}
    assert f"пустая карточка #{wrong} удалена" in journal[aid]["text"]
    with pytest.raises(ValueError, match="уже на этой карточке"):
        dq.move_result(conn, r_moved, USER, to_client_id=girl)

    dq.undo_action(conn, aid, USER)
    assert owner(cur, "results", r_moved)["client_id"] == wrong and card(cur, wrong) == wrong_before


def test_move_result_to_new_card_and_undo(db):
    conn, cur = db
    e1, e2 = event(cur, 21.1), event(cur, 10.0)
    r1, cid = result(cur, e1, 1, "1980-03-09")
    r2, cid2 = result(cur, e2, 2, "1980-03-09")                               # тёзки с одной ДР — одна карточка
    lead(cur, e1, "1980-03-09")
    conn.commit()
    assert cid == cid2
    with pytest.raises(ValueError, match=f"#{cid}"):
        dq.move_result(conn, r2, USER, new_card={"surname": SUR, "name": "Иван", "birthday": "1980-03-09"})
    to, aid = dq.move_result(conn, r2, USER, new_card={"surname": SUR, "name": "Иван", "birthday": "1981-03-09"})
    assert to != cid and owner(cur, "results", r2)["client_id"] == to and card(cur, cid)   # у старой остались строки
    assert card(cur, to)["birthday"] == datetime.date(1981, 3, 9)
    dq.undo_action(conn, aid, USER)
    assert owner(cur, "results", r2)["client_id"] == cid and card(cur, to) is None


def test_search_cards_by_fio_any_order(db):
    conn, cur = db
    _, cid = result(cur, event(cur, 5.0), 1, "1990-05-05", name="Софья")
    conn.commit()
    for q in (f"{SUR.lower()} соф", f"Соф {SUR[:5]}", SUR):
        found = {c["id"]: c for c in dq.search_cards(conn, q)}
        assert cid in found, q
    c = found[cid]
    assert c["birthday"] == "1990-05-05" and c["events"] == [f"{EV} 5 2099 (результат)"]
    assert dq.search_cards(conn, "Т") == [] and dq.search_cards(conn, "") == []
