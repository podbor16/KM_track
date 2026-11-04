"""Б2: представители карточки (athlete_reps) на локальной БД. Тестовые данные — почты *@reps-test.local, событие
«Тест представители» 2099 года, карточки «Тестпред …»; фикстура убирает их до и после."""
import json
from datetime import date
from unittest.mock import patch

import pytest

from src.analytics.db_pool import get_pooled_connection
from src.krasmarafon.services import athlete_claims as ac
from src.krasmarafon.services import athlete_reps as ar
from src.krasmarafon.services.athlete_claims import ClaimResult
from src.krasmarafon.services.athlete_reps import RepResult

DOMAIN = "reps-test.local"
EV = "Тест представители"
SURNAME = "Тестпред"
PARENT = f"parent@{DOMAIN}"       # записывал ребёнка
COACH = f"coach@{DOMAIN}"         # тренер, тоже записывал
KID = f"kid@{DOMAIN}"             # почта самого ребёнка (владелец карточки)
GRAN = f"gran@{DOMAIN}"           # бабушка: есть в заявках ребёнка, аккаунта нет
GRAN_MA = f"granma@{DOMAIN}"
BD_KID, BD_OTHER = date(2015, 4, 5), date(1985, 2, 3)
MERGER = "test-reps-merge"


@pytest.fixture
def db():
    conn = get_pooled_connection()
    if not conn:
        pytest.skip("Нет локальной БД")
    cur = conn.cursor(dictionary=True)
    for table in ("athlete_claims", "athlete_reps"):
        cur.execute("SHOW TABLES LIKE %s", (table,))
        if not cur.fetchone():
            conn.close()
            pytest.skip(f"Миграция {table} не применена")

    def cleanup():
        for table in ("athlete_claims", "athlete_reps", "athlete_claim_attempts"):
            cur.execute(f"DELETE FROM {table} WHERE email LIKE %s", (f"%@{DOMAIN}",))
        cur.execute("DELETE FROM dq_actions WHERE action IN ('athlete_claim', 'athlete_unclaim', 'athlete_rep', "
                    "'athlete_unrep') AND JSON_UNQUOTE(JSON_EXTRACT(details, '$.email')) LIKE %s", (f"%@{DOMAIN}",))
        cur.execute("DELETE FROM dq_actions WHERE done_by = %s", (MERGER,))
        cur.execute("SELECT id FROM events WHERE event_name = %s", (EV,))
        evs = [r["id"] for r in cur.fetchall()]
        if evs:
            ph = ",".join(map(str, evs))
            cur.execute(f"DELETE FROM results WHERE event_id IN ({ph})")
        cur.execute("DELETE FROM leads WHERE event_name = %s", (EV,))
        if evs:
            cur.execute(f"DELETE FROM events WHERE id IN ({ph})")
        cur.execute("DELETE FROM clients WHERE surname = %s", (SURNAME,))
        conn.commit()

    cleanup()
    yield conn, cur
    cleanup()
    cur.close()
    conn.close()


def add_lead(cur, name, birthday, email, start_number, ma_email=None):
    """Карточку и событие заводят триггеры leads (они же выставляют client_id/event_id)."""
    cur.execute("""INSERT INTO leads (surname, name, sex, city, club, birthday, email, ma_email, phone, event_name,
                   event_distance, event_year, products, amount, client_id, event_id, is_duplicate, status, is_new,
                   is_new_event, is_name_suspicious, start_number, created_at)
                   VALUES (%s, %s, 'Женщина', '', '', %s, %s, %s, '', %s, '5 км', 2099, '', 0, 0, 0, 0, 0, 0, 0, 0,
                           %s, NOW())""", (SURNAME, name, birthday, email, ma_email, EV, start_number))
    cur.execute("SELECT client_id FROM leads WHERE id = %s", (cur.lastrowid,))
    return cur.fetchone()["client_id"]


