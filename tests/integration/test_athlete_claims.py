"""Привязка карточки к кабинету («Это я») на локальной БД. Тестовые данные — почты *@athlete-test.local,
событие «Тест кабинет Б1» 2099 года, карточки «Тестклейм …»; фикстура убирает их до и после."""
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from unittest.mock import patch

import pytest

from src.analytics.db_pool import get_pooled_connection
from src.krasmarafon.services import athlete_claims as ac
from src.krasmarafon.services.athlete_claims import ClaimResult
from src.krasmarafon.services.athlete_history import build_history

DOMAIN = "athlete-test.local"
EV = "Тест кабинет Б1"
SURNAME = "Тестклейм"
ME = f"me@{DOMAIN}"
OTHER = f"other@{DOMAIN}"
KAB = f"kab@{DOMAIN}"
BD1, BD2 = date(1986, 5, 1), date(2018, 3, 2)


@pytest.fixture
def db():
    conn = get_pooled_connection()
    if not conn:
        pytest.skip("Нет локальной БД")
    cur = conn.cursor(dictionary=True)
    cur.execute("SHOW TABLES LIKE 'athlete_claims'")
    if not cur.fetchone():
        conn.close()
        pytest.skip("Миграция athlete_claims не применена")

    def cleanup():
        # Порядок из-за внешних ключей: результаты -> заявки -> события -> карточки
        cur.execute("DELETE FROM athlete_claims WHERE email LIKE %s", (f"%@{DOMAIN}",))
        cur.execute("DELETE FROM athlete_claim_attempts WHERE email LIKE %s", (f"%@{DOMAIN}",))
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
        cur.execute("DELETE FROM clients WHERE surname = %s", (SURNAME,))
        conn.commit()

    cleanup()
    yield conn, cur
    cleanup()
    cur.close()
    conn.close()


def add_lead(cur, name, birthday, email, start_number, ma_email=None, year=2099):
    """Карточку и событие заводят триггеры leads (они же выставляют client_id/event_id)."""
    cur.execute("""INSERT INTO leads (surname, name, sex, city, club, birthday, email, ma_email, phone, event_name,
                   event_distance, event_year, products, amount, client_id, event_id, is_duplicate, status, is_new,
                   is_new_event, is_name_suspicious, start_number, created_at)
                   VALUES (%s, %s, 'Мужчина', '', '', %s, %s, %s, '', %s, '5 км', %s, '', 0, 0, 0, 0, 0, 0, 0, 0,
                           %s, NOW())""", (SURNAME, name, birthday, email, ma_email, EV, year, start_number))
    cur.execute("SELECT client_id, event_id FROM leads WHERE id = %s", (cur.lastrowid,))
    return cur.fetchone()


@pytest.fixture
def cards(db):
    """c1 (ДР 1986, заявки с me@, other@ и ma_email kab@, один результат), vanya («Ваня», та же ДР 1986, заявка с me@ —
    дубль карточки того же человека), c2 (ДР 2018, заявка с me@ — другой человек), nobd (без ДР, заявка с me@),
    foreign (заявка только с other@)."""
    conn, cur = db
    c1 = add_lead(cur, "Иван", BD1, ME, 9001)
    add_lead(cur, "Иван", BD1, OTHER, 9003, ma_email=KAB)
    c2 = add_lead(cur, "Мария", BD2, ME, 9002)
    vanya = add_lead(cur, "Ваня", BD1, ME, 9010)
    nobd = add_lead(cur, "Безбд", date(1900, 1, 1), ME, 9004)
    foreign = add_lead(cur, "Чужой", date(1990, 1, 1), OTHER, 9005)
    cur.execute("""INSERT INTO results (surname, name, birthday, sex, event_id, start_number, race_status,
                   time_gun_finish, rank_absolute) VALUES (%s, 'Иван', %s, 'Мужчина', %s, 9001, 'Finished',
                   '00:25:00', 1)""", (SURNAME, BD1, c1["event_id"]))
    conn.commit()
    return {"c1": c1["client_id"], "c2": c2["client_id"], "vanya": vanya["client_id"], "nobd": nobd["client_id"],
            "foreign": foreign["client_id"], "event_id": c1["event_id"]}


@pytest.fixture
def mail():
    with patch.object(ac, "send_mail") as m:
        yield m


def journal(cur, action, client_id):
    cur.execute("SELECT details, done_by FROM dq_actions WHERE action = %s AND finding_key = %s ORDER BY id",
                (action, f"client:{client_id}"))
    return [(json.loads(r["details"]), r["done_by"]) for r in cur.fetchall()]


def claim_rows(cur, email=ME):
    cur.execute("SELECT client_id, birthday FROM athlete_claims WHERE email = %s ORDER BY id", (email,))
    return cur.fetchall()


def test_claim_ok_writes_row_and_journal_without_sending_mail(db, cards, mail):
    conn, cur = db
    assert ac.claim(ME, cards["c1"], BD1) == ClaimResult.OK
    assert claim_rows(cur) == [{"client_id": cards["c1"], "birthday": BD1}]
    assert ac.claimed_cards(ME) == ([cards["c1"]], [])
    assert journal(cur, "athlete_claim", cards["c1"]) == [({"email": ME}, ME)]
    assert not mail.called                      # письма — отдельно, в фоне (notify_claimed)


def test_notify_claimed_sends_to_other_addresses(db, cards, mail):
    ac.notify_claimed(cards["c1"], ME)
    assert {c.args[0] for c in mail.call_args_list} == {OTHER, KAB}
    _, subject, text, html = mail.call_args_list[0].args
    assert subject == "Вашу историю забегов привязали к личному кабинету"
    assert "Тестклейм Иван" in text and f"m***@{DOMAIN}" in text and "1@krasmarafon.ru" in text
    assert ME not in text and "Тестклейм Иван" in html


