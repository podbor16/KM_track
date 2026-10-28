"""Ответы на вопросы дел на локальной БД (.env.local): цепочки, отложить, устаревший вопрос, «живой» забег.
Тестовые данные — события 2099 года, фамилия «Тестделов», убираются после теста."""
import datetime

import pytest

from src.analytics import dq_cases
from src.analytics import data_quality as dq
from src.analytics.db_pool import get_pooled_connection

EV, SUR, USER = "Тест дел", "Тестделов", "test-cases"


@pytest.fixture
def db():
    conn = get_pooled_connection()
    if not conn:
        pytest.skip("Нет локальной БД")
    cur = conn.cursor(dictionary=True)

    def cleanup():
        # тестовые события: «Тест дел …» и переименованные в «Детский забег» — только 2099 года
        cur.execute("SELECT id FROM events WHERE event_year = 2099 AND (event_name LIKE %s OR event_name = 'Детский забег')",
                    (f"{EV}%",))
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


def event(cur, name, dist, year=2099, date=None):
    cur.execute("INSERT INTO events (event_name, event_distance, event_year, event_date) VALUES (%s, %s, %s, %s)",
                (f"{EV} {name}", dist, year, date))
    return cur.lastrowid


def result(cur, ev, bib, bd, name="Александр", cat="М18-49"):
    cur.execute("""INSERT INTO results (surname, name, birthday, client_id, event_id, sex, start_number, category,
                   race_status) VALUES (%s, %s, %s, 0, %s, 'Мужчина', %s, %s, 'Finished')""", (SUR, name, bd, ev, bib, cat))
    rid = cur.lastrowid
    cur.execute("SELECT client_id FROM results WHERE id = %s", (rid,))
    return rid, cur.fetchone()["client_id"]


def foreign_case(conn, cur):
    """Пцаревы в миниатюре: детский результат на карточке отца, сын — отдельной карточкой.
    Взрослый результат отца — без категории: 1980 г.р. в 2099 не подходит ни к одной (была бы вторая R-FOREIGN)."""
    _, father = result(cur, event(cur, "Жара", 21.1), 1, "1980-03-09", cat="")
    rid, _ = result(cur, event(cur, "Детский", 1.0), 1012, "1980-03-09", cat="Мальчики 2005 г.р. и младше")
    cur.execute("UPDATE events SET event_name = 'Детский забег' WHERE id = (SELECT event_id FROM results WHERE id = %s)", (rid,))
    _, son = result(cur, event(cur, "Детский 2", 1.0), 1141, "2093-12-20", name="Саша", cat="Мальчики")
    conn.commit()
    return rid, father, son


def test_answer_foreign_moves_and_aligns_then_case_has_no_question(db):
    conn, cur = db
    rid, father, son = foreign_case(conn, cur)
    case = dq_cases.case_for_card(conn, father)
    q = next(q for q in case["questions"] if q["code"] == "R-FOREIGN")
    assert q["answers"][0]["id"] == f"to:{son}"
    out = dq_cases.apply_answer(conn, case["key"], q["id"], f"to:{son}", {}, USER)
    assert out["action_ids"]
    cur.execute("SELECT client_id, name, birthday FROM results WHERE id = %s", (rid,))
    assert cur.fetchone() == {"client_id": son, "name": "Саша", "birthday": datetime.date(2093, 12, 20)}
    assert out["case"] is None          # других вопросов у дела нет — дело закрыто


def test_stale_question_raises(db):
    conn, cur = db
    rid, father, son = foreign_case(conn, cur)
    case = dq_cases.case_for_card(conn, father)
    q = next(q for q in case["questions"] if q["code"] == "R-FOREIGN")
    dq_cases.apply_answer(conn, case["key"], q["id"], f"to:{son}", {}, USER)
    with pytest.raises(dq_cases.StaleQuestion):
        dq_cases.apply_answer(conn, case["key"], q["id"], f"to:{son}", {}, USER)