@pytest.fixture
def cards(db):
    """kid (ДР 2015: заявки с parent@, coach@, kid@ и gran@+ma_email), twin («Маруся», та же ДР и заявка с parent@ —
    дубль карточки того же ребёнка), nobd (без ДР, заявка с parent@), foreign (заявка только с gran@)."""
    conn, cur = db
    kid = add_lead(cur, "Маша", BD_KID, PARENT, 9101)
    add_lead(cur, "Маша", BD_KID, COACH, 9102)
    add_lead(cur, "Маша", BD_KID, KID, 9103)
    add_lead(cur, "Маша", BD_KID, GRAN, 9104, ma_email=GRAN_MA)
    twin = add_lead(cur, "Маруся", BD_KID, PARENT, 9105)
    nobd = add_lead(cur, "Безбд", date(1900, 1, 1), PARENT, 9106)
    foreign = add_lead(cur, "Чужая", BD_OTHER, GRAN, 9107)
    conn.commit()
    return {"kid": kid, "twin": twin, "nobd": nobd, "foreign": foreign}


@pytest.fixture
def mail():
    with patch.object(ac, "send_mail") as m:
        yield m


def journal(cur, action, client_id):
    cur.execute("SELECT details, done_by FROM dq_actions WHERE action = %s AND finding_key = %s ORDER BY id",
                (action, f"client:{client_id}"))
    return [(json.loads(r["details"]), r["done_by"]) for r in cur.fetchall()]


def rep_rows(cur, email=PARENT):
    cur.execute("SELECT client_id, birthday FROM athlete_reps WHERE email = %s ORDER BY id", (email,))
    return cur.fetchall()


# ---------------------------------------------------------------- become_rep

def test_become_rep_ok_writes_row_and_journal_without_mail(db, cards, mail):
    conn, cur = db
    assert ar.become_rep(PARENT, cards["kid"], BD_KID) == RepResult.OK
    assert rep_rows(cur) == [{"client_id": cards["kid"], "birthday": BD_KID}]
    assert ar.rep_cards(PARENT) == ([cards["kid"]], [])
    assert journal(cur, "athlete_rep", cards["kid"]) == [({"email": PARENT}, PARENT)]
    assert not mail.called                      # письма — отдельно, в фоне (notify_rep)


def test_several_reps_of_one_card(db, cards, mail):
    conn, cur = db
    assert ar.become_rep(PARENT, cards["kid"], BD_KID) == RepResult.OK
    assert ar.become_rep(COACH, cards["kid"], BD_KID) == RepResult.OK
    assert ar.rep_cards(PARENT) == ([cards["kid"]], []) and ar.rep_cards(COACH) == ([cards["kid"]], [])


def test_no_lead_of_this_person_on_account_email_is_not_yours(db, cards, mail):
    with pytest.raises(ValueError):
        ar.become_rep(PARENT, cards["foreign"], BD_OTHER)
    with pytest.raises(ValueError):
        ar.become_rep(PARENT, 10 ** 9, BD_KID)


def test_own_claimed_card_is_own(db, cards, mail):
    conn, cur = db
    assert ac.claim(KID, cards["kid"], BD_KID) == ClaimResult.OK
    assert ar.become_rep(KID, cards["kid"], BD_KID) == RepResult.OWN
    assert rep_rows(cur, KID) == []


def test_claim_by_other_account_does_not_block_rep(db, cards, mail):
    assert ac.claim(KID, cards["kid"], BD_KID) == ClaimResult.OK
    assert ar.become_rep(PARENT, cards["kid"], BD_KID) == RepResult.OK


def test_second_time_is_already(db, cards, mail):
    conn, cur = db
    assert ar.become_rep(PARENT, cards["kid"], BD_KID) == RepResult.OK
    assert ar.become_rep(PARENT, cards["kid"], BD_KID) == RepResult.ALREADY
    assert len(rep_rows(cur)) == 1 and len(journal(cur, "athlete_rep", cards["kid"])) == 1


def test_card_without_birthday(db, cards, mail):
    assert ar.become_rep(PARENT, cards["nobd"], date(1990, 1, 1)) == RepResult.NO_BIRTHDAY


def test_mismatch_records_attempt_and_limit_is_shared_with_claims(db, cards, mail):
    conn, cur = db
    wrong = date(2015, 4, 6)
    for _ in range(3):
        assert ac.claim(PARENT, cards["kid"], wrong) == ClaimResult.MISMATCH
    assert [ar.become_rep(PARENT, cards["kid"], wrong) for _ in range(2)] == [RepResult.MISMATCH] * 2
    assert ar.become_rep(PARENT, cards["kid"], wrong) == RepResult.LIMIT
    assert ar.become_rep(PARENT, cards["kid"], BD_KID) == RepResult.LIMIT       # верная ДР тоже: лимит раньше сверки
    assert rep_rows(cur) == []
    cur.execute("SELECT COUNT(*) n FROM athlete_claim_attempts WHERE email = %s", (PARENT,))
    assert cur.fetchone()["n"] == 5


