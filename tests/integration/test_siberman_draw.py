"""
Жеребьёвка на локальной БД siberman (.env.local): вытягивание, исправление/отмена,
оплаты с автопередачей, публичные данные без утечки wild card, фиды, маршруты.
Год 2099 — тестовый, чистится до и после.
"""
import datetime

import pytest

from app import app
from src.core.auth import api_require_auth
from src.siberman.db import get_siberman_connection
from src.siberman.draw import db as ddb
from src.siberman.draw import service
from src.siberman.draw.service import DrawError

YEAR = 2099


def _app(surname, fmt="individual", gender="M", pool="novice", wc=False, chances=1, starts=0):
    return {"format": fmt, "surname": surname, "name": "Тест",
            "gender": gender if fmt == "individual" else None, "city": "Красноярск", "pool": pool,
            "is_wildcard": wc, "chances": chances, "starts_individual": starts, "starts_relay": 0,
            "draw_accumulated": 0, "is_local": 0, "duathlon_222": 0, "race_24h": 0, "tattoo": 0,
            "relay_swim": "", "relay_bike": "", "relay_run": "", "wildcard_reason": "", "results_text": ""}


APPS = [
    _app("Вайлдкардов", pool="wildcard", wc=True, starts=2),
    _app("Повторов", pool="repeat", starts=1, chances=3),
    _app("Новиков"), _app("Новикова", gender="F"), _app("Запасной"), _app("Последний"),
    _app("Капитанов", fmt="relay", pool="relay", chances=2),
]


def _clean(conn):
    cur = conn.cursor()
    for t in ("draw_audit", "draw_picks", "draw_applicants", "draw_config"):
        cur.execute(f"DELETE FROM {t} WHERE draw_year=%s", (YEAR,))


@pytest.fixture
def draw():
    conn = get_siberman_connection()
    if conn is None:
        pytest.skip("Нет локальной БД siberman")
    cur = conn.cursor()
    cur.execute("SHOW TABLES LIKE 'draw_picks'")
    if not cur.fetchone():
        conn.close()
        pytest.skip("Миграция 013_draw не применена")
    _clean(conn)
    ddb.replace_applicants(conn, YEAR, APPS)
    ddb.save_config(conn, YEAR, {"capacity_men": 3, "capacity_women": 1, "capacity_relay": 1,
                                 "quota_repeat_men": 2, "quota_repeat_women": 0, "quota_novice_men": 1,
                                 "quota_novice_women": 1, "auto_invite_until": datetime.date(2098, 1, 1)})
    service.clear_cache()
    yield {a["surname"]: a["id"] for a in ddb.load_applicants(conn, YEAR)}
    _clean(conn)
    conn.close()
    service.clear_cache()


def _men_after_wildcard_and_three(ids):
    service.pick(YEAR, ids["Вайлдкардов"])
    service.set_round(YEAR, 4)
    for s in ("Новиков", "Запасной", "Последний"):
        service.pick(YEAR, ids[s])


def test_wildcard_round_and_refusals(draw):
    r = service.pick(YEAR, draw["Вайлдкардов"])
    assert (r["category"], r["position"]) == ("men", 1)
    with pytest.raises(DrawError, match="уже вытянут — Мужчины №1"):
        service.pick(YEAR, draw["Вайлдкардов"])
    with pytest.raises(DrawError, match="не в этом раунде"):
        service.pick(YEAR, draw["Новиков"])


def test_replace_keeps_position_cancel_shifts(draw):
    service.set_round(YEAR, 4)
    a = service.pick(YEAR, draw["Новиков"])
    b = service.pick(YEAR, draw["Запасной"])
    service.pick(YEAR, draw["Последний"])
    service.replace(YEAR, a["pick_id"], draw["Повторов"])
    assert [r["surname"] for r in service.admin_state(YEAR)["lists"]["men"]] == ["Повторов", "Запасной", "Последний"]
    service.cancel(YEAR, b["pick_id"])
    men = service.admin_state(YEAR)["lists"]["men"]
    assert [(r["position"], r["surname"]) for r in men] == [(1, "Повторов"), (2, "Последний")]
    assert service.pick(YEAR, draw["Запасной"])["position"] == 3


def test_replace_other_category_rejected(draw):
    service.set_round(YEAR, 4)
    a = service.pick(YEAR, draw["Новиков"])
    with pytest.raises(DrawError, match="другой зачёт"):
        service.replace(YEAR, a["pick_id"], draw["Новикова"])


