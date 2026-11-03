"""Вход и кабинет через HTTP на локальной БД. Тестовые почты — *@athlete-test.local."""
import re
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app import app
from src.analytics.db_pool import get_pooled_connection
from src.krasmarafon.services import athlete_auth as aa

DOMAIN = "athlete-test.local"
EV = "Тест кабинет"


@pytest.fixture
def db():
    conn = get_pooled_connection()
    if not conn:
        pytest.skip("Нет локальной БД")
    cur = conn.cursor(dictionary=True)
    cur.execute("SHOW TABLES LIKE 'athlete_sessions'")
    if not cur.fetchone():
        conn.close()
        pytest.skip("Миграция athlete_login не применена")

    def cleanup():
        cur.execute("DELETE FROM athlete_login_codes WHERE email LIKE %s OR ip = 'testclient'", (f"%@{DOMAIN}",))
        cur.execute("DELETE FROM athlete_sessions WHERE email LIKE %s", (f"%@{DOMAIN}",))
        cur.execute("DELETE FROM leads WHERE event_name = %s", (EV,))
        conn.commit()

    cleanup()
    yield conn, cur
    cleanup()
    cur.close()
    conn.close()


@pytest.fixture
def client():
    return TestClient(app, base_url="https://testserver")


def request_code(client, email):
    with patch.object(aa, "send_mail") as mail:
        r = client.post("/me/login", data={"email": email})
    assert r.status_code == 200
    text = mail.call_args[0][2]
    return r, re.search(r"\b(\d{6})\b", text).group(1), re.search(r"/me/link\?t=([\w-]+)", text).group(1)


def add_lead(cur, surname, email="", ma_email=None):
    cur.execute("""INSERT INTO leads (surname, name, sex, city, club, birthday, email, ma_email, phone, event_name,
                   event_distance, event_year, products, amount, client_id, event_id, is_duplicate, status, is_new,
                   is_new_event, is_name_suspicious, created_at)
                   VALUES (%s, 'Тест', 'Мужчина', '', '', '1990-01-01', %s, %s, '', %s, '5 км', 2099,
                           '', 0, NULL, NULL, 0, 0, 0, 0, 0, NOW())""", (surname, email, ma_email, EV))


