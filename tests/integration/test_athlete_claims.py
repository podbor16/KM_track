"""Привязка карточки к кабинету («Это я») на локальной БД. Тестовые данные — почты *@athlete-test.local,
событие «Тест кабинет Б1» 2099 года, карточки «Тестклейм …»; фикстура убирает их до и после."""
import json
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


def add_lead(cur, name, birthday, email, start_number, ma_email=None):
    """Карточку и событие заводят триггеры leads (они же выставляют client_id/event_id)."""
    cur.execute("""INSERT INTO leads (surname, name, sex, city, club, birthday, email, ma_email, phone, event_name,
                   event_distance, event_year, products, amount, client_id, event_id, is_duplicate, status, is_new,
                   is_new_event, is_name_suspicious, start_number, created_at)
                   VALUES (%s, %s, 'Мужчина', '', '', %s, %s, %s, '', %s, '5 км', 2099, '', 0, 0, 0, 0, 0, 0, 0, 0,
                           %s, NOW())""", (SURNAME, name, birthday, email, ma_email, EV, start_number))
    cur.execute("SELECT client_id, event_id FROM leads WHERE id = %s", (cur.lastrowid,))
    return cur.fetchone()


@pytest.fixture
def cards(db):
    """c1 (ДР 1986, заявки с me@, other@ и ma_email kab@, один результат), c2 (ДР 2018, заявка с me@),
    nobd (без ДР, заявка с me@), foreign (заявка только с other@)."""
    conn, cur = db
    c1 = add_lead(cur, "Иван", BD1, ME, 9001)
    add_lead(cur, "Иван", BD1, OTHER, 9003, ma_email=KAB)
    c2 = add_lead(cur, "Мария", BD2, ME, 9002)
    nobd = add_lead(cur, "Безбд", date(1900, 1, 1), ME, 9004)
    foreign = add_lead(cur, "Чужой", date(1990, 1, 1), OTHER, 9005)
    cur.execute("""INSERT INTO results (surname, name, birthday, sex, event_id, start_number, race_status,
                   time_gun_finish, rank_absolute) VALUES (%s, 'Иван', %s, 'Мужчина', %s, 9001, 'Finished',
                   '00:25:00', 1)""", (SURNAME, BD1, c1["event_id"]))
    conn.commit()
    return {"c1": c1["client_id"], "c2": c2["client_id"], "nobd": nobd["client_id"],
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


def test_claim_ok_writes_row_journal_and_notifies_other_addresses(db, cards, mail):
    conn, cur = db
    assert ac.claim(ME, cards["c1"], BD1) == ClaimResult.OK
    assert claim_rows(cur) == [{"client_id": cards["c1"], "birthday": BD1}]
    assert ac.claimed_cards(ME) == ([cards["c1"]], [])
    assert journal(cur, "athlete_claim", cards["c1"]) == [({"email": ME}, ME)]

    assert {c.args[0] for c in mail.call_args_list} == {OTHER, KAB}
    _, subject, text, html = mail.call_args_list[0].args
    assert subject == "Вашу историю забегов привязали к личному кабинету"
    assert "Тестклейм Иван" in text and f"m***@{DOMAIN}" in text and "1@krasmarafon.ru" in text
    assert ME not in text and "Тестклейм Иван" in html


def test_mail_failure_does_not_break_claim(db, cards, mail):
    mail.side_effect = RuntimeError("smtp")
    assert ac.claim(ME, cards["c1"], BD1) == ClaimResult.OK
    assert ac.claimed_cards(ME) == ([cards["c1"]], [])


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
    assert ac.claim(ME, cards["c2"], BD2) == ClaimResult.OK


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


def test_two_cards_one_account(db, cards, mail):
    assert ac.claim(ME, cards["c1"], BD1) == ClaimResult.OK
    assert ac.claim(ME, cards["c2"], BD2) == ClaimResult.OK
    assert ac.claimed_cards(ME) == ([cards["c1"], cards["c2"]], [])


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
    ac.claim(ME, cards["c2"], BD2)
    ac.claim(ME, cards["c1"], BD1)
    cur.execute("DELETE FROM leads WHERE client_id = %s", (cards["c2"],))
    cur.execute("DELETE FROM clients WHERE id = %s", (cards["c2"],))
    conn.commit()
    assert ac.claimed_cards(ME) == ([cards["c1"]], [cards["c2"]])
    assert journal(cur, "athlete_unclaim", cards["c2"]) == [({"email": ME, "reason": "card_deleted"}, "system")]


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
    assert len(hist["years"][0]["items"]) == 3          # заявка 9001 слилась с результатом
    assert ac.history_rows([]) == ([], [])


def test_history_rows_skip_duplicate_leads(db, cards, mail):
    conn, cur = db
    cur.execute("UPDATE leads SET is_duplicate = 1 WHERE client_id = %s AND start_number = 9002", (cards["c2"],))
    conn.commit()
    _, leads = ac.history_rows([cards["c1"], cards["c2"]])
    assert len(leads) == 2


def test_history_title_is_newest_claimed_card(db, cards, mail):
    conn, cur = db
    ac.claim(ME, cards["c1"], BD1)
    ac.claim(ME, cards["c2"], BD2)
    cur.execute("UPDATE athlete_claims SET created_at = NOW() - INTERVAL 1 DAY WHERE client_id = %s", (cards["c2"],))
    conn.commit()
    assert ac.history_title([cards["c1"], cards["c2"]]) == "Тестклейм Иван"
    assert ac.history_title([]) == ""


def test_duplicate_accounts_lists_only_two_or_more_valid_cards(db, cards, mail):
    conn, cur = db
    ac.claim(ME, cards["c1"], BD1)
    assert [a for a in ac.duplicate_accounts() if a["email"] == ME] == []
    ac.claim(ME, cards["c2"], BD2)
    mine = [a for a in ac.duplicate_accounts() if a["email"] == ME]
    assert len(mine) == 1
    assert mine[0]["cards"] == [
        {"id": cards["c1"], "surname": SURNAME, "name": "Иван", "birthday": BD1},
        {"id": cards["c2"], "surname": SURNAME, "name": "Мария", "birthday": BD2}]
    cur.execute("UPDATE clients SET birthday = '2018-03-03' WHERE id = %s", (cards["c2"],))   # недействительная — не в счёт
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


def test_mask_email():
    assert ac.mask_email("petr@mail.ru") == "p***@mail.ru"
    assert ac.mask_email("P@x.ru") == "P***@x.ru"
    assert ac.mask_email("broken") == "b***"


# ---------------------------------------------------------------- склейка карточек («Качество данных»)

MERGER = "test-claims-merge"


@pytest.fixture
def merge_env(db, cards, mail):
    """c1 (основная: 2 заявки + результат) и карточка «Ваня» (1 заявка с me@) с той же ДР — один человек."""
    from src.analytics import dq_actions

    conn, cur = db
    vanya = add_lead(cur, "Ваня", BD1, ME, 9010)["client_id"]
    conn.commit()
    yield conn, cur, dq_actions, {**cards, "vanya": vanya}
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
