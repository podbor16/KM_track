from src.duathlon222.service import _stage_times


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
