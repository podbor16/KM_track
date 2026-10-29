"""
Отмена действий «Качества данных» на реальной БД (локальный снимок, .env.local) с триггерами:
склейка → отмена (карточка с прежним id, заявки/результаты на местах), порядок отмен,
удалённый «Not started» → обратно с прежним id и карточкой, «Исправить ФИО» и решение → отмена.
Тестовые данные — на событиях 2099 года, убираются после теста.
"""

import datetime
import random

import pytest

from src.analytics import data_quality as dq
from src.analytics.db_pool import get_pooled_connection

# суффикс прогона: параллельные прогоны не убирают данные друг друга
RUN = "".join(random.choice("бвгджзклмнпрстф") for _ in range(4))
EV, SUR, USER = f"Тест отмены {RUN}", f"Тестотменов{RUN}", f"test-undo-{RUN}"
KEY = f"TEST-UNDO-{RUN}"


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
        cur.execute("DELETE FROM clients WHERE surname = %s OR name = %s", (SUR, SUR))     # и «Иван <SUR>»
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

    surv, aid = dq.merge_cards(conn, [a, b], SUR, "Иван", "1980-03-09", USER, f"{KEY}::merge")
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
    aid = dq.delete_result(conn, r_dns, USER, f"{KEY}::dup")
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
    _, aid = dq.fix_fio(conn, rid, SUR, "Иван", USER, f"{KEY}::hyg")
    cur.execute("SELECT surname, name FROM results WHERE id = %s", (rid,))
    assert cur.fetchone() == {"surname": SUR, "name": "Иван"}
    dq.undo_action(conn, aid, USER)
    cur.execute("SELECT surname, name FROM results WHERE id = %s", (rid,))
    assert cur.fetchone() == {"surname": "Иван", "name": SUR}

    did = dq.dismiss(conn, f"{KEY}::keep", "keep", "", USER)
    assert f"{KEY}::keep" in dq.load_decisions(conn)
    dq.undo_action(conn, did, USER)
    assert f"{KEY}::keep" not in dq.load_decisions(conn)


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
    _, aid = dq.edit_record(conn, "results", rid, {"birthday": "2014-12-12", "category": "Д7"}, USER, f"{KEY}::card")
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

    to, aid = dq.move_row(conn, "results", r_moved, USER, f"{KEY}::move", to_client_id=girl)
    assert to == girl and owner(cur, "results", r_moved) == {"client_id": girl, "birthday": datetime.date(1900, 1, 1)}
    assert card(cur, wrong) is None                                          # опустела — удалена
    assert card(cur, girl)["last_result_id"] == max(r_own, r_moved)
    journal = {x["id"]: x for x in dq.recent_actions(conn, 10)}
    assert f"пустая карточка #{wrong} удалена" in journal[aid]["text"]
    with pytest.raises(ValueError, match="результат уже на этой карточке"):
        dq.move_row(conn, "results", r_moved, USER, to_client_id=girl)

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
        dq.move_row(conn, "results", r2, USER, new_card={"surname": SUR, "name": "Иван", "birthday": "1980-03-09"})
    to, aid = dq.move_row(conn, "results", r2, USER, new_card={"surname": SUR, "name": "Иван", "birthday": "1981-03-09"})
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


def test_move_lead_restores_contacts_on_undo(db):
    conn, cur = db
    e1 = event(cur, 1.0)
    _, kid = result(cur, e1, 5, "2017-04-15", name="Иван")
    lid, parent = lead(cur, e1, "1994-06-30", phone="+70000000009")       # заявка ребёнка на карточке родителя
    conn.commit()
    cur.execute("UPDATE clients SET phone = '+70000000001', email = 'kid@test.ru' WHERE id = %s", (kid,))
    conn.commit()
    before = {i: card(cur, i) for i in (kid, parent)}
    to, aid = dq.move_row(conn, "leads", lid, USER, f"{KEY}::lead", to_client_id=kid)
    assert to == kid and owner(cur, "leads", lid)["client_id"] == kid
    assert card(cur, parent) is None                                       # у родителя больше ничего — удалена
    assert card(cur, kid)["count_leads"] == 1 and card(cur, kid)["phone"] == "+70000000009"   # триггер заявок
    journal = {x["id"]: x for x in dq.recent_actions(conn, 10)}
    assert journal[aid]["text"].startswith(f"Перенос заявки #{lid}")
    dq.undo_action(conn, aid, USER)
    assert {i: card(cur, i) for i in (kid, parent)} == before and owner(cur, "leads", lid)["client_id"] == parent
    with pytest.raises(ValueError, match="не поддерживается"):
        dq.move_row(conn, "clients", kid, USER, to_client_id=parent)



