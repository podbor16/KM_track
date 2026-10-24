"""Возраст для возрастной группы считается от события, а не от текущего года (баг 2026-10-24:
2013 г.р. на Жаре 2027 попадал в Ж12-13), в одном из режимов на событие+дистанцию:
birth_year — на 31.12 года забега, event_date — полных лет на день старта."""
import datetime

import pytest

import src.analytics.db_results as db
from src.analytics.db_results import _age_for_group, get_age_group_label

D = datetime.date
ZHARA_F = [(12, 13, "Ж12-13"), (14, 15, "Ж14-15"), (16, 17, "Ж16-17")]


@pytest.mark.parametrize("birth, year, event_date, mode, age", [
    (D(2013, 9, 1), 2027, None, "birth_year", 14),            # Жара 2027: по году рождения — 14
    (D(2013, 9, 1), 2027, D(2027, 8, 28), "birth_year", 14),  # дата старта в этом режиме не важна
    (D(2013, 9, 1), 2027, D(2027, 8, 28), "event_date", 13),  # ДР после старта — ещё 13
    (D(2013, 8, 28), 2027, D(2027, 8, 28), "event_date", 14), # ДР в день старта — уже 14
    (D(2013, 5, 1), 2027, D(2027, 8, 28), "event_date", 14),
    (D(2013, 9, 1), 2027, None, "event_date", 14),             # дата старта не указана — по году
    ("2013-09-01", 2027, D(2027, 8, 28), "event_date", 13),    # ДР строкой, как в заявках
])
def test_age_for_group(birth, year, event_date, mode, age):
    assert _age_for_group(birth, year, event_date, mode) == age


def test_age_without_event_year_keeps_old_behaviour():
    assert _age_for_group(D(2000, 6, 1), None, None, "birth_year") == datetime.date.today().year - 2000


def test_unknown_birthday_and_plain_age():
    assert _age_for_group(D(1900, 1, 1), 2027, None, "birth_year") is None
    assert _age_for_group("1900-01-01", 2027, None, "birth_year") is None
    assert _age_for_group(None, 2027, None, "birth_year") is None
    assert _age_for_group(35, 2027, D(2027, 8, 28), "event_date") == 35   # готовый возраст как есть


@pytest.fixture
def zhara(monkeypatch):
    monkeypatch.setattr(db, "_get_age_group_configs", lambda: {("Жара", "5 км", "F"): ZHARA_F})
    modes, dates = {}, {131: D(2027, 8, 28)}
    monkeypatch.setattr(db, "_get_age_group_modes", lambda: modes)
    monkeypatch.setattr(db, "_get_event_dates", lambda: dates)
    return modes


def test_label_zhara_2027_by_birth_year(zhara):
    assert get_age_group_label("Жара", "5 км", "2013-09-01", "Женщина", event_year=2027, event_id=131) == "Ж14-15"


def test_label_zhara_2027_on_event_date(zhara):
    zhara[("Жара", "5 км")] = "event_date"
    assert get_age_group_label("Жара", "5 км", "2013-09-01", "Женщина", event_year=2027, event_id=131) == "Ж12-13"
    assert get_age_group_label("Жара", "5 км", "2013-05-01", "Женщина", event_year=2027, event_id=131) == "Ж14-15"
