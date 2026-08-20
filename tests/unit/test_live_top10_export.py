"""Тесты для live_top10_export.py — сборка live-JSON топ-10 по отметкам
для трансляции Жары. TIME-поля MySQL (mysql-connector) приходят как
datetime.timedelta, не строки — см. _td_to_seconds()."""
import json
from datetime import timedelta
from unittest.mock import MagicMock, patch

from src.krasmarafon.services.live_top10_export import (
    _td_to_seconds, _seconds_to_hms, _seconds_to_pace_str, _format_gap,
    _sex_code, _format_distance_label, _forecast_finish_seconds,
)


def test_td_to_seconds_converts_timedelta():
    assert _td_to_seconds(timedelta(hours=1, minutes=2, seconds=3)) == 3723.0


def test_td_to_seconds_none_for_none():
    assert _td_to_seconds(None) is None


def test_seconds_to_hms_formats_with_leading_zeros():
    assert _seconds_to_hms(3723) == "01:02:03"


def test_seconds_to_hms_under_an_hour():
    assert _seconds_to_hms(125) == "00:02:05"


def test_seconds_to_pace_str_mmss():
    assert _seconds_to_pace_str(349) == "5:49"


def test_format_gap_leader_is_zero():
    assert _format_gap(0) == "Лидер"


def test_format_gap_negative_treated_as_leader():
    """Защита от округления/погрешности — небольшая отрицательная разница
    (сам лидер, сравнение с самим собой) не должна давать "-00:00"."""
    assert _format_gap(-0.4) == "Лидер"


def test_format_gap_under_an_hour():
    assert _format_gap(18) == "+00:18"


def test_format_gap_over_an_hour():
    assert _format_gap(3725) == "+01:02:05"


def test_sex_code_male():
    assert _sex_code("Мужчина") == "M"


def test_sex_code_female():
    assert _sex_code("Женщина") == "F"


def test_format_distance_label_drops_trailing_zero():
    assert _format_distance_label(5.0) == "5 км"


def test_format_distance_label_keeps_decimal():
    assert _format_distance_label(21.1) == "21.1 км"


def test_forecast_finish_seconds_extrapolates_remaining_distance():
    # elapsed 1:10:00 = 4200с, темп 5:00/км = 300с/км, осталось 1.1 км
    assert _forecast_finish_seconds(4200.0, 300.0, 1.1) == 4530.0


def test_forecast_finish_seconds_none_pace_returns_none():
    """Темп неизвестен — прогноз невозможен, не 0 (явно отличимо от
    "прогноз совпадает с текущим временем")."""
    assert _forecast_finish_seconds(4200.0, None, 1.1) is None


def test_forecast_finish_seconds_zero_remaining_returns_elapsed():
    assert _forecast_finish_seconds(4200.0, 300.0, 0.0) == 4200.0


def test_forecast_finish_seconds_negative_remaining_does_not_raise():
    """checkpoint_distances может содержать небольшую неточность —
    формула не должна падать, просто даёт прогноз чуть меньше текущего
    времени на КТ (не вводит в заблуждение при таких малых величинах)."""
    assert _forecast_finish_seconds(4200.0, 300.0, -0.5) == 4050.0


from src.krasmarafon.services.live_top10_export import _build_checkpoint


def _row(start_number, surname, sex, city, rank_abs, rank_sex, time_str, pace_str):
    h, m, s = map(int, time_str.split(':'))
    ph, pm = map(int, pace_str.split(':'))
    return {
        "start_number": start_number, "surname": surname, "name": "Тест", "sex": sex,
        "city": city, "rank_absolute": rank_abs, "rank_sex": rank_sex,
        "time_clear": timedelta(hours=h, minutes=m, seconds=s),
        "pace_avg": timedelta(minutes=ph, seconds=pm),
    }


