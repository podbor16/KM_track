import pytest

import openpyxl

from scripts.import_results_xlsx import finish_columns, parse


def test_three_finish_columns_clean_official_pace():
    h = ["Bib", "Finish", "Finish", "Finish"]                     # чистое / официальное / темп (Ночной 2025)
    rows = [(1, "00:16:01", "00:16:02", "3'12\"/km"), (2, "00:20:00", "00:20:05", "4'00\"/km")]
    assert finish_columns(h, rows) == (1, 2)


def test_named_clean_column_and_handicap():
    h = ["Bib", "Start", "Finish", "чистое "]                      # Снежная: официальное — от первого выстрела
    rows = [(1, "00:09:46", "00:38:50", "00:29:03")]
    assert finish_columns([x.strip() for x in h], rows) == (3, 2)


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