# ---------------------------------------------------------------- общее правило действительности

def test_changed_birthday_drops_rep_with_journal(db, cards, mail):
    conn, cur = db
    ar.become_rep(PARENT, cards["kid"], BD_KID)
    cur.execute("UPDATE clients SET birthday = '2015-04-06' WHERE id = %s AND surname = %s", (cards["kid"], SURNAME))
    conn.commit()
    assert ar.rep_cards(PARENT) == ([], [cards["kid"]])
    assert rep_rows(cur) == []
    assert journal(cur, "athlete_unrep", cards["kid"]) == [({"email": PARENT, "reason": "birthday_changed"}, "system")]
    assert ar.rep_cards(PARENT) == ([], [])      # повторно уже не «снято сейчас»


def test_deleted_card_drops_rep(db, cards, mail):
    conn, cur = db
    ar.become_rep(PARENT, cards["twin"], BD_KID)
    ar.become_rep(PARENT, cards["kid"], BD_KID)
    cur.execute("DELETE FROM leads WHERE client_id = %s AND event_name = %s", (cards["twin"], EV))
    cur.execute("DELETE FROM clients WHERE id = %s AND surname = %s", (cards["twin"], SURNAME))
    conn.commit()
    assert ar.rep_cards(PARENT) == ([cards["kid"]], [cards["twin"]])
    assert journal(cur, "athlete_unrep", cards["twin"]) == [({"email": PARENT, "reason": "card_deleted"}, "system")]


def test_stale_rep_does_not_block_new_one(db, cards, mail):
    conn, cur = db
    ar.become_rep(PARENT, cards["kid"], BD_KID)
    cur.execute("UPDATE clients SET birthday = '2015-04-06' WHERE id = %s AND surname = %s", (cards["kid"], SURNAME))
    conn.commit()
    assert ar.become_rep(PARENT, cards["kid"], date(2015, 4, 6)) == RepResult.OK


# ---------------------------------------------------------------- снятие, список владельца

def test_remove_rep_by_user(db, cards, mail):
    conn, cur = db
    ar.become_rep(PARENT, cards["kid"], BD_KID)
    ar.become_rep(COACH, cards["kid"], BD_KID)
    ar.remove_rep(PARENT, cards["kid"])
    ar.remove_rep(PARENT, cards["kid"])          # повтор — тихо
    assert rep_rows(cur) == [] and len(rep_rows(cur, COACH)) == 1
    assert journal(cur, "athlete_unrep", cards["kid"]) == [({"email": PARENT, "reason": "user"}, PARENT)]


def test_reps_of_lists_valid_reps_of_valid_claims(db, cards, mail):
    conn, cur = db
    ac.claim(KID, cards["kid"], BD_KID)
    ar.become_rep(PARENT, cards["kid"], BD_KID)
    ar.become_rep(COACH, cards["kid"], BD_KID)
    ar.become_rep(PARENT, cards["twin"], BD_KID)      # чужая для владельца карточка
    got = ar.reps_of(KID)
    assert [(r["client_id"], r["email_masked"]) for r in got] == [(cards["kid"], f"p***@{DOMAIN}"),
                                                                  (cards["kid"], f"c***@{DOMAIN}")]
    assert all(set(r) == {"id", "client_id", "email_masked", "created_at"} for r in got)
    assert ar.reps_of(PARENT) == []
    cur.execute("UPDATE clients SET birthday = '2015-04-06' WHERE id = %s AND surname = %s", (cards["kid"], SURNAME))
    conn.commit()
    assert ar.reps_of(KID) == []                      # привязка и доступы недействительны


