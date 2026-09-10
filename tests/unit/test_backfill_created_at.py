"""Тесты ядра scripts/backfill_created_at_from_tilda.py — разбор файла Tilda +
матчинг + расчёт «что сдвинется». БД замокана (скрипт сам ничего не пишет в
dry-run)."""
import importlib.util
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

_spec = importlib.util.spec_from_file_location(
    "backfill_created_at_from_tilda",
    Path(__file__).parents[2] / "scripts" / "backfill_created_at_from_tilda.py",
)
backfill = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(backfill)


def _csv_file(tmp_path, text):
    p = tmp_path / "leads-export.csv"
    p.write_bytes(text.encode("utf-8-sig"))
    return p


_ROW = (
    "surname;Name;birthday;product;Date\r\n"
    "Тестов;Иван;01.05.1990;"
    "\"5 км Жара 2026 (zhara2026-5, Выберите категорию: Основная категория)\";"
    "2026-05-01 10:00:00\r\n"
)


def test_analyze_file_queues_update_and_counts_move_when_db_date_is_later(tmp_path):
    cur = MagicMock()
    # _find_lead_matches: нет order_id → один SELECT по surname+name → [id=5];
    # затем SELECT id, created_at → текущая дата ПОЗЖЕ даты файла
    cur.fetchall.side_effect = [
        [{"id": 5}],
        [{"id": 5, "created_at": datetime(2026, 8, 14, 3, 0, 0)}],
    ]

    s = backfill._analyze_file(cur, _csv_file(tmp_path, _ROW))

    assert s["with_date"] == 1
    assert s["matched_rows"] == 1
    assert s["unmatched_rows"] == 0
    assert s["updates"] == [(5, datetime(2026, 5, 1, 10, 0, 0))]
    assert s["would_move"] == 1
    assert s["already_ok"] == 0
    assert s["file_month_hist"] == {"2026-05": 1}
    assert ("Жара", 2026) in s["events"]


def test_analyze_file_no_move_when_db_date_already_earlier(tmp_path):
    cur = MagicMock()
    cur.fetchall.side_effect = [
        [{"id": 7}],
        [{"id": 7, "created_at": datetime(2026, 3, 1, 0, 0, 0)}],  # раньше даты файла
    ]

    s = backfill._analyze_file(cur, _csv_file(tmp_path, _ROW))

    assert s["updates"] == [(7, datetime(2026, 5, 1, 10, 0, 0))]
    assert s["would_move"] == 0
    assert s["already_ok"] == 1


def test_analyze_file_counts_unmatched_rows(tmp_path):
    cur = MagicMock()
    cur.fetchall.side_effect = [[]]  # _find_lead_matches — ничего не нашёл

    s = backfill._analyze_file(cur, _csv_file(tmp_path, _ROW))

    assert s["matched_rows"] == 0
    assert s["unmatched_rows"] == 1
    assert s["updates"] == []


def test_analyze_file_skips_rows_without_parseable_date(tmp_path):
    cur = MagicMock()
    text = _ROW.replace("2026-05-01 10:00:00", "")  # пустая Date

    s = backfill._analyze_file(cur, _csv_file(tmp_path, text))

    assert s["with_date"] == 0
    assert s["updates"] == []
    cur.execute.assert_not_called()  # до матчинга не дошли
