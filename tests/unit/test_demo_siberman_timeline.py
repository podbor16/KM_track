from datetime import datetime

import pytest

from tools.demo.siberman.timeline import (
    KRSK, abs_ms, abs_to_compact, compact_to_abs, day_windows, stage_day, total_compact_s)

RS = datetime(2026, 8, 6, 8, 0)
B2M = datetime(2026, 8, 7, 0, 0)
RUN = datetime(2026, 8, 8, 8, 30)
KW = dict(race_start=RS, bike2_day_midnight=B2M, run_start=RUN)


def ms(*a):
    return int(datetime(*a, tzinfo=KRSK).timestamp() * 1000)


def test_swim_and_bike1_from_race_start():
    assert abs_ms('swim', 1800, handicap_s=None, **KW) == ms(2026, 8, 6, 8, 30)
    assert abs_ms('bike_day1', 3600, handicap_s=None, **KW) == ms(2026, 8, 6, 9, 0)


def test_bike2_handicap_is_seconds_of_day():
    assert abs_ms('bike_day2', 600, handicap_s=8 * 3600 + 180, **KW) == ms(2026, 8, 7, 8, 13)


def test_bike2_requires_handicap():
    with pytest.raises(ValueError):
        abs_ms('bike_day2', 1, handicap_s=None, **KW)


def test_run_and_submarks_from_run_start():
    assert abs_ms('run', 1895.5, handicap_s=None, **KW) == ms(2026, 8, 8, 9, 1, 35) + 500
    assert abs_ms('run', 0, handicap_s=None, **KW) == ms(2026, 8, 8, 8, 30)


def test_stage_day():
    assert [stage_day(s) for s in ('swim', 'bike_day1', 'bike_day2', 'run')] == [1, 1, 2, 3]


ANCH = dict(race_start=RS, bike2_start=datetime(2026, 8, 7, 8, 0), run_start=RUN)
MARKS = [(1, ms(2026, 8, 6, 8, 10)), (1, ms(2026, 8, 6, 12, 0)),
         (2, ms(2026, 8, 7, 8, 30)), (2, ms(2026, 8, 7, 10, 0)),
         (3, ms(2026, 8, 8, 9, 0)), (3, ms(2026, 8, 8, 9, 30))]


def wins():
    return day_windows(MARKS, ANCH)


def test_windows_bounds_and_labels():
    w = wins()
    assert [x['day'] for x in w] == [1, 2, 3]
    assert w[0]['label'] == 'День 1 · плавание и вело'
    assert w[1]['label'] == 'День 2 · вело' and w[2]['label'] == 'День 3 · бег'
    assert w[0]['start_ms'] == ms(2026, 8, 6, 8, 0) - 300_000
    assert w[0]['end_ms'] == ms(2026, 8, 6, 12, 0) + 300_000
    assert w[2]['start_ms'] == ms(2026, 8, 8, 8, 30) - 300_000
    assert w[2]['end_ms'] == ms(2026, 8, 8, 9, 30) + 300_000


def test_day2_uses_earliest_personal_start():
    a = dict(ANCH, bike2_first_start=ms(2026, 8, 7, 8, 3))
    assert day_windows(MARKS, a)[1]['start_ms'] == ms(2026, 8, 7, 8, 3) - 300_000


def test_total_is_sum_of_windows():
    w = wins()
    assert total_compact_s(w) == sum((x['end_ms'] - x['start_ms']) / 1000 for x in w)


def test_glue_and_reversibility():
    w = wins()
    d1 = (w[0]['end_ms'] - w[0]['start_ms']) / 1000
    assert abs_to_compact(w[1]['start_ms'], w) == d1
    for x in w:
        for m in (x['start_ms'], (x['start_ms'] + x['end_ms']) // 2, x['start_ms'] + 12345):
            assert compact_to_abs(abs_to_compact(m, w), w) == m
    assert compact_to_abs(0, w) == w[0]['start_ms']


def test_night_maps_to_next_window_start():
    w = wins()
    night = ms(2026, 8, 6, 23, 0)
    assert abs_to_compact(night, w) == abs_to_compact(w[1]['start_ms'], w)


def test_clamp():
    w = wins()
    assert abs_to_compact(0, w) == 0
    assert abs_to_compact(ms(2030, 1, 1), w) == total_compact_s(w)
    assert compact_to_abs(10 ** 9, w) == w[-1]['end_ms']
    assert compact_to_abs(-5, w) == w[0]['start_ms']
