import datetime
from collections import Counter

import pytest

from scripts.import_zhara_2023_2024 import (
    distance_from_product, fill_missing_dates, parse_birthday, registered_at,
)


@pytest.mark.parametrize("product, expected", [
    ("Полумарафон 21.1 км (zhara2024-21, Выберите категорию: Основная", "21.1 км"),
    ("Забег на 2 км (zhara2024-2y, Выберите категорию: Дети 7-17 лет", "2 км"),
    ("Слот на участие в Жаре 2023 (zhara2023-10b, Выберите дистанцию", "10 км"),
    ("Слот на участие в Жаре 2022 (zhara2022-21, Выберите дистанцию", "21.1 км"),
    ("Забег на 5 км (zhara2024-5, ...", "5 км"),
    ("1", None),
    (None, None),
])
def test_distance_from_product(product, expected):
    assert distance_from_product(product) == expected


@pytest.mark.parametrize("raw, expected", [
    ("26.03.1975", "1975-03-26"),
    ("\xa026.03.1975", "1975-03-26"),
    (datetime.datetime(1990, 5, 17), "1990-05-17"),
    ("12.05.991", "1991-05-12"),
    ("1/15/88", "1988-01-15"),
    ("3/4/15", "2015-03-04"),
    ("01.01.3004", "1900-01-01"),
    (datetime.datetime(2024, 3, 1), "1900-01-01"),
    (None, "1900-01-01"),
    ("мусор", "1900-01-01"),
])
def test_parse_birthday(raw, expected):
    assert parse_birthday(raw, 2024) == expected


COLS = {"product": 0, "Total amount": 1, "Payment status": 2, "sent": 3}


def test_registered_at_from_sent():
    assert registered_at(("p", "1990", "Paid", "2024-06-05 07:53:07"), COLS) == datetime.datetime(2024, 6, 5, 7, 53, 7)


def test_registered_at_shifted_row():
    assert registered_at(("p", "Слот", "2024-06-05 07:53:07", "1290"), COLS) == datetime.datetime(2024, 6, 5, 7, 53, 7)


def test_registered_at_missing():
    assert registered_at(("p", "0", None, None), COLS) is None


def test_fill_missing_dates_uses_previous_then_next():
    d1, d2 = datetime.datetime(2024, 1, 1), datetime.datetime(2024, 2, 1)
    rows = [{"registered_at": None}, {"registered_at": d1}, {"registered_at": None}, {"registered_at": d2}]
    stats = Counter()
    fill_missing_dates(rows, stats)
    assert [r["registered_at"] for r in rows] == [d1, d1, d1, d2]
    assert stats["date_from_neighbor"] == 2
