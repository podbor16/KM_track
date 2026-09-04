from src.duathlon222.service import (
    _stage_times, _speed_kmh, _current_stage, _forecast_stage_finish,
    _lap_ranks_from_rows, _build_stage_laps,
    _distance_covered_km, _display_status, _rank_standings_rows,
    _forecast_race_finish, _speed_kmh_for_distance,
    _stage_start_s, _frontier_lap,
    _lap_distance_km, _lap_split_distance_km,
    _global_km, _live_gap_map,
)


def test_lap_distance_km_run1_uniform_no_offset():
    # Реальные отметки Copernico: 1.25, 2.5, 3.75, 5, 6.25, 7.5, 8.75, 9.98
    assert _lap_distance_km("run1", 1) == 1.25
    assert _lap_distance_km("run1", 4) == 5.0
    assert _lap_distance_km("run1", 8) == 10.0


def test_lap_distance_km_bike_first_lap_shorter_prologue():
    # Реальные отметки Copernico: b3,4 / b7,44 / b11,48 ... — первая короче
    # полного круга (3.4 не 4.04), см. STAGE_LAP_OFFSET.
    assert _lap_distance_km("bike", 1) == 3.4
    assert round(_lap_distance_km("bike", 2), 2) == 7.44
    assert round(_lap_distance_km("bike", 42), 2) == 169.04


def test_lap_distance_km_none_lap_number_is_zero():
    assert _lap_distance_km("run1", None) == 0.0


def test_lap_split_distance_km_bike_first_lap_is_the_prologue():
    assert _lap_split_distance_km("bike", 1) == 3.4


def test_lap_split_distance_km_bike_later_laps_is_constant_step():
    assert _lap_split_distance_km("bike", 2) == 4.04
    assert _lap_split_distance_km("bike", 42) == 4.04


def test_stage_start_s_run1_is_always_zero():
    assert _stage_start_s("run1", None, None, None, None) == 0


def test_stage_start_s_bike_is_run1_plus_t1():
    assert _stage_start_s("bike", 2400, 60, None, None) == 2460


def test_stage_start_s_bike_none_when_run1_not_finished():
    assert _stage_start_s("bike", None, None, None, None) is None


def test_stage_start_s_run2_is_bike_plus_t2():
    assert _stage_start_s("run2", 2400, 60, 22800, 90) == 22890


def test_stage_start_s_run2_none_when_bike_not_finished():
    assert _stage_start_s("run2", 2400, 60, None, None) is None


def test_frontier_lap_returns_max():
    assert _frontier_lap([1, 3, 2]) == 3


def test_frontier_lap_none_when_empty():
    assert _frontier_lap([]) is None


def test_speed_kmh_for_distance_basic():
    assert _speed_kmh_for_distance(10.0, 3600) == 10.0


def test_speed_kmh_for_distance_none_when_no_elapsed():
    assert _speed_kmh_for_distance(10.0, None) is None
    assert _speed_kmh_for_distance(10.0, 0) is None


def test_speed_kmh_for_distance_none_when_no_distance():
    assert _speed_kmh_for_distance(0, 3600) is None


def test_stage_times_all_finished():
    run1, bike, run2 = _stage_times(2400, None, 22800, None, 40800)
    assert run1 == 2400
    assert bike == 20400
    assert run2 == 18000


def test_stage_times_only_run1_done():
    run1, bike, run2 = _stage_times(2400, None, None, None, None)
    assert run1 == 2400
    assert bike is None
    assert run2 is None


def test_stage_times_run1_and_bike_done():
    run1, bike, run2 = _stage_times(2400, None, 22800, None, None)
    assert run1 == 2400
    assert bike == 20400
    assert run2 is None


def test_stage_times_nothing_done():
    run1, bike, run2 = _stage_times(None, None, None, None, None)
    assert run1 is None
    assert bike is None
    assert run2 is None


def test_stage_times_subtracts_known_transitions():
    # Т1=300с, Т2=200с — эти секунды не должны попадать во время этапа
    run1, bike, run2 = _stage_times(2400, 300, 22800, 200, 40800)
    assert run1 == 2400
    assert bike == 22800 - 2400 - 300
    assert run2 == 40800 - 22800 - 200


