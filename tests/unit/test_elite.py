"""«Элита» — элитный кластер Жары 21,1 км (решения пользователя 2026-10-06)."""
from unittest.mock import MagicMock

from src.analytics.elite import distance_label, is_elite, main_ranges

RANGES = [(100, 1999)]


def test_text_bib_elite_or_name_bib_but_not_sweeper():
    assert is_elite("Элита", [])
    assert is_elite("элита", RANGES)
    assert is_elite("ПОПОВ", [], surname="Попов")          # именной номер (протокол Жары 2025)
    assert is_elite("Чёрный", [], surname="Черный")
    assert not is_elite("Зам", [], surname="Иванов")       # замыкающий — не элита
    assert not is_elite("", RANGES)


def test_number_outside_main_ranges_is_elite():
    assert is_elite("17", RANGES)
    assert not is_elite("150", RANGES)
    assert not is_elite("17", [])                         # диапазоны не заданы — по номеру не определяем


def test_main_ranges_only_for_elite_cluster():
    cur = MagicMock()
    cur.fetchall.return_value = [(100, 1999)]
    assert main_ranges(cur, "Жара", "21.1 км") == [(100, 1999)]
    assert main_ranges(cur, "Жара", "5 км") == []
    assert cur.execute.call_count == 1
    assert distance_label(21.1) == "21.1 км" and distance_label("5.0") == "5 км"


def test_pacer_text():
    from src.analytics.elite import is_pacer
    assert is_pacer("Пейсер") and is_pacer("пейсмейкер 1:30") and is_pacer("Pacer")
    assert is_pacer("ЗАМЫКАЮЩИЙ") and is_pacer("Зам")                      # замыкающие — тоже «Пейсер»
    assert not is_pacer("Элита") and not is_pacer("150") and not is_pacer("Замятин")
    assert not is_elite("Пейсер", [], surname="Пцарев")


def test_import_protocol_helpers():
    from scripts.import_results_xlsx import _number, short_category
    assert [_number(b) for b in ("1859", "1859а", "ЗАМЫКАЮЩИЙ", "ПОПОВ")] == [1859, 1859, None, None]
    assert short_category("Женщины 1960 г.р. и старше", 2025) == "Ж65+"
    assert short_category("Мужчины 1950 г.р. и старше", 2025) == "М75+"
    assert short_category("Мужчины 1976-2007 г. р.", 2025) == "М18-49"
