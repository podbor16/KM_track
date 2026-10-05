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


@pytest.mark.parametrize("raw, expected", [
    ("Cнежная семерка", "Снежная семерка"),        # латинская C — событие-двойник 2026-10-05
    ("Снежная семерка", "Снежная семерка"),
    ("Х Трейл", "Х Трейл"),
    ("XTrail", "XTrail"),                           # целиком латиница — не трогаем
])
def test_normalize_event_name(raw, expected):
    from src.common.names import normalize_event_name
    assert normalize_event_name(raw) == expected


def test_tilda_product_with_latin_c_maps_to_cyrillic_event():
    from src.krasmarafon.services.tilda_webhook import parse_products
    info = parse_products(["2 км Cнежная семерка 2026 (snow2-2026, Выберите категорию: Основная) x 1 ≡ 700"])
    assert info["event_name"] == "Снежная семерка"
