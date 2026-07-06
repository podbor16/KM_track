import datetime
import pytest
from src.siberman.parser import parse_time_to_seconds, _normalize_header, _build_col_index


def test_parse_time_hmmss_string():
    assert parse_time_to_seconds("2:24:07") == 8647


def test_parse_time_mmss_string():
    assert parse_time_to_seconds("06:15") == 375


def test_parse_time_timedelta():
    td = datetime.timedelta(hours=2, minutes=24, seconds=7)
    assert parse_time_to_seconds(td) == 8647


def test_parse_time_excel_float():
    # Excel хранит время как долю суток: 1 час = 1/24
    val = 2 / 24  # 2 часа = 7200 сек
    assert parse_time_to_seconds(val) == 7200


def test_parse_time_dnf_returns_none():
    assert parse_time_to_seconds("DNF") is None
    assert parse_time_to_seconds("днф") is None


def test_parse_time_empty_returns_none():
    assert parse_time_to_seconds("") is None
    assert parse_time_to_seconds(None) is None
    assert parse_time_to_seconds("-") is None


def test_normalize_header_strips_and_lowercases():
    assert _normalize_header("  Финиш 145 км  ") == "финиш 145 км"


def test_normalize_header_startswith_match():
    # "4 круг / Финиш плавания" начинается с "4 круг"
    assert _normalize_header("4 круг / Финиш плавания").startswith("4 круг")


def test_build_col_index_handles_duplicates():
    headers = ["Формат", "Разворот", "1 круг", "Разворот", "2 круг", "Разворот"]
    idx = _build_col_index(headers)
    # First "Разворот" has occurrence 0, second has 1, third has 2
    assert idx[("разворот", 0)] == 1
    assert idx[("разворот", 1)] == 3
    assert idx[("разворот", 2)] == 5