def test_notify_claimed_mail_failure_does_not_raise(db, cards, mail):
    mail.side_effect = RuntimeError("smtp")
    ac.notify_claimed(cards["c1"], ME)
    assert mail.call_count == 2                 # сбой первого письма не мешает второму
    ac.notify_claimed(10 ** 9, ME)              # нет карточки — тихо ничего


def test_parallel_wrong_claims_respect_attempt_limit(db, cards, mail):
    conn, cur = db
    with ThreadPoolExecutor(max_workers=8) as ex:
        results = list(ex.map(lambda _: ac.claim(ME, cards["c1"], date(1990, 1, 1)), range(8)))
    assert sorted(r.value for r in results) == ["limit"] * 3 + ["mismatch"] * 5
    cur.execute("SELECT COUNT(*) n FROM athlete_claim_attempts WHERE email = %s", (ME,))
    assert cur.fetchone()["n"] == 5


def test_mismatch_cleans_attempts_older_than_a_day(db, cards, mail):
    conn, cur = db
    cur.execute("INSERT INTO athlete_claim_attempts (email, client_id, created_at) "
                "VALUES (%s, %s, NOW() - INTERVAL 2 DAY)", (OTHER, cards["c1"]))
    conn.commit()
    assert ac.claim(ME, cards["c1"], date(1990, 1, 1)) == ClaimResult.MISMATCH
    cur.execute("SELECT email FROM athlete_claim_attempts WHERE email LIKE %s", (f"%@{DOMAIN}",))
    assert [r["email"] for r in cur.fetchall()] == [ME]


def test_wrong_birthday_is_mismatch_and_logs_attempt(db, cards, mail):
    conn, cur = db
    assert ac.claim(ME, cards["c1"], date(1986, 5, 2)) == ClaimResult.MISMATCH
    cur.execute("SELECT COUNT(*) n FROM athlete_claim_attempts WHERE email = %s AND client_id = %s",
                (ME, cards["c1"]))
    assert cur.fetchone()["n"] == 1
    assert claim_rows(cur) == [] and not mail.called


def test_five_wrong_attempts_then_limit_even_for_right_birthday(db, cards, mail):
    conn, cur = db
    for _ in range(ac.CLAIM_ATTEMPTS_PER_DAY):
        assert ac.claim(ME, cards["c1"], date(1990, 1, 1)) == ClaimResult.MISMATCH
    assert ac.claim(ME, cards["c1"], BD1) == ClaimResult.LIMIT
    assert claim_rows(cur) == []
    cur.execute("SELECT COUNT(*) n FROM athlete_claim_attempts WHERE email = %s", (ME,))
    assert cur.fetchone()["n"] == 5          # попытка сверх лимита не пишется
    # лимит — на пару (аккаунт, карточка): другую карточку можно заявить
    assert ac.claim(ME, cards["vanya"], BD1) == ClaimResult.OK


def test_old_attempts_do_not_count(db, cards, mail):
    conn, cur = db
    for _ in range(5):
        cur.execute("INSERT INTO athlete_claim_attempts (email, client_id, created_at) "
                    "VALUES (%s, %s, NOW() - INTERVAL 2 DAY)", (ME, cards["c1"]))
    conn.commit()
    assert ac.claim(ME, cards["c1"], BD1) == ClaimResult.OK


def test_repeat_claim_is_already_mine_without_second_mail(db, cards, mail):
    assert ac.claim(ME, cards["c1"], BD1) == ClaimResult.OK
    mail.reset_mock()
    assert ac.claim(ME, cards["c1"], BD1) == ClaimResult.ALREADY_MINE
    assert not mail.called


def test_card_claimed_by_other_account_is_taken(db, cards, mail):
    conn, cur = db
    assert ac.claim(ME, cards["c1"], BD1) == ClaimResult.OK
    assert ac.claim(OTHER, cards["c1"], BD1) == ClaimResult.TAKEN
    assert ac.claim(OTHER, cards["c1"], date(1999, 1, 1)) == ClaimResult.TAKEN   # ДР не проверяется, кто владелец — не раскрываем
    assert [r["client_id"] for r in claim_rows(cur, OTHER)] == []
    assert claim_rows(cur) == [{"client_id": cards["c1"], "birthday": BD1}]


def test_stale_claim_does_not_block_other_account(db, cards, mail):
    """Привязка с устаревшей ДР снимается при проверке — карточку может заявить другой аккаунт."""
    conn, cur = db
    assert ac.claim(ME, cards["c1"], BD1) == ClaimResult.OK
    cur.execute("UPDATE clients SET birthday = '1986-05-02' WHERE id = %s", (cards["c1"],))
    conn.commit()
    assert ac.claim(OTHER, cards["c1"], date(1986, 5, 2)) == ClaimResult.OK
    assert claim_rows(cur) == []
    assert ac.claimed_cards(OTHER) == ([cards["c1"]], [])
    assert journal(cur, "athlete_unclaim", cards["c1"])[0][0]["reason"] == "birthday_changed"


def test_card_without_birthday(db, cards, mail):
    for bd in (date(1900, 1, 1), date(1986, 5, 1)):
        assert ac.claim(ME, cards["nobd"], bd) == ClaimResult.NO_BIRTHDAY


def test_card_not_in_account_leads_raises(db, cards, mail):
    with pytest.raises(ValueError):
        ac.claim(ME, cards["foreign"], date(1990, 1, 1))
    with pytest.raises(ValueError):
        ac.claim(ME, 10 ** 9, date(1990, 1, 1))


def test_email_is_normalized(db, cards, mail):
    assert ac.claim(f"  ME@{DOMAIN.upper()} ", cards["c1"], BD1) == ClaimResult.OK
    assert ac.claimed_cards(ME) == ([cards["c1"]], [])


def test_two_cards_one_account_with_same_birthday(db, cards, mail):
    assert ac.claim(ME, cards["c1"], BD1) == ClaimResult.OK
    assert ac.claim(ME, cards["vanya"], BD1) == ClaimResult.OK
    assert ac.claimed_cards(ME) == ([cards["c1"], cards["vanya"]], [])