def test_unknown_answer_raises(db):
    conn, cur = db
    rid, father, son = foreign_case(conn, cur)
    case = dq_cases.case_for_card(conn, father)
    q = next(q for q in case["questions"] if q["code"] == "R-FOREIGN")
    with pytest.raises(ValueError, match="неизвестный ответ"):
        dq_cases.apply_answer(conn, case["key"], q["id"], f"to:{father}", {}, USER)


def test_card_from_row_conflict_offers_merge(db):
    conn, cur = db
    ev = event(cur, "Конфликт", 5.0)
    _, a = result(cur, ev, 1, "2093-12-12", name="Елизавета")
    rid, b = result(cur, event(cur, "Конфликт 2", 5.0), 2, "2093-01-01", name="Елизавета")
    cur.execute("UPDATE results SET client_id = %s WHERE id = %s", (a, rid))   # строка 2093-01-01 — на карточке A
    conn.commit()
    case = dq_cases.case_for_card(conn, a)
    q = next(q for q in case["questions"] if q["code"] == "R-CARD" and q["result_id"] == rid)
    out = dq_cases.apply_answer(conn, case["key"], q["id"], "card_from_row", {}, USER)
    assert out["conflict"]["merge_with"] == b and "Склеить" in out["conflict"]["message"]
    out = dq_cases.apply_answer(conn, case["key"], q["id"], f"merge_with:{b}",
                                {"surname": SUR, "name": "Елизавета", "birthday": "2093-12-12"}, USER)
    cur.execute("SELECT COUNT(*) n FROM clients WHERE id IN (%s, %s)", (a, b))
    assert cur.fetchone()["n"] == 1


def test_two_finishes_new_card_takes_chosen_row(db):
    conn, cur = db
    ev = event(cur, "Два финиша", 5.0)
    first, cid = result(cur, ev, 1, "1990-05-05", cat="")
    second, same = result(cur, ev, 2, "1990-05-05", cat="")
    _, other = result(cur, event(cur, "Другой", 5.0), 3, "1991-01-02", name="Борис", cat="")
    conn.commit()
    assert same == cid
    case = dq_cases.case_for_card(conn, cid)
    q = next(q for q in case["questions"] if q["code"] == "R-DUP")
    new = {"surname": SUR, "name": "Алексей", "birthday": "1990-05-05"}
    with pytest.raises(ValueError, match="финиш этой карточки"):
        dq_cases.apply_answer(conn, case["key"], q["id"], "new", {**new, "row_id": str(other)}, USER)
    dq_cases.apply_answer(conn, case["key"], q["id"], "new", {**new, "row_id": str(second)}, USER)
    cur.execute("SELECT id, client_id, name FROM results WHERE id IN (%s, %s) ORDER BY id", (first, second))
    a, b = cur.fetchall()
    assert a["client_id"] == cid and b["client_id"] != cid and b["name"] == "Алексей"


def test_live_race_hides_and_rejects_field_answers(db):
    conn, cur = db
    rid, cid = result(cur, event(cur, "Живой", 5.0, date=dq_cases._today()), 1, "1990-05-05", cat="")
    cur.execute("UPDATE results SET birthday = '1990-01-01' WHERE id = %s", (rid,))
    conn.commit()
    case = dq_cases.case_for_card(conn, cid)
    q = next(q for q in case["questions"] if q["code"] == "R-CARD")
    assert q["live"] and not {a["id"] for a in q["answers"]} & dq_cases.FIELD_ANSWERS
    with pytest.raises(ValueError, match="загружается"):
        dq_cases.apply_answer(conn, case["key"], q["id"], "row_from_card", {}, USER)


def test_postpone_case_moves_it_to_postponed_and_back_on_undo(db):
    conn, cur = db
    rid, father, son = foreign_case(conn, cur)
    key = dq_cases.case_for_card(conn, father)["key"]
    ids = dq_cases.postpone_case(conn, key, "не знаю ДР", USER)
    assert ids and key not in {c["key"] for c in dq_cases.list_cases(conn, "open")}
    assert key in {c["key"] for c in dq_cases.list_cases(conn, "postponed")}
    for aid in ids:
        dq.undo_action(conn, aid, USER)
    assert key in {c["key"] for c in dq_cases.list_cases(conn, "open")}