def test_build_checkpoint_splits_absolute_and_sex_with_shared_row_shape():
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value = cur

    abs_rows = [
        _row(10, "Иванов", "Мужчина", "Красноярск", 1, 1, "00:14:14", "5:41"),
        _row(20, "Петрова", "Женщина", "Москва", 2, 1, "00:14:32", "5:49"),
    ]
    male_rows = [abs_rows[0]]
    female_rows = [abs_rows[1]]
    # Порядок вызовов внутри _build_checkpoint: абсолют, мужчины, женщины
    cur.fetchall.side_effect = [abs_rows, male_rows, female_rows]

    photo_map = {10: "https://example.com/ivanov.jpg"}

    checkpoint = _build_checkpoint(
        conn, event_id=116, code="kt1", label="КТ1 (6.0 км)",
        time_col="time_clear_kt1", rank_abs_col="rank_absolute_kt1",
        rank_sex_col="rank_sex_kt1", pace_col="pace_avg_kt1",
        photo_map=photo_map,
    )

    assert checkpoint["code"] == "kt1"
    assert len(checkpoint["top10_absolute"]) == 2
    assert checkpoint["top10_absolute"][0]["gap_absolute"] == "Лидер"
    assert checkpoint["top10_absolute"][1]["gap_absolute"] == "+00:18"
    # Петрова — лидер СВОЕГО пола (единственная женщина в списке), хотя
    # вторая по абсолюту
    assert checkpoint["top10_absolute"][1]["gap_sex"] == "Лидер"
    assert checkpoint["top10_absolute"][0]["photo_url"] == "https://example.com/ivanov.jpg"
    assert checkpoint["top10_absolute"][1]["photo_url"] == (
        "https://results.krasmarafon.ru/static/images/krasmarafon/participant-placeholder.png"
    )
    assert checkpoint["top10_absolute"][0]["sex"] == "M"
    assert checkpoint["top10_absolute"][1]["sex"] == "F"

    # Проверка не только результата, но и того, что _build_checkpoint
    # реально передал правильные sex_filter в запросы к _query_checkpoint_rows
    # (без этого перепутанные местами фильтры остались бы незамеченными —
    # порядок вызовов сохранился бы, а данные внутри были бы неверными).
    execute_calls = cur.execute.call_args_list
    assert len(execute_calls) == 3
    abs_params = execute_calls[0].args[1]
    male_params = execute_calls[1].args[1]
    female_params = execute_calls[2].args[1]
    assert list(abs_params) == [116]
    assert list(male_params) == [116, "Мужчина"]
    assert list(female_params) == [116, "Женщина"]


def test_build_checkpoint_truncates_below_ten_without_padding():
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value = cur
    three_rows = [_row(i, f"Участник{i}", "Мужчина", "Красноярск", i, i, "00:10:0" + str(i), "4:0" + str(i)) for i in range(1, 4)]
    cur.fetchall.side_effect = [three_rows, three_rows, []]

    checkpoint = _build_checkpoint(
        conn, event_id=116, code="finish", label="Финиш",
        time_col="time_clear_finish", rank_abs_col="rank_absolute_clean",
        rank_sex_col="rank_sex_clean", pace_col="finish_pace_avg_clean",
        photo_map={},
    )

    assert len(checkpoint["top10_absolute"]) == 3
    assert checkpoint["top10_female"] == []


from src.krasmarafon.services import live_top10_export
from src.krasmarafon.services.live_top10_export import generate_top10_json


def test_generate_top10_json_writes_atomic_file_with_all_checkpoints(tmp_path, monkeypatch):
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value = cur
    # 1-й fetchone — событие; 1-й fetchall — фото (пусто)
    cur.fetchone.return_value = {
        "event_name": "Жара", "event_distance": 5.0, "event_year": 2026,
        "checkpoint_distances": "[0, 2.5, 5.0]",
    }
    cur.fetchall.return_value = []

    calls = []

    def fake_build_checkpoint(connection, event_id, code, label, **kwargs):
        calls.append(code)
        return {"code": code, "label": label, "top10_absolute": [], "top10_male": [], "top10_female": []}

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
    cur.fetchall.return_value = []

    def fake_build_checkpoint(connection, event_id, code, label, **kwargs):
        return {"code": code, "label": label, "top10_absolute": [], "top10_male": [], "top10_female": []}

    monkeypatch.setattr(live_top10_export, "_build_checkpoint", fake_build_checkpoint)

    nested_path = str(tmp_path / "nested" / "dir" / "zhara_top10.json")
    generate_top10_json(conn, event_id=135, output_path=nested_path)

    assert (tmp_path / "nested" / "dir" / "zhara_top10.json").exists()
