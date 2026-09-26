import pytest

from scripts.import_results_xlsx import finish_columns


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
