"""Перепривязка заявки/результата к верной карточке после правки ФИ/ДР (dq_actions.plan_relink / relink_row)
на локальной БД. Тестовые данные — событие «Тест перепривязка» 2099, почты *@relink-test.local, фамилии «Тестрелинк…»,
журнал done_by='relink-test'; фикстура убирает их до и после. Любые UPDATE/DELETE — только по ним."""
import json
from datetime import date

import pytest

from src.analytics.db_pool import get_pooled_connection
from src.analytics.dq_actions import plan_relink, relink_row, undo_action
from src.krasmarafon.services import athlete_claims as ac

DOMAIN = "relink-test.local"
EV = "Тест перепривязка"
SURNAME = "Тестрелинк"
USER = "relink-test"
BD_MAMA, BD_DAUGHTER, BD_SON, BD_PHANTOM = date(1986, 5, 1), date(2015, 4, 5), date(2017, 7, 9), date(1990, 2, 3)
TABLES = ("leads", "results")


@pytest.fixture
def db():
    conn = get_pooled_connection()
    if not conn:
        pytest.skip("Нет локальной БД")
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT COUNT(*) n FROM leads WHERE surname LIKE %s AND event_name <> %s", (f"{SURNAME}%", EV))
    if cur.fetchone()["n"]:
        conn.close()
        pytest.skip("Фамилии «Тестрелинк…» заняты не тестовыми данными")

    def cleanup():
        # Порядок из-за внешних ключей: результаты -> заявки -> события -> карточки
        cur.execute("DELETE FROM dq_actions WHERE done_by = %s", (USER,))
        cur.execute("SHOW TABLES LIKE 'athlete_claims'")
        if cur.fetchone():
            cur.execute("DELETE FROM athlete_claims WHERE email LIKE %s", (f"%@{DOMAIN}",))
            cur.execute("DELETE FROM dq_actions WHERE action IN ('athlete_claim', 'athlete_unclaim') "
                        "AND JSON_UNQUOTE(JSON_EXTRACT(details, '$.email')) LIKE %s", (f"%@{DOMAIN}",))
        cur.execute("SELECT id FROM events WHERE event_name = %s", (EV,))
        evs = [r["id"] for r in cur.fetchall()]
        if evs:
            ph = ",".join(map(str, evs))
            cur.execute(f"DELETE FROM results WHERE event_id IN ({ph})")
        cur.execute("DELETE FROM leads WHERE event_name = %s", (EV,))
        if evs:
            cur.execute(f"DELETE FROM events WHERE id IN ({ph})")
        cur.execute("DELETE FROM clients WHERE surname LIKE %s", (f"{SURNAME}%",))
        conn.commit()

    cleanup()
    yield conn, cur
    cleanup()
    cur.close()
    conn.close()


def add_lead(cur, name, birthday, num, surname=SURNAME):
    """Карточку и событие заводят триггеры leads."""
    cur.execute("""INSERT INTO leads (surname, name, sex, city, club, birthday, email, ma_email, phone, event_name,
                   event_distance, event_year, products, amount, client_id, event_id, is_duplicate, status, is_new,
                   is_new_event, is_name_suspicious, start_number, created_at)
                   VALUES (%s, %s, 'Мужчина', '', '', %s, %s, NULL, '', %s, '5 км', 2099, '', 0, 0, 0, 0, 0, 0, 0, 0,
                           %s, NOW())""", (surname, name, birthday, f"{num}@{DOMAIN}", EV, num))
    cur.execute("SELECT id, client_id, event_id FROM leads WHERE id = %s", (cur.lastrowid,))
    return cur.fetchone()


def add_result(cur, name, birthday, event_id, num, surname=SURNAME):
    cur.execute("""INSERT INTO results (surname, name, birthday, sex, event_id, start_number, race_status,
                   time_gun_finish, rank_absolute) VALUES (%s, %s, %s, 'Мужчина', %s, %s, 'Finished', '00:25:00', 1)""",
                (surname, name, birthday, event_id, num))
    cur.execute("SELECT id, client_id, event_id FROM results WHERE id = %s", (cur.lastrowid,))
    return cur.fetchone()