def test_speed_kmh_run1_25_min_for_10km():
    assert _speed_kmh("run1", 1500) == 24.0


def test_speed_kmh_none_when_no_time():
    assert _speed_kmh("bike", None) is None
    assert _speed_kmh("bike", 0) is None


def test_current_stage_not_started_defaults_to_run1():
    stage, start_s = _current_stage(None, None, None, None, None)
    assert stage == "run1"
    assert start_s == 0


def test_current_stage_on_bike():
    stage, start_s = _current_stage(2400, None, None, None, None)
    assert stage == "bike"
    assert start_s == 2400


def test_current_stage_on_bike_accounts_for_t1():
    # Вело реально начинается ПОСЛЕ транзита, не сразу на финише бег-1
    stage, start_s = _current_stage(2400, 300, None, None, None)
    assert stage == "bike"
    assert start_s == 2700


def test_current_stage_on_run2():
    stage, start_s = _current_stage(2400, None, 22800, None, None)
    assert stage == "run2"
    assert start_s == 22800


def test_current_stage_on_run2_accounts_for_t2():
    stage, start_s = _current_stage(2400, None, 22800, 200, None)
    assert stage == "run2"
    assert start_s == 23000


def test_current_stage_finished():
    stage, start_s = _current_stage(2400, None, 22800, None, 40800)
    assert stage == "finished"
    assert start_s is None


def test_forecast_stage_finish_full_stage_ratio_one():
    # 8 из 8 отметок бег-1 (все 10 км, шаг 1.25км) за 2400с -> прогноз = факт
    assert _forecast_stage_finish("run1", 8, 2400, 0) == 2400


def test_forecast_stage_finish_partial_progress():
    # 2 из 8 отметок бег-1 (2.5 км из 10, шаг 1.25км) за 1000с -> прогноз 4000с
    assert _forecast_stage_finish("run1", 2, 1000, 0) == 4000


def test_forecast_stage_finish_with_nonzero_stage_start():
    # Этап начался на 2400с от общего старта (конец бег-1); на вело прошло
    # 2 отметки за 1000с внутри этапа. Реальная дистанция 2-й отметки —
    # 7.44км (не 8.08 = 2*4.04 — первая отметка Вело короче полного круга,
    # см. STAGE_LAP_OFFSET), экстраполяция на 170 км от неё.
    forecast = _forecast_stage_finish("bike", 2, 2400 + 1000, 2400)
    expected_stage_s = 1000 * (170.0 / 7.44)
    assert forecast == round(2400 + expected_stage_s)


def test_forecast_stage_finish_no_lap_data_returns_none():
    assert _forecast_stage_finish("run1", None, None, 0) is None


def test_forecast_stage_finish_zero_lap_returns_none():
    assert _forecast_stage_finish("run1", 0, 500, 0) is None


def test_lap_ranks_abs_and_gender():
    rows = [
        {"participant_id": 1, "stage": "run1", "lap_number": 1, "cumulative_s": 500, "gender": "M"},
        {"participant_id": 2, "stage": "run1", "lap_number": 1, "cumulative_s": 520, "gender": "M"},
        {"participant_id": 3, "stage": "run1", "lap_number": 1, "cumulative_s": 510, "gender": "F"},
    ]
    ranks = _lap_ranks_from_rows(rows)

    assert ranks[(1, "run1", 1)] == {"rank_abs": 1, "gap_abs": 0, "rank_gender": 1, "gap_gender": 0}
    assert ranks[(3, "run1", 1)] == {"rank_abs": 2, "gap_abs": 10, "rank_gender": 1, "gap_gender": 0}
    assert ranks[(2, "run1", 1)] == {"rank_abs": 3, "gap_abs": 20, "rank_gender": 2, "gap_gender": 20}


