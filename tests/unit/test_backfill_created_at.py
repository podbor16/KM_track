"""Тесты ядра scripts/backfill_created_at_from_tilda.py — разбор файла Tilda +
матчинг + расчёт «что сдвинется». БД замокана (скрипт сам ничего не пишет в
dry-run)."""
import importlib.util
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

def _load(name):
    spec = importlib.util.spec_from_file_location(
        name, Path(__file__).parents[2] / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


backfill = _load("backfill_created_at_from_tilda")
gen_sql = _load("gen_backfill_created_at_sql")


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


# --- gen_backfill_created_at_sql -----------------------------------------

_TWO_ROWS = (
    "surname;Name;birthday;order_id;product;Date\r\n"
    "Тестов;Иван;01.05.1990;111;"
    "\"5 км Жара 2026 (zhara2026-5, кат)\";2026-05-01 10:00:00\r\n"
    "Петров;Пётр;02.06.1985;0;"
    "\"21.1 км Жара 2026 (zhara2026-21, кат)\";2026-06-02 11:00:00\r\n"
)


def test_gen_sql_emits_transaction_temp_table_and_least_updates(tmp_path):
    f = tmp_path / "leads-export.csv"
    f.write_bytes(_TWO_ROWS.encode("utf-8-sig"))
    rows = gen_sql._collect_rows([f], min_per_event=1)
    sql = gen_sql._emit_sql(rows)

    assert "START TRANSACTION;" in sql and sql.rstrip().endswith("COMMIT;")
    assert "CREATE TEMPORARY TABLE _tilda_reg" in sql
    assert "DROP TEMPORARY TABLE IF EXISTS _tilda_reg;" in sql
    assert sql.count("SET l.created_at = LEAST(l.created_at, t.registered_at)") == 2
    assert "DELETE FROM" not in sql.upper() and "DELETE l" not in sql
    # order_id=0 → NULL (заглушка Tilda, не настоящий номер)
    assert "(111, 'Тестов'" in sql
    assert "(NULL, 'Петров'" in sql
    assert "'2026-05-01 10:00:00'" in sql


def test_gen_sql_str_escapes_apostrophe():
    assert gen_sql._sql_str("О'Брайен") == "'О''Брайен'"
    assert gen_sql._sql_str("простой") == "'простой'"


def test_gen_sql_drops_tiny_event_groups_as_parse_noise(tmp_path):
    text = _TWO_ROWS + (
        "Одиночкин;Лев;03.03.2000;222;"
        "\"5 км Весна 2026 (vesna2026-5, кат)\";2026-04-01 09:00:00\r\n"
    )
    f = tmp_path / "leads-export.csv"
    f.write_bytes(text.encode("utf-8-sig"))

    rows = gen_sql._collect_rows([f], min_per_event=2)  # «Весна» = 1 строка → drop

    events = {(r[4], r[5]) for r in rows}
    assert ("Весна", 2026) not in events
    assert ("Жара", 2026) in events