def add_row(cur, table, name, birthday, num, event_id, surname=SURNAME):
    return (add_lead(cur, name, birthday, num, surname) if table == "leads"
            else add_result(cur, name, birthday, event_id, num, surname))


@pytest.fixture
def world(db):
    """cm — карточка «Мама» (ДР 1986) с заявкой 9001; cx — карточка «Дочь» (ДР 2015) с заявкой 9002."""
    conn, cur = db
    cm = add_lead(cur, "Мама", BD_MAMA, 9001)
    cx = add_lead(cur, "Дочь", BD_DAUGHTER, 9002)
    conn.commit()
    return {"cm": cm["client_id"], "cx": cx["client_id"], "event_id": cm["event_id"]}


def fix(conn, cur, table, row_id, name=None, birthday=None):
    """Исправление ФИ/ДР строки (как «Изменить»/импорт/загрузчик) — только по id своей тестовой строки."""
    sets = {k: v for k, v in (("name", name), ("birthday", birthday)) if v is not None}
    where = f"id = {int(row_id)} AND surname LIKE '{SURNAME}%'"
    cur.execute(f"SELECT COUNT(*) n FROM {table} WHERE {where}")
    assert cur.fetchone()["n"] == 1
    cur.execute(f"UPDATE {table} SET {', '.join(f'{k} = %s' for k in sets)} WHERE {where}", list(sets.values()))
    conn.commit()


def row_state(cur, table, row_id):
    cur.execute(f"SELECT client_id, surname, name, birthday FROM {table} WHERE id = %s", (row_id,))
    return cur.fetchone()


def card(cur, cid):
    cur.execute("SELECT id, surname, name, birthday FROM clients WHERE id = %s", (cid,))
    return cur.fetchone()


def journal(cur):
    cur.execute("SELECT id, action, finding_key, details, done_by FROM dq_actions WHERE done_by = %s ORDER BY id", (USER,))
    return [{**r, "details": json.loads(r["details"])} for r in cur.fetchall()]


@pytest.mark.parametrize("table", TABLES)
def test_none_when_fio_and_bd_match_current_card(db, world, table):
    conn, cur = db
    row = add_row(cur, table, "Мама", BD_MAMA, 9500, world["event_id"])
    assert row["client_id"] == world["cm"]
    plan = plan_relink(conn, table, row["id"])
    assert plan["action"] == "none" and plan["from_card"] == plan["to_card"] == world["cm"]
    res = relink_row(conn, table, row["id"], USER, "admin")
    assert res["action"] == "none" and res["action_id"] is None
    assert journal(cur) == []


def test_yo_ye_difference_is_still_a_match_like_uk_client(db, world):
    conn, cur = db
    row = add_lead(cur, "Алёна", BD_SON, 9501)
    fix(conn, cur, "leads", row["id"], name="Алена")
    plan = plan_relink(conn, "leads", row["id"])
    assert plan["action"] == "none" and plan["to_card"] == row["client_id"]


@pytest.mark.parametrize("table", TABLES)
def test_move_to_existing_card_and_undo(db, world, table):
    conn, cur = db
    row = add_row(cur, table, "Мама", BD_MAMA, 9500, world["event_id"])       # ошибочно на карточке мамы
    fix(conn, cur, table, row["id"], name="Дочь", birthday=BD_DAUGHTER)
    plan = plan_relink(conn, table, row["id"])
    assert plan["action"] == "move" and plan["from_card"] == world["cm"] and plan["to_card"] == world["cx"]
    assert plan["card"]["id"] == world["cx"] and (plan["card"]["leads"], plan["card"]["results"]) == (1, 0)
    assert plan["new"] == {"surname": SURNAME, "name": "Дочь", "birthday": str(BD_DAUGHTER)} and plan["reason"]
    assert row_state(cur, table, row["id"])["client_id"] == world["cm"]         # план ничего не пишет
    assert journal(cur) == []

    res = relink_row(conn, table, row["id"], USER, "admin")
    assert res["action"] == "move" and res["to_card"] == world["cx"] and res["action_id"]
    assert row_state(cur, table, row["id"])["client_id"] == world["cx"]
    assert card(cur, world["cm"])                                                # у мамы есть другая заявка
    (entry,) = journal(cur)
    assert (entry["id"], entry["action"], entry["finding_key"]) == (res["action_id"], "move_result", "relink:admin")

    undo_action(conn, res["action_id"], USER)
    assert row_state(cur, table, row["id"])["client_id"] == world["cm"]
    assert card(cur, world["cx"])


