"""Обращения кабинета (Б3) на локальной БД. Тестовые данные — почты *@b3-test.local, событие «Тест Б3» 2099 года,
карточки «Тестбтри …»; фикстура убирает их до и после."""
import json
from datetime import date
from unittest.mock import patch

import pytest

from src.analytics.db_pool import get_pooled_connection
from src.krasmarafon.services import athlete_claims as ac
from src.krasmarafon.services import athlete_find as af
from src.krasmarafon.services import athlete_reps as ar
from src.krasmarafon.services import athlete_requests as rq
from src.krasmarafon.services.athlete_requests import RequestError

DOMAIN = "b3-test.local"
EV = "Тест Б3"
SURNAME = "Тестбтри"
OWNER = f"owner@{DOMAIN}"      # владелец карточки a
ME = f"me@{DOMAIN}"           # заявитель: своя заявка на карточку a на почте
FINDER = f"finder@{DOMAIN}"   # заявитель без заявки: доказательство — находка
REP = f"rep@{DOMAIN}"         # представитель карточки a
PARENT = f"parent@{DOMAIN}"   # владелец карточки b
OP = f"operator@{DOMAIN}"
BD1, BD2 = date(1986, 5, 1), date(2018, 3, 2)


@pytest.fixture
def db():
    conn = get_pooled_connection()
    if not conn:
        pytest.skip("Нет локальной БД")
    cur = conn.cursor(dictionary=True)
    cur.execute("SHOW TABLES LIKE 'athlete_requests'")
    if not cur.fetchone():
        conn.close()
        pytest.skip("Миграция athlete_requests не применена")

    def cleanup():
        like = f"%@{DOMAIN}"
        cur.execute("DELETE FROM athlete_claims WHERE email LIKE %s", (like,))
        cur.execute("DELETE FROM athlete_reps WHERE email LIKE %s", (like,))
        cur.execute("DELETE FROM athlete_claim_attempts WHERE email LIKE %s", (like,))
        cur.execute("DELETE FROM athlete_find_attempts WHERE email LIKE %s", (like,))
        cur.execute("DELETE FROM dq_actions WHERE action LIKE 'athlete\\_%' AND (details LIKE %s OR finding_key IN "
                    "(SELECT CONCAT('client:', id) FROM clients WHERE surname = %s))", (f"%{DOMAIN}%", SURNAME))
        cur.execute("DELETE FROM athlete_requests WHERE email LIKE %s", (like,))
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


def add_lead(cur, name, birthday, email, start_number):
    cur.execute("""INSERT INTO leads (surname, name, sex, city, club, birthday, email, ma_email, phone, event_name,
                   event_distance, event_year, products, amount, client_id, event_id, is_duplicate, status, is_new,
                   is_new_event, is_name_suspicious, start_number, created_at)
                   VALUES (%s, %s, 'Мужчина', '', '', %s, %s, NULL, '', %s, '5 км', 2099, '', 0, 0, 0, 0, 0, 0, 0, 0,
                           %s, NOW())""", (SURNAME, name, birthday, email, EV, start_number))
    cur.execute("SELECT id, client_id, event_id FROM leads WHERE id = %s", (cur.lastrowid,))
    return cur.fetchone()


@pytest.fixture
def cards(db):
    """a — Иван ДР 1986 (заявки owner@, me@, rep@; результат 9202); b — Мария ДР 2018 (заявка parent@, свободная);
    stub — без ДР."""
    conn, cur = db
    a = add_lead(cur, "Иван", BD1, OWNER, 9201)
    add_lead(cur, "Иван", BD1, ME, 9203)
    add_lead(cur, "Иван", BD1, REP, 9204)
    b = add_lead(cur, "Мария", BD2, PARENT, 9205)
    stub = add_lead(cur, "Безбд", date(1900, 1, 1), PARENT, 9206)
    cur.execute("""INSERT INTO results (surname, name, birthday, sex, event_id, start_number, race_status,
                   time_gun_finish, rank_absolute, client_id) VALUES (%s, 'Иван', %s, 'Мужчина', %s, 9202, 'Finished',
                   '00:25:00', 1, %s)""", (SURNAME, BD1, a["event_id"], a["client_id"]))
    result_a = cur.lastrowid
    conn.commit()
    return {"a": a["client_id"], "b": b["client_id"], "stub": stub["client_id"], "result_a": result_a,
            "lead_a": a["id"], "lead_b": b["id"]}