def test_lap_ranks_separates_stages_and_laps():
    rows = [
        {"participant_id": 1, "stage": "run1", "lap_number": 1, "cumulative_s": 500, "gender": "M"},
        {"participant_id": 1, "stage": "bike", "lap_number": 1, "cumulative_s": 900, "gender": "M"},
    ]
    ranks = _lap_ranks_from_rows(rows)
    assert (1, "run1", 1) in ranks
    assert (1, "bike", 1) in ranks
    assert ranks[(1, "run1", 1)]["rank_abs"] == 1
    assert ranks[(1, "bike", 1)]["rank_abs"] == 1


def test_build_stage_laps_split_and_speed():
    lap_rows = [
        {"lap_number": 1, "cumulative_s": 500},
        {"lap_number": 2, "cumulative_s": 1050},
    ]
    laps = _build_stage_laps("run1", lap_rows, 0, {}, participant_id=1)

    assert laps[0]["lap_number"] == 1
    assert laps[0]["split_s"] == 500
    assert laps[0]["speed_kmh"] == round(1.25 / (500 / 3600.0), 2)
    assert laps[1]["split_s"] == 550
    assert laps[1]["speed_kmh"] == round(1.25 / (550 / 3600.0), 2)


def test_build_stage_laps_split_uses_stage_start_for_first_lap():
    lap_rows = [{"lap_number": 1, "cumulative_s": 2900}]
    laps = _build_stage_laps("bike", lap_rows, 2400, {}, participant_id=1)
    assert laps[0]["split_s"] == 500


def test_build_stage_laps_includes_ranks():
    lap_rows = [{"lap_number": 1, "cumulative_s": 500}]
    ranks = {(1, "run1", 1): {"rank_abs": 2, "gap_abs": 10, "rank_gender": 1, "gap_gender": 0}}
    laps = _build_stage_laps("run1", lap_rows, 0, ranks, participant_id=1)
    assert laps[0]["rank_abs"] == 2
    assert laps[0]["rank_gender"] == 1


def test_distance_covered_km_within_run1():
    assert _distance_covered_km("run1", 2) == 2.5  # шаг 1.25км (см. LAP_KM)
    assert _distance_covered_km("run1", None) == 0.0


def test_distance_covered_km_within_bike_includes_completed_run1():
    # Первая отметка Вело короче полного круга (см. STAGE_LAP_OFFSET) —
    # distance(5) = 5*4.04 + (3.4-4.04) = 19.56, реальная марка Copernico b19,56
    assert _distance_covered_km("bike", 5) == 10.0 + (5 * 4.04 + (3.4 - 4.04))


def test_distance_covered_km_within_run2_includes_completed_run1_and_bike():
    assert _distance_covered_km("run2", 3) == 10.0 + 170.0 + 3 * 1.757


def test_distance_covered_km_finished_is_full_race():
    assert _distance_covered_km("finished", None) == 222.0


def test_display_status_terminal_states_pass_through():
    assert _display_status("dnf", 50.0) == "dnf"
    assert _display_status("dsq", 0.0) == "dsq"
    assert _display_status("finished", 222.0) == "finished"


def test_display_status_derived_from_progress_not_raw_db_value():
    # Copernico для этой гонки не различает "не стартовал"/"на дистанции" —
    # оба хранятся как один и тот же raw-статус, реальный статус выводится
    # из факта прогресса (>0 км), а не из буквального значения в БД.
    assert _display_status("active", 0.0) == "notstarted"
    assert _display_status("active", 5.0) == "active"


def _row(id, distance_km, elapsed_s, is_out=False, start_number=None):
    return {
        "id": id, "start_number": start_number or id,
        "_is_out": is_out, "_distance_km": distance_km, "_elapsed_s": elapsed_s,
    }


def test_rank_standings_more_distance_ranks_first():
    # Ровно сценарий из багрепорта: один прошёл 5 км, другой 10 — второй
    # должен быть на первом месте, даже если оба ещё внутри одного этапа.
    rows = [_row(1, 5.0, 1000), _row(2, 10.0, 2000)]
    ranked = _rank_standings_rows(rows)
    assert [r["id"] for r in ranked] == [2, 1]
    assert ranked[0]["rank"] == 1
    assert ranked[1]["rank"] == 2


