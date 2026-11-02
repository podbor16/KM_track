import copy

from tools.demo.siberman.record import apply_change, diff, state_at


def _ind(bib, overall=None, cp=None):
    return {'bib': bib, 'surname': 'А', 'overall_s': overall, 'rank_overall': None, 'cp': cp or {}}


def _team(bib, swim=None):
    return {'bib': bib, 'team_name': 'Команда 1', 'overall_s': swim,
            'members': [{'relay_stage': 'swim', 'swim_s': swim, 'cp': {}}]}


def _resp(ind, rel, records=None, **top):
    return {'individual': ind, 'relay': rel, 'race_year': 2026, 'race_start': '2026-08-06T08:00:00+07:00',
            'records': records or [{'column_key': 'swim', 'category': 'absolute', 'best_s': 100}], **top}


def _states():
    s0 = _resp([_ind('1'), _ind('2')], [_team('50')])
    s1 = copy.deepcopy(s0)
    s1['individual'][1] = _ind('2', 500, {'swim': {'1': 60}})          # изменение элемента
    s1['individual'] = [s1['individual'][1], s1['individual'][0]]       # и порядка
    s2 = copy.deepcopy(s1)
    s2['individual'].append(_ind('3'))                                  # добавление
    s2['relay'][0] = _team('50', 300)
    s2['records'] = [{'column_key': 'swim', 'category': 'absolute', 'best_s': 90}]  # records
    s3 = copy.deepcopy(s2)
    s3['individual'] = [r for r in s3['individual'] if r['bib'] != '1']  # удаление
    s3['bike2_start'] = '2026-08-07T08:00:00+07:00'                       # новый top-ключ
    s4 = copy.deepcopy(s3)
    del s4['bike2_start']
    return [s0, s1, s2, s3, s4]


def _rec(states):
    changes = []
    for t, (a, b) in enumerate(zip(states, states[1:]), 1):
        ch = diff(a, b)
        if ch:
            changes.append({'t_s': t * 20, **ch})
    return {'initial': states[0], 'changes': changes}


def test_diff_none_when_equal():
    s = _states()[0]
    assert diff(s, copy.deepcopy(s)) is None


def test_diff_only_changed_items_and_keys():
    s0, s1, s2 = _states()[:3]
    ch = diff(s0, s1)
    assert [r['bib'] for r in ch['individual']] == ['2']
    assert ch['order'] == {'individual': ['2', '1']}
    assert 'relay' not in ch and 'top' not in ch
    ch2 = diff(s1, s2)
    assert [r['bib'] for r in ch2['individual']] == ['3']
    assert [r['bib'] for r in ch2['relay']] == ['50']
    assert set(ch2['top']) == {'records'}


def test_state_at_reproduces_every_step():
    states = _states()
    rec = _rec(states)
    for t, s in enumerate(states):
        assert state_at(rec, t * 20) == s
        assert state_at(rec, t * 20 + 19) == s
    assert state_at(rec, -1) == states[0]


def test_removed_and_top_removed():
    states = _states()
    ch = diff(states[2], states[3])
    assert ch['removed'] == {'individual': ['1']}
    assert ch['top'] == {'bike2_start': '2026-08-07T08:00:00+07:00'}
    assert diff(states[3], states[4])['top_removed'] == ['bike2_start']
    assert apply_change(states[2], ch) == states[3]


def test_state_at_does_not_mutate_record():
    states = _states()
    rec = _rec(states)
    before = copy.deepcopy(rec)
    state_at(rec, 1000)
    assert rec == before