def test_unclaim_removes_own_claim_only_and_logs(db, cards, mail):
    conn, cur = db
    ac.claim(ME, cards["c1"], BD1)
    ac.unclaim(OTHER, cards["c1"])                      # чужую не трогает
    assert ac.claimed_cards(ME) == ([cards["c1"]], [])
    assert journal(cur, "athlete_unclaim", cards["c1"]) == []
    ac.unclaim(ME, cards["c1"])
    assert ac.claimed_cards(ME) == ([], [])
    assert journal(cur, "athlete_unclaim", cards["c1"]) == [({"email": ME, "reason": "user"}, ME)]
    ac.unclaim(ME, cards["c1"])                         # повтор — без ошибки и без второй записи
    assert len(journal(cur, "athlete_unclaim", cards["c1"])) == 1


def test_changed_birthday_drops_claim_and_allows_reclaim(db, cards, mail):
    conn, cur = db
    ac.claim(ME, cards["c1"], BD1)
    cur.execute("UPDATE clients SET birthday = '1986-05-02' WHERE id = %s", (cards["c1"],))
    conn.commit()
    assert ac.claimed_cards(ME) == ([], [cards["c1"]])
    assert claim_rows(cur) == []
    assert journal(cur, "athlete_unclaim", cards["c1"]) == [({"email": ME, "reason": "birthday_changed"}, "system")]
    assert ac.claimed_cards(ME) == ([], [])             # второй раз снимать нечего
    assert ac.claim(ME, cards["c1"], date(1986, 5, 2)) == ClaimResult.OK


def test_changed_name_keeps_claim(db, cards, mail):
    conn, cur = db
    ac.claim(ME, cards["c1"], BD1)
    cur.execute("UPDATE clients SET name = 'Ванечка' WHERE id = %s", (cards["c1"],))
    conn.commit()
    assert ac.claimed_cards(ME) == ([cards["c1"]], [])


def test_deleted_card_drops_claim(db, cards, mail):
    conn, cur = db
    ac.claim(ME, cards["vanya"], BD1)
    ac.claim(ME, cards["c1"], BD1)
    cur.execute("DELETE FROM leads WHERE client_id = %s", (cards["vanya"],))
    cur.execute("DELETE FROM clients WHERE id = %s", (cards["vanya"],))
    conn.commit()
    assert ac.claimed_cards(ME) == ([cards["c1"]], [cards["vanya"]])
    assert journal(cur, "athlete_unclaim", cards["vanya"]) == [({"email": ME, "reason": "card_deleted"}, "system")]


def test_history_rows_cover_all_claimed_cards(db, cards, mail):
    results, leads = ac.history_rows([cards["c1"], cards["c2"]])
    assert len(results) == 1 and len(leads) == 3
    r = results[0]
    assert r["client_id"] == cards["c1"] and r["surname"] == SURNAME and r["event_name"] == EV
    assert r["event_year"] == 2099 and r["event_id"] == cards["event_id"]
    assert float(r["event_distance"]) == 5 and r["race_status"] == "Finished"
    assert {ld["client_id"] for ld in leads} == {cards["c1"], cards["c2"]}
    assert all(ld["event_name"] == EV and "refund" in ld and "event_date" in ld for ld in leads)

    hist = build_history(results, leads, date(2026, 11, 3), {EV: "kt"}, set())
    assert hist["tiles"]["finishes"] == 1
    assert [y["year"] for y in hist["years"]] == [2099]
    assert len(hist["years"][0]["items"]) == 2          # заявки 9001 и 9003 карточки c1 слились с её результатом
    assert ac.history_rows([]) == ([], [])


def test_lead_without_number_is_hidden_by_result_of_same_card_and_event(db, cards, mail):
    """Заявка без стартового номера не дублирует результат той же карточки в том же событии."""
    conn, cur = db
    from src.krasmarafon.services import athlete_cabinet

    add_lead(cur, "Иван", BD1, ME, None)
    conn.commit()
    results, leads = ac.history_rows([cards["c1"]])
    assert len(leads) == 3 and len(results) == 1
    hist = build_history(results, leads, date(2026, 11, 3), {EV: "kt"}, set())
    assert len(hist["years"][0]["items"]) == 1

    rows = [r for r in athlete_cabinet.fetch_leads(ME) if r["client_id"] == cards["c1"]]
    assert len(rows) == 2 and all(r["time_gun_finish"] is not None for r in rows)   # и с номером, и без
    past = athlete_cabinet.cabinet(ME, date(2100, 1, 1))
    c1_group = next(g for g in past if g["title"].startswith("Тестклейм Иван"))
    assert [e["time"] for e in c1_group["past"]] == ["0:25:00", "0:25:00"]


def test_history_rows_skip_duplicate_leads(db, cards, mail):
    conn, cur = db
    cur.execute("UPDATE leads SET is_duplicate = 1 WHERE client_id = %s AND start_number = 9002", (cards["c2"],))
    conn.commit()
    _, leads = ac.history_rows([cards["c1"], cards["c2"]])
    assert len(leads) == 2


def test_history_title_is_newest_claimed_card(db, cards, mail):
    conn, cur = db
    ac.claim(ME, cards["c1"], BD1)
    ac.claim(ME, cards["vanya"], BD1)
    cur.execute("UPDATE athlete_claims SET created_at = NOW() - INTERVAL 1 DAY WHERE client_id = %s", (cards["vanya"],))
    conn.commit()
    assert ac.history_title([cards["c1"], cards["vanya"]]) == "Тестклейм Иван"
    assert ac.history_title([]) == ""


