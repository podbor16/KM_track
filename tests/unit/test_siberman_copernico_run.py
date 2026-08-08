import datetime
from unittest.mock import patch, MagicMock

from src.siberman.copernico_run import (
    _fmt_km, _lap_fields, _parse_copernico_elapsed_ms, apply_copernico_snapshot,
)

CFG = {
    "fields": {"bib": "dorsal", "gender": "gender", "category": "category", "status": "status"},
    "relay": {"category_value": "Эстафета"},
    "laps": {
        "count": 12,
        "lap_km": 7.0,
        "boundary_field_pattern": "times.official_{km}km",
        "submark_field_pattern": "times.official_{km}km",
        "finish_field": "times.official_:::finish:::",
    },
}


def test_fmt_km_integer_vs_half():
    assert _fmt_km(7.0) == "7"
    assert _fmt_km(6.5) == "6.5"
    assert _fmt_km(83.5) == "83.5"


def test_lap_fields_matches_real_copernico_field_names():
    fields = _lap_fields(CFG)
    assert len(fields) == 24
    d = dict(fields)
    # Круговые (подтверждено живым fetch 2026-08-05)
    assert d[1] == "times.official_7km"
    assert d[2] == "times.official_14km"
    assert d[12] == "times.official_:::finish:::"  # 12-й круг — спец-поле, не "84km"
    # Субметки "-500м до круга" (seq 101..112)
    assert d[101] == "times.official_6.5km"
    assert d[102] == "times.official_13.5km"
    assert d[112] == "times.official_83.5km"


def test_parse_copernico_elapsed_ms_accepts_int_and_numeric_string():
    # Реальный пример живого fetch 2026-08-08: 1895002мс = ~31.6 минуты бега.
    assert _parse_copernico_elapsed_ms(1895002) == 1895002
    assert _parse_copernico_elapsed_ms("1895002") == 1895002


def test_parse_copernico_elapsed_ms_none_and_garbage():
    assert _parse_copernico_elapsed_ms(None) is None
    assert _parse_copernico_elapsed_ms("") is None
    assert _parse_copernico_elapsed_ms("not-a-number") is None
    # Формат, который раньше ошибочно предполагался (ISO8601) — тоже не число.
    assert _parse_copernico_elapsed_ms("2026-08-08T01:30:00.988Z") is None


def _mk_conn():
    return MagicMock()


@patch("src.siberman.copernico_run.get_copernico_run_enabled", return_value=True)
@patch("src.siberman.copernico_run.recompute_totals_ranks_records")
@patch("src.siberman.copernico_run.get_checkpoint_times_for_year", return_value=({}, {}))
@patch("src.siberman.copernico_run.get_participants_for_year")
@patch("src.siberman.copernico_run.get_checkpoints")
@patch("src.siberman.copernico_run.get_stage_starts")
@patch("src.siberman.copernico_run.upsert_checkpoint_time")
@patch("src.siberman.copernico_run.update_participant_status")
def test_apply_snapshot_individual_writes_checkpoint_and_computes_cumulative_from_run_start(
    mock_update_status, mock_upsert_cp, mock_stage_starts, mock_checkpoints, mock_participants,
    mock_cp_times, mock_recompute, mock_run_enabled,
):
    run_start = datetime.datetime(2026, 8, 8, 8, 30, 0)
    mock_stage_starts.return_value = {"run_start": run_start, "bike2_start": None}
    mock_checkpoints.return_value = [
        {"stage": "run", "seq": 1, "id": 5001},
        {"stage": "run", "seq": 101, "id": 5101},
    ]
    mock_participants.return_value = [
        {"id": 900, "bib": "156", "relay_stage": "none", "status": "active", "dnf_stage": None},
    ]
    runners = [{
        # times.official_* — целые миллисекунды от старта забега, не ISO8601
        # (см. _parse_copernico_elapsed_ms) — 600000мс = 600с = 10 мин.
        "dorsal": 156, "category": "Мужчины", "status": "running",
        "times.official_7km": 600000,
    }]

    result = apply_copernico_snapshot(_mk_conn(), 2026, runners, CFG)

    assert result["ok"] is True
    assert result["skipped"] == 0
    calls_by_checkpoint = {c.args[2]: c.args for c in mock_upsert_cp.call_args_list}
    assert calls_by_checkpoint[5001][1] == 900   # participant_id
    assert calls_by_checkpoint[5001][3] == 600   # cumulative_s
    mock_recompute.assert_called_once()