@pytest.mark.parametrize("table", TABLES)
def test_move_that_empties_source_deletes_it_and_undo_restores_with_same_id(db, world, table):
    conn, cur = db
    row = add_row(cur, table, "Фантом", BD_PHANTOM, 9500, world["event_id"])    # фантомная карточка с единственной строкой
    phantom = row["client_id"]
    fix(conn, cur, table, row["id"], name="Дочь", birthday=BD_DAUGHTER)
    res = relink_row(conn, table, row["id"], USER, "import")
    assert res["action"] == "move" and res["from_card"] == phantom and res["to_card"] == world["cx"]
    assert card(cur, phantom) is None
    undo_action(conn, res["action_id"], USER)
    restored = card(cur, phantom)
    assert restored and restored["name"] == "Фантом" and str(restored["birthday"]) == str(BD_PHANTOM)
    assert row_state(cur, table, row["id"])["client_id"] == phantom


@pytest.mark.parametrize("table", TABLES)
def test_rename_phantom_card_and_undo(db, world, table):
    conn, cur = db
    row = add_row(cur, table, "Фантом", BD_PHANTOM, 9500, world["event_id"])
    phantom = row["client_id"]
    fix(conn, cur, table, row["id"], name="Сын", birthday=BD_SON)               # такой карточки нет
    plan = plan_relink(conn, table, row["id"])
    assert plan["action"] == "rename" and plan["to_card"] == phantom
    assert plan["card"]["id"] == phantom and plan["card"]["name"] == "Фантом"      # переименовывается эта карточка
    res = relink_row(conn, table, row["id"], USER, "loader")
    assert res["action"] == "rename" and res["to_card"] == phantom and res["action_id"]
    renamed = card(cur, phantom)
    assert (renamed["surname"], renamed["name"], str(renamed["birthday"])) == (SURNAME, "Сын", str(BD_SON))
    assert row_state(cur, table, row["id"])["client_id"] == phantom
    (entry,) = journal(cur)
    assert (entry["action"], entry["finding_key"], entry["details"]["table"]) == ("edit", "relink:loader", "clients")

    undo_action(conn, res["action_id"], USER)
    back = card(cur, phantom)
    assert (back["name"], str(back["birthday"])) == ("Фантом", str(BD_PHANTOM))


@pytest.mark.parametrize("table", TABLES)
def test_new_card_when_current_card_has_other_rows_and_undo(db, world, table):
    conn, cur = db
    row = add_row(cur, table, "Мама", BD_MAMA, 9500, world["event_id"])
    fix(conn, cur, table, row["id"], name="Сын", birthday=BD_SON)               # карточки «Сын» нет, у мамы есть заявка 9001
    plan = plan_relink(conn, table, row["id"])
    assert plan["action"] == "new_card" and plan["from_card"] == world["cm"] and plan["to_card"] is None
    assert plan["card"] is None
    res = relink_row(conn, table, row["id"], USER, "admin")
    new_id = res["to_card"]
    assert res["action"] == "new_card" and new_id not in (None, world["cm"], world["cx"]) and res["action_id"]
    created = card(cur, new_id)
    assert (created["surname"], created["name"], str(created["birthday"])) == (SURNAME, "Сын", str(BD_SON))
    assert row_state(cur, table, row["id"])["client_id"] == new_id and card(cur, world["cm"])

    undo_action(conn, res["action_id"], USER)
    assert row_state(cur, table, row["id"])["client_id"] == world["cm"]
    assert card(cur, new_id) is None


