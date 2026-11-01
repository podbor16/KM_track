from datetime import timedelta as td

from tools.demo.timeline import rows_at

ROWS = [
    {'id': 1, 'sex': 'Мужчина', 'category': 'М', 'race_status': 'Finished',
     'time_gun_start': td(seconds=10), 'time_clear_start': td(0),
     'time_clear_kt1': td(minutes=20), 'pace_avg_kt1': '4:00',
     'time_gun_finish': td(minutes=90), 'time_clear_finish': td(minutes=89, seconds=50),
     'finish_pace_avg': '4:15', 'rank_absolute': 1},
    {'id': 2, 'sex': 'Женщина', 'category': 'Ж', 'race_status': 'DNF',
     'time_gun_start': td(seconds=30), 'time_clear_kt1': td(minutes=30)},
    {'id': 3, 'sex': 'Мужчина', 'category': 'М', 'race_status': 'Not started'},
    {'id': 4, 'sex': 'Мужчина', 'category': 'М', 'race_status': 'Finished',
     'time_gun_start': td(seconds=5), 'time_gun_finish': td(minutes=80),
     'time_clear_finish': td(minutes=79, seconds=55)},
]
END = 100 * 60


def by_id(rows):
    return {r['id']: r for r in rows}


def test_before_start_everyone_not_started():
    r = by_id(rows_at(ROWS, 0, END))
    assert all(x['race_status'] == 'Not started' for x in r.values())
    assert r[1]['time_gun_start'] is None and r[1]['time_clear_kt1'] is None


def test_mid_race():
    r = by_id(rows_at(ROWS, 25 * 60, END))
    assert r[1]['race_status'] == 'Running'
    assert r[1]['time_clear_kt1'] == td(minutes=20) and r[1]['pace_avg_kt1'] == '4:00'
    assert r[1]['time_gun_finish'] is None and r[1]['finish_pace_avg'] is None
    assert r[1]['rank_absolute'] is None
    assert r[2]['race_status'] == 'Running' and r[2]['time_clear_kt1'] is None


def test_ranks_among_finished_so_far():
    r = by_id(rows_at(ROWS, 85 * 60, END))
    assert r[4]['race_status'] == 'Finished' and r[4]['rank_absolute'] == 1
    assert r[4]['rank_absolute_clean'] == 1 and r[4]['rank_sex'] == 1
    r = by_id(rows_at(ROWS, 95 * 60, END))
    assert r[4]['rank_absolute'] == 1 and r[1]['rank_absolute'] == 2


def test_dnf_visible_only_at_end():
    assert by_id(rows_at(ROWS, 95 * 60, END))[2]['race_status'] == 'Running'
    assert by_id(rows_at(ROWS, END, END))[2]['race_status'] == 'DNF'
    assert by_id(rows_at(ROWS, END, END))[3]['race_status'] == 'Not started'


def test_no_start_time_runs_from_gun():
    rows = [{'id': 5, 'sex': 'Мужчина', 'category': 'М', 'race_status': 'Finished',
             'time_clear_kt1': td(minutes=22), 'time_gun_finish': td(minutes=88),
             'time_clear_finish': td(minutes=88)}]
    end = 100 * 60
    assert rows_at(rows, -10, end)[0]['race_status'] == 'Not started'
    r = rows_at(rows, 60, end)[0]
    assert r['race_status'] == 'Running' and r['time_clear_kt1'] is None
    r = rows_at(rows, 23 * 60, end)[0]
    assert r['race_status'] == 'Running' and r['time_clear_kt1'] == td(minutes=22)
    assert rows_at(rows, 89 * 60, end)[0]['race_status'] == 'Finished'
