"""Тесты для live_top10_export.py — сборка live-JSON топ-3 (муж/жен) по
отметкам для трансляции Жары. TIME-поля MySQL (mysql-connector) приходят
как datetime.timedelta, не строки — см. _td_to_seconds()."""
import json
from datetime import timedelta
from unittest.mock import MagicMock

from src.krasmarafon.services.live_top10_export import (
    _td_to_seconds, _seconds_to_time_str, _format_distance_label, _build_checkpoint,
)


def test_td_to_seconds_converts_timedelta():
    assert _td_to_seconds(timedelta(hours=1, minutes=2, seconds=3)) == 3723.0


def test_td_to_seconds_none_for_none():
    assert _td_to_seconds(None) is None


def test_seconds_to_time_str_hour_and_above_hms():
    assert _seconds_to_time_str(3723) == "1:02:03"


def test_seconds_to_time_str_under_an_hour_ms():
    assert _seconds_to_time_str(125) == "2:05"


def test_format_distance_label_drops_trailing_zero():
    assert _format_distance_label(5.0) == "5 км"


def test_format_distance_label_keeps_decimal():
    assert _format_distance_label(21.1) == "21.1 км"


def _row(surname, time_str):
    h, m, s = map(int, time_str.split(':'))
    return {"surname": surname, "name": "Тест", "time_clear": timedelta(hours=h, minutes=m, seconds=s)}


def test_build_checkpoint_returns_only_full_name_and_time():
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value = cur
    male_rows = [_row("Иванов", "00:14:14")]
    female_rows = [_row("Петрова", "00:14:32")]
    # Порядок вызовов внутри _build_checkpoint: мужчины, женщины
    cur.fetchall.side_effect = [male_rows, female_rows]

    checkpoint = _build_checkpoint(
        conn, event_id=116, code="kt1", label="КТ1 (6.0 км)", time_col="time_clear_kt1",
    )

    assert checkpoint == {
        "code": "kt1",
        "label": "КТ1 (6.0 км)",
        "top3_male": [{"full_name": "Иванов Тест", "time": "14:14"}],
        "top3_female": [{"full_name": "Петрова Тест", "time": "14:32"}],
    }


def test_build_checkpoint_passes_correct_sex_filter_to_each_query():
    """Проверка не только результата, но и того, что _build_checkpoint
    реально передал правильный sex-фильтр в SQL — без этого перепутанные
    местами мужской/женский запросы остались бы незамеченными (порядок
    вызовов сохранился бы, а данные внутри были бы неверными)."""
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value = cur
    cur.fetchall.side_effect = [[], []]

    _build_checkpoint(conn, event_id=116, code="finish", label="Финиш", time_col="time_clear_finish")

    execute_calls = cur.execute.call_args_list
    assert len(execute_calls) == 2
    assert tuple(execute_calls[0].args[1]) == (116, "Мужчина")
    assert tuple(execute_calls[1].args[1]) == (116, "Женщина")


def test_build_checkpoint_empty_when_no_finishers_of_that_sex():
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value = cur
    cur.fetchall.side_effect = [[_row("Иванов", "00:10:01")], []]

    checkpoint = _build_checkpoint(
        conn, event_id=116, code="finish", label="Финиш", time_col="time_clear_finish",
    )

    assert len(checkpoint["top3_male"]) == 1
    assert checkpoint["top3_female"] == []


from src.krasmarafon.services import live_top10_export
from src.krasmarafon.services.live_top10_export import generate_top10_json


def _fake_checkpoint(code, label):
    return {"code": code, "label": label, "top3_male": [], "top3_female": []}


def test_generate_top10_json_writes_atomic_file_with_all_checkpoints(tmp_path, monkeypatch):
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value = cur
    cur.fetchone.return_value = {
        "event_name": "Жара", "event_distance": 5.0, "event_year": 2026,
        "checkpoint_distances": "[0, 2.5, 5.0]",
    }

    calls = []

    def fake_build_checkpoint(connection, event_id, code, label, **kwargs):
        calls.append(code)
        return _fake_checkpoint(code, label)

    monkeypatch.setattr(live_top10_export, "_build_checkpoint", fake_build_checkpoint)

    output_path = str(tmp_path / "zhara_5km_top10.json")
    generate_top10_json(conn, event_id=115, output_path=output_path)

    assert calls == ["kt1", "finish"], "5 км: 1 промежуточная КТ + финиш"
    assert not (tmp_path / "zhara_5km_top10.json.tmp").exists(), "временный файл должен быть переименован, не остаться"

    with open(output_path, encoding="utf-8") as f:
        data = json.load(f)
    assert data["event_name"] == "Жара"
    assert data["distance"] == "5 км"
    assert len(data["checkpoints"]) == 2
    assert data["checkpoints"][0]["code"] == "kt1"
    assert data["checkpoints"][1]["code"] == "finish"


def test_generate_top10_json_creates_parent_directory(tmp_path, monkeypatch):
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value = cur
    cur.fetchone.return_value = {
        "event_name": "Жара", "event_distance": 2.0, "event_year": 2026,
        "checkpoint_distances": None,
    }

    monkeypatch.setattr(
        live_top10_export, "_build_checkpoint",
        lambda connection, event_id, code, label, **kwargs: _fake_checkpoint(code, label),
    )

    nested_path = str(tmp_path / "nested" / "dir" / "zhara_top10.json")
    generate_top10_json(conn, event_id=135, output_path=nested_path)

    assert (tmp_path / "nested" / "dir" / "zhara_top10.json").exists()


def test_generate_top10_json_builds_checkpoint_for_every_intermediate_kt(tmp_path, monkeypatch):
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value = cur
    cur.fetchone.return_value = {
        "event_name": "Жара", "event_distance": 21.1, "event_year": 2026,
        "checkpoint_distances": "[0, 5.0, 6.0, 10.55, 14.65, 15.65, 20.2, 21.1]",
    }

    captured_time_cols = {}

    def fake_build_checkpoint(connection, event_id, code, label, time_col, **kwargs):
        captured_time_cols[code] = time_col
        return _fake_checkpoint(code, label)

    monkeypatch.setattr(live_top10_export, "_build_checkpoint", fake_build_checkpoint)

    output_path = str(tmp_path / "zhara_21km_top10.json")
    generate_top10_json(conn, event_id=116, output_path=output_path)

    assert list(captured_time_cols.keys()) == ["kt1", "kt2", "kt3", "kt4", "kt5", "kt6", "finish"]
    assert captured_time_cols["kt1"] == "time_clear_kt1"
    assert captured_time_cols["finish"] == "time_clear_finish"
