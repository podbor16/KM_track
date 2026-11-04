"""«Найти себя» (Б3) на локальной БД. Тестовые данные — почты *@b3-test.local, событие «Тест Б3» 2099 года,
карточки «Тестбтри …»; фикстура убирает их до и после."""
import json
from datetime import date
from unittest.mock import patch

import pytest

from src.analytics.db_pool import get_pooled_connection
from src.krasmarafon.services import athlete_claims as ac
from src.krasmarafon.services import athlete_find as af
from src.krasmarafon.services.athlete_claims import ClaimResult
from src.krasmarafon.services.athlete_find import FindLimit

DOMAIN = "b3-test.local"
EV = "Тест Б3"
SURNAME = "Тестбтри"
ME = f"me@{DOMAIN}"
OWNER = f"owner@{DOMAIN}"
OTHER = f"other@{DOMAIN}"
BD1, BD2 = date(1986, 5, 1), date(2018, 3, 2)


@pytest.fixture
def db():
    conn = get_pooled_connection()
    if not conn:
        pytest.skip("Нет локальной БД")
    cur = conn.cursor(dictionary=True)
    cur.execute("SHOW TABLES LIKE 'athlete_find_attempts'")
    if not cur.fetchone():
        conn.close()
        pytest.skip("Миграция athlete_requests не применена")

    def cleanup():
        like = f"%@{DOMAIN}"
        cur.execute("DELETE FROM athlete_claims WHERE email LIKE %s", (like,))
        cur.execute("DELETE FROM athlete_reps WHERE email LIKE %s", (like,))
        cur.execute("DELETE FROM athlete_claim_attempts WHERE email LIKE %s", (like,))
        cur.execute("DELETE FROM athlete_find_attempts WHERE email LIKE %s", (like,))
        cur.execute("DELETE FROM athlete_requests WHERE email LIKE %s", (like,))
        cur.execute("DELETE FROM dq_actions WHERE action LIKE 'athlete\\_%' AND (details LIKE %s OR finding_key IN "
                    "(SELECT CONCAT('client:', id) FROM clients WHERE surname = %s))", (f"%{DOMAIN}%", SURNAME))
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


def add_lead(cur, name, birthday, email, start_number, year=2099):
    cur.execute("""INSERT INTO leads (surname, name, sex, city, club, birthday, email, ma_email, phone, event_name,
                   event_distance, event_year, products, amount, client_id, event_id, is_duplicate, status, is_new,
                   is_new_event, is_name_suspicious, start_number, created_at)
                   VALUES (%s, %s, 'Мужчина', '', '', %s, %s, NULL, '', %s, '5 км', %s, '', 0, 0, 0, 0, 0, 0, 0, 0,
                           %s, NOW())""", (SURNAME, name, birthday, email, EV, year, start_number))
    cur.execute("SELECT client_id, event_id FROM leads WHERE id = %s", (cur.lastrowid,))
    return cur.fetchone()


@pytest.fixture
def cards(db):
    """a — Иван, ДР 1986, заявка с owner@ (номер 9101) и результат с номером 9102 (привязан к карточке явно);
    b — Мария, ДР 2018, номер 9103; stub — без ДР, номер 9104."""
    conn, cur = db
    a = add_lead(cur, "Иван", BD1, OWNER, 9101)
    b = add_lead(cur, "Мария", BD2, OTHER, 9103)
    stub = add_lead(cur, "Безбд", date(1900, 1, 1), OTHER, 9104)
    cur.execute("""INSERT INTO results (surname, name, birthday, sex, event_id, start_number, race_status,
                   time_gun_finish, rank_absolute, client_id) VALUES (%s, 'Иван', %s, 'Мужчина', %s, 9102, 'Finished',
                   '00:25:00', 1, %s)""", (SURNAME, BD1, a["event_id"], a["client_id"]))
    conn.commit()
    return {"a": a["client_id"], "b": b["client_id"], "stub": stub["client_id"]}


@pytest.fixture(autouse=True)
def no_mail():
    with patch.object(ac, "send_mail") as m:
        yield m


def journal(cur, action, client_id):
    cur.execute("SELECT details, done_by FROM dq_actions WHERE action = %s AND finding_key = %s ORDER BY id",
                (action, f"client:{client_id}"))
    return [(json.loads(r["details"]), r["done_by"]) for r in cur.fetchall()]


# --- find_card -------------------------------------------------------------------------------------------------

def test_find_by_lead_number(db, cards):
    found = af.find_card(ME, SURNAME, "Иван", BD1, 9101)
    assert found["client_id"] == cards["a"]
    assert found["title"] == f"{SURNAME} Иван"
    assert found["since"] == 2099 and found["starts"] == 1


def test_find_by_result_number(db, cards):
    assert af.find_card(ME, SURNAME, "Иван", BD1, 9102)["client_id"] == cards["a"]