def test_remove_rep_by_owner_only_own_cards(db, cards, mail):
    conn, cur = db
    ac.claim(KID, cards["kid"], BD_KID)
    ar.become_rep(PARENT, cards["kid"], BD_KID)
    ar.become_rep(PARENT, cards["twin"], BD_KID)
    cur.execute("SELECT id, client_id FROM athlete_reps WHERE email = %s", (PARENT,))
    ids = {r["client_id"]: r["id"] for r in cur.fetchall()}

    assert ar.remove_rep_by_owner(KID, ids[cards["twin"]]) is False         # чужая карточка
    assert ar.remove_rep_by_owner(COACH, ids[cards["kid"]]) is False        # чужой аккаунт
    assert len(rep_rows(cur)) == 2
    assert ar.remove_rep_by_owner(KID, ids[cards["kid"]]) is True
    assert rep_rows(cur) == [{"client_id": cards["twin"], "birthday": BD_KID}]
    assert journal(cur, "athlete_unrep", cards["kid"]) == [({"email": PARENT, "reason": "owner_removed"}, KID)]


# ---------------------------------------------------------------- уведомление

def test_notify_rep_goes_to_card_addresses_without_account(db, cards, mail):
    ar.notify_rep(cards["kid"], PARENT)
    assert {c.args[0] for c in mail.call_args_list} == {COACH, KID, GRAN, GRAN_MA}
    _, subject, text, html = mail.call_args_list[0].args
    assert f"Доступ к истории забегов Тестпред Маша на сайте результатов Красмарафона получил аккаунт p***@{DOMAIN}" in text
    assert "Если вы не знаете этого человека" in text and "1@krasmarafon.ru" in text
    assert PARENT not in text and "Тестпред Маша" in html


def test_notify_rep_mail_failure_does_not_raise(db, cards, mail):
    mail.side_effect = RuntimeError("smtp")
    ar.notify_rep(cards["kid"], PARENT)
    assert mail.call_count == 4
    ar.notify_rep(10 ** 9, PARENT)


# ---------------------------------------------------------------- склейка и отмена

@pytest.fixture
def dq(db, cards, mail):
    from src.analytics import dq_actions
    return dq_actions


def merge(dq, conn, cards, name="Маша"):
    """kid (4 заявки) и twin (1) -> kid; -> (survivor, action_id)."""
    return dq.merge_cards(conn, [cards["kid"], cards["twin"]], SURNAME, name, BD_KID.isoformat(), MERGER)


def action_details(cur, action_id):
    cur.execute("SELECT details FROM dq_actions WHERE id = %s", (action_id,))
    return json.loads(cur.fetchone()["details"])


def test_merge_moves_rep_to_survivor(db, cards, dq):
    conn, cur = db
    ar.become_rep(PARENT, cards["twin"], BD_KID)
    surv, action_id = merge(dq, conn, cards)
    assert surv == cards["kid"]
    assert rep_rows(cur) == [{"client_id": cards["kid"], "birthday": BD_KID}]
    assert ar.rep_cards(PARENT) == ([cards["kid"]], [])
    assert action_details(cur, action_id)["athlete_reps"] == [
        {"client_id": cards["twin"], "email": PARENT, "moved_to": cards["kid"]}]


def test_merge_drops_duplicate_rep(db, cards, dq):
    conn, cur = db
    add_lead(cur, "Маруся", BD_KID, COACH, 9108)
    conn.commit()
    ar.become_rep(PARENT, cards["kid"], BD_KID)
    ar.become_rep(PARENT, cards["twin"], BD_KID)
    ar.become_rep(COACH, cards["twin"], BD_KID)
    _, action_id = merge(dq, conn, cards)
    assert rep_rows(cur) == [{"client_id": cards["kid"], "birthday": BD_KID}]
    assert rep_rows(cur, COACH) == [{"client_id": cards["kid"], "birthday": BD_KID}]
    assert action_details(cur, action_id)["athlete_reps"] == [
        {"client_id": cards["twin"], "email": PARENT, "dropped": True},
        {"client_id": cards["twin"], "email": COACH, "moved_to": cards["kid"]}]
    assert journal(cur, "athlete_unrep", cards["twin"]) == [({"email": PARENT, "reason": "merged"}, MERGER)]


def test_merge_drops_rep_of_account_that_owns_the_survivor(db, cards, dq):
    conn, cur = db
    ar.become_rep(PARENT, cards["twin"], BD_KID)
    assert ac.claim(PARENT, cards["kid"], BD_KID) == ClaimResult.OK
    _, action_id = merge(dq, conn, cards)
    assert rep_rows(cur) == []
    assert action_details(cur, action_id)["athlete_reps"] == [
        {"client_id": cards["twin"], "email": PARENT, "dropped": True}]


