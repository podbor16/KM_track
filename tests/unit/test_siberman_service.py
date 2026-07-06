import pytest
from src.siberman.service import format_seconds, format_pace, compute_split_times


def test_format_seconds_full():
    assert format_seconds(8647) == "2:24:07"


def test_format_seconds_zero():
    assert format_seconds(0) == "0:00:00"


def test_format_seconds_none():
    assert format_seconds(None) == "—"


def test_format_pace_normal():
    # 375 сек/км → "6:15"
    assert format_pace(375) == "6:15"


def test_format_pace_none():
    assert format_pace(None) == "—"


def test_compute_split_times_basic():
    # Накопленные: [100, 350, 600] → сплиты: [100, 250, 250]
    cumulative = [100, 350, 600]
    splits = compute_split_times(cumulative)
    assert splits == [100, 250, 250]


def test_compute_split_times_with_none():
    # None в середине → соответствующий сплит тоже None
    cumulative = [100, None, 600]
    splits = compute_split_times(cumulative)
    assert splits[0] == 100
    assert splits[1] is None
    assert splits[2] is None