def test_move_with_align_sets_row_fio_bd_of_target_and_undo(db):
    conn, cur = db
    e1 = event(cur, 1.0)
    rid, father = result(cur, e1, 1012, "1980-03-09", name="Александр")
    _, son = result(cur, event(cur, 5.0), 1141, "2013-12-20", name="Саша")
    conn.commit()
    to, aid = dq.move_row(conn, "results", rid, USER, "k", to_client_id=son, align=True)
    cur.execute("SELECT client_id, surname, name, birthday FROM results WHERE id = %s", (rid,))
    assert cur.fetchone() == {"client_id": son, "surname": SUR, "name": "Саша", "birthday": datetime.date(2013, 12, 20)}
    dq.undo_action(conn, aid, USER)
    cur.execute("SELECT client_id, name, birthday FROM results WHERE id = %s", (rid,))
    assert cur.fetchone() == {"client_id": father, "name": "Александр", "birthday": datetime.date(1980, 3, 9)}


def test_category_change_sets_neighbor_rank_and_undo(db):
    conn, cur = db
    ev = event(cur, 5.0)
    rows = []
    for bib, cat, mins in ((1, "М18-29", 24), (2, "М30-39", 21), (3, "М30-39", 23), (4, "М18-29", 22)):
        rid, _ = result(cur, ev, bib, f"1990-01-0{bib}", name=f"Иван{bib}")
        cur.execute("""UPDATE results SET category = %s, time_gun_finish = SEC_TO_TIME(%s), rank_category = %s
                       WHERE id = %s""", (cat, mins * 60, {1: 2, 2: 1, 3: 2, 4: 1}[bib], rid))
        rows.append(rid)
    conn.commit()
    # №4 (22 мин) переводим в М30-39: сосед снизу — №3 (23 мин, место 2) → №4 получает место 2
    _, aid = dq.edit_record(conn, "results", rows[3], {"category": "М30-39"}, USER)
    cur.execute("SELECT category, rank_category FROM results WHERE id = %s", (rows[3],))
    assert cur.fetchone() == {"category": "М30-39", "rank_category": 2}
    cur.execute("SELECT rank_category FROM results WHERE id IN (%s, %s) ORDER BY id", (rows[1], rows[2]))
    assert [r["rank_category"] for r in cur.fetchall()] == [1, 2]            # остальных не трогаем
    dq.undo_action(conn, aid, USER)
    cur.execute("SELECT category, rank_category FROM results WHERE id = %s", (rows[3],))
    assert cur.fetchone() == {"category": "М18-29", "rank_category": 1}


def test_postponed_decision_and_undo(db):
    conn, cur = db
    did = dq.dismiss(conn, f"{KEY}::postpone", "postponed", "не знаю ДР", USER)
    assert dq.load_decisions(conn)[f"{KEY}::postpone"] == "postponed"
    journal = {x["id"]: x for x in dq.recent_actions(conn, 10)}
    assert journal[did]["text"] == "Решение: отложено (не знаю ДР)"
    dq.undo_action(conn, did, USER)
    assert f"{KEY}::postpone" not in dq.load_decisions(conn)


def _runners(cur, ev, spec):
    """spec: (sex, category, мин гонга, мин чистого|None, rank_category, rank_category_clean, rank_sex) -> [id]."""
    ids = []
    for i, (sex, cat, gun, clean, rc, rcc, rs) in enumerate(spec, 1):
        rid, _ = result(cur, ev, i, f"1990-01-0{i}", name=f"Иван{i}")
        cur.execute("""UPDATE results SET sex = %s, category = %s, time_gun_finish = SEC_TO_TIME(%s),
                       time_clear_finish = SEC_TO_TIME(%s), rank_category = %s, rank_category_clean = %s, rank_sex = %s
                       WHERE id = %s""", (sex, cat, gun * 60, clean * 60 if clean else None, rc, rcc, rs, rid))
        ids.append(rid)
    return ids


