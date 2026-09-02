from src.duathlon222.service import _stage_times, _speed_kmh, _current_stage, _forecast_stage_finish


def test_stage_times_all_finished():
    run1, bike, run2 = _stage_times(2400, 22800, 40800)
    assert run1 == 2400
    assert bike == 20400
    assert run2 == 18000


def test_stage_times_only_run1_done():
    run1, bike, run2 = _stage_times(2400, None, None)
    assert run1 == 2400
    assert bike is None
    assert run2 is None


def test_stage_times_run1_and_bike_done():
    run1, bike, run2 = _stage_times(2400, 22800, None)
    assert run1 == 2400
    assert bike == 20400
    assert run2 is None


def test_stage_times_nothing_done():
    run1, bike, run2 = _stage_times(None, None, None)
    assert run1 is None
    assert bike is None
    assert run2 is None


def test_speed_kmh_run1_25_min_for_10km():
    assert _speed_kmh("run1", 1500) == 24.0


def test_speed_kmh_none_when_no_time():
    assert _speed_kmh("bike", None) is None
    assert _speed_kmh("bike", 0) is None


def test_current_stage_not_started_defaults_to_run1():
    stage, start_s = _current_stage(None, None, None)
    assert stage == "run1"
    assert start_s == 0


def test_current_stage_on_bike():
    stage, start_s = _current_stage(2400, None, None)
    assert stage == "bike"
    assert start_s == 2400


def test_current_stage_on_run2():
    stage, start_s = _current_stage(2400, 22800, None)
    assert stage == "run2"
    assert start_s == 22800


def test_current_stage_finished():
    stage, start_s = _current_stage(2400, 22800, 40800)
    assert stage == "finished"
    assert start_s is None


def test_forecast_stage_finish_full_stage_ratio_one():
    # 4 из 4 кругов бег-1 (все 10 км) за 2400с -> прогноз = фактическое время
    assert _forecast_stage_finish("run1", 4, 2400, 0) == 2400


def test_forecast_stage_finish_partial_progress():
    # 2 из 4 кругов бег-1 (5 км из 10) за 1000с -> прогноз 2000с на весь этап
    assert _forecast_stage_finish("run1", 2, 1000, 0) == 2000


def test_forecast_stage_finish_with_nonzero_stage_start():
    # Этап начался на 2400с от общего старта (конец бег-1); на вело прошло
    # 2 круга (8.08 км) за 1000с внутри этапа -> экстраполяция на 170 км
    forecast = _forecast_stage_finish("bike", 2, 2400 + 1000, 2400)
    expected_stage_s = 1000 * (170.0 / (2 * 4.04))
    assert forecast == round(2400 + expected_stage_s)


def test_forecast_stage_finish_no_lap_data_returns_none():
    assert _forecast_stage_finish("run1", None, None, 0) is None


def test_forecast_stage_finish_zero_lap_returns_none():
    assert _forecast_stage_finish("run1", 0, 500, 0) is None