@pytest.fixture
def claimed(cards):
    """OWNER заявил карточку a, PARENT — b."""
    assert ac.claim(OWNER, cards["a"], BD1).value == "ok"
    assert ac.claim(PARENT, cards["b"], BD2).value == "ok"
    return cards


@pytest.fixture
def mail():
    with patch.object(rq, "send_mail") as m:
        yield m


def journal(cur, action, key):
    cur.execute("SELECT details, done_by FROM dq_actions WHERE action = %s AND finding_key = %s ORDER BY id",
                (action, key))
    return [(json.loads(r["details"]), r["done_by"]) for r in cur.fetchall()]


def request_row(cur, rid):
    cur.execute("SELECT * FROM athlete_requests WHERE id = %s", (rid,))
    return cur.fetchone()


# --- create: dispute --------------------------------------------------------------------------------------------

def test_dispute_with_own_lead_on_email(db, claimed, mail):
    conn, cur = db
    rid = rq.create(ME, "dispute", client_id=claimed["a"], comment="  это я  ")
    r = request_row(cur, rid)
    assert (r["email"], r["kind"], r["client_id"], r["status"], r["comment"]) == (ME, "dispute", claimed["a"], "new", "это я")
    [(details, who)] = journal(cur, "athlete_request", f"client:{claimed['a']}")
    assert who == ME and details["kind"] == "dispute" and details["request_id"] == rid
    assert not mail.called


def test_dispute_with_find_token_only(db, claimed):
    conn, cur = db
    with pytest.raises(RequestError) as e:
        rq.create(FINDER, "dispute", client_id=claimed["a"])
    assert e.value.code == "forbidden"
    with pytest.raises(RequestError):
        rq.create(FINDER, "dispute", client_id=claimed["a"], find_token=af.make_token(ME, claimed["a"]))   # чужая почта
    with pytest.raises(RequestError):
        rq.create(FINDER, "dispute", client_id=claimed["a"], find_token=af.make_token(FINDER, claimed["b"]))  # не та карточка
    rid = rq.create(FINDER, "dispute", client_id=claimed["a"], find_token=af.make_token(FINDER, claimed["a"]))
    assert json.loads(request_row(cur, rid)["payload"]) == {"via": "find"}


def test_dispute_needs_card_claimed_by_someone_else(db, cards):
    with pytest.raises(RequestError) as e:                       # карточку никто не заявил
        rq.create(ME, "dispute", client_id=cards["a"])
    assert e.value.code == "forbidden"


def test_dispute_on_own_card_refused(db, claimed):
    with pytest.raises(RequestError):
        rq.create(OWNER, "dispute", client_id=claimed["a"])


# --- create: wrong_row ------------------------------------------------------------------------------------------

@pytest.mark.parametrize("table,key", [("results", "result_a"), ("leads", "lead_a")])
def test_wrong_row_of_own_card(db, claimed, table, key):
    conn, cur = db
    rid = rq.create(OWNER, "wrong_row", row=(table, claimed[key]), comment="не я")
    r = request_row(cur, rid)
    assert (r["kind"], r["client_id"], r["row_table"], r["row_id"]) == ("wrong_row", claimed["a"], table, claimed[key])


def test_wrong_row_of_foreign_card_refused(db, claimed):
    with pytest.raises(RequestError) as e:
        rq.create(OWNER, "wrong_row", row=("leads", claimed["lead_b"]))
    assert e.value.code == "forbidden"
    with pytest.raises(RequestError):
        rq.create(OWNER, "wrong_row", row=("users", 1))
    with pytest.raises(RequestError):
        rq.create(OWNER, "wrong_row", row=("results", 10 ** 9))
    with pytest.raises(RequestError):
        rq.create(OWNER, "wrong_row")


def test_wrong_row_of_card_you_represent(db, claimed):
    assert ar.become_rep(REP, claimed["a"], BD1).value == "ok"      # у REP есть заявка Иван ДР 1986 на почте
    assert rq.create(REP, "wrong_row", row=("leads", claimed["lead_a"])) > 0


# --- create: not_found, общие правила ---------------------------------------------------------------------------

def test_not_found_stores_payload_without_rights_check(db, cards):
    conn, cur = db
    payload = {"surname": "Тестбтри", "name": "Иван", "birthday": "1986-05-01", "bib": 77}
    rid = rq.create(FINDER, "not_found", payload=payload)
    r = request_row(cur, rid)
    assert r["client_id"] is None and json.loads(r["payload"]) == payload
    assert journal(cur, "athlete_request", f"request:{rid}")[0][1] == FINDER