def test_unpaid_auto_invites_next_and_suggests_revert(draw):
    _men_after_wildcard_and_three(draw)          # мест 3 → «Последний» №4 в листе ожидания
    r = service.set_payment(YEAR, draw["Новиков"], "unpaid", today=datetime.date(2097, 11, 1))
    assert (r["auto_invited"]["surname"], r["auto_invited"]["position"]) == ("Последний", 4)
    status = {a["surname"]: a["payment_status"] for a in service.admin_state(YEAR)["applicants"]}
    assert status["Последний"] == "pending"
    back = service.set_payment(YEAR, draw["Новиков"], "paid", today=datetime.date(2097, 11, 2))
    assert back["suggest_revert"]["surname"] == "Последний"


def test_auto_invite_off_after_deadline(draw):
    _men_after_wildcard_and_three(draw)
    r = service.set_payment(YEAR, draw["Новиков"], "unpaid", today=datetime.date(2098, 1, 1))
    assert r["auto_invited"] is None


def test_waitlist_empty_warning(draw):
    service.set_round(YEAR, 4)
    for s in ("Новиков", "Запасной", "Последний"):
        service.pick(YEAR, draw[s])
    r = service.set_payment(YEAR, draw["Новиков"], "unpaid", today=datetime.date(2097, 11, 1))
    assert r["waitlist_empty"] is True and r["auto_invited"] is None


def test_payment_requires_drawn(draw):
    with pytest.raises(DrawError, match="ещё не вытянут"):
        service.set_payment(YEAR, draw["Новиков"], "paid")


def test_public_state_hides_unrevealed_wildcard(draw):
    pub = service.public_state(YEAR)
    assert "Вайлдкардов" not in str(pub)
    assert "Повторов" in [p["surname"] for p in pub["aquarium"]["people"]]
    assert service.feed_rows(YEAR, "wildcard") == []
    service.pick(YEAR, draw["Вайлдкардов"])
    service.clear_cache()
    pub = service.public_state(YEAR)
    assert pub["lists"]["men"][0]["surname"] == "Вайлдкардов"
    assert "is_wildcard" not in pub["lists"]["men"][0]
    assert [r["name"] for r in service.feed_rows(YEAR, "wildcard")] == ["Вайлдкардов Тест"]


def test_feed_padded_to_capacity_and_csv(draw):
    rows = service.feed_rows(YEAR, "men")
    assert [r["num"] for r in rows] == [1, 2, 3] and all(r["name"] == "" for r in rows)
    assert service.to_csv(rows, service.FEED_COLUMNS["men"]).startswith("\ufeffnum,name,city,section,status")


def test_import_blocked_after_start(draw, monkeypatch):
    monkeypatch.setattr(service, "parse_applicants", lambda b: (APPS, []))
    service.pick(YEAR, draw["Вайлдкардов"])
    with pytest.raises(DrawError, match="уже началась"):
        service.import_applicants(YEAR, b"x", dry_run=False)
    assert service.import_applicants(YEAR, b"x", dry_run=True)["written"] is False


def test_reset_needs_year(draw):
    service.pick(YEAR, draw["Вайлдкардов"])
    with pytest.raises(DrawError):
        service.reset(YEAR, "2028")
    service.reset(YEAR, str(YEAR))
    assert service.admin_state(YEAR)["lists"]["men"] == []


def test_summary_has_history_and_placement(draw):
    service.pick(YEAR, draw["Вайлдкардов"])
    s = service.applicant_summary(YEAR, draw["Вайлдкардов"])
    assert s["placement"]["category"] == "men" and s["placement"]["position"] == 1
    assert set(s["history"]) == {"individual", "relay", "finished"}


def test_routes(draw, client):
    app.dependency_overrides[api_require_auth] = lambda: "testuser"
    try:
        r = client.post(f"/api/siberman/admin/draw/{YEAR}/pick", json={"applicant_id": draw["Вайлдкардов"]})
        assert r.status_code == 200 and r.json()["position"] == 1
        r = client.post(f"/api/siberman/admin/draw/{YEAR}/pick", json={"applicant_id": draw["Вайлдкардов"]})
        assert r.status_code == 409 and "уже вытянут" in r.json()["detail"]
    finally:
        app.dependency_overrides.pop(api_require_auth, None)
    service.clear_cache()
    assert client.get(f"/api/siberman/draw/{YEAR}/state").json()["lists"]["men"][0]["surname"] == "Вайлдкардов"
    csv_r = client.get(f"/api/siberman/draw/{YEAR}/feed/men.csv")
    assert csv_r.status_code == 200 and csv_r.content.startswith(b"\xef\xbb\xbf")
    assert client.get(f"/api/siberman/draw/{YEAR}/feed/nope.json").status_code == 404
    assert client.get(f"/draw/{YEAR}/results", headers={"host": "siberman.localhost"}).status_code == 200
    assert client.get(f"/draw/{YEAR}/results").status_code == 404
    assert client.get(f"/api/siberman/admin/draw/{YEAR}/state").status_code == 401