def test_merge_marks_dropped_stale_rep(db, cards, dq):
    conn, cur = db
    ar.become_rep(PARENT, cards["kid"], BD_KID)
    ar.become_rep(PARENT, cards["twin"], BD_KID)
    cur.execute("UPDATE clients SET birthday = '2015-04-06' WHERE id = %s AND surname = %s", (cards["twin"], SURNAME))
    conn.commit()
    _, action_id = merge(dq, conn, cards)
    assert action_details(cur, action_id)["athlete_reps"] == [
        {"client_id": cards["twin"], "email": PARENT, "dropped": True, "stale": True}]


def test_apply_directly_collects_reps_out(db, cards, tmp_path):
    from src.analytics import client_merge
    conn, cur = db
    ar.become_rep(PARENT, cards["twin"], BD_KID)
    reps = []
    client_merge.apply(conn, None, {cards["kid"]: (SURNAME, "Маша", BD_KID.isoformat())}, {cards["twin"]: cards["kid"]},
                       str(tmp_path / "b.json"), reps_out=reps)
    assert reps == [{"client_id": cards["twin"], "email": PARENT, "moved_to": cards["kid"]}]
    assert rep_rows(cur) == [{"client_id": cards["kid"], "birthday": BD_KID}]


def test_undo_merge_moves_rep_back(db, cards, dq):
    conn, cur = db
    ar.become_rep(PARENT, cards["twin"], BD_KID)
    _, action_id = merge(dq, conn, cards)
    undo_id = dq.undo_action(conn, action_id, MERGER)
    assert rep_rows(cur) == [{"client_id": cards["twin"], "birthday": BD_KID}]
    assert ar.rep_cards(PARENT) == ([cards["twin"]], [])
    assert action_details(cur, undo_id)["athlete_reps"] == [
        {"client_id": cards["twin"], "email": PARENT, "moved_back": True}]


def test_undo_merge_returns_dropped_rep_and_keeps_survivor_rep(db, cards, dq):
    conn, cur = db
    ar.become_rep(PARENT, cards["kid"], BD_KID)
    ar.become_rep(PARENT, cards["twin"], BD_KID)
    _, action_id = merge(dq, conn, cards)
    undo_id = dq.undo_action(conn, action_id, MERGER)
    assert sorted(r["client_id"] for r in rep_rows(cur)) == sorted([cards["kid"], cards["twin"]])
    assert action_details(cur, undo_id)["athlete_reps"] == [
        {"client_id": cards["twin"], "email": PARENT, "restored": True}]


def test_undo_merge_skips_stale_dropped_rep(db, cards, dq):
    conn, cur = db
    ar.become_rep(PARENT, cards["kid"], BD_KID)
    ar.become_rep(PARENT, cards["twin"], BD_KID)
    cur.execute("UPDATE clients SET birthday = '2015-04-06' WHERE id = %s AND surname = %s", (cards["twin"], SURNAME))
    conn.commit()
    _, action_id = merge(dq, conn, cards)
    dq.undo_action(conn, action_id, MERGER)
    assert rep_rows(cur) == [{"client_id": cards["kid"], "birthday": BD_KID}]


def test_undo_merge_skips_rep_that_user_removed_meanwhile(db, cards, dq):
    conn, cur = db
    ar.become_rep(PARENT, cards["twin"], BD_KID)
    _, action_id = merge(dq, conn, cards)
    ar.remove_rep(PARENT, cards["kid"])
    undo_id = dq.undo_action(conn, action_id, MERGER)
    assert rep_rows(cur) == []
    assert action_details(cur, undo_id).get("athlete_reps", []) == []


