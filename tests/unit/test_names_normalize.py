"""Нормализация ФИО на входе — строки из аудита 2026-10-01."""
import pytest

from src.common.names import normalize_person_name


@pytest.mark.parametrize("raw, expected", [
    ("капустин-богданов", "Капустин-Богданов"),
    ("Ли-ла-лю", "Ли-Ла-Лю"),
    ("Уран-хээ", "Уран-Хээ"),
    ("ПОлина", "Полина"),
    ("ПЕТРОВ", "Петров"),
    ("COQUET", "Coquet"),
    ("⁠трускова", "Трускова"),
    ("Алëна", "Алена"),
    ("Семёнов", "Семенов"),
    ("Нинa", "Нина"),                      # латинская a
    ("Салимжанов.", "Салимжанов"),
    ("Ксения69_", "Ксения"),
    ("  анна   мария ", "Анна Мария"),
    ("Петров- Дельверс", "Петров-Дельверс"),
    ("Боз-али Оглы", "Боз-Али Оглы"),
])
def test_normalize_person_name(raw, expected):
    assert normalize_person_name(raw) == expected


@pytest.mark.parametrize("raw", [None, "", 5])
def test_normalize_person_name_passthrough(raw):
    assert normalize_person_name(raw) == raw