def test_result_with_own_lead_on_card_gets_new_card_not_rename(db, world):
    """«Других строк нет» считает и заявки, и результаты: у карточки есть заявка — переименовывать нельзя."""
    conn, cur = db
    res_row = add_result(cur, "Мама", BD_MAMA, world["event_id"], 9001)         # триггер: заявка 9001 той же ФИ -> карточка мамы
    assert res_row["client_id"] == world["cm"]
    fix(conn, cur, "results", res_row["id"], name="Сын", birthday=BD_SON)
    assert plan_relink(conn, "results", res_row["id"])["action"] == "new_card"


@pytest.mark.parametrize("table", TABLES)
@pytest.mark.parametrize("bd", ["1900-01-01", "1905-01-01"])
def test_placeholder_birthday_is_skipped(db, world, table, bd):
    conn, cur = db
    row = add_row(cur, table, "Мама", BD_MAMA, 9500, world["event_id"])
    fix(conn, cur, table, row["id"], name="Дочь", birthday=bd)
    plan = plan_relink(conn, table, row["id"])
    assert plan["action"] == "skip" and plan["reason"]
    res = relink_row(conn, table, row["id"], USER, "admin")
    assert res["action"] == "skip" and res["action_id"] is None
    assert row_state(cur, table, row["id"])["client_id"] == world["cm"] and journal(cur) == []


@pytest.mark.parametrize("table", TABLES)
def test_preview_with_future_values_does_not_write(db, world, table):
    conn, cur = db
    row = add_row(cur, table, "Мама", BD_MAMA, 9500, world["event_id"])
    before = row_state(cur, table, row["id"])
    plan = plan_relink(conn, table, row["id"], new={"name": "Дочь", "birthday": str(BD_DAUGHTER)})
    assert plan["action"] == "move" and plan["to_card"] == world["cx"]
    assert plan["new"] == {"surname": SURNAME, "name": "Дочь", "birthday": str(BD_DAUGHTER)}
    assert plan_relink(conn, table, row["id"], new={"name": "Сын", "birthday": BD_SON})["action"] == "new_card"
    assert plan_relink(conn, table, row["id"], new={"birthday": "1900-01-01"})["action"] == "skip"
    assert row_state(cur, table, row["id"]) == before and journal(cur) == []


def test_arguments_are_validated(db, world):
    conn, cur = db
    row = add_lead(cur, "Мама", BD_MAMA, 9500)
    with pytest.raises(ValueError):
        plan_relink(conn, "clients", row["id"])
    with pytest.raises(ValueError):
        plan_relink(conn, "leads", 10 ** 9)
    with pytest.raises(ValueError):
        relink_row(conn, "leads", row["id"], USER, "bogus")


def test_cabinet_claim_stays_valid_after_move_but_goes_stale_after_rename(db, world):
    """Привязка кабинета — общее правило: действует, пока карточка есть и её ДР = ДР привязки."""
    conn, cur = db
    cur.execute("SHOW TABLES LIKE 'athlete_claims'")
    if not cur.fetchone():
        pytest.skip("Миграция athlete_claims не применена")
    mail = f"me@{DOMAIN}"
    row = add_lead(cur, "Мама", BD_MAMA, 9500)
    fix(conn, cur, "leads", row["id"], name="Дочь", birthday=BD_DAUGHTER)
    cur.execute("INSERT INTO athlete_claims (email, client_id, birthday) VALUES (%s, %s, %s)",
                (mail, world["cm"], BD_MAMA))
    conn.commit()
    assert relink_row(conn, "leads", row["id"], USER, "admin")["action"] == "move"
    assert ac.claimed_cards(mail) == ([world["cm"]], [])

    ph = add_lead(cur, "Фантом", BD_PHANTOM, 9510)
    cur.execute("INSERT INTO athlete_claims (email, client_id, birthday) VALUES (%s, %s, %s)",
                (f"ph@{DOMAIN}", ph["client_id"], BD_PHANTOM))
    conn.commit()
    fix(conn, cur, "leads", ph["id"], name="Сын", birthday=BD_SON)
    assert relink_row(conn, "leads", ph["id"], USER, "admin")["action"] == "rename"
    assert ac.claimed_cards(f"ph@{DOMAIN}") == ([], [ph["client_id"]])