@patch("src.siberman.copernico_run.get_copernico_run_enabled", return_value=True)
@patch("src.siberman.copernico_run.recompute_totals_ranks_records")
@patch("src.siberman.copernico_run.get_checkpoint_times_for_year", return_value=({}, {}))
@patch("src.siberman.copernico_run.get_participants_for_year")
@patch("src.siberman.copernico_run.get_checkpoints")
@patch("src.siberman.copernico_run.get_stage_starts")
@patch("src.siberman.copernico_run.upsert_checkpoint_time")
@patch("src.siberman.copernico_run.update_participant_status")
def test_apply_snapshot_computes_split_s_from_consecutive_laps(
    mock_update_status, mock_upsert_cp, mock_stage_starts, mock_checkpoints, mock_participants,
    mock_cp_times, mock_recompute, mock_run_enabled,
):
    """Регрессия 2026-08-08: split_s писался как None на каждом опросе, а
    upsert_checkpoint_time затирает им уже посчитанное значение
    (ON DUPLICATE KEY UPDATE split_s=VALUES(split_s)) — график "Темп/
    скорость" на вкладке "Бег" оставался пустым весь этап, хотя
    cumulative_s (время/место) писались верно."""
    run_start = datetime.datetime(2026, 8, 8, 8, 30, 0)
    mock_stage_starts.return_value = {"run_start": run_start, "bike2_start": None}
    mock_checkpoints.return_value = [
        {"stage": "run", "seq": 1, "id": 5001},
        {"stage": "run", "seq": 2, "id": 5002},
        {"stage": "run", "seq": 101, "id": 5101},
    ]
    mock_participants.return_value = [
        {"id": 900, "bib": "156", "relay_stage": "none", "status": "active", "dnf_stage": None},
    ]
    runners = [{
        "dorsal": 156, "category": "Мужчины", "status": "running",
        "times.official_7km": 600000,   # 600с — 1 круг
        "times.official_14km": 1350000,  # 1350с — 2 круга (сплит 2 круга = 750с)
    }]

    apply_copernico_snapshot(_mk_conn(), 2026, runners, CFG)

    calls_by_checkpoint = {c.args[2]: c.args for c in mock_upsert_cp.call_args_list}
    assert calls_by_checkpoint[5001][3] == 600   # cumulative_s круг 1
    assert calls_by_checkpoint[5001][4] == 600   # split_s круг 1 = cumulative (первый круг)
    assert calls_by_checkpoint[5002][3] == 1350  # cumulative_s круг 2
    assert calls_by_checkpoint[5002][4] == 750   # split_s круг 2 = 1350 - 600
    # Субметка "-500м до круга" — не участвует в графике темпа, split_s не нужен.
    assert calls_by_checkpoint[5101][4] is None


@patch("src.siberman.copernico_run.get_copernico_run_enabled", return_value=True)
@patch("src.siberman.copernico_run.recompute_totals_ranks_records")
@patch("src.siberman.copernico_run.get_checkpoint_times_for_year", return_value=({}, {}))
@patch("src.siberman.copernico_run.get_participants_for_year")
@patch("src.siberman.copernico_run.get_checkpoints")
@patch("src.siberman.copernico_run.get_stage_starts")
@patch("src.siberman.copernico_run.upsert_checkpoint_time")
@patch("src.siberman.copernico_run.update_participant_status")
def test_apply_snapshot_relay_runner_matched_by_bib_and_relay_stage_run(
    mock_update_status, mock_upsert_cp, mock_stage_starts, mock_checkpoints, mock_participants,
    mock_cp_times, mock_recompute, mock_run_enabled,
):
    # Реальный пример из живого fetch: surname=название команды, name=ФИО
    # бегуна целиком — идентичность участника берётся из УЖЕ существующей
    # записи в Siberman БД (по bib+relay_stage='run'), Copernico только
    # дополняет времена, имя из Copernico не используется вовсе.
    mock_stage_starts.return_value = {"run_start": datetime.datetime(2026, 8, 8, 8, 30, 0), "bike2_start": None}
    mock_checkpoints.return_value = [{"stage": "run", "seq": 1, "id": 5001}]
    mock_participants.return_value = [
        {"id": 1906, "bib": "1053", "relay_stage": "run", "status": "active", "dnf_stage": None},
    ]
    runners = [{
        "dorsal": 1053, "surname": "Раф и его лаванда", "name": "Паремузян Рафаэл",
        "category": "Эстафета", "status": "notstarted",
    }]

    result = apply_copernico_snapshot(_mk_conn(), 2026, runners, CFG)

    assert result["skipped"] == 0
    mock_recompute.assert_called_once()


