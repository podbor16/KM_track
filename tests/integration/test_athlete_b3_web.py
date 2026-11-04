"""Б3, интерфейс кабинета: «Найти себя», обращения (спор, «не мой забег», «не могу найти себя»). Тестовые данные —
почты *@b3-test.local, событие «Тест Б3» 2099, карточки «Тестбтри …» (фикстуры — из test_athlete_requests)."""
import re
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app import app
from src.krasmarafon.services import athlete_auth as aa
from src.krasmarafon.services import athlete_claims as ac
from src.krasmarafon.services import athlete_find as af
from src.krasmarafon.services import athlete_reps as ar
from tests.integration.test_athlete_requests import (  # noqa: F401  (фикстуры)
    BD1, BD2, DOMAIN, FINDER, ME, OWNER, PARENT, REP, SURNAME, cards, claimed, db, request_row)


@pytest.fixture(autouse=True)
def no_mail():
    with patch.object(ac, "send_mail") as m:
        yield m


@pytest.fixture
def web(db, cards, tmp_path, monkeypatch):
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
    assert client.post("/me/verify", data={"email": email, "code": code}, follow_redirects=False).status_code == 303


def search(client, bib, name="Иван", surname=SURNAME, birthday="1986-05-01"):
    return client.post("/me/find", data={"surname": surname, "name": name, "birthday": birthday, "bib": bib})


def find_token(html):
    return re.search(r'name="token" value="([^"]+)"', html).group(1)


# --- /me/find ---------------------------------------------------------------------------------------------------

def test_me_has_find_link(web, cards):
    client, _ = web
    login(client)
    assert 'href="/me/find"' in client.get("/me").text and "Не нашли себя?" in client.get("/me").text


def test_find_form_needs_session_and_cabinet_flag(web, cards):
    client, flag = web
    assert client.get("/me/find", follow_redirects=False).headers["location"] == "/me/login"
    login(client)
    page = client.get("/me/find").text
    for field in ("surname", "name", "birthday", "bib"):
        assert f'name="{field}"' in page
    assert 'action="/me/find"' in page
    flag.unlink()
    assert client.get("/me/find").status_code == 404
    assert client.post("/me/find", data={}).status_code == 404
    assert client.post("/me/find/claim", data={}).status_code == 404
    assert client.post("/me/request", data={}).status_code == 404


def test_find_found_shows_card_and_claim_form(web, cards):
    client, _ = web
    login(client, FINDER)
    page = search(client, "9201").text
    assert f"Это вы: {SURNAME} Иван, бегает с 2099, 1 старт" in page
    assert 'action="/me/find/claim"' in page and 'name="birthday" value="1986-05-01"' in page
    assert f'name="client_id" value="{cards["a"]}"' not in page         # карточка — только в подписанном токене
    assert af.read_token(FINDER, find_token(page)) == cards["a"]


def test_find_not_found_is_same_for_every_reason_and_offers_request(web, cards):
    client, _ = web
    login(client, FINDER)
    pages = [search(client, "9201", birthday="1986-05-02").text,      # не та ДР
             search(client, "9999").text,                              # нет такого номера
             search(client, "9201", name="Пётр").text]                 # не то имя
    for page in pages:
        assert "Не нашли — проверьте данные или отправьте обращение" in page
        assert "Не могу найти себя" in page and 'action="/me/request"' in page
        assert 'name="kind" value="not_found"' in page and "Это вы" not in page
        assert 'action="/me/find/claim"' not in page
    assert 'name="bib" value="9999"' in pages[1]                      # введённое сохраняется


def test_find_limit(web, cards):
    client, _ = web
    login(client, FINDER)
    for _ in range(af.FIND_PER_DAY):
        search(client, "1")
    assert "Слишком много попыток. Попробуйте завтра" in search(client, "9201").text


def test_find_bad_date_does_not_count_attempt(web, cards, db):
    conn, cur = db
    client, _ = web
    login(client, FINDER)
    assert "Проверьте дату" in search(client, "9201", birthday="не дата").text
    cur.execute("SELECT COUNT(*) AS n FROM athlete_find_attempts WHERE email = %s", (FINDER,))
    assert cur.fetchone()["n"] == 0