# ---- «Изменить» заявку в стартовом списке: PATCH и предпросмотр ----

@pytest.fixture
def as_admin():
    from app import app
    from src.core.auth import api_require_auth
    app.dependency_overrides[api_require_auth] = lambda: USER
    yield
    app.dependency_overrides.pop(api_require_auth, None)


def _snapshot(cur, row_id):
    cur.execute("SELECT * FROM leads WHERE id = %s", (row_id,))
    lead = cur.fetchone()
    cur.execute("SELECT id, surname, name, birthday FROM clients WHERE surname LIKE %s ORDER BY id", (f"{SURNAME}%",))
    return lead, cur.fetchall()


def test_preview_endpoint_does_not_change_db(client, as_admin, db, world):
    conn, cur = db
    row = add_lead(cur, "Мама", BD_MAMA, 9500)
    conn.commit()
    before = _snapshot(cur, row["id"])
    r = client.post(f"/api/admin/leads/{row['id']}/relink-preview", json={"name": "Дочь", "birthday": str(BD_DAUGHTER)})
    assert r.status_code == 200
    plan = r.json()
    assert plan["action"] == "move" and plan["to_card"] == world["cx"]
    assert plan["card"]["id"] == world["cx"] and plan["card"]["leads"] == 1
    r = client.post(f"/api/admin/leads/{row['id']}/relink-preview", json={"name": "Сын", "birthday": str(BD_SON)})
    assert r.json()["action"] == "new_card"
    conn.commit()
    assert _snapshot(cur, row["id"]) == before and journal(cur) == []


def test_preview_unknown_lead_is_404_and_bad_birthday_422(client, as_admin, db, world):
    conn, cur = db
    row = add_lead(cur, "Мама", BD_MAMA, 9500)
    conn.commit()
    assert client.post("/api/admin/leads/999999999/relink-preview", json={"name": "Х"}).status_code == 404
    assert client.post(f"/api/admin/leads/{row['id']}/relink-preview", json={"birthday": "31.12.1990"}).status_code == 422


def test_patch_birthday_correction_moves_lead_to_right_card_and_logs(client, as_admin, db, world):
    conn, cur = db
    row = add_lead(cur, "Дочь", BD_MAMA, 9500)  # ошибочная ДР: попала на карточку Мамы
    conn.commit()
    assert row["client_id"] != world["cx"]
    r = client.patch(f"/api/admin/leads/{row['id']}", json={"birthday": str(BD_DAUGHTER)})
    assert r.status_code == 200
    body = r.json()
    assert body["relink"]["action"] == "move" and body["relink"]["to_card"] == world["cx"]
    assert body["client_id"] == world["cx"]
    conn.commit()
    assert row_state(cur, "leads", row["id"])["client_id"] == world["cx"]
    log = [j for j in journal(cur) if j["finding_key"] == "relink:admin"]
    assert len(log) == 1 and log[0]["done_by"] == USER


def test_patch_without_fio_change_does_not_relink(client, as_admin, db, world):
    conn, cur = db
    row = add_lead(cur, "Мама", BD_MAMA, 9500)
    conn.commit()
    r = client.patch(f"/api/admin/leads/{row['id']}", json={"surname": SURNAME, "name": "Мама", "status": 1})
    assert r.status_code == 200 and r.json()["relink"] is None
    assert journal(cur) == []