def test_rank_standings_zero_progress_gets_no_rank():
    rows = [_row(1, 5.0, 1000), _row(2, 0.0, 0)]
    ranked = _rank_standings_rows(rows)
    by_id = {r["id"]: r for r in ranked}
    assert by_id[1]["rank"] == 1
    assert by_id[2]["rank"] is None


def test_rank_standings_dnf_always_last_regardless_of_distance():
    # DNF прошёл БОЛЬШЕ (150км), но всё равно должен быть внизу
    rows = [_row(1, 5.0, 1000), _row(2, 150.0, 5000, is_out=True)]
    ranked = _rank_standings_rows(rows)
    assert [r["id"] for r in ranked] == [1, 2]
    assert ranked[0]["rank"] == 1
    assert ranked[1]["rank"] is None


def test_rank_standings_ties_broken_by_earlier_elapsed_time():
    rows = [_row(1, 10.0, 2000), _row(2, 10.0, 1500)]
    ranked = _rank_standings_rows(rows)
    assert [r["id"] for r in ranked] == [2, 1]


def test_forecast_race_finish_only_on_run2():
    # Прогноз финиша ГОНКИ появляется только на бег-2 (последнем этапе) —
    # на run1/bike возвращает None, даже если прогноз этапа уже посчитан.
    assert _forecast_race_finish("run1", 12345) is None
    assert _forecast_race_finish("bike", 12345) is None
    assert _forecast_race_finish("finished", 12345) is None


def test_forecast_race_finish_equals_stage_forecast_on_run2():
    # На бег-2 (последнем этапе) прогноз финиша этапа И ЕСТЬ прогноз финиша
    # гонки — префикс (бег-1+Т1+вело+Т2) уже внутри forecast_stage_finish_s.
    assert _forecast_race_finish("run2", 54321) == 54321


def test_forecast_race_finish_none_before_first_run2_lap():
    # "После первой отсечки на беге-2" — до неё forecast_stage_finish_s сам
    # уже None (см. _forecast_stage_finish), значит и прогноз гонки тоже.
    assert _forecast_race_finish("run2", None) is None


def test_global_km_run1_no_prefix():
    assert _global_km("run1", 4) == 5.0


def test_global_km_bike_adds_run1_prefix():
    # 10 км (весь бег-1) + 3.4 км (первая отметка вело, короткий "пролог")
    assert _global_km("bike", 1) == 13.4


def test_global_km_run2_adds_run1_and_bike_prefix():
    # 10 + 170 = 180 км до старта бег-2, + 1.757 км первой отметки
    assert round(_global_km("run2", 1), 3) == 181.757


def test_live_gap_map_leader_gets_zero_and_follower_interpolated():
    # Лидер (id=1) дальше всех (позиция 2), у follower (id=2) позиция 1 —
    # отставание считается ОТНОСИТЕЛЬНО значения лидера НА ТОЙ ЖЕ позиции
    # (100), а не относительно текущего значения лидера (200).
    entries = [
        {"id": 1, "status": "active", "points": [(1, 100), (2, 200)]},
        {"id": 2, "status": "active", "points": [(1, 150)]},
    ]
    gaps = _live_gap_map(entries)
    assert gaps == {1: 0, 2: 50}


def test_live_gap_map_dnf_excluded_from_pool():
    entries = [
        {"id": 1, "status": "dnf", "points": [(5, 50)]},
        {"id": 2, "status": "active", "points": [(1, 100)]},
    ]
    gaps = _live_gap_map(entries)
    assert gaps == {2: 0}


def test_live_gap_map_empty_entries_returns_empty():
    assert _live_gap_map([]) == {}


def test_live_gap_map_no_leader_history_before_position_skips_follower():
    # follower дальше в прошлом, чем САМАЯ РАННЯЯ известная точка лидера —
    # интерполировать нечем, follower остаётся без отставания (не 0/не
    # фиктивное число).
    entries = [
        {"id": 1, "status": "active", "points": [(5, 500)]},
        {"id": 2, "status": "active", "points": [(1, 10)]},
    ]
    gaps = _live_gap_map(entries)
    assert gaps[1] == 0
    assert 2 not in gaps