@patch("src.siberman.copernico_run.get_copernico_run_enabled", return_value=True)
@patch("src.siberman.copernico_run.recompute_totals_ranks_records")
@patch("src.siberman.copernico_run.get_checkpoint_times_for_year", return_value=({}, {}))
@patch("src.siberman.copernico_run.get_participants_for_year")
@patch("src.siberman.copernico_run.get_checkpoints")
@patch("src.siberman.copernico_run.get_stage_starts")
@patch("src.siberman.copernico_run.upsert_checkpoint_time")
@patch("src.siberman.copernico_run.update_participant_status")
def test_apply_snapshot_unknown_bib_is_skipped_not_fatal(
    mock_update_status, mock_upsert_cp, mock_stage_starts, mock_checkpoints, mock_participants,
    mock_cp_times, mock_recompute, mock_run_enabled,
):
    mock_stage_starts.return_value = {"run_start": datetime.datetime(2026, 8, 8, 8, 30, 0), "bike2_start": None}
    mock_checkpoints.return_value = [{"stage": "run", "seq": 1, "id": 5001}]
    mock_participants.return_value = []  # никого нет в БД
    runners = [{"dorsal": 999, "category": "Мужчины", "status": "notstarted"}]

    result = apply_copernico_snapshot(_mk_conn(), 2026, runners, CFG)

    assert result["ok"] is True
    assert result["skipped"] == 1
    mock_upsert_cp.assert_not_called()


@patch("src.siberman.copernico_run.get_copernico_run_enabled", return_value=True)
@patch("src.siberman.copernico_run.recompute_totals_ranks_records")
@patch("src.siberman.copernico_run.get_checkpoint_times_for_year", return_value=({}, {}))
@patch("src.siberman.copernico_run.get_participants_for_year")
@patch("src.siberman.copernico_run.get_checkpoints")
@patch("src.siberman.copernico_run.get_stage_starts")
@patch("src.siberman.copernico_run.upsert_checkpoint_time")
@patch("src.siberman.copernico_run.update_participant_status")
def test_apply_snapshot_dnf_status_maps_to_dnf_run_and_updates(
    mock_update_status, mock_upsert_cp, mock_stage_starts, mock_checkpoints, mock_participants,
    mock_cp_times, mock_recompute, mock_run_enabled,
):
    mock_stage_starts.return_value = {"run_start": datetime.datetime(2026, 8, 8, 8, 30, 0), "bike2_start": None}
    mock_checkpoints.return_value = [{"stage": "run", "seq": 1, "id": 5001}]
    mock_participants.return_value = [
        {"id": 900, "bib": "156", "relay_stage": "none", "status": "active", "dnf_stage": None},
    ]
    runners = [{"dorsal": 156, "category": "Мужчины", "status": "dnf"}]

    apply_copernico_snapshot(_mk_conn(), 2026, runners, CFG)

    mock_update_status.assert_called_once()
    call_args = mock_update_status.call_args[0]
    assert call_args[1] == 900
    assert call_args[2] == "dnf"
    assert call_args[3] == "run"


