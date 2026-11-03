"""Загрузчик результатов (load_race_results.RaceLoader._update_existing) и перепривязка: исправленные в протоколе
ФИ/ДР по номеру переносят результат на верную карточку (журнал relink:loader, пользователь loader).
Тестовые данные — как в test_relink.py (событие «Тест перепривязка» 2099)."""
import logging

import pytest

import src.analytics.dq_actions as dq_actions
from load_race_results import RaceLoader
from tests.integration.test_relink import (  # noqa: F401  (фикстуры)
    BD_DAUGHTER, BD_MAMA, SURNAME, add_result, db, row_state, world,
)

NUM = 9010


@pytest.fixture
def loader(db, world):
    """Загрузчик на соединении пула (как в бою) и кэшем одного результата «Мама» №9010 на карточке мамы.
    Записи журнала от пользователя loader, созданные тестом, убираются по id."""
    conn, cur = db
    cur.execute("SELECT COALESCE(MAX(id), 0) m FROM dq_actions")
    last_action = cur.fetchone()["m"]
    res = add_result(cur, "Мама", BD_MAMA, world["event_id"], NUM)
    conn.commit()
    assert res["client_id"] == world["cm"]

    ld = RaceLoader(world["event_id"], logging.LoggerAdapter(logging.getLogger("relink-loader-test"), {}))
    ld.connection, ld.cursor = conn, conn.cursor(dictionary=True)
    ld.event_distance_km = 5.0
    ld._kt_fields = [None] * 7
    ld.existing_results = {str(NUM): {
        "id": res["id"], "surname": SURNAME, "name": "Мама", "birthday": BD_MAMA, "race_status": "Finished",
        "time_gun_finish": "00:25:00", "time_gun_start": None, "time_clear_start": None, "time_clear_finish": None,
        "time_gun_finish_ms": None, "time_clear_finish_ms": None,
    }}
    ld.res = res
    yield ld
    ld.cursor.close()
    cur.execute("DELETE FROM dq_actions WHERE id > %s AND done_by = 'loader' AND finding_key = 'relink:loader' "
                "AND JSON_EXTRACT(details, '$.row_id') = %s", (last_action, res["id"]))
    conn.commit()


def runner(name="Мама", birthdate="1986-05-01"):
    return {"dorsal": str(NUM), "surname": SURNAME, "name": name, "birthdate": birthdate, "gender": "Female",
            "category": "Ж18-34", "status": "finished"}


def test_corrected_name_and_birthday_move_result_to_right_card(loader, world, db):
    conn, cur = db
    updated, _, _ = loader._update_existing([runner("Дочь", "2015-04-05")])

    assert updated == 1
    state = row_state(cur, "results", loader.res["id"])
    assert (state["name"], str(state["birthday"])) == ("Дочь", "2015-04-05")
    assert state["client_id"] == world["cx"]
    cur.execute("SELECT action, finding_key, done_by FROM dq_actions WHERE id = (SELECT MAX(id) FROM dq_actions)")
    assert cur.fetchone() == {"action": "move_result", "finding_key": "relink:loader", "done_by": "loader"}


def test_birthday_only_correction_is_detected_and_relinked(loader, world, db):
    """Раньше ДР не входила в сравнение — исправление одной только ДР не доходило до БД."""
    conn, cur = db
    loader.existing_results[str(NUM)]["time_gun_finish"] = None      # прочих отличий нет
    cur.execute(f"UPDATE results SET time_gun_finish = NULL WHERE id = {int(loader.res['id'])} "
                f"AND surname LIKE '{SURNAME}%'")
    conn.commit()

    updated, _, _ = loader._update_existing([runner("Мама", "2015-04-05")])        # у «Мамы» теперь ДР дочери

    assert updated == 1
    assert str(row_state(cur, "results", loader.res["id"])["birthday"]) == "2015-04-05"


def test_no_fio_change_does_not_call_relink(loader, monkeypatch):
    calls = []
    monkeypatch.setattr(dq_actions, "relink_row", lambda *a, **k: calls.append(a))
    loader._update_existing([runner("Мама", "1986-05-01")])
    assert calls == []


def test_relink_failure_is_logged_and_loading_continues(loader, db, monkeypatch, caplog):
    conn, cur = db

    def boom(*a, **k):
        raise ValueError("boom")

    monkeypatch.setattr(dq_actions, "relink_row", boom)
    with caplog.at_level(logging.ERROR):
        updated, _, _ = loader._update_existing([runner("Дочь", "2015-04-05")])

    assert updated == 1                                                      # загрузка не упала
    assert row_state(cur, "results", loader.res["id"])["name"] == "Дочь"      # данные протокола записаны
    assert "boom" in caplog.text