def test_unknown_kind_and_long_comment(db, claimed):
    with pytest.raises(RequestError) as e:
        rq.create(ME, "spam", client_id=claimed["a"])
    assert e.value.code == "bad_kind"
    with pytest.raises(RequestError) as e:
        rq.create(ME, "dispute", client_id=claimed["a"], comment="я" * 1001)
    assert e.value.code == "too_long"
    assert rq.create(ME, "dispute", client_id=claimed["a"], comment="я" * 1000) > 0


def test_duplicate_open_request_returns_same_id(db, claimed):
    conn, cur = db
    first = rq.create(ME, "dispute", client_id=claimed["a"])
    assert rq.create(ME, "dispute", client_id=claimed["a"], comment="ещё раз") == first
    assert rq.create(OWNER, "wrong_row", row=("leads", claimed["lead_a"])) != first
    cur.execute("SELECT COUNT(*) n FROM athlete_requests WHERE email = %s", (ME,))
    assert cur.fetchone()["n"] == 1
    assert len(journal(cur, "athlete_request", f"client:{claimed['a']}")) == 2    # дубль журнал не пишет
    rq.resolve(first, "close", OP)
    assert rq.create(ME, "dispute", client_id=claimed["a"]) != first               # закрытое — не дубль


def test_limit_three_open_requests(db, cards):
    for bib in (1, 2, 3):
        rq.create(FINDER, "not_found", payload={"bib": bib})
    with pytest.raises(RequestError) as e:
        rq.create(FINDER, "not_found", payload={"bib": 4})
    assert e.value.code == "limit"
    assert rq.create(FINDER, "not_found", payload={"bib": 3}) > 0                  # дубль — не ошибка лимита
    rid = rq.create(ME, "not_found", payload={"bib": 1})                            # лимит — на аккаунт
    rq.resolve(rid, "close", OP)
    rq.resolve(rq.create(FINDER, "not_found", payload={"bib": 1}), "close", OP)
    assert rq.create(FINDER, "not_found", payload={"bib": 4}) > 0                   # закрытые не считаются


# --- list_requests / count_new ---------------------------------------------------------------------------------

def test_list_and_count(db, claimed):
    base = rq.count_new()
    r1 = rq.create(ME, "dispute", client_id=claimed["a"], comment="я")
    r2 = rq.create(FINDER, "not_found", payload={"bib": 5})
    assert rq.count_new() == base + 2
    new = {r["id"]: r for r in rq.list_requests("new")}
    assert new[r1]["card"] == f"{SURNAME} Иван" and new[r1]["comment"] == "я" and new[r1]["email"] == ME
    assert new[r2]["payload"] == {"bib": 5} and new[r2]["card"] is None
    rq.resolve(r1, "reject", OP, "нет")
    assert r1 not in {r["id"] for r in rq.list_requests("new")}
    closed = {r["id"]: r for r in rq.list_requests("closed")}
    assert closed[r1]["resolution"] == "reject" and closed[r1]["answer"] == "нет" and closed[r1]["resolved_by"] == OP
    assert rq.count_new() == base + 1


# --- resolve ---------------------------------------------------------------------------------------------------

def test_transfer_moves_claim_keeps_reps_and_logs(db, claimed, mail):
    conn, cur = db
    assert ar.become_rep(REP, claimed["a"], BD1).value == "ok"
    rid = rq.create(ME, "dispute", client_id=claimed["a"])
    info = rq.resolve(rid, "transfer", OP, "проверили")
    assert info["email"] == ME and info["former_owner"] == OWNER and info["action"] == "transfer"
    cur.execute("SELECT email, birthday FROM athlete_claims WHERE client_id = %s", (claimed["a"],))
    assert cur.fetchall() == [{"email": ME, "birthday": BD1}]
    cur.execute("SELECT email FROM athlete_reps WHERE client_id = %s", (claimed["a"],))
    assert [r["email"] for r in cur.fetchall()] == [REP]
    key = f"client:{claimed['a']}"
    assert journal(cur, "athlete_unclaim", key)[-1] == ({"email": OWNER, "reason": "dispute"}, OP)
    assert journal(cur, "athlete_claim", key)[-1][0] == {"email": ME, "via": "dispute", "by": OP}
    [(det, who)] = journal(cur, "athlete_request_resolve", key)
    assert who == OP and det["action"] == "transfer" and det["answer"] == "проверили" and det["request_id"] == rid
    r = request_row(cur, rid)
    assert (r["status"], r["resolution"], r["answer"], r["resolved_by"]) == ("resolved", "transfer", "проверили", OP)
    assert r["resolved_at"] is not None
    assert not mail.called                                       # письма — отдельно, notify_resolved в фоне