def test_duplicate_accounts_lists_only_two_or_more_valid_cards(db, cards, mail):
    conn, cur = db
    ac.claim(ME, cards["c1"], BD1)
    assert [a for a in ac.duplicate_accounts() if a["email"] == ME] == []
    ac.claim(ME, cards["vanya"], BD1)
    mine = [a for a in ac.duplicate_accounts() if a["email"] == ME]
    assert len(mine) == 1
    assert mine[0]["cards"] == [
        {"id": cards["c1"], "surname": SURNAME, "name": "Иван", "birthday": BD1},
        {"id": cards["vanya"], "surname": SURNAME, "name": "Ваня", "birthday": BD1}]
    cur.execute("UPDATE clients SET birthday = '1986-05-03' WHERE id = %s", (cards["vanya"],))   # недействительная — не в счёт
    conn.commit()
    assert [a for a in ac.duplicate_accounts() if a["email"] == ME] == []


def test_notify_recipients(db, cards):
    assert ac.notify_recipients(cards["c1"], ME) == [KAB, OTHER]
    assert ac.notify_recipients(cards["c1"], OTHER) == [KAB, ME]
    assert ac.notify_recipients(cards["c2"], ME) == []


def test_notify_recipients_capped(db, cards):
    conn, cur = db
    for i in range(15):
        add_lead(cur, "Иван", BD1, f"extra{i:02d}@{DOMAIN}", 9100 + i)
    conn.commit()
    got = ac.notify_recipients(cards["c1"], ME)
    assert len(got) == ac.NOTIFY_MAX and got == sorted(got)


# ---------------------------------------------------------------- склейка карточек («Качество данных»)

MERGER = "test-claims-merge"


@pytest.fixture
def merge_env(db, cards, mail):
    """c1 (основная: 2 заявки + результат) и карточка «Ваня» (1 заявка с me@) с той же ДР — один человек."""
    from src.analytics import dq_actions

    conn, cur = db
    yield conn, cur, dq_actions, cards
    cur.execute("DELETE FROM dq_actions WHERE done_by = %s", (MERGER,))
    conn.commit()


def merge_details(cur, action_id):
    cur.execute("SELECT details FROM dq_actions WHERE id = %s", (action_id,))
    return json.loads(cur.fetchone()["details"])


def test_merge_moves_claim_to_survivor_when_birthday_same(merge_env):
    conn, cur, dq, c = merge_env
    assert ac.claim(ME, c["vanya"], BD1) == ClaimResult.OK

    surv, action_id = dq.merge_cards(conn, [c["c1"], c["vanya"]], SURNAME, "Иван", BD1.isoformat(), MERGER)

    assert surv == c["c1"]
    assert claim_rows(cur) == [{"client_id": c["c1"], "birthday": BD1}]
    assert ac.claimed_cards(ME) == ([c["c1"]], [])
    assert merge_details(cur, action_id)["athlete_claims"] == [
        {"client_id": c["vanya"], "email": ME, "moved_to": c["c1"]}]


def test_merge_with_other_final_birthday_drops_moved_claim(merge_env):
    conn, cur, dq, c = merge_env
    ac.claim(ME, c["vanya"], BD1)

    _, action_id = dq.merge_cards(conn, [c["c1"], c["vanya"]], SURNAME, "Иван", "1986-05-03", MERGER)

    assert merge_details(cur, action_id)["athlete_claims"][0]["moved_to"] == c["c1"]
    assert ac.claimed_cards(ME) == ([], [c["c1"]])
    assert journal(cur, "athlete_unclaim", c["c1"]) == [({"email": ME, "reason": "birthday_changed"}, "system")]


def test_merge_drops_claim_when_survivor_claimed_by_other_account(merge_env):
    conn, cur, dq, c = merge_env
    assert ac.claim(OTHER, c["c1"], BD1) == ClaimResult.OK
    assert ac.claim(ME, c["vanya"], BD1) == ClaimResult.OK

    _, action_id = dq.merge_cards(conn, [c["c1"], c["vanya"]], SURNAME, "Иван", BD1.isoformat(), MERGER)

    assert claim_rows(cur) == [] and claim_rows(cur, OTHER) == [{"client_id": c["c1"], "birthday": BD1}]
    assert merge_details(cur, action_id)["athlete_claims"] == [{"client_id": c["vanya"], "email": ME, "dropped": True}]
    assert journal(cur, "athlete_unclaim", c["vanya"]) == [({"email": ME, "reason": "merged"}, MERGER)]


def test_merge_keeps_survivor_claim_and_drops_second_claim_of_same_person(merge_env):
    conn, cur, dq, c = merge_env
    ac.claim(ME, c["c1"], BD1)
    ac.claim(ME, c["vanya"], BD1)

    _, action_id = dq.merge_cards(conn, [c["c1"], c["vanya"]], SURNAME, "Иван", BD1.isoformat(), MERGER)

    assert claim_rows(cur) == [{"client_id": c["c1"], "birthday": BD1}]
    assert ac.claimed_cards(ME) == ([c["c1"]], [])
    assert merge_details(cur, action_id)["athlete_claims"] == [{"client_id": c["vanya"], "email": ME, "dropped": True}]


def test_merge_without_claims_has_empty_list(merge_env):
    conn, cur, dq, c = merge_env
    _, action_id = dq.merge_cards(conn, [c["c1"], c["vanya"]], SURNAME, "Иван", BD1.isoformat(), MERGER)
    assert merge_details(cur, action_id)["athlete_claims"] == []


def test_failed_merge_leaves_claim_on_card(merge_env):
    """Ошибка склейки откатывает и перенос привязки: привязки на удалённой карточке не остаётся."""
    conn, cur, dq, c = merge_env
    ac.claim(ME, c["vanya"], BD1)
    with patch("src.analytics.client_merge.recompute_duplicates", side_effect=RuntimeError("boom")):
        with pytest.raises(RuntimeError):
            dq.merge_cards(conn, [c["c1"], c["vanya"]], SURNAME, "Иван", BD1.isoformat(), MERGER)
    assert claim_rows(cur) == [{"client_id": c["vanya"], "birthday": BD1}]
    cur.execute("SELECT COUNT(*) n FROM clients WHERE id IN (%s, %s)", (c["c1"], c["vanya"]))
    assert cur.fetchone()["n"] == 2
    assert ac.claimed_cards(ME) == ([c["vanya"]], [])


