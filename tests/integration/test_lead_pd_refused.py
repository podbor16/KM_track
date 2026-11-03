"""Флаг «не согласен на ПД» на реальной БД (локальный снимок): set_lead_pd_refused ставит/снимает
флаг и пишет в журнал dq_actions. Тестовые записи — событие «Тест ПД» 2099 года, убираются."""
import json
from unittest.mock import patch

import pytest

from src.analytics import db_results
from src.analytics.db_athletes import get_athlete_by_client
from src.analytics.db_pool import get_pooled_connection
from src.analytics.db_results import set_lead_pd_refused
from src.config.event_loader import EventConfig, DistanceConfig, DiplomaConfig, DiplomaBoxConfig
from src.krasmarafon.services import results_service
from src.krasmarafon.services.diploma_service import get_diploma_data

EV = "Тест ПД"


@pytest.fixture
def db():
    conn = get_pooled_connection()
    if not conn:
        pytest.skip("Нет локальной БД")
    cur = conn.cursor(dictionary=True)
    cur.execute("SHOW COLUMNS FROM leads LIKE 'pd_refused'")
    if not cur.fetchone():
        conn.close()
        pytest.skip("Миграция lead_pd_refused не применена")

    def cleanup():
        # Порядок из-за внешних ключей: результаты -> заявки -> события -> карточки клиентов
        cur.execute("SELECT id FROM events WHERE event_name = %s", (EV,))
        evs = [r["id"] for r in cur.fetchall()]
        cards = set()
        if evs:
            ph = ",".join(map(str, evs))
            cur.execute(f"SELECT DISTINCT client_id FROM results WHERE event_id IN ({ph}) AND client_id IS NOT NULL")
            cards |= {r["client_id"] for r in cur.fetchall()}
            cur.execute(f"DELETE FROM results WHERE event_id IN ({ph})")
        cur.execute("SELECT id, client_id FROM leads WHERE event_name = %s", (EV,))
        rows = cur.fetchall()
        if rows:
            ids = ",".join(str(r["id"]) for r in rows)
            keys = ",".join(f"'lead:{r['id']}'" for r in rows)
            cur.execute(f"DELETE FROM dq_actions WHERE finding_key IN ({keys})")
            cur.execute(f"DELETE FROM leads WHERE id IN ({ids})")
            cards |= {r["client_id"] for r in rows if r["client_id"]}
        if evs:
            cur.execute(f"DELETE FROM events WHERE id IN ({ph})")
        if cards:
            cur.execute(f"DELETE FROM clients WHERE id IN ({','.join(map(str, cards))}) "
                        f"AND id NOT IN (SELECT client_id FROM leads WHERE client_id IS NOT NULL) "
                        f"AND id NOT IN (SELECT client_id FROM results WHERE client_id IS NOT NULL)")
        conn.commit()

    cleanup()
    yield conn, cur
    cleanup()
    cur.close()
    conn.close()


def add_lead(cur):
    cur.execute("""INSERT INTO leads (surname, name, sex, city, club, birthday, email, phone, event_name, event_distance,
                   event_year, products, amount, client_id, event_id, is_duplicate, status, is_new, is_new_event,
                   is_name_suspicious, created_at)
                   VALUES ('Тестпд', 'Иван', 'Мужчина', '', '', '1990-01-01', 'pd@test.ru', '', %s, '5 км', 2099,
                           '', 0, 0, 0, 0, 0, 0, 0, 0, NOW())""", (EV,))
    return cur.lastrowid


def test_set_and_clear_pd_refused_with_journal(db):
    conn, cur = db
    lead = add_lead(cur)
    conn.commit()

    assert set_lead_pd_refused(lead, True, "tester")
    cur.execute("SELECT pd_refused FROM leads WHERE id = %s", (lead,))
    assert cur.fetchone()["pd_refused"] == 1

    assert set_lead_pd_refused(lead, False, "tester")
    cur.execute("SELECT pd_refused FROM leads WHERE id = %s", (lead,))
    assert cur.fetchone()["pd_refused"] == 0

    cur.execute("SELECT action, details, done_by FROM dq_actions WHERE finding_key = %s ORDER BY id", (f"lead:{lead}",))
    log = cur.fetchall()
    assert [r["action"] for r in log] == ["pd_refused", "pd_refused"]
    assert [json.loads(r["details"])["pd_refused"] for r in log] == [1, 0]
    assert {r["done_by"] for r in log} == {"tester"}


