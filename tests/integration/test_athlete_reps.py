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