# ---------------------------------------------------------------- интерфейс: /me, «Это я», /me/history

import re  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from app import app  # noqa: E402
from src.core.auth import api_require_auth  # noqa: E402
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


def login(client, email=ME):
    with patch.object(aa, "send_mail") as m:
        client.post("/me/login", data={"email": email})
    code = re.search(r"\b(\d{6})\b", m.call_args[0][2]).group(1)
    r = client.post("/me/verify", data={"email": email, "code": code}, follow_redirects=False)
    assert r.status_code == 303


def claim_via_web(client, card, birthday):
    return client.post("/me/claim", data={"client_id": card, "birthday": birthday}, follow_redirects=False)


def test_me_shows_claim_button_with_form(web, cards):
    client, _ = web
    login(client)
    page = client.get("/me").text
    assert "Это я" in page and 'action="/me/claim"' in page and 'type="date"' in page
    assert f'name="client_id" value="{cards["c1"]}"' in page
    assert "Это вы" not in page and not re.search(r"<details[^>]* open", page)


def test_wrong_birthday_shows_error_at_the_card_form(web, cards):
    client, _ = web
    login(client)
    r = claim_via_web(client, cards["c1"], "1986-05-02")
    assert r.status_code == 303 and r.headers["location"] == f"/me?claim={cards['c1']}&r=mismatch"
    page = client.get(r.headers["location"]).text
    assert "Дата не совпадает" in page and re.search(r"<details[^>]* open", page)


@pytest.mark.parametrize("code, text", [
    ("limit", "Слишком много попыток. Попробуйте завтра или напишите нам на 1@krasmarafon.ru"),
    ("taken", "Эту карточку уже заявили — напишите нам на 1@krasmarafon.ru"),
    ("no_birthday", "Подтвердить не получится — напишите нам на 1@krasmarafon.ru"),
    ("date", "Проверьте дату"),
])
def test_claim_error_texts(web, cards, code, text):
    client, _ = web
    login(client)
    assert text in client.get(f"/me?claim={cards['c1']}&r={code}").text


def test_claim_error_for_unknown_code_or_card_is_not_shown(web, cards):
    client, _ = web
    login(client)
    assert "Дата не совпадает" not in client.get(f"/me?claim={cards['c2']}&r=bogus").text
    assert "Дата не совпадает" not in client.get("/me?claim=abc&r=mismatch").text


def test_invalid_date_no_birthday_and_taken_redirects(web, cards):
    client, _ = web
    login(client)
    assert claim_via_web(client, cards["c1"], "не дата").headers["location"] == f"/me?claim={cards['c1']}&r=date"
    assert claim_via_web(client, cards["nobd"], "1986-05-01").headers["location"] == \
        f"/me?claim={cards['nobd']}&r=no_birthday"
    ac.claim(OTHER, cards["c1"], BD1)
    assert claim_via_web(client, cards["c1"], "1986-05-01").headers["location"] == f"/me?claim={cards['c1']}&r=taken"


def test_right_birthday_claims_and_shows_badge_and_notifies(web, cards, mail):
    client, _ = web
    login(client)
    r = claim_via_web(client, cards["c1"], "1986-05-01")
    assert r.status_code == 303 and r.headers["location"] == "/me"
    assert {c.args[0] for c in mail.call_args_list} == {OTHER, KAB}      # фоновая задача выполнена после ответа
    page = client.get("/me").text
    assert "Это вы" in page and 'href="/me/history"' in page and "История" in page
    mail.reset_mock()                                                   # повтор — идемпотентно, без рассылки
    assert claim_via_web(client, cards["c1"], "1986-05-01").headers["location"] == "/me"
    assert not mail.called


def test_wrong_claim_does_not_notify(web, cards, mail):
    client, _ = web
    login(client)
    claim_via_web(client, cards["c1"], "1986-05-02")
    assert not mail.called


def test_claim_foreign_or_missing_card_redirects_with_same_not_yours_error(web, cards):
    """Чужая и несуществующая карточка неразличимы: тот же редирект с ошибкой, не 404 и не раскрытие существования."""
    client, _ = web
    login(client)
    for card in (cards["foreign"], 10 ** 9):
        r = claim_via_web(client, card, "1990-01-01")
        assert r.status_code == 303 and r.headers["location"] == f"/me?claim={card}&r=not_yours"
    assert "Эта карточка не совпадает с данными ваших заявок — напишите нам на 1@krasmarafon.ru" in         client.get(f"/me?claim={cards['foreign']}&r=not_yours").text


def test_claim_requires_session_and_same_origin(web, cards):
    client, _ = web
    r = claim_via_web(client, cards["c1"], "1986-05-01")
    assert r.status_code == 303 and r.headers["location"] == "/me/login"
    login(client)
    evil = {"Origin": "https://evil.example"}
    r = client.post("/me/claim", data={"client_id": cards["c1"], "birthday": "1986-05-01"}, headers=evil,
                    follow_redirects=False)
    assert r.status_code == 403
    r = client.post("/me/unclaim", data={"client_id": cards["c1"]}, headers=evil, follow_redirects=False)
    assert r.status_code == 403
    assert ac.claimed_cards(ME) == ([], [])


def test_history_page_for_claimed_card(web, cards):
    client, _ = web
    login(client)
    claim_via_web(client, cards["c1"], "1986-05-01")
    r = client.get("/me/history")
    assert r.status_code == 200
    page = r.text
    assert "Тестклейм Иван" in page and "Бегает с 2099" in page
    assert "Личные рекорды" in page and "Забеги и заявки" in page
    assert "0:25:00" in page and "5 км" in page and "5:00" in page          # время результата и темп
    assert "стартов" in page and "финишей" in page and "ср. темп" in page
    assert 'id="dyn"' not in page                                         # один год — динамики нет
    assert "mailto:1@krasmarafon.ru?subject=" in page
    assert "/me/unclaim" in page and f"Отвязать карточку №{cards['c1']}?" in page


