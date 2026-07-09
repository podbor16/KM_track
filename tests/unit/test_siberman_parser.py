import datetime
import io

import openpyxl
import pytest
from src.siberman.parser import parse_time_to_seconds, _normalize_header, _build_col_index, parse_excel


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


def _build_workbook(headers: list[str], row: list) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(headers)
    ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


RELAY_HEADERS = [
    "Формат", "Номер", "Название команды", "Страна", "Город",
    "Пловец", "Велосипедист", "Бегун", "3 км", "1,3 км",
]


def test_relay_uses_dedicated_team_and_member_columns():
    row = [
        "Эстафета", "501", "Скорость Сибири", "Россия", "Абакан",
        "Иванов Иван", "Петров Пётр", "Сидоров Семён", "0:05:00", "0:10:00",
    ]
    data = _build_workbook(RELAY_HEADERS, row)
    result = parse_excel(data, 2026)

    by_stage = {p["relay_stage"]: p for p in result.participants}
    assert set(by_stage) == {"swim", "bike", "run"}

    swim = by_stage["swim"]
    assert swim["relay_team_name"] == "Скорость Сибири"
    assert swim["surname"] == "Иванов"
    assert swim["name"] == "Иван"
    assert swim["country"] == "Россия"
    assert swim["city"] == "Абакан"

    bike = by_stage["bike"]
    assert bike["surname"] == "Петров"
    assert bike["name"] == "Пётр"
    assert bike["country"] == "Россия"
    assert bike["city"] == "Абакан"

    run = by_stage["run"]
    assert run["surname"] == "Сидоров"
    assert run["name"] == "Семён"

    assert result.checkpoint_times["501:bike"][("bike_day1", 1)] == 300
    assert result.checkpoint_times["501:swim"][("swim", 1)] == 600