def test_patch_relink_failure_keeps_edit_and_reports_error(client, as_admin, db, world, monkeypatch):
    """Правка заявки уже закоммичена — сбой подбора карточки не превращается в 4xx/5xx: PATCH 200, relink.error."""
    import src.analytics.dq_actions as dq_actions

    def boom(*a, **k):
        raise RuntimeError("boom-relink")

    conn, cur = db
    row = add_lead(cur, "Дочь", BD_MAMA, 9500)
    conn.commit()
    monkeypatch.setattr(dq_actions, "relink_row", boom)
    r = client.patch(f"/api/admin/leads/{row['id']}", json={"birthday": str(BD_DAUGHTER)})
    assert r.status_code == 200, r.text
    assert r.json()["relink"] == {"action": "error", "reason": "boom-relink"}
    conn.commit()
    state = row_state(cur, "leads", row["id"])
    assert str(state["birthday"]) == str(BD_DAUGHTER) and state["client_id"] == row["client_id"]


def test_patch_distance_change_recomputes_event_id(client, as_admin, db, world):
    conn, cur = db
    row = add_lead(cur, "Мама", BD_MAMA, 9500)
    conn.commit()
    cur.execute("INSERT INTO events (event_name, event_year, event_distance) "
                "SELECT event_name, event_year, 10 FROM events WHERE id = %s", (row["event_id"],))
    new_event = cur.lastrowid
    conn.commit()
    r = client.patch(f"/api/admin/leads/{row['id']}", json={"event_distance": "10 км"})
    assert r.status_code == 200, r.text
    assert r.json()["event_id"] == new_event
    cur.execute("SELECT event_id FROM leads WHERE id = %s", (row["id"],))
    assert cur.fetchone()["event_id"] == new_event


def test_patch_unknown_distance_is_422_and_not_saved(client, as_admin, db, world):
    conn, cur = db
    row = add_lead(cur, "Мама", BD_MAMA, 9500)
    conn.commit()
    r = client.patch(f"/api/admin/leads/{row['id']}", json={"event_distance": "77 км"})
    assert r.status_code == 422
    cur.execute("SELECT event_distance, event_id FROM leads WHERE id = %s", (row["id"],))
    assert cur.fetchone() == {"event_distance": "5 км", "event_id": row["event_id"]}


def test_endpoints_require_login(client):
    assert client.post("/api/admin/leads/1/relink-preview", json={"name": "Х"}).status_code == 401
    assert client.patch("/api/admin/leads/1", json={"name": "Х"}).status_code == 401


# ---- «Изменить»: почта формы и журнал правок заявки ----

def _lead_email(cur, row_id):
    cur.execute("SELECT email, ma_email FROM leads WHERE id = %s", (row_id,))
    return cur.fetchone()


def test_patch_email_saves_normalized_and_logs_undoable_edit(client, as_admin, db, world):
    conn, cur = db
    row = add_lead(cur, "Мама", BD_MAMA, 9500)
    cur.execute("UPDATE leads SET ma_email = %s WHERE id = %s AND surname LIKE %s", (f"ma@{DOMAIN}", row["id"], f"{SURNAME}%"))
    conn.commit()
    r = client.patch(f"/api/admin/leads/{row['id']}", json={"email": f"  Новая@{DOMAIN.upper()} ", "ma_email": f"hack@{DOMAIN}"})
    assert r.status_code == 200, r.text
    assert r.json()["relink"] is None
    conn.commit()
    assert _lead_email(cur, row["id"]) == {"email": f"новая@{DOMAIN}", "ma_email": f"ma@{DOMAIN}"}   # ma_email не правится
    [entry] = journal(cur)
    assert (entry["action"], entry["finding_key"], entry["done_by"]) == ("edit", f"lead:{row['id']}", USER)
    assert entry["details"]["table"] == "leads" and entry["details"]["id"] == row["id"]
    assert entry["details"]["before"] == {"email": f"{9500}@{DOMAIN}"} and entry["details"]["after"] == {"email": f"новая@{DOMAIN}"}
    undo_action(conn, entry["id"], USER)
    assert _lead_email(cur, row["id"])["email"] == f"9500@{DOMAIN}"