def ranks(cur, rid):
    cur.execute("""SELECT rank_category, rank_category_clean, rank_sex, rank_sex_clean FROM results WHERE id = %s""",
                (rid,))
    return cur.fetchone()


def test_sex_change_sets_rank_sex_only(db):
    conn, cur = db
    m, w = "Мужчина", "Женщина"
    ids = _runners(cur, event(cur, 5.0), ((m, "Абсолют", 24, None, 4, None, 2), (w, "Абсолют", 21, None, 1, None, 1),
                                          (w, "Абсолют", 23, None, 3, None, 2), (m, "Абсолют", 22, None, 2, None, 1)))
    conn.commit()
    _, aid = dq.edit_record(conn, "results", ids[3], {"sex": w}, USER)
    assert ranks(cur, ids[3]) == {"rank_category": 2, "rank_category_clean": None, "rank_sex": 2, "rank_sex_clean": None}
    dq.undo_action(conn, aid, USER)
    assert ranks(cur, ids[3])["rank_sex"] == 1


def test_category_change_in_race_without_places_creates_none(db):
    conn, cur = db
    ids = _runners(cur, event(cur, 5.0), (("Мужчина", "М18-29", 20, 20, None, None, None),
                                          ("Мужчина", "М30-39", 21, 21, None, None, None)))
    conn.commit()
    dq.edit_record(conn, "results", ids[0], {"category": "М30-39"}, USER)
    assert ranks(cur, ids[0]) == {"rank_category": None, "rank_category_clean": None, "rank_sex": None,
                                  "rank_sex_clean": None}


def test_empty_category_with_places_in_race_is_first(db):
    conn, cur = db
    ids = _runners(cur, event(cur, 5.0), (("Мужчина", "М18-29", 20, 20, 1, 1, 1),
                                          ("Мужчина", "М30-39", 21, 21, 1, 1, 2),
                                          ("Мужчина", "М30-39", 23, 22, 3, 3, 3)))
    conn.commit()
    _, aid = dq.edit_record(conn, "results", ids[2], {"category": "М60-69"}, USER)
    assert ranks(cur, ids[2])["rank_category"] == 1 and ranks(cur, ids[2])["rank_category_clean"] == 1
    journal = {x["id"]: x for x in dq.recent_actions(conn, 10)}
    assert "место в категории 3 → 1" in journal[aid]["text"]
    dq.undo_action(conn, aid, USER)
    assert ranks(cur, ids[2])["rank_category"] == 3 and ranks(cur, ids[2])["rank_category_clean"] == 3


def test_undo_decision_restores_previous(db):
    conn, cur = db
    key = f"{KEY}::prev"
    dq.dismiss(conn, key, "postponed", "не знаю ДР", USER)
    did = dq.dismiss(conn, key, "keep", "", USER)
    assert dq.load_decisions(conn)[key] == "keep"
    dq.undo_action(conn, did, USER)
    assert dq.load_decisions(conn)[key] == "postponed"
    cur.execute("SELECT note FROM dq_decisions WHERE finding_key = %s", (key,))
    assert cur.fetchone()["note"] == "не знаю ДР"


def test_undo_earlier_decision_blocked_by_later(db):
    conn, cur = db
    key = f"{KEY}::order"
    d1 = dq.dismiss(conn, key, "postponed", "", USER)
    d2 = dq.dismiss(conn, key, "keep", "", USER)
    with pytest.raises(ValueError, match=f"#{d2}"):
        dq.undo_action(conn, d1, USER)
    journal = {x["id"]: x for x in dq.recent_actions(conn, 10)}
    assert journal[d1]["can_undo"] is False and f"#{d2}" in journal[d1]["why_not"]
    dq.undo_action(conn, d2, USER)
    dq.undo_action(conn, d1, USER)
    assert key not in dq.load_decisions(conn)