def test_transfer_drops_applicants_own_rep_access(db, claimed):
    conn, cur = db
    assert ar.become_rep(REP, claimed["a"], BD1).value == "ok"
    rq.resolve(rq.create(REP, "dispute", client_id=claimed["a"]), "transfer", OP)
    cur.execute("SELECT 1 FROM athlete_reps WHERE client_id = %s AND email = %s", (claimed["a"], REP))
    assert cur.fetchone() is None
    cur.execute("SELECT email FROM athlete_claims WHERE client_id = %s", (claimed["a"],))
    assert cur.fetchone()["email"] == REP


@pytest.mark.parametrize("action,kind", [("transfer", "not_found"), ("transfer", "wrong_row"), ("attach", "dispute")])
def test_action_not_allowed_for_kind(db, claimed, action, kind):
    conn, cur = db
    kw = {"not_found": {"payload": {"bib": 1}}, "wrong_row": {"row": ("leads", claimed["lead_a"])}}[kind] \
        if kind != "dispute" else {"client_id": claimed["a"]}
    rid = rq.create(ME if kind == "dispute" else OWNER, kind, **kw)
    with pytest.raises(RequestError) as e:
        rq.resolve(rid, action, OP, client_id=claimed["b"])
    assert e.value.code == "bad_action"
    assert request_row(cur, rid)["status"] == "new"


@pytest.mark.parametrize("action", ["reject", "close"])
def test_reject_and_close_with_answer(db, claimed, action):
    conn, cur = db
    rid = rq.create(OWNER, "wrong_row", row=("results", claimed["result_a"]))
    info = rq.resolve(rid, action, OP, "ответ")
    assert info["former_owner"] is None and info["answer"] == "ответ"
    r = request_row(cur, rid)
    assert (r["status"], r["resolution"], r["answer"]) == ("resolved", action, "ответ")
    cur.execute("SELECT email FROM athlete_claims WHERE client_id = %s", (claimed["a"],))
    assert cur.fetchone()["email"] == OWNER                      # карточку reject/close не трогают
    with pytest.raises(RequestError) as e:
        rq.resolve(rid, "close", OP)
    assert e.value.code == "closed"


def test_resolve_validation(db, claimed):
    rid = rq.create(OWNER, "wrong_row", row=("results", claimed["result_a"]))
    with pytest.raises(RequestError) as e:
        rq.resolve(rid, "explode", OP)
    assert e.value.code == "bad_action"
    with pytest.raises(RequestError) as e:
        rq.resolve(rid, "close", OP, "я" * 1001)
    assert e.value.code == "too_long"
    with pytest.raises(RequestError) as e:
        rq.resolve(10 ** 9, "close", OP)
    assert e.value.code == "not_found"


def test_attach_binds_chosen_free_card(db, claimed):
    conn, cur = db
    free = add_lead(cur, "Свободный", BD1, PARENT, 9207)["client_id"]
    conn.commit()
    rid = rq.create(FINDER, "not_found", payload={"surname": SURNAME, "name": "Свободный", "bib": 1})
    info = rq.resolve(rid, "attach", OP, "привязали", client_id=free)
    assert info["email"] == FINDER and info["client_id"] == free and info["former_owner"] is None
    cur.execute("SELECT email, birthday FROM athlete_claims WHERE client_id = %s", (free,))
    assert cur.fetchall() == [{"email": FINDER, "birthday": BD1}]
    assert journal(cur, "athlete_claim", f"client:{free}")[-1][0] == {"email": FINDER, "via": "attach", "by": OP}
    assert request_row(cur, rid)["client_id"] == free


def test_attach_refusals(db, claimed):
    conn, cur = db
    rid = rq.create(FINDER, "not_found", payload={"bib": 1})
    with pytest.raises(RequestError) as e:
        rq.resolve(rid, "attach", OP)                            # карточка не указана
    assert e.value.code == "no_card"
    with pytest.raises(RequestError) as e:
        rq.resolve(rid, "attach", OP, client_id=10 ** 9)
    assert e.value.code == "no_card"
    with pytest.raises(RequestError) as e:
        rq.resolve(rid, "attach", OP, client_id=claimed["a"])    # уже заявлена другим
    assert e.value.code == "taken"
    with pytest.raises(RequestError) as e:
        rq.resolve(rid, "attach", OP, client_id=claimed["stub"])  # без ДР
    assert e.value.code == "no_birthday"
    assert request_row(cur, rid)["status"] == "new"              # ошибка — решение откатилось
    cur.execute("SELECT 1 FROM athlete_claims WHERE email = %s", (FINDER,))
    assert cur.fetchone() is None