def test_undo_fix_fio_merge_moves_rep_back(db, cards, dq):
    conn, cur = db
    cur.execute("SELECT event_id FROM leads WHERE client_id = %s AND event_name = %s LIMIT 1", (cards["kid"], EV))
    event_id = cur.fetchone()["event_id"]
    cur.execute("""INSERT INTO results (surname, name, birthday, sex, event_id, start_number, race_status,
                   time_gun_finish, rank_absolute) VALUES (%s, 'Маша', %s, 'Женщина', %s, 9101, 'Finished',
                   '00:25:00', 1)""", (SURNAME, BD_KID, event_id))
    result_id = cur.lastrowid
    conn.commit()
    ar.become_rep(PARENT, cards["twin"], BD_KID)

    _, action_id = dq.fix_fio(conn, result_id, SURNAME, "Маруся", MERGER)
    assert rep_rows(cur) == [{"client_id": cards["kid"], "birthday": BD_KID}]

    undo_id = dq.undo_action(conn, action_id, MERGER)
    assert rep_rows(cur) == [{"client_id": cards["twin"], "birthday": BD_KID}]
    assert action_details(cur, undo_id)["athlete_reps"] == [
        {"client_id": cards["twin"], "email": PARENT, "moved_back": True}]


# ---------------------------------------------------------------- интерфейс: /me, «Я представитель», история подопечного

import re  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from app import app  # noqa: E402
from src.krasmarafon.services import athlete_auth as aa  # noqa: E402


@pytest.fixture
def web(db, cards, mail, tmp_path, monkeypatch):
    """Кабинет включён (файл-флаг подменён), клиент HTTPS, коды/сессии тестовых почт убираются до и после."""
    conn, cur = db
    flag = tmp_path / "athlete_cabinet_enabled.local"
    flag.write_text("true", encoding="utf-8")
    monkeypatch.setattr("src.config.event_loader._ATHLETE_CABINET_FILE", flag)

    def wipe():
        cur.execute("DELETE FROM athlete_login_codes WHERE email LIKE %s OR ip = 'testclient'", (f"%@{DOMAIN}",))
        cur.execute("DELETE FROM athlete_sessions WHERE email LIKE %s", (f"%@{DOMAIN}",))
        conn.commit()

    wipe()
    yield TestClient(app, base_url="https://testserver"), flag
    wipe()


def login(client, email=PARENT):
    with patch.object(aa, "send_mail") as m:
        client.post("/me/login", data={"email": email})
    code = re.search(r"\b(\d{6})\b", m.call_args[0][2]).group(1)
    assert client.post("/me/verify", data={"email": email, "code": code}, follow_redirects=False).status_code == 303


def rep_via_web(client, card, birthday):
    return client.post("/me/rep", data={"client_id": card, "birthday": birthday}, follow_redirects=False)


def test_me_shows_both_buttons_with_forms(web, cards):
    client, _ = web
    login(client)
    page = client.get("/me").text
    assert "Это я" in page and "Я представитель" in page
    assert 'action="/me/claim"' in page and 'action="/me/rep"' in page
    assert "Дата рождения этого человека" in page
    assert f'name="client_id" value="{cards["kid"]}"' in page
    assert "Вы представитель" not in page and not re.search(r"<details[^>]* open", page)


def test_becoming_rep_shows_badge_instead_of_buttons_and_notifies(web, cards, mail):
    client, _ = web
    login(client)
    r = rep_via_web(client, cards["kid"], "2015-04-05")
    assert r.status_code == 303 and r.headers["location"] == "/me"
    page = client.get("/me").text
    assert "Вы представитель · История →" in page and f'href="/me/athlete/{cards["kid"]}"' in page
    assert f'name="client_id" value="{cards["kid"]}"' not in page
    assert {c.args[0] for c in mail.call_args_list} == {COACH, KID, GRAN, GRAN_MA}
    assert rep_via_web(client, cards["kid"], "2015-04-05").headers["location"] == "/me"     # повтор — без писем
    assert mail.call_count == 4


@pytest.mark.parametrize("code, text", [
    ("mismatch", "Дата не совпадает"),
    ("limit", "Слишком много попыток. Попробуйте завтра или напишите нам на 1@krasmarafon.ru"),
    ("no_birthday", "Подтвердить не получится — напишите нам на 1@krasmarafon.ru"),
    ("date", "Проверьте дату"),
    ("own", "Это ваша карточка — откройте свою историю"),
])
def test_rep_error_is_shown_at_the_rep_form_only(web, cards, code, text):
    client, _ = web
    login(client)
    page = client.get(f"/me?rep={cards['kid']}&r={code}").text
    box = re.search(r"<details[^>]* open[^>]*>.*?</details>", page, re.S).group(0)
    assert text in box and 'action="/me/rep"' in box and 'action="/me/claim"' not in box
    assert "Дата не совпадает" not in client.get(f"/me?rep={cards['twin']}&r=bogus").text
    assert "Дата не совпадает" not in client.get("/me?rep=abc&r=mismatch").text


