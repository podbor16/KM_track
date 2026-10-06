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


def test_kids_and_group_sex():
    from scripts.import_results_xlsx import group_sex, short_category
    assert short_category("Мальчики 2014 г.р.", 2025) == "Мальчики 2014 г.р."      # как Детский 2026
    assert short_category("Девочки  2016 г. р.", 2025) == "Девочки 2016 г.р."
    assert group_sex("Девочки 2016 г.р.") == "Женщина" and group_sex(" Юноши 2012-2013 г.р.") == "Мужчина"
    assert group_sex("Unknown") == ""


def test_checkpoint_columns():
    from scripts.import_results_xlsx import checkpoint_columns
    h = ["#", "Bib", "2,5", "Status", "4,5", "2,5km", "razv1", "Razv2", "Finish", "Start"]
    assert checkpoint_columns(h, {"razv1": 1.75, "razv2": 5.25}) == {2: 2.5, 4: 4.5, 5: 2.5, 6: 1.75, 7: 5.25}


def test_write_checkpoints_sets_distances_and_pace():
    import json
    from unittest.mock import MagicMock
    from scripts.import_results_xlsx import write_checkpoints
    cur = MagicMock()
    cur.rowcount = 1
    rows = [{"start_number": 7, "kt": {2.5: 557, 4.5: 1023}}, {"start_number": 8, "kt": {}}]
    kms, updated = write_checkpoints(cur, 89, 5.0, rows)
    assert kms == [2.5, 4.5] and updated == 1
    assert json.loads(cur.execute.call_args_list[0].args[1][0]) == [0, 2.5, 4.5, 5.0]
    vals = cur.execute.call_args_list[1].args[1]
    assert vals[:4] == ["00:09:17", "00:03:42", "00:17:03", "00:03:47"] and vals[4:14] == [None] * 10
    assert vals[-2:] == [89, 7]


def test_fill_from_leads():
    import datetime
    from unittest.mock import MagicMock
    from scripts.import_results_xlsx import SENTINEL, fill_from_leads
    cur = MagicMock()
    cur.fetchall.return_value = [
        ("Попов", "Артем", datetime.date(2001, 7, 5), None),
        ("Петрова", "Анна", datetime.date(1990, 1, 2), 77),
        ("Иванов", "Иван", datetime.date(1980, 1, 1), None), ("Иванов", "Иван", datetime.date(1980, 5, 5), None),
    ]
    rows = [
        {"surname": "Попов", "name": "Артём", "birthday": SENTINEL, "birth_year": 2001, "start_number": 1087, "bib": "1087", "race_status": "Finished"},
        {"surname": "Петрова", "name": "Анна", "birthday": "1990-01-02", "birth_year": None, "start_number": None, "bib": "", "race_status": "Finished"},
        {"surname": "Иванов", "name": "Иван", "birthday": SENTINEL, "birth_year": 1980, "start_number": 5, "bib": "5", "race_status": "Finished"},
    ]
    done, missing = fill_from_leads(cur, 1, rows)
    assert rows[0]["birthday"] == "2001-07-05"                    # «ё» в имени — не помеха
    assert rows[1]["start_number"] == 77
    assert rows[2]["birthday"] == "1980-01-01" and len(missing) == 1  # две заявки — неоднозначно
    assert done == {"ДР из заявки": 1, "номер из заявки": 1}
