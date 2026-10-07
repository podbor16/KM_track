import pytest

import openpyxl

from scripts.import_results_xlsx import finish_columns, parse, rank, set_bibs


def test_three_finish_columns_clean_official_pace():
    h = ["Bib", "Finish", "Finish", "Finish"]                     # чистое / официальное / темп (Ночной 2025)
    rows = [(1, "00:16:01", "00:16:02", "3'12\"/km"), (2, "00:20:00", "00:20:05", "4'00\"/km")]
    assert finish_columns(h, rows) == (1, 2)


def test_named_clean_column_and_handicap():
    h = ["Bib", "Start", "Finish", "чистое "]                      # Снежная: официальное — от первого выстрела
    rows = [(1, "00:09:46", "00:38:50", "00:29:03")]
    assert finish_columns([x.strip() for x in h], rows) == (3, 2)


def test_single_finish_column_is_official_only():
    assert finish_columns(["Bib", "Результат"], [(1, "00:15:11")]) == (None, 1)


def test_clean_greater_than_official_is_error():
    h = ["Bib", "Finish \"чистое\"", "Finish"]
    rows = [(1, "00:30:00", "00:29:00")]
    with pytest.raises(ValueError):
        finish_columns(h, rows)



def test_group_headers_by_age(tmp_path):
    # Весна 2024: категория — строка-заголовок группы над участниками, пол — из неё же
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["#", "Номер", "Фамилия", "Имя", "Дата рождения", "Статус", "Результат"])
    ws.append(["Мужчины до 49 лет (1975 г.р. и младше)"])
    ws.append([1, 1003, "Тарасов", "Павел", "05/08/2001", "Финишировал", "00:15:11"])
    ws.append([])
    ws.append(["Женщины 60 лет и старше (1964 г.р. и старше)"])
    ws.append([1, 55, "Иванова", "Анна", "01/02/1960", "Финишировал", "00:30:00"])
    path = tmp_path / "p.xlsx"
    wb.save(path)
    rows = parse(path, 2024)
    assert [(r["category"], r["sex"]) for r in rows] == [("М49", "Мужчина"), ("Ж60+", "Женщина")]
    # одна колонка времени — только официальное, чистого нет
    assert [(r["gun"], r["clean"]) for r in rows] == [(911, None), (1800, None)]
    rank(rows)
    assert (rows[0]["rank_absolute"], rows[0].get("rank_absolute_clean")) == (1, None)



def test_pacer_group_has_no_category(tmp_path):
    # Жара 2024: группа «Пейсмейкеры» в конце — не наследует предыдущую группу
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["#", "Номер", "Фамилия", "Имя", "Год рождения", "Статус", "Результат"])
    ws.append(["Женщины 1949 г. р. и старше"])
    ws.append([1, 55, "Антипина", "Лидия", 1949, "Финишировал", "02:30:00"])
    ws.append(["Пейсмейкеры"])
    ws.append([1, 900, "Глазунов", "Владимир", None, "Финишировал", "01:45:00"])
    path = tmp_path / "p.xlsx"
    wb.save(path)
    rows = parse(path, 2024)
    assert [(r["category"], r["sex"], r["pacer_group"]) for r in rows] == [("Ж75+", "Женщина", False), ("", "", True)]



def test_set_bib():
    rows = [{"surname": "Давыденко", "name": "Петр", "bib": "515", "start_number": 515},
            {"surname": "Трегубов", "name": "Сергей", "bib": "515", "start_number": 515}]
    set_bibs(rows, ["Давыденко Пётр=593"])
    assert [r["start_number"] for r in rows] == [593, 515] and rows[0]["bib"] == "593"
    with pytest.raises(ValueError):
        set_bibs(rows, ["Иванов Иван=1"])



def test_russian_sex_and_category_headers(tmp_path):
    # Ночной 2023: «Пол» (Male/Female); Снежная 2023: «Категория» и единственное «Чистое время» — официальное
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["#", "Номер", "Имя", "Фамилия", "Статус", "Пол", "Категория", "Чистое время", "Дата рождения"])
    ws.append([1, 11, "Валентин", "Тяпкин", "Финишировал", "Male", "Мужчины", "00:31:28", "30/03/1957"])
    path = tmp_path / "p.xlsx"
    wb.save(path)
    r = parse(path, 2023)[0]
    assert (r["sex"], r["category"], r["gun"], r["clean"]) == ("Мужчина", "Мужчины", 1888, None)



def test_full_name_column_without_status(tmp_path):
    # Жара 2023: «Имя» = «Имя Фамилия», статуса нет (только финишировавшие), год рождения в «Date of Birth»
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["ИТОГОВЫЙ ПРОТОКОЛ РЕЗУЛЬТАТОВ"])
    ws.append(["#", "Номер", "Имя", "Результат", "Клуб", "Город", "Date of Birth"])
    ws.append(["женщины 2010−2011 г. р."])
    ws.append(["1", "1179", "Кира Огер", "00:48:05", "Сибиряк", "Красноярск", 2011])
    ws.append(["Вне зачета"])
    ws.append(["1", "777", "Александр Ермолов", "02:19:01", None, "Красноярск", "-"])
    ws.append([])
    ws.append(["Главный судья", "Кондоба А.С."])
    path = tmp_path / "p.xlsx"
    wb.save(path)
    r = parse(path, 2023)[0]
    assert (r["surname"], r["name"], r["race_status"], r["gun"], r["birth_year"], r["birthday"], r["sex"], r["start_number"]) == \
        ("Огер", "Кира", "Finished", 2885, 2011, "1900-01-01", "Женщина", 1179)
    assert r["category"] == "Ж12-13"
    rows = parse(path, 2023)
    assert len(rows) == 2 and (rows[1]["surname"], rows[1]["category"], rows[1]["pacer_group"]) == ("Ермолов", "", True)
