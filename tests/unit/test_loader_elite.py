"""Загрузчик Copernico (--init): «Элита» на Жаре 21,1 км — «Элита» в dorsal (служебный номер,
как у замыкающих) или номер вне основных диапазонов «Присвоить номера»."""
import logging
from unittest.mock import MagicMock

from load_race_results import RaceLoader, SWEEPER_NUMBER_OFFSET


def test_init_marks_elite():
    loader = RaceLoader(93, logging.LoggerAdapter(logging.getLogger("t"), {}))
    loader.cursor = MagicMock()
    loader.cursor.fetchall.return_value = []
    loader.elite_ranges = [(100, 1999)]
    batches = []
    loader._bulk_insert = lambda batch: batches.extend(batch) or len(batch)
    runners = [
        {"dorsal": "150", "surname": "Обычный", "name": "Иван", "gender": "Male", "category": "М18-24"},
        {"dorsal": "7", "surname": "Быстров", "name": "Олег", "gender": "Male", "category": "М18-24"},
        {"dorsal": "Элита", "surname": "Попов", "name": "Артем", "gender": "Male", "category": "М18-24"},
        {"dorsal": "Зам", "surname": "Замыкающий", "name": "Петр", "gender": "Male", "category": ""},
    ]
    assert loader.init_mode(runners)
    got = {row[2]: (row[1], row[-1]) for row in batches}
    assert got["Обычный"] == ("150", 0)
    assert got["Быстров"] == ("7", 1)                                   # вне основного диапазона
    assert got["Попов"][1] == 1 and int(got["Попов"][0]) >= SWEEPER_NUMBER_OFFSET   # служебный номер — для диплома
    assert got["Замыкающий"][1] == 0