def test_rep_redirects_for_wrong_date_invalid_date_and_foreign_card(web, cards):
    client, _ = web
    login(client)
    assert rep_via_web(client, cards["kid"], "2015-04-06").headers["location"] == f"/me?rep={cards['kid']}&r=mismatch"
    assert rep_via_web(client, cards["kid"], "не дата").headers["location"] == f"/me?rep={cards['kid']}&r=date"
    assert rep_via_web(client, cards["nobd"], "2015-04-05").headers["location"] == \
        f"/me?rep={cards['nobd']}&r=no_birthday"
    r = rep_via_web(client, cards["foreign"], "1985-02-03")
    assert r.headers["location"] == f"/me?rep={cards['foreign']}&r=not_yours"
    assert "Эта карточка не совпадает с данными ваших заявок" in client.get(r.headers["location"]).text


def test_own_card_via_web_is_own(web, cards):
    client, _ = web
    ac.claim(PARENT, cards["kid"], BD_KID)
    login(client)
    assert rep_via_web(client, cards["kid"], "2015-04-05").headers["location"] == "/me/history"


def test_rep_requires_session_and_same_origin(web, cards):
    client, _ = web
    assert rep_via_web(client, cards["kid"], "2015-04-05").headers["location"] == "/me/login"
    login(client)
    evil = {"origin": "https://evil.example"}
    for url, data in (("/me/rep", {"client_id": cards["kid"], "birthday": "2015-04-05"}),
                      ("/me/unrep", {"client_id": cards["kid"]}), ("/me/rep/remove", {"rep_id": 1})):
        assert client.post(url, data=data, headers=evil, follow_redirects=False).status_code == 403
    assert ar.rep_cards(PARENT) == ([], [])


def test_athlete_page_shows_history_of_ward(web, cards):
    client, _ = web
    login(client)
    rep_via_web(client, cards["kid"], "2015-04-05")
    r = client.get(f"/me/athlete/{cards['kid']}")
    assert r.status_code == 200
    page = r.text
    assert "Тестпред Маша" in page and 'data-tab="results"' in page and 'data-tab="leads"' in page
    assert "mailto:1@krasmarafon.ru?subject=" in page
    assert "/me/unrep" in page and "Отказаться от доступа" in page and "confirm(" in page
    assert "/me/unclaim" not in page and "отвязать" not in page
    assert "Доступ к вашей истории" not in page


def test_athlete_page_access_rules(web, cards):
    client, flag = web
    assert client.get(f"/me/athlete/{cards['kid']}", follow_redirects=False).headers["location"] == "/me/login"
    login(client)
    assert client.get(f"/me/athlete/{cards['kid']}").status_code == 404           # доступа нет
    assert client.get(f"/me/athlete/{cards['foreign']}").status_code == 404
    rep_via_web(client, cards["kid"], "2015-04-05")
    assert client.get(f"/me/athlete/{cards['kid']}").status_code == 200
    ac.claim(PARENT, cards["kid"], BD_KID)                                          # потом заявил сам -> своя история
    r = client.get(f"/me/athlete/{cards['kid']}", follow_redirects=False)
    assert r.status_code in (302, 303) and r.headers["location"] == "/me/history"
    flag.unlink()
    assert client.get(f"/me/athlete/{cards['kid']}", follow_redirects=False).status_code == 404
    assert client.post("/me/rep", data={"client_id": 1, "birthday": "2000-01-01"}).status_code == 404
    assert client.post("/me/unrep", data={"client_id": 1}).status_code == 404
    assert client.post("/me/rep/remove", data={"rep_id": 1}).status_code == 404