# --- письма ----------------------------------------------------------------------------------------------------

def test_notify_resolved_transfer_mails_both(db, claimed, mail):
    rid = rq.create(ME, "dispute", client_id=claimed["a"])
    info = rq.resolve(rid, "transfer", OP, "проверили <b>")
    rq.notify_resolved(info)
    sent = {c.args[0]: c.args for c in mail.call_args_list}
    assert set(sent) == {ME, OWNER}
    _, subject, text, html = sent[ME]
    assert subject == "Ваше обращение рассмотрено"
    assert "Карточка привязана к вашему кабинету" in text and "проверили <b>" in text and "&lt;b&gt;" in html
    _, subject, text, html = sent[OWNER]
    assert "передана другому аккаунту по решению организаторов" in text and f"{SURNAME} Иван" in text
    assert "1@krasmarafon.ru" in text


@pytest.mark.parametrize("action,phrase", [("reject", "Обращение отклонено"), ("close", "Обращение закрыто")])
def test_notify_resolved_reject_close_mail_applicant_only(db, claimed, mail, action, phrase):
    rid = rq.create(OWNER, "wrong_row", row=("results", claimed["result_a"]))
    rq.notify_resolved(rq.resolve(rid, action, OP))
    assert [c.args[0] for c in mail.call_args_list] == [OWNER]
    assert phrase in mail.call_args_list[0].args[2] and "Ответ" not in mail.call_args_list[0].args[2]


def test_notify_resolved_mail_failure_does_not_raise(db, claimed, mail):
    mail.side_effect = RuntimeError("smtp")
    rid = rq.create(ME, "dispute", client_id=claimed["a"])
    rq.notify_resolved(rq.resolve(rid, "transfer", OP))
    assert mail.call_count == 2                                  # сбой первого письма не мешает второму


# --- гонки и одна ДР ---------------------------------------------------------------------------------------------

def _parallel(n, fn):
    from concurrent.futures import ThreadPoolExecutor
    outcomes = []

    def call(i):
        try:
            return ("ok", fn(i))
        except RequestError as e:
            return ("err", e.code)

    with ThreadPoolExecutor(max_workers=n) as pool:
        outcomes = list(pool.map(call, range(n)))
    return outcomes


def test_parallel_identical_create_makes_one_row(db, claimed):
    conn, cur = db
    outcomes = _parallel(5, lambda i: rq.create(ME, "dispute", client_id=claimed["a"]))
    assert {kind for kind, _ in outcomes} == {"ok"} and len({v for _, v in outcomes}) == 1
    cur.execute("SELECT COUNT(*) n FROM athlete_requests WHERE email = %s", (ME,))
    assert cur.fetchone()["n"] == 1


def test_parallel_different_create_respects_limit(db, cards):
    conn, cur = db
    outcomes = _parallel(5, lambda i: rq.create(FINDER, "not_found", payload={"bib": i}))
    assert sorted(v for k, v in outcomes if k == "err") == ["limit", "limit"]
    cur.execute("SELECT COUNT(*) n FROM athlete_requests WHERE email = %s AND status = 'new'", (FINDER,))
    assert cur.fetchone()["n"] == 3


def test_transfer_and_attach_refuse_applicant_with_other_birthday(db, claimed):
    conn, cur = db
    rid = rq.create(ME, "dispute", client_id=claimed["a"])
    cur.execute("INSERT INTO athlete_claims (email, client_id, birthday) VALUES (%s, %s, %s)", (ME, claimed["stub"], BD2))
    cur.execute("UPDATE clients SET birthday = %s WHERE id = %s", (BD2, claimed["stub"]))   # своя карточка ДР 2018
    conn.commit()
    with pytest.raises(RequestError) as e:
        rq.resolve(rid, "transfer", OP)
    assert e.value.code == "other_person"
    assert request_row(cur, rid)["status"] == "new"
    cur.execute("SELECT email FROM athlete_claims WHERE client_id = %s", (claimed["a"],))
    assert cur.fetchone()["email"] == OWNER                                           # прежний владелец на месте
    nid = rq.create(ME, "not_found", payload={"bib": 1})
    free = add_lead(cur, "Свободный", BD1, PARENT, 9208)["client_id"]
    conn.commit()
    with pytest.raises(RequestError) as e:
        rq.resolve(nid, "attach", OP, client_id=free)
    assert e.value.code == "other_person"
