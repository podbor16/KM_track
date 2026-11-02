from tools.demo.sandbox import recreate, use_sandbox
from tools.demo.siberman.anonymize import build_person_map, remap_bibs
from tools.demo.triatleta.anonymize import group_bib_map, guess_sex, split_members, team_labels

import pytest


def test_split_members():
    assert split_members('Иванов Пётр, Белова Анна') == [('Иванов', 'Пётр'), ('Белова', 'Анна')]
    assert split_members('') == []


def test_guess_sex():
    assert guess_sex('Белова') == 'F' and guess_sex('Иванов') == 'M'


def test_team_labels_unique_deterministic():
    a = team_labels([5, 3, 9], 1)
    assert sorted(a.values()) == ['Команда 1', 'Команда 2', 'Команда 3']
    assert a == team_labels([9, 5, 3], 1)


def test_member_map_sex_and_not_real():
    rows = [{'key': ('И', 'П'), 'surname': 'Иванов', 'name': 'Пётр', 'sex': 'M'},
            {'key': ('Б', 'А'), 'surname': 'Белова', 'name': 'Анна', 'sex': 'F'}]
    m = build_person_map(rows, 3)
    assert m == build_person_map(rows, 3)
    assert m[('Б', 'А')][0].endswith('а') and m[('И', 'П')][0] not in ('Иванов',)


def test_bibs_permutation_deterministic():
    m = remap_bibs([1, 3, 9, 1001, 1002], 7)
    assert sorted(m) == sorted(m.values()) and all(k != v for k, v in m.items())
    assert m == remap_bibs([1, 3, 9, 1001, 1002], 7)


def test_recreate_rejects_non_demo():
    with pytest.raises(RuntimeError):
        recreate('triatleta_24h', 'triatleta_24h_copy')


def test_use_sandbox_restores_and_rejects():
    import types
    mod = types.SimpleNamespace(conn=lambda: 'orig')
    with pytest.raises(RuntimeError):
        with use_sandbox(mod, 'conn', 'prod_db'):
            pass
    assert mod.conn() == 'orig'


def test_group_bib_map_keeps_relay_range():
    parts = [{'event_id': 1, 'start_number': b, 'gender': g}
             for b, g in [(1, 'Мужчина'), (3, 'Женщина'), (9, 'Мужчина'), (12, 'Мужчина'),
                          (1001, 'mixed'), (1002, 'mixed'), (1003, 'mixed')]]
    m = group_bib_map(parts, 7)
    assert m == group_bib_map(parts, 7)
    assert sorted(m) == sorted((1, b) for b in (1, 3, 9, 12, 1001, 1002, 1003))
    assert sorted(m.values()) == [1, 3, 9, 12, 1001, 1002, 1003]
    assert all((old >= 1001) == (new >= 1001) for (_, old), new in m.items())
