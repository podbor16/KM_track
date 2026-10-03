"""Загрузчик выключается сам через 5 дней после даты старта (решение пользователя 2026-10-03):
Жара 21.1 крутилась с 21.08 по 24.09.2026, перезапускаясь каждые ~3 мин."""
from datetime import date
from unittest.mock import MagicMock

import pytest

from load_race_results import RaceLoader, loader_should_stop


@pytest.mark.parametrize("event_date, today, stop", [
    ("2026-09-27", date(2026, 9, 27), False),      # день гонки
    ("2026-09-27", date(2026, 10, 2), False),      # 5-й день после старта — ещё работает
    ("2026-09-27", date(2026, 10, 3), True),       # 6-й — выключается
    (date(2026, 8, 23), date(2026, 9, 24), True),  # дата из БД (date), месяц после Жары
    (None, date(2030, 1, 1), False),               # даты нет — не останавливаем
    ("", date(2030, 1, 1), False),
    ("заполнить", date(2030, 1, 1), False),        # мусор в конфиге — не останавливаем
])
def test_loader_should_stop(event_date, today, stop):
    assert loader_should_stop(event_date, today) is stop


def test_continuous_mode_exits_before_polling_after_race():
    loader = MagicMock()
    RaceLoader.continuous_mode(loader, [], 5, 60, "2020-01-01")
    loader.load_race_data.assert_not_called()
