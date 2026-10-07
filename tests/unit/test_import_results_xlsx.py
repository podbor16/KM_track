import pytest

import openpyxl

from scripts.import_results_xlsx import finish_columns, parse, rank


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