def test_find_ignores_case_and_spaces(db, cards):
    assert af.find_card(ME, f"  {SURNAME.upper()} ", " иван", BD1, "9101")["client_id"] == cards["a"]


@pytest.mark.parametrize("surname,name,bd,bib", [
    (SURNAME, "Иван", BD1, 9999),                 # нет такого номера
    (SURNAME, "Иван", BD1, 9103),                 # номер другой карточки
    (SURNAME, "Петр", BD1, 9101),                 # другое имя
    ("Тестдругой", "Иван", BD1, 9101),            # другая фамилия
    (SURNAME, "Иван", date(1986, 5, 2), 9101),    # другая ДР
])
def test_find_misses_return_none(db, cards, surname, name, bd, bib):
    assert af.find_card(ME, surname, name, bd, bib) is None


def test_find_stub_birthday_never_matches(db, cards):
    assert af.find_card(ME, SURNAME, "Безбд", date(1900, 1, 1), 9104) is None


def test_find_bad_bib_is_none(db, cards):
    assert af.find_card(ME, SURNAME, "Иван", BD1, "abc") is None
    assert af.find_card(ME, SURNAME, "Иван", BD1, "") is None


def test_find_limit_five_per_day(db, cards):
    conn, cur = db
    for _ in range(5):
        assert af.find_card(ME, SURNAME, "Иван", BD1, 9999) is None
    with pytest.raises(FindLimit):
        af.find_card(ME, SURNAME, "Иван", BD1, 9101)           # лимит и на удачный поиск
    assert af.find_card(OTHER, SURNAME, "Иван", BD1, 9101) is not None    # лимит — на аккаунт
    cur.execute("UPDATE athlete_find_attempts SET created_at = NOW() - INTERVAL 2 DAY WHERE email = %s", (ME,))
    conn.commit()
    assert af.find_card(ME, SURNAME, "Иван", BD1, 9101) is not None       # старые попытки не считаются


# --- токен -----------------------------------------------------------------------------------------------------

def test_token_roundtrip_and_binding_to_email():
    t = af.make_token(ME, 123)
    assert af.read_token(ME, t) == 123
    assert af.read_token(f"ME@{DOMAIN} ", t) == 123           # почта нормализуется
    assert af.read_token(OTHER, t) is None


def test_token_expires_after_15_minutes():
    with patch.object(af.time, "time", return_value=1_000_000):
        t = af.make_token(ME, 5)
    with patch.object(af.time, "time", return_value=1_000_000 + 14 * 60):
        assert af.read_token(ME, t) == 5
    with patch.object(af.time, "time", return_value=1_000_000 + 16 * 60):
        assert af.read_token(ME, t) is None


@pytest.mark.parametrize("mutate", [
    lambda t: t[:-1] + ("0" if t[-1] != "0" else "1"),    # подпись
    lambda t: "9" + t,                                    # client_id
    lambda t: "",
    lambda t: "a.b.c",
    lambda t: "1.2",
])
def test_token_forgery_rejected(mutate):
    assert af.read_token(ME, mutate(af.make_token(ME, 7))) is None
    assert af.read_token(ME, None) is None


# --- заявление после поиска ------------------------------------------------------------------------------------

def test_claim_via_find_ok_without_lead_on_email(db, cards):
    conn, cur = db
    with pytest.raises(ValueError):
        ac.claim(ME, cards["a"], BD1)                              # без поиска заявки на почте нет
    assert ac.claim(ME, cards["a"], BD1, via_find=True) == ClaimResult.OK
    assert ac.claimed_cards(ME) == ([cards["a"]], [])
    assert journal(cur, "athlete_claim", cards["a"]) == [({"email": ME, "via": "find"}, ME)]


def test_claim_via_find_already_mine_and_taken(db, cards):
    assert ac.claim(ME, cards["a"], BD1, via_find=True) == ClaimResult.OK
    assert ac.claim(ME, cards["a"], BD1, via_find=True) == ClaimResult.ALREADY_MINE
    assert ac.claim(OTHER, cards["a"], BD1, via_find=True) == ClaimResult.TAKEN


def test_claim_via_find_other_person(db, cards):
    assert ac.claim(ME, cards["a"], BD1, via_find=True) == ClaimResult.OK
    assert ac.claim(ME, cards["b"], BD2, via_find=True) == ClaimResult.OTHER_PERSON


def test_claim_via_find_no_birthday(db, cards):
    assert ac.claim(ME, cards["stub"], date(1900, 1, 1), via_find=True) == ClaimResult.NO_BIRTHDAY


def test_claim_via_find_birthday_attempt_limit(db, cards):
    wrong = date(1990, 1, 1)
    results = [ac.claim(ME, cards["a"], wrong, via_find=True).value for _ in range(6)]
    assert results == ["mismatch"] * 5 + ["limit"]
