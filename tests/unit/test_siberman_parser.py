import datetime
import io

import openpyxl
import pytest
from src.siberman.parser import (
    parse_time_to_seconds, _normalize_header, _build_col_index, parse_excel, _classify_time_cell,
)


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
    "Пловец", "Пол пловца", "Велосипедист", "Пол велосипедиста",
    "Бегун", "Пол бегуна", "3 км", "Плавание: разворот 1 (1,3 км)",
]


def test_relay_uses_dedicated_team_and_member_columns():
    row = [
        "Эстафета", "501", "Скорость Сибири", "Россия", "Абакан",
        "Иванов Иван", "М", "Петрова Анна", "Ж",
        "Сидоров Семён", "М", "0:05:00", "0:10:00",
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
    assert swim["gender"] == "M"

    bike = by_stage["bike"]
    assert bike["surname"] == "Петрова"
    assert bike["name"] == "Анна"
    assert bike["country"] == "Россия"
    assert bike["city"] == "Абакан"
    assert bike["gender"] == "F"

    run = by_stage["run"]
    assert run["surname"] == "Сидоров"
    assert run["name"] == "Семён"
    assert run["gender"] == "M"


def test_relay_member_gender_defaults_to_male_when_column_missing():
    headers = ["Формат", "Номер", "Название команды", "Пловец", "Велосипедист", "Бегун", "3 км"]
    row = ["Эстафета", "502", "Тест", "Иванов Иван", "Петров Пётр", "Сидоров Семён", "0:05:00"]
    data = _build_workbook(headers, row)
    result = parse_excel(data, 2026)
    assert all(p["gender"] == "M" for p in result.participants)


# ---------------------------------------------------------------------------
# Валидация с указанием ячеек (задача 3)
# ---------------------------------------------------------------------------

def test_classify_time_cell_valid_returns_no_error():
    seconds, err = _classify_time_cell("1:00:00")
    assert seconds == 3600
    assert err is None


def test_classify_time_cell_dnf_returns_no_error():
    seconds, err = _classify_time_cell("DNF")
    assert seconds is None
    assert err is None


def test_classify_time_cell_empty_returns_no_error():
    seconds, err = _classify_time_cell(None)
    assert seconds is None
    assert err is None


def test_classify_time_cell_garbage_returns_error():
    seconds, err = _classify_time_cell("вчера в обед")
    assert seconds is None
    assert err is not None
    assert "вчера в обед" in err


def test_classify_time_cell_period_instead_of_colon_two_dots_is_text_error():
    # "1.23.45" не парсится как число (2 точки) — Excel хранит как текст,
    # split(":") даёт 1 часть → уже ловится как нераспознанное время.
    seconds, err = _classify_time_cell("1.23.45")
    assert seconds is None
    assert err is not None


def test_classify_time_cell_period_instead_of_colon_one_dot_excel_float():
    # "1.30" (одна точка) Excel читает как число 1.3 — round(1.3*86400)=112320с.
    # Без явной проверки правдоподобности это тихо проходит как "верное" время.
    seconds, err = _classify_time_cell(1.3)
    assert seconds is None
    assert err is not None
    assert "разделитель" in err


def test_classify_time_cell_plausible_boundary_ok():
    # Ровно 25ч — ещё в пределах допустимого
    seconds, err = _classify_time_cell("25:00:00")
    assert seconds == 25 * 3600
    assert err is None


def test_classify_time_cell_implausibly_large_value_is_error():
    seconds, err = _classify_time_cell("30:00:00")
    assert seconds is None
    assert err is not None


def test_classify_time_cell_comma_as_decimal_seconds_excel_quirk():
    # Реальный кейс: судья ввёл "0:35,01" (0ч 35мин 01с), но Excel (RU-локаль)
    # ещё до сохранения сам распознал это как время формата М:СС,сс —
    # 0 минут 35.01 секунды. Наш код получает уже готовое число (float,
    # доля суток) — 35.01/86400 — а не строку с запятой.
    seconds, err = _classify_time_cell(35.01 / 86400)
    assert seconds is None
    assert err is not None
    assert "меньше минуты" in err


def test_classify_time_cell_plausible_minimum_boundary_ok():
    seconds, err = _classify_time_cell("0:01:00")
    assert seconds == 60
    assert err is None


def test_classify_time_cell_implausibly_small_value_is_error():
    seconds, err = _classify_time_cell("0:00:35")
    assert seconds is None
    assert err is not None


BASIC_HEADERS = ["Формат", "Номер", "Фамилия", "Имя", "Пол", "Плавание: разворот 1 (1,3 км)"]


def test_malformed_checkpoint_reports_cell_coordinate():
    row = ["Лично", "1", "Иванов", "Иван", "М", "неверное время"]
    data = _build_workbook(BASIC_HEADERS, row)
    result = parse_excel(data, 2026)
    assert len(result.errors) == 1
    assert "F2" in result.errors[0]
    assert "разворот 1" in result.errors[0].lower()
    assert "участник 1" in result.errors[0]
    # Значение всё равно None, но участник не теряется
    assert result.checkpoint_times["1"][("swim", 1)] is None


def test_legitimate_dnf_checkpoint_produces_no_error():
    row = ["Лично", "1", "Иванов", "Иван", "М", "DNF"]
    data = _build_workbook(BASIC_HEADERS, row)
    result = parse_excel(data, 2026)
    assert result.errors == []


# ---------------------------------------------------------------------------
# Круги плавания vs круги бега (задача 5) — заголовки "N круг(а)" повторяются
# в обеих секциях, "плавания" в тексте должен предотвращать коллизию
# occurrence-индекса в _build_col_index.
# ---------------------------------------------------------------------------

SWIM_RUN_LAP_HEADERS = [
    "Формат", "Номер", "Фамилия", "Имя", "Пол",
    "Плавание: разворот 1 (1,3 км)", "Плавание: 1 круг (2,6 км)",
    "Плавание: разворот 2 (3,9 км)", "Плавание: 2 круга (5,2 км)",
    "Плавание: разворот 3 (6,5 км)", "Плавание: 3 круга (7,8 км)",
    "Финиш 10 км (плавание, 4 круг)",
    "1 круг (7 км)", "2 круга (14 км)", "3 круга (21 км)",
]


def test_swim_and_run_lap_headers_do_not_collide():
    row = [
        "Лично", "1", "Иванов", "Иван", "М",
        "0:20:00", "0:40:00", "1:00:00", "1:20:00", "1:40:00", "2:00:00", "2:20:00",
        "3:00:00", "3:40:00", "4:20:00",
    ]
    data = _build_workbook(SWIM_RUN_LAP_HEADERS, row)
    result = parse_excel(data, 2026)
    assert result.errors == []
    cp = result.checkpoint_times["1"]
    assert cp[("swim", 1)] == 20 * 60
    assert cp[("swim", 2)] == 40 * 60
    assert cp[("swim", 6)] == 2 * 3600
    assert cp[("swim", 7)] == 2 * 3600 + 20 * 60
    assert cp[("run", 1)] == 3 * 3600
    assert cp[("run", 2)] == 3 * 3600 + 40 * 60
    assert cp[("run", 3)] == 4 * 3600 + 20 * 60


def test_missing_bib_with_data_reports_error_and_skips_row():
    row = ["Лично", None, "Иванов", "Иван", "М", "0:10:00"]
    data = _build_workbook(BASIC_HEADERS, row)
    result = parse_excel(data, 2026)
    assert len(result.errors) == 1
    assert "не заполнен номер участника" in result.errors[0]
    assert result.participants == []


def test_invalid_gender_reports_error_with_coordinate_and_defaults_to_male():
    row = ["Лично", "1", "Иванов", "Иван", "Мужской", "0:10:00"]
    data = _build_workbook(BASIC_HEADERS, row)
    result = parse_excel(data, 2026)
    assert len(result.errors) == 1
    assert "E2" in result.errors[0]
    assert "Мужской" in result.errors[0]
    assert result.participants[0]["gender"] == "M"
