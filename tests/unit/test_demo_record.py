from datetime import timedelta as td

from tools.demo.record import build_record, state_at, compress_series
from tools.demo.timeline import rows_at
from src.krasmarafon.services.results_service import assemble_event_results
from tests.unit.test_results_assemble import _ev_info, _gun_local_naive

HIST = {'personal': {}, 'category_avg': {}, 'prev_year': 2025}
ROWS = [
    {'id': i, 'surname': f'Ф{i}', 'name': 'И', 'sex': 'Мужчина', 'category': 'М18-29',
     'race_status': 'Finished', 'time_gun_start': td(seconds=i * 7),
     'time_clear_kt1': td(minutes=20 + i), 'time_gun_finish': td(minutes=95 + i * 2, seconds=i * 7),
     'time_clear_finish': td(minutes=95 + i * 2)}
    for i in range(1, 6)
] + [{'id': 6, 'surname': 'Ф6', 'name': 'И', 'sex': 'Женщина', 'category': 'Ж',
      'race_status': 'DNF', 'time_gun_start': td(seconds=3)}]


def _build():
    return build_record(ROWS, _ev_info(), {}, {}, HIST, event_id=116,
                        t_from=-300, t_to=120 * 60, end_s=110 * 60, step_s=5)


def test_state_at_every_step_matches_server_code():
    rec = _build()
    gun = _gun_local_naive()
    for t in range(-300, 120 * 60 + 1, 5):
        expect = assemble_event_results(rows_at(ROWS, t, 110 * 60), _ev_info(), {}, {}, HIST,
                                        event_id=116, now=gun + td(seconds=t))
        expect = {r['id']: r for r in rec['_normalize'](expect.results)}
        got = {r['id']: r for r in state_at(rec, t)}
        assert got.keys() == expect.keys()
        for i, e in expect.items():
            g = dict(got[i])
            assert abs(g.pop('current_distance') - e.pop('current_distance')) <= 0.001 + 1e-9, (t, i)
            assert g == e, (t, i)


def test_compress_series_linear_and_steps():
    pts = [[t, round(min(t * 0.003, 5.0), 3)] for t in range(0, 4000, 5)]
    c = compress_series(pts)
    assert len(c) <= 4
    assert c[0] == pts[0] and c[-1] == pts[-1]


def test_meta_fields():
    rec = _build()
    assert rec['meta']['step_s'] == 5
    assert rec['meta']['gun_unix_ms'] > 0
    assert rec['meta']['t_from'] == -300 and rec['meta']['t_to'] == 120 * 60