@pytest.mark.parametrize("bad", ["", "   ", "без-собаки", "a b@x.ru", "a@b", "a@b.ru, c@d.ru", "a@" + "x" * 260 + ".ru"])
def test_patch_bad_email_is_422_and_not_saved(client, as_admin, db, world, bad):
    conn, cur = db
    row = add_lead(cur, "Мама", BD_MAMA, 9500)
    conn.commit()
    r = client.patch(f"/api/admin/leads/{row['id']}", json={"email": bad, "status": 1})
    assert r.status_code == 422
    conn.commit()
    assert _lead_email(cur, row["id"])["email"] == f"9500@{DOMAIN}"
    cur.execute("SELECT status FROM leads WHERE id = %s", (row["id"],))
    assert cur.fetchone()["status"] == 0 and journal(cur) == []


def test_patch_same_email_writes_nothing(client, as_admin, db, world):
    conn, cur = db
    row = add_lead(cur, "Мама", BD_MAMA, 9500)
    conn.commit()
    r = client.patch(f"/api/admin/leads/{row['id']}", json={"email": f"9500@{DOMAIN}".upper()})
    assert r.status_code == 200 and r.json()["relink"] is None
    assert journal(cur) == []


def test_patch_email_does_not_relink(client, as_admin, db, world):
    conn, cur = db
    row = add_lead(cur, "Мама", BD_MAMA, 9500)
    conn.commit()
    r = client.patch(f"/api/admin/leads/{row['id']}", json={"email": f"x@{DOMAIN}"})
    assert r.status_code == 200 and r.json()["relink"] is None
    conn.commit()
    assert row_state(cur, "leads", row["id"])["client_id"] == world["cm"]
    assert [j["action"] for j in journal(cur)] == ["edit"]


def test_patch_fio_with_move_logs_edit_then_move_and_undoes_in_reverse(client, as_admin, db, world):
    conn, cur = db
    row = add_lead(cur, "Мама", BD_MAMA, 9500)
    conn.commit()
    r = client.patch(f"/api/admin/leads/{row['id']}", json={"name": "Дочь", "birthday": str(BD_DAUGHTER)})
    assert r.status_code == 200 and r.json()["relink"]["action"] == "move"
    conn.commit()
    edit, move = journal(cur)
    assert (edit["action"], edit["finding_key"]) == ("edit", f"lead:{row['id']}")
    assert edit["details"]["before"] == {"name": "Мама", "birthday": str(BD_MAMA)}
    assert edit["details"]["after"] == {"name": "Дочь", "birthday": str(BD_DAUGHTER)}
    assert (move["action"], move["finding_key"]) == ("move_result", "relink:admin")
    with pytest.raises(ValueError):                      # правку заявки раньше переезда не отменить
        undo_action(conn, edit["id"], USER)
    undo_action(conn, move["id"], USER)
    undo_action(conn, edit["id"], USER)
    state = row_state(cur, "leads", row["id"])
    assert (state["client_id"], state["name"], state["birthday"]) == (world["cm"], "Мама", BD_MAMA)


def test_patch_distance_is_logged_with_event_id(client, as_admin, db, world):
    conn, cur = db
    row = add_lead(cur, "Мама", BD_MAMA, 9500)
    conn.commit()
    cur.execute("INSERT INTO events (event_name, event_year, event_distance) "
                "SELECT event_name, event_year, 10 FROM events WHERE id = %s", (row["event_id"],))
    new_event = cur.lastrowid
    conn.commit()
    assert client.patch(f"/api/admin/leads/{row['id']}", json={"event_distance": "10 км"}).status_code == 200
    conn.commit()
    [entry] = journal(cur)
    assert entry["details"]["after"]["event_distance"] == "10 км" and entry["details"]["after"]["event_id"] == str(new_event)
    undo_action(conn, entry["id"], USER)
    cur.execute("SELECT event_id, event_distance FROM leads WHERE id = %s", (row["id"],))
    assert cur.fetchone() == {"event_id": row["event_id"], "event_distance": "5 км"}


def test_is_valid_email_shared_rule():
    from src.common.emails import is_valid_email
    assert is_valid_email("a@b.ru") and not is_valid_email("a@b") and not is_valid_email("a b@c.ru")