@patch("src.siberman.copernico_run.get_copernico_run_enabled", return_value=True)
@patch("src.siberman.copernico_run.recompute_totals_ranks_records")
@patch("src.siberman.copernico_run.get_checkpoint_times_for_year", return_value=({}, {}))
@patch("src.siberman.copernico_run.get_participants_for_year")
@patch("src.siberman.copernico_run.get_checkpoints")
@patch("src.siberman.copernico_run.get_stage_starts")
@patch("src.siberman.copernico_run.upsert_checkpoint_time")
@patch("src.siberman.copernico_run.update_participant_status")
def test_apply_snapshot_does_not_clear_dnf_from_earlier_stage_when_run_status_is_notstarted(
    mock_update_status, mock_upsert_cp, mock_stage_starts, mock_checkpoints, mock_participants,
    mock_cp_times, mock_recompute, mock_run_enabled,
):
    """Регрессия 2026-08-08: Copernico отдаёт статус ТОЛЬКО по бегу —
    "notstarted" для всех, кто ещё не финишировал бег, в т.ч. для тех, кто
    сошёл на плавании/вело. Такой снапшот не должен затирать уже
    проставленный dnf/dsq обратно в active."""
    mock_stage_starts.return_value = {"run_start": datetime.datetime(2026, 8, 8, 8, 30, 0), "bike2_start": None}
    mock_checkpoints.return_value = [{"stage": "run", "seq": 1, "id": 5001}]
    mock_participants.return_value = [
        {"id": 900, "bib": "156", "relay_stage": "none", "status": "dnf", "dnf_stage": "bike_day1"},
    ]
    runners = [{"dorsal": 156, "category": "Мужчины", "status": "notstarted"}]

    apply_copernico_snapshot(_mk_conn(), 2026, runners, CFG)

    mock_update_status.assert_not_called()


@patch("src.siberman.copernico_run.get_copernico_run_enabled", return_value=True)
@patch("src.siberman.copernico_run.recompute_totals_ranks_records")
@patch("src.siberman.copernico_run.get_checkpoint_times_for_year", return_value=({}, {}))
@patch("src.siberman.copernico_run.get_participants_for_year")
@patch("src.siberman.copernico_run.get_checkpoints")
@patch("src.siberman.copernico_run.get_stage_starts")
@patch("src.siberman.copernico_run.upsert_checkpoint_time")
@patch("src.siberman.copernico_run.update_participant_status")
def test_apply_snapshot_no_run_start_configured_returns_error_without_writes(
    mock_update_status, mock_upsert_cp, mock_stage_starts, mock_checkpoints, mock_participants,
    mock_cp_times, mock_recompute, mock_run_enabled,
):
    mock_stage_starts.return_value = {"run_start": None, "bike2_start": None}

    result = apply_copernico_snapshot(_mk_conn(), 2026, [{"dorsal": 156}], CFG)

    assert result["ok"] is False
    mock_upsert_cp.assert_not_called()
    mock_recompute.assert_not_called()


@patch("src.siberman.copernico_run.get_copernico_run_enabled", return_value=False)
@patch("src.siberman.copernico_run.recompute_totals_ranks_records")
@patch("src.siberman.copernico_run.get_checkpoint_times_for_year", return_value=({}, {}))
@patch("src.siberman.copernico_run.get_participants_for_year")
@patch("src.siberman.copernico_run.get_checkpoints")
@patch("src.siberman.copernico_run.get_stage_starts")
@patch("src.siberman.copernico_run.upsert_checkpoint_time")
@patch("src.siberman.copernico_run.update_participant_status")
def test_apply_snapshot_disabled_in_admin_skips_writes_without_touching_run_start(
    mock_update_status, mock_upsert_cp, mock_stage_starts, mock_checkpoints, mock_participants,
    mock_cp_times, mock_recompute, mock_run_enabled,
):
    # Админский тумблер выключен — поллер продолжает опрашивать Copernico,
    # но apply_copernico_snapshot ничего не пишет и не трогает даже
    # get_stage_starts (флаг проверяется РАНЬШЕ любых остальных чтений).
    result = apply_copernico_snapshot(_mk_conn(), 2026, [{"dorsal": 156, "category": "Мужчины"}], CFG)

    assert result == {"ok": True, "enabled": False, "checkpoint_writes": 0, "status_updates": 0, "skipped": 0}
    mock_stage_starts.assert_not_called()
    mock_upsert_cp.assert_not_called()
    mock_update_status.assert_not_called()
    mock_recompute.assert_not_called()
