from tools.demo.anonymize import _FEMALE, _MALE
from tools.demo.siberman.anonymize import build_person_map, norm, remap_bibs


def _rows():
    return [
        {'key': ('p', 1), 'surname': 'Иванов', 'name': 'Пётр', 'sex': 'M'},
        {'key': ('p', 1), 'surname': 'Иванов', 'name': 'Пётр', 'sex': 'M'},
        {'key': ('p', 2), 'surname': 'Белова', 'name': 'Анна', 'sex': 'F'},
        {'key': ('n', 'А', 'Б'), 'surname': 'Волков', 'name': 'Иван', 'sex': 'M'},
    ]


def test_one_person_one_fake_and_unique():
    m = build_person_map(_rows(), 1)
    assert set(m) == {('p', 1), ('p', 2), ('n', 'А', 'Б')}
    assert len(set(m.values())) == 3


def test_sex_preserved_female_suffix():
    m = build_person_map(_rows(), 1)
    assert m[('p', 2)][0].endswith('а') and m[('p', 2)][1] in _FEMALE
    assert m[('p', 1)][1] in _MALE and not m[('p', 1)][0].endswith('а')


def test_not_real_surnames():
    m = build_person_map(_rows(), 1)
    real = {'ИВАНОВ', 'БЕЛОВ', 'ВОЛКОВ'}
    assert all(norm(s) not in real and norm(s).rstrip('А') not in real for s, _ in m.values())


def test_deterministic_and_seed_changes():
    assert build_person_map(_rows(), 5) == build_person_map(_rows(), 5)
    assert build_person_map(_rows(), 5) != build_person_map(_rows(), 6)


def test_pool_extends_for_many_people():
    rows = [{'key': ('p', i), 'surname': f'Р{i}', 'name': 'X', 'sex': 'M' if i % 2 else 'F'} for i in range(1500)]
    assert len(set(build_person_map(rows, 1).values())) == 1500


def test_remap_bibs_relay_shared_and_permutation():
    m = remap_bibs(['1', '2', '3', '3', '3', '10'], 7)
    assert set(m) == set(m.values()) == {'1', '2', '3', '10'}
    assert all(k != v for k, v in m.items())


def test_remap_bibs_deterministic():
    assert remap_bibs(['1', '2', '3', '4'], 3) == remap_bibs(['4', '3', '2', '1'], 3)