def test_me_without_session_redirects_to_login(client):
    r = client.get("/me", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == "/me/login"


def test_full_login_by_code_shows_leads_by_email_and_ma_email(db, client):
    conn, cur = db
    add_lead(cur, "Формапочта", email=f"Me@{DOMAIN}")
    add_lead(cur, "Кабинетпочта", ma_email=f"me@{DOMAIN}")
    add_lead(cur, "Чужойчеловек", email=f"other@{DOMAIN}")
    conn.commit()

    r, code, _ = request_code(client, f"me@{DOMAIN}")
    assert "Введите код" in r.text
    r = client.post("/me/verify", data={"email": f"me@{DOMAIN}", "code": code}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/me"
    cookie = r.headers["set-cookie"]
    assert "km_athlete=" in cookie and "HttpOnly" in cookie and "Secure" in cookie
    assert "samesite=lax" in cookie.lower() and "Max-Age" in cookie

    page = client.get("/me").text
    assert "Формапочта" in page and "Кабинетпочта" in page and "Чужойчеловек" not in page


def test_wrong_code_shows_error(db, client):
    request_code(client, f"wrong@{DOMAIN}")
    r = client.post("/me/verify", data={"email": f"wrong@{DOMAIN}", "code": "abcdef"})
    assert "Код неверный или устарел" in r.text
    assert "km_athlete" not in r.headers.get("set-cookie", "")


def test_shared_computer_cookie_without_max_age(db, client):
    _, code, _ = request_code(client, f"shared@{DOMAIN}")
    r = client.post("/me/verify", data={"email": f"shared@{DOMAIN}", "code": code, "shared": "1"},
                    follow_redirects=False)
    assert "km_athlete=" in r.headers["set-cookie"] and "Max-Age" not in r.headers["set-cookie"]


def test_link_shows_button_then_logs_in(db, client):
    _, _, token = request_code(client, f"link@{DOMAIN}")
    r = client.get(f"/me/link?t={token}")
    assert f"link@{DOMAIN}" in r.text and "km_athlete" not in r.headers.get("set-cookie", "")
    r = client.post("/me/link", data={"t": token}, follow_redirects=False)
    assert r.status_code == 303 and "km_athlete=" in r.headers["set-cookie"]
    assert "Ссылка устарела" in client.get(f"/me/link?t={token}").text


def test_rate_limit_message(db, client):
    request_code(client, f"rl@{DOMAIN}")
    with patch.object(aa, "send_mail") as mail:
        r = client.post("/me/login", data={"email": f"rl@{DOMAIN}"})
    assert "Слишком много попыток" in r.text
    mail.assert_not_called()


def test_mail_failure_message(db, client):
    with patch.object(aa, "send_mail", side_effect=OSError("smtp down")):
        r = client.post("/me/login", data={"email": f"fail@{DOMAIN}"})
    assert "Не удалось отправить код" in r.text


def test_too_long_email_rejected(db, client):
    with patch.object(aa, "send_mail") as mail:
        r = client.post("/me/login", data={"email": "a" * 295 + "@x.ru"})
    assert "Проверьте почту" in r.text
    mail.assert_not_called()


def test_logout_everywhere(db, client):
    _, code, _ = request_code(client, f"out@{DOMAIN}")
    client.post("/me/verify", data={"email": f"out@{DOMAIN}", "code": code})
    other = aa.create_session(f"out@{DOMAIN}", shared=False, user_agent=None)
    r = client.post("/me/logout-all", follow_redirects=False)
    assert r.status_code == 303
    assert aa.session_email(other) is None
    assert client.get("/me", follow_redirects=False).status_code == 302


def test_foreign_origin_post_rejected(db, client):
    with patch.object(aa, "send_mail") as mail:
        r = client.post("/me/login", data={"email": f"csrf@{DOMAIN}"}, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403
    mail.assert_not_called()


def test_empty_cabinet_message(db, client):
    _, code, _ = request_code(client, f"empty@{DOMAIN}")
    client.post("/me/verify", data={"email": f"empty@{DOMAIN}", "code": code})
    assert "Заявок с этой почты не найдено" in client.get("/me").text

def test_cabinet_groups_upcoming_and_results(db, client):
    conn, cur = db
    cur.execute("SELECT id FROM events WHERE event_date < CURDATE() AND event_name = 'Жара' "
                "ORDER BY event_date DESC LIMIT 1")
    past_ev = cur.fetchone()
    add_lead(cur, "Будущий", email=f"cab@{DOMAIN}")  # event_id NULL → даты нет → «Заявки»
    if past_ev:
        add_lead(cur, "Прошлый", email=f"cab@{DOMAIN}")
        cur.execute("UPDATE leads SET event_id = %s WHERE event_name = %s AND surname = 'Прошлый'",
                    (past_ev["id"], EV))
    conn.commit()
    _, code, _ = request_code(client, f"cab@{DOMAIN}")
    client.post("/me/verify", data={"email": f"cab@{DOMAIN}", "code": code})
    page = client.get("/me").text
    assert "🎟 Заявки" in page and "номер ещё не присвоен" in page
    if past_ev:
        assert "🏁 Результаты" in page and "нет результата" in page


def test_header_shows_login_or_cabinet(db, client):
    assert "ВОЙТИ" in client.get("/results").text
    _, code, _ = request_code(client, f"hdr@{DOMAIN}")
    client.post("/me/verify", data={"email": f"hdr@{DOMAIN}", "code": code})
    assert "КАБИНЕТ" in client.get("/results").text
