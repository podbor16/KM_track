"""_time_str_to_seconds(): кэш результатов из БД отдаёт TIME как timedelta —
раньше падало на .split() и лоадер Икса 2026 перезапускался по кругу с 27.09."""
from datetime import time, timedelta

from load_race_results import _time_str_to_seconds


def test_string():
    assert _time_str_to_seconds("00:01:40") == 100


def test_timedelta_from_db_cache():
    assert _time_str_to_seconds(timedelta(seconds=7)) == 7


def test_time_object():
    assert _time_str_to_seconds(time(0, 1, 40)) == 100


def test_empty_and_invalid():
    assert _time_str_to_seconds(None) is None
    assert _time_str_to_seconds("") is None
    assert _time_str_to_seconds("1:2") is None
