"""Коды входа и сессии спортсмена на локальной БД. Тестовые почты — *@athlete-test.local."""
import re
from unittest.mock import patch

import pytest

from src.analytics.db_pool import get_pooled_connection
from src.krasmarafon.services import athlete_auth as aa

DOMAIN = "athlete-test.local"


@pytest.fixture
def db():
    conn = get_pooled_connection()
    if not conn:
        pytest.skip("Нет локальной БД")
    cur = conn.cursor(dictionary=True)
    cur.execute("SHOW TABLES LIKE 'athlete_login_codes'")
    if not cur.fetchone():
        conn.close()
        pytest.skip("Миграция athlete_login не применена")

    def cleanup():
        cur.execute("DELETE FROM athlete_login_codes WHERE email LIKE %s OR ip LIKE '203.0.113.%%'", (f"%@{DOMAIN}",))
        cur.execute("DELETE FROM athlete_sessions WHERE email LIKE %s", (f"%@{DOMAIN}",))
        conn.commit()

    cleanup()
    yield conn, cur
    cleanup()
    cur.close()
    conn.close()


def send(email, ip="203.0.113.1"):
    """request_code с перехватом письма: возвращает (код, токен ссылки)."""
    with patch.object(aa, "send_mail") as mail:
        aa.request_code(email, ip)
    to, subject, text, html = mail.call_args[0]
    assert to == aa.normalize_email(email)
    code = re.search(r"\b(\d{6})\b", text).group(1)
    token = re.search(r"/me/link\?t=([\w-]+)", text).group(1)
    assert code in subject.replace(" ", "")
    return code, token


def test_code_logs_in_once(db):
    code, _ = send(f"Petr@{DOMAIN} ")
    assert aa.verify_code(f"petr@{DOMAIN}", code)
    assert not aa.verify_code(f"petr@{DOMAIN}", code)


def test_secrets_stored_only_as_hashes(db):
    conn, cur = db
    code, token = send(f"h@{DOMAIN}")
    cur.execute("SELECT code_hash, link_hash FROM athlete_login_codes WHERE email = %s", (f"h@{DOMAIN}",))
    row = cur.fetchone()
    assert code not in row["code_hash"] and token != row["link_hash"]
    assert len(row["code_hash"]) == len(row["link_hash"]) == 64


def test_wrong_code_five_attempts_burns_code(db):
    code, _ = send(f"w@{DOMAIN}")
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(aa.MAX_ATTEMPTS):
        assert not aa.verify_code(f"w@{DOMAIN}", wrong)
    assert not aa.verify_code(f"w@{DOMAIN}", code)


def test_four_wrong_attempts_still_allow_code(db):
    code, _ = send(f"w4@{DOMAIN}")
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(aa.MAX_ATTEMPTS - 1):
        assert not aa.verify_code(f"w4@{DOMAIN}", wrong)
    assert aa.verify_code(f"w4@{DOMAIN}", code)


def test_expired_code_rejected(db):
    conn, cur = db
    code, token = send(f"e@{DOMAIN}")
    cur.execute("UPDATE athlete_login_codes SET expires_at = NOW() - INTERVAL 1 SECOND WHERE email = %s",
                (f"e@{DOMAIN}",))
    conn.commit()
    assert not aa.verify_code(f"e@{DOMAIN}", code)
    assert aa.link_email(token) is None


def test_new_code_cancels_previous(db):
    conn, cur = db
    old_code, old_token = send(f"n@{DOMAIN}")
    # обойти лимит «1 код в минуту»
    cur.execute("UPDATE athlete_login_codes SET created_at = NOW() - INTERVAL 2 MINUTE WHERE email = %s",
                (f"n@{DOMAIN}",))
    conn.commit()
    new_code, _ = send(f"n@{DOMAIN}")
    assert aa.link_email(old_token) is None
    if old_code != new_code:
        assert not aa.verify_code(f"n@{DOMAIN}", old_code)
    assert aa.verify_code(f"n@{DOMAIN}", new_code)


def test_link_shows_email_then_consumed_once(db):
    _, token = send(f"l@{DOMAIN}")
    assert aa.link_email(token) == f"l@{DOMAIN}"
    assert aa.link_email(token) == f"l@{DOMAIN}"  # просмотр страницы не тратит ссылку
    assert aa.consume_link(token) == f"l@{DOMAIN}"
    assert aa.consume_link(token) is None
    assert aa.link_email("garbage") is None


def test_limit_one_per_minute_per_email(db):
    send(f"m@{DOMAIN}")
    with patch.object(aa, "send_mail") as mail, pytest.raises(aa.TooManyRequests):
        aa.request_code(f"m@{DOMAIN}", "203.0.113.2")
    mail.assert_not_called()


def test_limit_five_per_hour_per_email(db):
    conn, cur = db
    for i in range(aa.EMAIL_PER_HOUR):
        send(f"hr@{DOMAIN}", ip=f"203.0.113.{10 + i}")
        cur.execute("UPDATE athlete_login_codes SET created_at = NOW() - INTERVAL 2 MINUTE WHERE email = %s",
                    (f"hr@{DOMAIN}",))
        conn.commit()
    with pytest.raises(aa.TooManyRequests):
        aa.request_code(f"hr@{DOMAIN}", "203.0.113.99")


def test_limit_ten_per_hour_per_ip(db):
    for i in range(aa.IP_PER_HOUR):
        send(f"ip{i}@{DOMAIN}", ip="203.0.113.50")
    with pytest.raises(aa.TooManyRequests):
        aa.request_code(f"ipx@{DOMAIN}", "203.0.113.50")


def test_session_roundtrip_and_logout(db):
    conn, cur = db
    token = aa.create_session(f"s@{DOMAIN}", shared=False, user_agent="pytest")
    assert aa.session_email(token) == f"s@{DOMAIN}"
    cur.execute("SELECT token_hash, TIMESTAMPDIFF(DAY, NOW(), expires_at) AS d FROM athlete_sessions "
                "WHERE email = %s", (f"s@{DOMAIN}",))
    row = cur.fetchone()
    assert row["token_hash"] != token and row["d"] >= aa.SESSION_DAYS - 1
    aa.delete_session(token)
    assert aa.session_email(token) is None


def test_shared_session_lives_one_day(db):
    conn, cur = db
    aa.create_session(f"sh@{DOMAIN}", shared=True, user_agent=None)
    cur.execute("SELECT TIMESTAMPDIFF(HOUR, NOW(), expires_at) AS h FROM athlete_sessions WHERE email = %s",
                (f"sh@{DOMAIN}",))
    assert cur.fetchone()["h"] <= aa.SHARED_SESSION_HOURS


def test_expired_session_rejected(db):
    conn, cur = db
    token = aa.create_session(f"x@{DOMAIN}", shared=False, user_agent=None)
    cur.execute("UPDATE athlete_sessions SET expires_at = NOW() - INTERVAL 1 SECOND WHERE email = %s",
                (f"x@{DOMAIN}",))
    conn.commit()
    assert aa.session_email(token) is None


def test_logout_everywhere(db):
    a = aa.create_session(f"all@{DOMAIN}", shared=False, user_agent=None)
    b = aa.create_session(f"all@{DOMAIN}", shared=True, user_agent=None)
    other = aa.create_session(f"other@{DOMAIN}", shared=False, user_agent=None)
    aa.delete_all_sessions(f"all@{DOMAIN}")
    assert aa.session_email(a) is None and aa.session_email(b) is None
    assert aa.session_email(other) == f"other@{DOMAIN}"


def test_garbage_session_token(db):
    assert aa.session_email("") is None
    assert aa.session_email("nope") is None