def test_history_dynamics_block_with_two_years(web, cards, db):
    conn, cur = db
    old = add_lead(cur, "Иван", BD1, ME, 9020, year=2098)
    cur.execute("""INSERT INTO results (surname, name, birthday, sex, event_id, start_number, race_status,
                   time_gun_finish, rank_absolute) VALUES (%s, 'Иван', %s, 'Мужчина', %s, 9020, 'Finished',
                   '00:27:30', 1)""", (SURNAME, BD1, old["event_id"]))
    conn.commit()
    client, _ = web
    login(client)
    claim_via_web(client, cards["c1"], "1986-05-01")
    page = client.get("/me/history").text
    m = re.search(r'<script type="application/json" id="dyn">(.*?)</script>', page, re.S)
    assert m and json.loads(m.group(1)) == {"default": "5", "series": {"5": [[2098, 1650], [2099, 1500]]}}
    assert "/static/lib/chart4/chart.umd.min.js" in page


def test_history_redirects(web, cards):
    client, flag = web
    assert client.get("/me/history", follow_redirects=False).headers["location"] == "/me/login"
    login(client)
    r = client.get("/me/history", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/me"
    flag.unlink()
    assert client.get("/me/history", follow_redirects=False).status_code == 404
    assert client.post("/me/claim", data={"client_id": 1, "birthday": "2000-01-01"}).status_code == 404


def test_unclaim_via_web_removes_badge_and_history(web, cards):
    client, _ = web
    login(client)
    claim_via_web(client, cards["c1"], "1986-05-01")
    r = client.post("/me/unclaim", data={"client_id": cards["c1"]}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/me"
    assert "Это вы" not in client.get("/me").text
    assert client.get("/me/history", follow_redirects=False).headers["location"] == "/me"


def test_history_ignores_card_claimed_by_someone_else(web, cards):
    client, _ = web
    ac.claim(OTHER, cards["c1"], BD1)
    login(client)
    assert client.get("/me/history", follow_redirects=False).headers["location"] == "/me"


def test_changed_birthday_shows_explanation_and_button(web, cards, db):
    conn, cur = db
    client, _ = web
    login(client)
    claim_via_web(client, cards["c1"], "1986-05-01")
    cur.execute("UPDATE clients SET birthday = '1986-05-02' WHERE id = %s", (cards["c1"],))
    conn.commit()
    page = client.get("/me").text
    assert "Данные карточки изменились — подтвердите, что это вы" in page
    assert "Это вы" not in page and 'action="/me/claim"' in page
    assert claim_via_web(client, cards["c1"], "1986-05-02").headers["location"] == "/me"


def test_admin_duplicates_endpoint_requires_login(client):
    assert client.get("/api/admin/athlete-cabinet-duplicates").status_code == 401


def test_admin_duplicates_endpoint_lists_account_with_two_cards(db, cards, mail, client):
    ac.claim(ME, cards["c1"], BD1)
    ac.claim(ME, cards["vanya"], BD1)
    app.dependency_overrides[api_require_auth] = lambda: "testuser"
    try:
        r = client.get("/api/admin/athlete-cabinet-duplicates")
    finally:
        app.dependency_overrides.pop(api_require_auth, None)
    assert r.status_code == 200
    mine = [a for a in r.json()["accounts"] if a["email"] == ME]
    assert mine == [{"email": ME, "cards": [
        {"id": cards["c1"], "surname": SURNAME, "name": "Иван", "birthday": "1986-05-01"},
        {"id": cards["vanya"], "surname": SURNAME, "name": "Ваня", "birthday": "1986-05-01"}]}]


def test_claim_journal_rows_do_not_break_or_enter_undo_list(db, cards, mail):
    from src.analytics import dq_actions

    conn, cur = db
    ac.claim(ME, cards["c1"], BD1)
    ac.unclaim(ME, cards["c1"])
    assert journal(cur, "athlete_claim", cards["c1"]) and journal(cur, "athlete_unclaim", cards["c1"])
    acts = dq_actions.recent_actions(conn)
    assert not [a for a in acts if a["action"] in ("athlete_claim", "athlete_unclaim")]


def test_fix_fio_merge_moves_claim_like_merge(merge_env):
    """«Исправить ФИО» тоже склеивает карточки (такие ФИ и ДР уже у другой) — привязка переходит так же."""
    conn, cur, dq, c = merge_env
    assert ac.claim(ME, c["vanya"], BD1) == ClaimResult.OK
    cur.execute("SELECT id FROM results WHERE client_id = %s LIMIT 1", (c["c1"],))
    result_id = cur.fetchone()["id"]

    cid, action_id = dq.fix_fio(conn, result_id, SURNAME, "Ваня", MERGER)

    assert cid == c["c1"]
    assert ac.claimed_cards(ME) == ([c["c1"]], [])
    assert merge_details(cur, action_id)["athlete_claims"] == [
        {"client_id": c["vanya"], "email": ME, "moved_to": c["c1"]}]


def test_history_redirect_carries_dropped_cards_to_explanation(web, cards, db):
    conn, cur = db
    client, _ = web
    login(client)
    claim_via_web(client, cards["c1"], "1986-05-01")
    cur.execute("UPDATE clients SET birthday = '1986-05-02' WHERE id = %s", (cards["c1"],))
    conn.commit()
    r = client.get("/me/history", follow_redirects=False)
    assert r.headers["location"] == f"/me?changed={cards['c1']}"
    assert "Данные карточки изменились — подтвердите, что это вы" in client.get(r.headers["location"]).text


def test_me_ignores_absurdly_long_claim_param(web, cards):
    client, _ = web
    login(client)
    assert client.get("/me?claim=" + "9" * 5000 + "&r=mismatch&changed=" + "9" * 5000).status_code == 200


# ---------------------------------------------------------------- доработки: один человек на аккаунте, чужие слоты

SLOT = f"slot@{DOMAIN}"
IGOR_BD = date(1975, 3, 3)


def move_to(cur, client_id, where_sql, params):
    cur.execute(f"UPDATE leads SET client_id = %s WHERE event_name = %s AND {where_sql}", (client_id, EV, *params))


@pytest.fixture
def slot(db, cards):
    """Карточка Игоря (ДР 1975, заявка с other@), на которую «передан слот»: заявка и результат Марии (ДР 2018)
    с почты slot@ записаны на карточку Игоря."""
    conn, cur = db
    igor = add_lead(cur, "Игорь", IGOR_BD, OTHER, 9030)
    add_lead(cur, "Мария", BD2, SLOT, 9031)
    move_to(cur, igor["client_id"], "start_number = 9031", ())
    cur.execute("""INSERT INTO results (surname, name, birthday, sex, event_id, start_number, race_status,
                   time_gun_finish, client_id) VALUES (%s, 'Мария', %s, 'Женщина', %s, 9031, 'Finished',
                   '00:30:00', %s)""", (SURNAME, BD2, igor["event_id"], igor["client_id"]))
    conn.commit()
    return {"igor": igor["client_id"], "event_id": igor["event_id"]}


def add_typo_lead(cur, card_id, email, start_number):
    """Заявка «Игор» с ДР на день позже — опечатки в ФИ и ДР того же человека — записана на карточку card_id."""
    add_lead(cur, "Игор", date(1975, 3, 4), email, start_number)
    move_to(cur, card_id, "start_number = %s", (start_number,))


def test_second_card_with_other_birthday_is_other_person_before_limit_and_attempt(db, cards, mail):
    conn, cur = db
    assert ac.claim(ME, cards["c1"], BD1) == ClaimResult.OK
    for _ in range(ac.CLAIM_ATTEMPTS_PER_DAY):                         # лимит по c2 уже исчерпан
        cur.execute("INSERT INTO athlete_claim_attempts (email, client_id) VALUES (%s, %s)", (ME, cards["c2"]))
    conn.commit()
    assert ac.claim(ME, cards["c2"], BD2) == ClaimResult.OTHER_PERSON      # и до лимита
    assert ac.claim(ME, cards["c2"], date(1999, 9, 9)) == ClaimResult.OTHER_PERSON   # и до сверки ДР
    cur.execute("SELECT COUNT(*) n FROM athlete_claim_attempts WHERE email = %s AND client_id = %s",
                (ME, cards["c2"]))
    assert cur.fetchone()["n"] == ac.CLAIM_ATTEMPTS_PER_DAY             # попытка не пишется
    assert ac.claimed_cards(ME) == ([cards["c1"]], [])


def test_other_person_check_uses_only_valid_claims(db, cards, mail):
    conn, cur = db
    assert ac.claim(ME, cards["c1"], BD1) == ClaimResult.OK
    cur.execute("UPDATE clients SET birthday = '1986-05-02' WHERE id = %s", (cards["c1"],))
    conn.commit()                                                       # привязка устарела — ограничения нет
    assert ac.claim(ME, cards["c2"], BD2) == ClaimResult.OK
    assert ac.claimed_cards(ME) == ([cards["c2"]], [cards["c1"]])


def test_transferred_slot_gives_no_right_to_claim(db, cards, slot, mail):
    conn, cur = db
    cur.execute("UPDATE leads SET email = %s WHERE event_name = %s AND start_number = 9031", (ME, EV))
    conn.commit()                                                       # заявка Марии на карточке Игоря — с почты me@
    with pytest.raises(ValueError):
        ac.claim(ME, slot["igor"], IGOR_BD)
    cur.execute("SELECT COUNT(*) n FROM athlete_claim_attempts WHERE email = %s", (ME,))
    assert cur.fetchone()["n"] == 0


def test_typo_in_name_and_birthday_still_gives_right_to_claim(db, cards, slot, mail):
    conn, cur = db
    add_typo_lead(cur, slot["igor"], ME, 9032)
    conn.commit()
    assert ac.claim(ME, slot["igor"], IGOR_BD) == ClaimResult.OK


def test_notify_recipients_skip_transferred_slot_mail(db, cards, slot, mail):
    conn, cur = db
    assert ac.notify_recipients(slot["igor"], ME) == [OTHER]            # slot@ — почта другого человека
    add_typo_lead(cur, slot["igor"], KAB, 9032)
    conn.commit()
    assert ac.notify_recipients(slot["igor"], ME) == [KAB, OTHER]       # опечатка — тот же человек


def test_history_rows_skip_transferred_slot_but_keep_typos(db, cards, slot, mail):
    conn, cur = db
    add_typo_lead(cur, slot["igor"], OTHER, 9033)
    cur.execute("""INSERT INTO results (surname, name, birthday, sex, event_id, start_number, race_status,
                   time_gun_finish, client_id) VALUES (%s, 'Игор', '1975-03-04', 'Мужчина', %s, 9033, 'Finished',
                   '00:40:00', %s)""", (SURNAME, slot["event_id"], slot["igor"]))
    conn.commit()
    results, leads = ac.history_rows([slot["igor"]])
    assert sorted(ld["start_number"] for ld in leads) == [9030, 9033]   # Мария (9031) не показывается
    assert [r["start_number"] for r in results] == [9033]               # результат Марии (9031) тоже


def test_history_rows_carry_order_and_place_fields(db, cards, mail):
    conn, cur = db
    cur.execute("""UPDATE leads SET order_id = 5551, amount = 1090, promocode = 'VIM99', discount = 109.5,
                   products = '5 км (kt)' WHERE event_name = %s AND start_number = 9001""", (EV,))
    cur.execute("""UPDATE results SET category = 'М35-39', rank_absolute = 4, rank_absolute_clean = 3
                   WHERE start_number = 9001 AND event_id = %s""", (cards["event_id"],))
    conn.commit()
    results, leads = ac.history_rows([cards["c1"]])
    r = results[0]
    assert (r["category"], r["rank_absolute"], r["rank_absolute_clean"], r["birthday"]) == ("М35-39", 4, 3, BD1)
    ld = next(x for x in leads if x["start_number"] == 9001)
    assert (ld["order_id"], ld["amount"], ld["promocode"], ld["discount"], ld["products"]) == \
        (5551, 1090, "VIM99", 109.5, "5 км (kt)")
    assert ld["email"] == ME and ld["created_at"] is not None and ld["surname"] == SURNAME and ld["birthday"] == BD1


def test_cabinet_group_title_comes_from_card_not_from_latest_lead(db, cards, mail):
    conn, cur = db
    from src.krasmarafon.services import athlete_cabinet

    add_lead(cur, "Мария", BD2, ME, 9040)                               # последняя заявка карточки c1 — чужого слота
    move_to(cur, cards["c1"], "start_number = 9040", ())
    conn.commit()
    people = athlete_cabinet.cabinet(ME, date(2100, 1, 1))
    titles = {p["client_id"]: p["title"] for p in people}
    assert titles[cards["c1"]] == "Тестклейм Иван" and titles[cards["c2"]] == "Тестклейм Мария"


def test_web_other_person_message_and_no_attempt(web, cards):
    client, _ = web
    login(client)
    assert claim_via_web(client, cards["c1"], "1986-05-01").headers["location"] == "/me"
    r = claim_via_web(client, cards["c2"], "2018-03-02")
    assert r.status_code == 303 and r.headers["location"] == f"/me?claim={cards['c2']}&r=other_person"
    page = client.get(r.headers["location"]).text
    assert ("У вас уже есть своя карточка с другой датой рождения. Если это ваш ребёнок или близкий — "
            "доступ к его истории появится позже") in page
    assert claim_via_web(client, cards["vanya"], "1986-05-01").headers["location"] == "/me"


def test_web_transferred_slot_claim_redirects_with_not_yours_error(web, cards, slot, db):
    conn, cur = db
    cur.execute("UPDATE leads SET email = %s WHERE event_name = %s AND start_number = 9031", (ME, EV))
    conn.commit()
    client, _ = web
    login(client)
    r = claim_via_web(client, slot["igor"], "1975-03-03")
    assert r.status_code == 303 and r.headers["location"] == f"/me?claim={slot['igor']}&r=not_yours"


def test_transferred_slot_group_has_lead_name_title_and_no_claim_button(web, cards, slot, db):
    """Заявка B лежит на карточке A (слот передали): B не видит имени чужого человека и кнопки «Это я»."""
    conn, cur = db
    from src.krasmarafon.services import athlete_cabinet

    cur.execute("UPDATE leads SET email = %s WHERE event_name = %s AND start_number = 9031", (ME, EV))
    conn.commit()
    people = {p["client_id"]: p for p in athlete_cabinet.cabinet(ME, date(2100, 1, 1))}
    assert people[slot["igor"]]["title"] == f"{SURNAME} Мария"           # ФИ заявки, не карточки Игоря
    assert not people[slot["igor"]]["can_claim"] and people[cards["c1"]]["can_claim"]
    client, _ = web
    login(client)
    page = client.get(f"/me?claim={slot['igor']}&r=not_yours").text
    assert "Игорь" not in page
    assert f'name="client_id" value="{slot["igor"]}"' not in page
    assert f'name="client_id" value="{cards["c1"]}"' in page
    assert "Эта карточка не совпадает с данными ваших заявок" in page      # ошибка видна и без формы


def test_group_with_one_matching_lead_keeps_card_title_and_claim_button(web, cards, slot, db):
    conn, cur = db
    from src.krasmarafon.services import athlete_cabinet

    cur.execute("UPDATE leads SET email = %s WHERE event_name = %s AND start_number = 9031", (ME, EV))
    add_typo_lead(cur, slot["igor"], ME, 9032)                          # своя заявка с опечаткой в ФИ и ДР
    conn.commit()
    people = {p["client_id"]: p for p in athlete_cabinet.cabinet(ME, date(2100, 1, 1))}
    assert people[slot["igor"]]["title"] == f"{SURNAME} Игорь" and people[slot["igor"]]["can_claim"]
    client, _ = web
    login(client)
    assert f'name="client_id" value="{slot["igor"]}"' in client.get("/me").text


def test_web_history_details_and_places(web, cards, db):
    conn, cur = db
    cur.execute("""UPDATE leads SET order_id = 5550 WHERE event_name = %s AND start_number = 9001""", (EV,))
    cur.execute("""UPDATE results SET category = 'М35-39', rank_absolute = 4, rank_category = 3
                   WHERE start_number = 9001 AND event_id = %s""", (cards["event_id"],))
    add_lead(cur, "Иван", BD1, ME, 9051, year=2098)                     # будущая заявка с почты аккаунта
    cur.execute("""UPDATE leads SET order_id = 5551, amount = 1090, promocode = 'VIM99', discount = 109.5,
                   products = '5 км (kt) - 1x1090' WHERE event_name = %s AND start_number = 9051""", (EV,))
    add_lead(cur, "Иван", BD1, OTHER, 9050, year=2098)                  # будущая заявка с чужой почты
    conn.commit()
    client, _ = web
    login(client)
    claim_via_web(client, cards["c1"], "1986-05-01")
    page = client.get("/me/history").text
    assert "Подробнее" in page and "<details" in page
    assert "4 абс. · 3 в М35-39" in page
    text = re.sub(r"<[^>]+>", "", page)
    assert "Номер заказа: 5551" in text and "Сумма: 1 090 ₽" in text
    assert "Промокод: VIM99 (скидка 109,5 ₽)" in text and "Состав заказа: 5 км (kt) - 1x1090" in text
    assert f"Участник: {SURNAME} Иван, 01.05.1986" in text
    assert f"Оформлено с почты: {ME}" in text                           # почта аккаунта — полностью
    assert f"Оформлено с почты: o***@{DOMAIN}" in text                  # чужая — маской
    assert OTHER not in page
    assert "Номер заказа: 5550" not in text                           # у результата подробностей заказа нет