def test_find_claim_ok_binds_card_without_own_lead(web, cards, db):
    conn, cur = db
    client, _ = web
    login(client, FINDER)
    page = search(client, "9201").text
    r = client.post("/me/find/claim", data={"token": find_token(page), "birthday": "1986-05-01"},
                    follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/me"
    assert ac.claimed_cards(FINDER) == ([cards["a"]], [])
    cur.execute("SELECT details FROM dq_actions WHERE action = 'athlete_claim' AND finding_key = %s",
                (f"client:{cards['a']}",))
    assert any('"find"' in row["details"] for row in cur.fetchall())


def test_find_claim_rejects_bad_token_and_wrong_date(web, cards):
    client, _ = web
    login(client, FINDER)
    token = find_token(search(client, "9201").text)
    r = client.post("/me/find/claim", data={"token": token + "x", "birthday": "1986-05-01"})
    assert "Ссылка устарела — найдите карточку заново" in r.text
    r = client.post("/me/find/claim", data={"token": af.make_token(ME, cards["a"]), "birthday": "1986-05-01"})
    assert "Ссылка устарела" in r.text                                      # токен другой почты
    assert "Дата не совпадает" in client.post("/me/find/claim", data={"token": token, "birthday": "1986-05-02"}).text
    assert ac.claimed_cards(FINDER) == ([], [])


def test_find_claim_taken_offers_dispute_with_token_and_it_works(web, claimed, db):
    conn, cur = db
    client, _ = web
    login(client, FINDER)
    token = find_token(search(client, "9201").text)
    page = client.post("/me/find/claim", data={"token": token, "birthday": "1986-05-01"}).text
    assert "Эту карточку уже заявили" in page
    assert "Это моя карточка — отправить обращение" in page
    assert 'name="kind" value="dispute"' in page and f'name="find_token" value="{token}"' in page
    r = client.post("/me/request", data={"kind": "dispute", "client_id": claimed["a"], "find_token": token,
                                         "comment": "я это"}, follow_redirects=False)
    assert r.headers["location"] == "/me?sent=1"
    cur.execute("SELECT kind, comment FROM athlete_requests WHERE email = %s", (FINDER,))
    assert cur.fetchall() == [{"kind": "dispute", "comment": "я это"}]


# --- обращения: спор на /me -------------------------------------------------------------------------------------

def test_me_taken_shows_dispute_button_instead_of_mailto_hint(web, claimed):
    client, _ = web
    login(client, ME)
    page = client.get(f"/me?claim={claimed['a']}&r=taken").text
    assert "Эту карточку уже заявили" in page and "напишите нам" not in page.split("Эту карточку уже заявили")[1][:80]
    assert "Это моя карточка — отправить обращение" in page
    assert 'name="find_token"' not in page and f'name="client_id" value="{claimed["a"]}"' in page
    assert "Это моя карточка" not in client.get(f"/me?claim={claimed['a']}&r=mismatch").text


def test_request_dispute_via_web_shows_confirmation_with_email(web, claimed, db):
    conn, cur = db
    client, _ = web
    login(client, ME)
    r = client.post("/me/request", data={"kind": "dispute", "client_id": claimed["a"]}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/me?sent=1"
    assert f"Обращение отправлено, ответим письмом на {ME}" in client.get(r.headers["location"]).text
    assert "Обращение отправлено" not in client.get("/me").text
    cur.execute("SELECT kind, client_id FROM athlete_requests WHERE email = %s", (ME,))
    assert cur.fetchall() == [{"kind": "dispute", "client_id": claimed["a"]}]


def test_request_errors_are_readable(web, claimed):
    client, _ = web
    login(client, FINDER)
    r = client.post("/me/request", data={"kind": "dispute", "client_id": claimed["a"]}, follow_redirects=False)
    assert r.headers["location"] == "/me?req_err=forbidden"
    assert "Не удалось отправить обращение" in client.get(r.headers["location"]).text
    r = client.post("/me/request", data={"kind": "not_found", "comment": "я" * 1001}, follow_redirects=False)
    assert r.headers["location"] == "/me?req_err=too_long"
    assert "не больше 1000 символов" in client.get(r.headers["location"]).text
    for i in range(3):
        client.post("/me/request", data={"kind": "not_found", "surname": f"Ф{i}"})
    r = client.post("/me/request", data={"kind": "not_found", "surname": "Ф9"}, follow_redirects=False)
    assert r.headers["location"] == "/me?req_err=limit"
    assert "открытых обращения" in client.get(r.headers["location"]).text
    assert client.post("/me/request", data={"kind": "bogus"}, follow_redirects=False).headers["location"] \
        == "/me?req_err=bad_kind"


def test_request_not_found_stores_entered_data(web, cards, db):
    conn, cur = db
    client, _ = web
    login(client, FINDER)
    r = client.post("/me/request", data={"kind": "not_found", "surname": "Тестбтри", "name": "Иван",
                                         "birthday": "1986-05-01", "bib": "42", "comment": "помогите"},
                    follow_redirects=False)
    assert r.headers["location"] == "/me?sent=1"
    cur.execute("SELECT kind, client_id, comment, payload FROM athlete_requests WHERE email = %s", (FINDER,))
    row = cur.fetchone()
    assert (row["kind"], row["client_id"], row["comment"]) == ("not_found", None, "помогите")
    import json
    assert json.loads(row["payload"]) == {"surname": "Тестбтри", "name": "Иван", "birthday": "1986-05-01", "bib": "42"}


def test_request_next_is_whitelisted(web, claimed):
    client, _ = web
    login(client, FINDER)
    for evil in ("https://evil.example/", "//evil.example", "/admin", "/me/history/../x"):
        r = client.post("/me/request", data={"kind": "bogus", "next": evil}, follow_redirects=False)
        assert r.headers["location"] == "/me?req_err=bad_kind"


def test_request_session_and_origin(web, claimed):
    client, _ = web
    r = client.post("/me/request", data={"kind": "not_found"}, follow_redirects=False)
    assert r.headers["location"] == "/me/login"
    login(client, FINDER)
    evil = {"origin": "https://evil.example"}
    for url, data in (("/me/request", {"kind": "not_found"}), ("/me/find", {"surname": "a"}),
                      ("/me/find/claim", {"token": "1.2.3", "birthday": "1986-05-01"})):
        assert client.post(url, data=data, headers=evil, follow_redirects=False).status_code == 403
    assert client.post("/me/find", data={"surname": "a"}, follow_redirects=False).status_code == 200


# --- обращения: «Это не мой забег» ------------------------------------------------------------------------------

def test_history_has_wrong_row_forms_and_no_mailto(web, cards):
    client, _ = web
    login(client, ME)
    assert ac.claim(ME, cards["a"], BD1).value == "ok"
    page = client.get("/me/history").text
    assert "mailto:" not in page.split("<main")[1].split("</main>")[0]
    assert "Сообщить об ошибке" not in page
    assert page.count("Это не мой забег") == 4                                     # результат и 3 заявки
    assert f'name="row" value="results:{cards["result_a"]}"' in page
    assert f'name="row" value="leads:{cards["lead_a"]}"' in page
    assert 'name="next" value="/me/history"' in page and "<textarea" in page and 'maxlength="1000"' in page
    results_html = page.split('id="tab-results"')[1].split('id="tab-leads"')[0]
    assert results_html.count("Это не мой забег") == 1 and "leads:" not in results_html


def test_wrong_row_via_web_creates_request_and_returns_to_history(web, cards, db):
    conn, cur = db
    client, _ = web
    login(client, ME)
    ac.claim(ME, cards["a"], BD1)
    r = client.post("/me/request", data={"kind": "wrong_row", "row": f"results:{cards['result_a']}",
                                         "next": "/me/history", "comment": "не я бежал"}, follow_redirects=False)
    assert r.headers["location"] == "/me/history?sent=1"
    assert f"Обращение отправлено, ответим письмом на {ME}" in client.get(r.headers["location"]).text
    cur.execute("SELECT kind, row_table, row_id, client_id FROM athlete_requests WHERE email = %s", (ME,))
    assert cur.fetchall() == [{"kind": "wrong_row", "row_table": "results", "row_id": cards["result_a"],
                               "client_id": cards["a"]}]
    r = client.post("/me/request", data={"kind": "wrong_row", "row": "results:1", "next": "/me/history"},
                    follow_redirects=False)                                   # чужая строка
    assert r.headers["location"] == "/me/history?req_err=forbidden"
    assert "Не удалось отправить обращение" in client.get(r.headers["location"]).text


def test_ward_history_has_wrong_row_forms_returning_to_ward_page(web, claimed):
    client, _ = web
    login(client, REP)
    assert ar.become_rep(REP, claimed["a"], BD1).value == "ok"
    page = client.get(f"/me/athlete/{claimed['a']}").text
    assert "Это не мой забег" in page and "mailto:" not in page.split("<main")[1].split("</main>")[0]
    assert f'name="next" value="/me/athlete/{claimed["a"]}"' in page
    r = client.post("/me/request", data={"kind": "wrong_row", "row": f"results:{claimed['result_a']}",
                                         "next": f"/me/athlete/{claimed['a']}"}, follow_redirects=False)
    assert r.headers["location"] == f"/me/athlete/{claimed['a']}?sent=1"


def test_confirm_texts_stay_js_safe(web, cards):
    client, _ = web
    login(client, ME)
    ac.claim(ME, cards["a"], BD1)
    page = client.get("/me/history").text
    assert "confirm(" in page          # отвязка по-прежнему спрашивает подтверждение