def test_unrep_via_web_removes_badge_and_access(web, cards):
    client, _ = web
    login(client)
    rep_via_web(client, cards["kid"], "2015-04-05")
    r = client.post("/me/unrep", data={"client_id": cards["kid"]}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/me"
    assert "Вы представитель" not in client.get("/me").text
    assert client.get(f"/me/athlete/{cards['kid']}").status_code == 404


def test_changed_birthday_drops_access_and_explains(web, cards, db):
    conn, cur = db
    client, _ = web
    login(client)
    rep_via_web(client, cards["kid"], "2015-04-05")
    cur.execute("UPDATE clients SET birthday = '2015-04-06' WHERE id = %s AND surname = %s", (cards["kid"], SURNAME))
    conn.commit()
    page = client.get("/me").text
    assert "Доступ к истории снят: данные карточки изменились — подтвердите заново" in page
    assert "Вы представитель" not in page and 'action="/me/rep"' in page
    assert client.get(f"/me/athlete/{cards['kid']}").status_code == 404


def test_owner_sees_reps_and_removes_them(web, cards):
    client, _ = web
    assert ac.claim(KID, cards["kid"], BD_KID) == ClaimResult.OK
    assert ar.become_rep(PARENT, cards["kid"], BD_KID) == RepResult.OK
    assert ar.become_rep(COACH, cards["kid"], BD_KID) == RepResult.OK
    login(client, KID)
    page = client.get("/me/history").text
    assert "Доступ к вашей истории" in page
    block = page.split('class="me-reps"')[1].split('class="me-foot"')[0]       # в «Подробнее» те же маски — смотрим блок
    assert "p***@reps-test.local" in block and "c***@reps-test.local" in block and PARENT not in page
    parent_rep = next(r for r in ar.reps_of(KID) if r["email_masked"].startswith("p"))
    assert f'name="rep_id" value="{parent_rep["id"]}"' in page and "/me/rep/remove" in page
    r = client.post("/me/rep/remove", data={"rep_id": parent_rep["id"]}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/me/history"
    assert ar.rep_cards(PARENT) == ([], []) and ar.rep_cards(COACH) == ([cards["kid"]], [])
    block = client.get("/me/history").text.split('class="me-reps"')[1].split('class="me-foot"')[0]
    assert "p***@reps-test.local" not in block and "c***@reps-test.local" in block


def test_owner_block_hidden_without_reps_and_foreign_rep_stays(web, cards):
    client, _ = web
    ac.claim(KID, cards["kid"], BD_KID)
    login(client, KID)
    assert "Доступ к вашей истории" not in client.get("/me/history").text
    ar.become_rep(PARENT, cards["kid"], BD_KID)
    rep_id = ar.reps_of(KID)[0]["id"]
    client.post("/me/unclaim", data={"client_id": cards["kid"]})             # привязки нет — убирать чужое нельзя
    client.post("/me/rep/remove", data={"rep_id": rep_id}, follow_redirects=False)
    assert ar.rep_cards(PARENT) == ([cards["kid"]], [])



def test_claim_own_card_drops_own_rep_access(db, cards, mail):
    """Заявил «Это я» карточку, к которой был представителем, — доступ представителя снимается (журнал claimed)."""
    conn, cur = db
    assert ar.become_rep(PARENT, cards["kid"], BD_KID) == ar.RepResult.OK
    assert ac.claim(PARENT, cards["kid"], BD_KID).value == "ok"
    assert all(r["client_id"] != cards["kid"] for r in rep_rows(cur))
    assert ({"email": PARENT, "reason": "claimed"}, PARENT) in journal(cur, "athlete_unrep", cards["kid"])


def test_confirm_texts_are_js_safe_for_apostrophe_in_name(web, cards, db):
    """ФИ с апострофом не ломает onsubmit="confirm(...)" (ни сырого ', ни незаэкранированных кавычек)."""
    import re as _re
    conn, cur = db
    client, _ = web
    login(client)
    rep_via_web(client, cards["kid"], "2015-04-05")
    cur.execute("UPDATE clients SET surname = %s WHERE id = %s AND surname LIKE 'Тестпред%%'",
                (f"Тестпред'О{cards['kid']}", cards["kid"]))        # уникально — uk_client(ФИ, ДР)
    conn.commit()
    page = client.get(f"/me/athlete/{cards['kid']}").text
    handler = _re.search(r'action="/me/unrep" onsubmit="([^"]*)"', page).group(1)
    assert "'" not in handler and "&#39;" not in handler
    assert handler.startswith("return confirm(&#34;") and r"\u0027" in handler   # апостроф экранирован tojson
