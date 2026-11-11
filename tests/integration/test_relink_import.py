"""Импорт Excel Tilda (bulk_import_leads) и перепривязка: исправленные ФИ/ДР по тому же order_id переносят заявку
на верную карточку (журнал relink:import), удаления «файл — источник истины» пишутся в журнал dq_actions.
Тестовые данные — как в test_relink.py (событие «Тест перепривязка» 2099, *@relink-test.local)."""
import json

from src.analytics.db_results import bulk_import_leads
from src.krasmarafon.services.tilda_import_parser import ImportRow
from tests.integration.test_relink import (  # noqa: F401  (фикстуры)
    BD_DAUGHTER, BD_MAMA, BD_PHANTOM, DOMAIN, EV, SURNAME, USER, add_lead, card, db, journal, row_state, world,
)

ORDER_A, ORDER_B = 2099000001, 2099000002


def set_order(conn, cur, lead_id, order_id):
    """Только по id своей тестовой заявки."""
    where = f"id = {int(lead_id)} AND event_name = '{EV}'"
    cur.execute(f"SELECT COUNT(*) n FROM leads WHERE {where}")
    assert cur.fetchone()["n"] == 1
    cur.execute(f"UPDATE leads SET order_id = %s WHERE {where}", (order_id,))
    conn.commit()


def import_row(order_id, name, birthday, surname=SURNAME, num=9003):
    return ImportRow(row_number=2, surname=surname, name=name, birthday=str(birthday), event_name=EV, event_year=2099,
                     event_distance="5 км", sex="Мужчина", email=f"{num}@{DOMAIN}", order_id=str(order_id),
                     start_number=str(num))


def test_import_with_corrected_birthday_relinks_lead_and_reports(db, world):
    conn, cur = db
    lead = add_lead(cur, "Мама", BD_MAMA, 9003)             # заявка ушла на «мамину» карточку по ошибочным ФИ+ДР
    conn.commit()
    assert lead["client_id"] == world["cm"]
    set_order(conn, cur, lead["id"], ORDER_A)

    res = bulk_import_leads([import_row(ORDER_A, "Дочь", BD_DAUGHTER)], scope=(EV, 2098), user=USER)

    assert res["errors"] == []
    assert res["updated"] == 1
    assert res["relinked"] == 1
    assert res["relinked_orders"] == [str(ORDER_A)]
    assert row_state(cur, "leads", lead["id"])["client_id"] == world["cx"]
    acts = [a for a in journal(cur) if a["finding_key"] == "relink:import"]
    assert len(acts) == 1 and acts[0]["done_by"] == USER


def test_import_without_fio_change_does_not_relink(db, world):
    conn, cur = db
    lead = add_lead(cur, "Мама", BD_MAMA, 9003)
    conn.commit()
    set_order(conn, cur, lead["id"], ORDER_A)

    res = bulk_import_leads([import_row(ORDER_A, "Мама", BD_MAMA)], scope=(EV, 2098), user=USER)

    assert res["updated"] == 1 and res["relinked"] == 0 and res["relinked_orders"] == []
    assert row_state(cur, "leads", lead["id"])["client_id"] == world["cm"]
    assert journal(cur) == []


def test_import_renames_phantom_card_when_lead_is_alone(db, world):
    conn, cur = db
    lead = add_lead(cur, "Фантом", BD_PHANTOM, 9004)
    conn.commit()
    set_order(conn, cur, lead["id"], ORDER_A)

    res = bulk_import_leads([import_row(ORDER_A, "Настоящий", BD_PHANTOM, num=9004)], scope=(EV, 2098), user=USER)

    assert res["relinked"] == 1
    state = row_state(cur, "leads", lead["id"])
    assert state["client_id"] == lead["client_id"]
    assert card(cur, lead["client_id"])["name"] == "Настоящий"


def test_import_deletions_are_written_to_journal_with_row_snapshot(db, world):
    conn, cur = db
    keep = add_lead(cur, "Остаётся", BD_PHANTOM, 9005)
    gone = add_lead(cur, "Пропал", BD_PHANTOM, 9006)
    conn.commit()
    set_order(conn, cur, keep["id"], ORDER_A)
    set_order(conn, cur, gone["id"], ORDER_B)
    cur.execute("SELECT id FROM leads WHERE event_name = %s AND id NOT IN (%s, %s)", (EV, keep["id"], gone["id"]))
    others = [r["id"] for r in cur.fetchall()]                  # заявки мира: тоже «пропали» из файла

    res = bulk_import_leads([import_row(ORDER_A, "Остаётся", BD_PHANTOM, num=9005)], scope=(EV, 2099), user=USER)

    assert res["deleted"] == 1 + len(others)
    cur.execute("SELECT id FROM leads WHERE id = %s", (gone["id"],))
    assert cur.fetchone() is None
    acts = {a["finding_key"]: a for a in journal(cur) if a["action"] == "delete_lead"}
    assert set(acts) == {f"lead:{i}" for i in [gone["id"], *others]}
    snap = acts[f"lead:{gone['id']}"]["details"]
    assert snap["surname"] == SURNAME and snap["name"] == "Пропал" and snap["order_id"] == ORDER_B


def test_new_order_of_same_person_is_separate_lead_from_refunded_one(db, world):
    """Снежная 2026: старый заказ ушёл в «Завершенные», человек оформил новый на ту же дистанцию —
    новый заказ не должен «прилипать» к заявке старого по ФИ+ДР (заказы считаем как Tilda)."""
    conn, cur = db
    old = add_lead(cur, "Двазаказа", BD_PHANTOM, 9007)
    conn.commit()
    set_order(conn, cur, old["id"], ORDER_A)
    refunded = import_row(ORDER_A, "Двазаказа", BD_PHANTOM, num=9007)
    refunded.refund = True

    res = bulk_import_leads([refunded, import_row(ORDER_B, "Двазаказа", BD_PHANTOM, num=9007)], scope=(EV, 2098), user=USER)

    assert res["errors"] == [] and res["updated"] == 1 and res["created"] == 1
    cur.execute("SELECT order_id, refund FROM leads WHERE event_name = %s AND name = 'Двазаказа' ORDER BY order_id", (EV,))
    assert [(r["order_id"], r["refund"]) for r in cur.fetchall()] == [(ORDER_A, 2), (ORDER_B, 0)]


def test_order_falls_back_to_name_match_only_for_lead_without_order(db, world):
    """Фоллбэк по ФИ+ДР — для старых заявок без номера заказа: такая заявка обновляется, а не дублируется."""
    conn, cur = db
    lead = add_lead(cur, "Двазаказа", BD_PHANTOM, 9007)
    conn.commit()

    res = bulk_import_leads([import_row(ORDER_B, "Двазаказа", BD_PHANTOM, num=9007)], scope=(EV, 2098), user=USER)

    assert res["updated"] == 1 and res["created"] == 0
    cur.execute("SELECT id, order_id FROM leads WHERE event_name = %s AND name = 'Двазаказа'", (EV,))
    assert [(r["id"], r["order_id"]) for r in cur.fetchall()] == [(lead["id"], ORDER_B)]
