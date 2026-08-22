"""Тесты для compute_pace()/_seconds_to_pace() в load_race_results.py.

Живой баг на Детском забеге 2026-08-22: оба помощника форматировали темп
как "00:{minutes:02d}:{seconds:02d}" без переноса минут в часы. Для очень
медленного темпа (>= 60 мин/км — реальный случай на короткой детской
дистанции) это давало невалидное значение вроде "00:75:18", которое MySQL
strict mode отклоняет как некорректный TIME — и валило executemany()
ЦЕЛИКОМ, включая ВСЕХ остальных участников в том же батче (не только
проблемную строку)."""
from load_race_results import compute_pace, _seconds_to_pace


def test_compute_pace_under_an_hour_keeps_00_hours():
    assert compute_pace(349) == "00:05:49"


def test_compute_pace_over_an_hour_carries_into_hours():
    # 75 мин 18 сек = 4518 сек — раньше давало невалидное "00:75:18"
    assert compute_pace(4518) == "01:15:18"


def test_compute_pace_none_for_non_positive():
    assert compute_pace(0) is None
    assert compute_pace(-5) is None
    assert compute_pace(None) is None


def test_seconds_to_pace_under_an_hour_keeps_00_hours():
    # 1000м за 349с → темп 5:49/км
    assert _seconds_to_pace(349, 1.0) == "00:05:49"


def test_seconds_to_pace_over_an_hour_carries_into_hours():
    # 1км за 4518с (75:18) — раньше давало невалидное "00:75:18"
    assert _seconds_to_pace(4518, 1.0) == "01:15:18"


def test_seconds_to_pace_none_for_missing_inputs():
    assert _seconds_to_pace(None, 1.0) is None
    assert _seconds_to_pace(300, None) is None
    assert _seconds_to_pace(300, 0) is None
