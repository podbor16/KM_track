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
        ("Попов", "Артем", datetime.date(2001, 7, 5), None, "Женщина"),
        ("Петрова", "Анна", datetime.date(1990, 1, 2), 77, "Женщина"),
        ("Иванов", "Иван", datetime.date(1980, 1, 1), None, "Женщина"), ("Иванов", "Иван", datetime.date(1980, 5, 5), None, "Женщина"),
    ]
    rows = [
        {"surname": "Попов", "name": "Артём", "birthday": SENTINEL, "birth_year": 2001, "start_number": 1087, "bib": "1087", "race_status": "Finished"},
        {"surname": "Петрова", "name": "Анна", "birthday": "1990-01-02", "birth_year": None, "start_number": None, "bib": "", "race_status": "Finished"},
        {"surname": "Иванов", "name": "Иван", "birthday": SENTINEL, "birth_year": 1980, "start_number": 5, "bib": "5", "race_status": "Finished"},
    ]
    done, missing, loose = fill_from_leads(cur, 1, rows)
    assert rows[0]["birthday"] == "2001-07-05"                    # «ё» в имени — не помеха
    assert rows[1]["start_number"] == 77
    assert rows[2]["birthday"] == "1980-01-01" and len(missing) == 1  # две заявки — неоднозначно
    assert done == {"ДР из заявки": 1, "номер из заявки": 1} and loose == []


def _row(surname, name, birthday, status="Finished"):
    return {"surname": surname, "name": name, "birthday": birthday, "birth_year": None,
            "start_number": None, "bib": "", "race_status": status}


def test_fill_from_leads_bib_stages():
    # Женская 2024: уменьшительное имя, опечатка в ДР, заглушка ДР в заявке; номер — однозначно
    import datetime
    from unittest.mock import MagicMock
    from scripts.import_results_xlsx import fill_from_leads
    cur = MagicMock()
    cur.fetchall.return_value = [
        ("Лопатеева", "Юлия", datetime.date(1979, 3, 3), 203, "Женщина"),
        ("Носкова", "Надежда", datetime.date(2012, 3, 14), 130, "Женщина"),
        ("Калькина", "Гульнара", datetime.date(1900, 1, 1), 262, "Женщина"),
        ("Лата", "Олеся", datetime.date(1987, 9, 16), 129, "Женщина"),
        ("Петрова", "Анна", datetime.date(1990, 1, 2), 77, "Женщина"), ("Петрова", "Анна", datetime.date(1991, 1, 2), 78, "Женщина"),
        ("Кощеева", "Дарья", datetime.date(1999, 2, 28), None, "Женщина"),
        ("Жиленков", "Татьяна", datetime.date(1988, 3, 8), 358, "Женщина"),
    ]
    rows = [_row("Лопатеева", "Юлька", "1979-03-03"), _row("Носкова", "Надежда", "2012-03-23"),
            _row("Калькина", "Гульнара", "1998-05-19"), _row("Лата", "Олеся", "1987-09-15"),
            _row("Петрова", "Анна", "1985-05-05"), _row("Сидорова", "Ольга", "1970-01-01"),
            _row("Жиленковв", "Татьяна", "1988-03-08")]
    done, missing, loose = fill_from_leads(cur, 1, rows)
    assert [r["start_number"] for r in rows] == [203, 130, 262, 129, None, None, 358]
    assert done == {"номер из заявки (фамилия+ДР)": 1, "номер из заявки (имя+ДР)": 1,
                    "номер из заявки (фамилия+имя)": 3}
    assert len(loose) == 5 and len(missing) == 2                  # две Петровы — неоднозначно; Сидоровой нет
    assert (rows[0]["name"], rows[6]["surname"]) == ("Юлия", "Жиленков")   # ФИ из заявки — триггер свяжет с её карточкой


def test_drop_protocol_duplicates_keeps_finished():
    from scripts.import_results_xlsx import drop_protocol_duplicates
    rows = [_row("Яковлева", "Дарья", "1989-08-17", "Not started"), _row("Яковлева", "Дарья", "1989-08-17"),
            _row("Яковлева", "Дарья", "1990-01-01")]
    keep, dropped = drop_protocol_duplicates(rows)
    assert [r["race_status"] for r in keep] == ["Finished", "Finished"]
    assert [r["race_status"] for r in dropped] == ["Not started"]
    rows[0]["start_number"], rows[1]["start_number"] = 5, 6       # разные номера — разные люди
    assert len(drop_protocol_duplicates(rows[:2])[0]) == 2



def test_fill_from_leads_by_bib():
    # Жара 2024: только год рождения, опечатка в имени, пейсер без пола — заявка с тем же номером
    import datetime
    from unittest.mock import MagicMock
    from scripts.import_results_xlsx import SENTINEL, fill_from_leads
    cur = MagicMock()
    cur.fetchall.return_value = [
        ("Яковлев", "Максим", datetime.date(1985, 4, 1), 501, "мужчина"),
        ("Глазунов", "Владимир", datetime.date(1970, 2, 2), 900, "Мужчина"),
        ("Петров", "Иван", datetime.date(1990, 3, 3), 77, "Мужчина"),
    ]
    row = lambda surname, name, year, bib: {"surname": surname, "name": name, "birthday": SENTINEL, "birth_year": year,
                                            "start_number": bib, "bib": str(bib), "sex": "", "race_status": "Finished"}
    rows = [row("Яковлев", "Макским", 1985, 501), row("Глазунов", "Владимир", None, 900), row("Сидоров", "Иван", 1980, 77)]
    done, missing, loose = fill_from_leads(cur, 1, rows)
    assert (rows[0]["birthday"], rows[0]["name"], rows[0]["sex"]) == ("1985-04-01", "Максим", "Мужчина")
    assert (rows[1]["birthday"], rows[1]["sex"]) == ("1970-02-02", "Мужчина")
    assert rows[2]["birthday"] == "1980-01-01" and rows[2]["surname"] == "Сидоров"   # чужая заявка: ни фамилии, ни года
    assert len(loose) == 1 and len(missing) == 1
