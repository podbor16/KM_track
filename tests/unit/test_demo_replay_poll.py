from decimal import Decimal

from tools.demo.replay_poll import apply_change, diff, normalize, record_steps, state_at, time_grid

ROWS = {'key': ['bib'], 'item': {'fields': {}}}
LAPS = {'key': ['pid', 'lap']}
RESP = {'fields': {'rows': ROWS, 'laps': LAPS, 'stages': {'fields': {'run': {'fields': {'laps': LAPS}}}}}}


def _roundtrip(a, b, spec):
    node = diff(a, b, spec)
    assert apply_change(a, node, spec) == b
    return node


def test_equal_is_none():
    assert diff({'rows': [{'bib': 1}]}, {'rows': [{'bib': 1}]}, RESP) is None


def test_list_add_change_remove_order():
    a = [{'bib': 1, 's': 'a'}, {'bib': 2, 's': 'b'}, {'bib': 3, 's': 'c'}]
    node = _roundtrip(a, [{'bib': 1, 's': 'a'}, {'bib': 3, 's': 'c'}, {'bib': 2, 's': 'b'}], ROWS)
    assert node == {'o': ['1', '3', '2']}
    node = _roundtrip(a, [{'bib': 1, 's': 'a'}, {'bib': 2, 's': 'B'}, {'bib': 3, 's': 'c'}], ROWS)
    assert node == {'u': {'2': {'f': {'s': {'=': 'B'}}}}}
    node = _roundtrip(a, [{'bib': 1, 's': 'a'}, {'bib': 3, 's': 'c'}], ROWS)
    assert node == {'x': ['2']}
    node = _roundtrip(a, a + [{'bib': 4, 's': 'd'}], ROWS)
    assert node == {'a': [{'bib': 4, 's': 'd'}]}
    node = _roundtrip(a, [{'bib': 4, 's': 'd'}] + a, ROWS)
    assert node['o'] == ['4', '1', '2', '3']
    _roundtrip([], a, ROWS)
    _roundtrip(a, [], ROWS)


def test_composite_key():
    a = [{'pid': 1, 'lap': 1, 'ms': 10}]
    node = _roundtrip(a, a + [{'pid': 1, 'lap': 2, 'ms': 20}], LAPS)
    assert node == {'a': [{'pid': 1, 'lap': 2, 'ms': 20}]}


def test_dict_nested_lists_and_other_keys():
    a = {'rows': [{'bib': 1, 'x': 1}], 'laps': [], 'title': 't', 'old': 1,
         'stages': {'run': {'laps': [{'pid': 1, 'lap': 1}], 'finish': None}}}
    b = {'rows': [{'bib': 1, 'x': 2}], 'laps': [{'pid': 1, 'lap': 1}], 'title': 'T', 'new': [1],
         'stages': {'run': {'laps': [{'pid': 1, 'lap': 1}, {'pid': 1, 'lap': 2}], 'finish': {'s': 5}}}}
    node = _roundtrip(a, b, RESP)
    assert node['x'] == ['old'] and node['f']['title'] == {'=': 'T'} and node['f']['new'] == {'=': [1]}
    assert node['f']['stages']['f']['run']['f']['laps'] == {'a': [{'pid': 1, 'lap': 2}]}
    # тип сменился (None ↔ dict/list) — замена целиком
    assert _roundtrip(None, b, RESP) == {'=': b}
    assert _roundtrip({'rows': None}, {'rows': [{'bib': 1}]}, RESP) == {'f': {'rows': {'=': [{'bib': 1}]}}}


def test_state_at_and_record_steps():
    spec = {'a': {'fields': {'rows': ROWS}}, 'b': None}
    data = {0: [], 30: [{'bib': 1, 'v': 1}], 60: [{'bib': 1, 'v': 1}], 90: [{'bib': 2, 'v': 0}, {'bib': 1, 'v': 2}]}
    cur = {}

    def advance(t):
        changed = cur.get('rows') != data[t]
        cur['rows'] = data[t]
        return changed

    calls = []

    def snap():
        calls.append(1)
        return {'a': {'rows': cur['rows'], 'n': Decimal('1.50')}, 'b': len(cur['rows'])}

    initial, changes = record_steps([0, 30, 60, 90], advance, snap, spec)
    assert len(calls) == 3 and [c['t_s'] for c in changes] == [30, 90]
    assert initial == {'a': {'rows': [], 'n': 1.5}, 'b': 0}
    rec = {'meta': {'spec': spec}, 'initial': initial, 'changes': changes}
    assert state_at(rec, -5) == initial
    assert state_at(rec, 59)['a']['rows'] == [{'bib': 1, 'v': 1}]
    assert state_at(rec, 90) == {'a': {'rows': data[90], 'n': 1.5}, 'b': 2}
    assert rec['initial'] == {'a': {'rows': [], 'n': 1.5}, 'b': 0}  # state_at не портит запись


def test_normalize_like_fastapi():
    assert normalize({'d': Decimal('4.040'), 'i': Decimal('3'), 't': (1, 2)}) == {'d': 4.04, 'i': 3, 't': [1, 2]}


def test_time_grid():
    assert time_grid(-60, 45, 30) == [-60, -30, 0, 30, 45]
    assert time_grid(-60, 30, 30) == [-60, -30, 0, 30]


def test_snap_marks_rounds_up_to_record_step():
    from tools.demo.replay_poll import snap_marks
    marks = [{'label': 'Старт', 't_s': 0}, {'label': 'Финиш', 't_s': 86247.996},
             {'label': 'Нет', 't_s': None}, {'label': 'Хвост', 't_s': 86540}]
    got = snap_marks(marks, -300, 86548, 30)
    assert [m['t_s'] for m in got] == [0, 86250, None, 86548]
    assert got[1]['label'] == 'Финиш' and marks[1]['t_s'] == 86247.996