def test_unknown_lead_returns_false(db):
    assert not set_lead_pd_refused(10 ** 12, True, "tester")


def add_event_with_result(cur):
    cur.execute("INSERT INTO events (event_name, event_distance, event_year, event_date) "
                "VALUES (%s, 5, 2099, '2099-01-01')", (EV,))
    ev = cur.lastrowid
    lead = add_lead(cur)
    cur.execute("UPDATE leads SET event_id = %s, start_number = 9901 WHERE id = %s", (ev, lead))
    cur.execute("""INSERT INTO results (surname, name, birthday, sex, event_id, start_number, race_status,
                   time_gun_finish, rank_absolute) VALUES ('Тестпд', 'Иван', '1990-01-01', 'Мужчина', %s, 9901,
                   'Finished', '00:25:00', 1)""", (ev,))
    return ev, lead


def reset_caches():
    """Сбрасывает кеши результатов, чтобы следующий запрос шёл в БД."""
    for cache in (db_results._results_cache, db_results._results_cache_ts,
                  db_results._event_info_cache, db_results._event_info_cache_ts,
                  db_results._stats_cache, db_results._stats_cache_ts,
                  results_service._response_cache, results_service._response_cache_ts,
                  results_service._json_cache, results_service._hist_cache, results_service._hist_cache_ts):
        cache.clear()


def fake_event_config(ev):
    return EventConfig(
        code="testpd", name=EV, display_name=EV, year=2099,
        distances=[DistanceConfig(
            distance="5 км", distance_km=5.0, db_event_id=ev, tracked=True,
            diploma=DiplomaConfig(
                background="static/images/diplomas/women7/7km/background.png",
                width_px=1080, height_px=1920,
                name_box=DiplomaBoxConfig(top=24.8, left=8.8, width=81.6, height=17.9),
                ranks_box=DiplomaBoxConfig(top=45.8, left=8.8, width=81.6, height=16.3),
            ),
        )],
    )


def test_refused_hidden_everywhere(db, client):
    conn, cur = db
    ev, lead = add_event_with_result(cur)
    conn.commit()
    cur.execute("SELECT client_id FROM results WHERE event_id = %s", (ev,))
    card = cur.fetchone()["client_id"]
    assert card, "триггер не проставил client_id"

    def event_results():
        reset_caches()
        r = client.get(f"/api/event-results?event_id={ev}")
        assert r.status_code == 200
        results = r.json()["results"]
        assert len(results) == 1  # в тестовом событии один участник (номер 9901)
        return r.text, results[0]

    with patch("src.config.settings.EVENTS", {"testpd": fake_event_config(ev)}):
        # Контроль: до установки флага ФИ видно
        reset_caches()
        assert db_results.get_race_results_by_event_id(ev)[0]["pd_refused"] == 0
        body, row = event_results()
        assert "Тестпд" in body
        assert get_diploma_data(ev, "9901")["surname"] == "Тестпд"
        assert "Тестпд" in client.get(f"/diploma/{ev}/9901").text
        assert any(r["event_id"] == ev for r in get_athlete_by_client(card)[1])

        set_lead_pd_refused(lead, True, "tester")

        # Лента результатов (JSON)
        body, row = event_results()
        assert "Тестпд" not in body
        assert row["surname"] == "Спортсмен"
        assert row["client_id"] is None

        # Публичный диплом
        reset_caches()
        assert get_diploma_data(ev, "9901")["surname"] == "Спортсмен"
        r = client.get(f"/diploma/{ev}/9901")
        assert r.status_code == 200
        assert "Тестпд" not in r.text
        assert "Спортсмен" in r.text

    # Профиль: событие с отказом не попадает в историю
    reset_caches()
    assert db_results.get_race_results_by_event_id(ev)[0]["pd_refused"] == 1
    assert all(r["event_id"] != ev for r in get_athlete_by_client(card)[1])
    reset_caches()
