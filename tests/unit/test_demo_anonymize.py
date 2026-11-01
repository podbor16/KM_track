from tools.demo.anonymize import anonymize


def _rows():
    return [
        {'id': 10, 'client_id': 5, 'surname': 'Петров', 'name': 'Иван', 'sex': 'Мужчина',
         'birthday': '1990-01-01', 'start_number': 101, 'category': 'М30-39'},
        {'id': 11, 'client_id': 6, 'surname': 'Сидорова', 'name': 'Анна', 'sex': 'Женщина',
         'birthday': '1992-02-02', 'start_number': 102, 'category': 'Ж30-39'},
        {'id': 12, 'client_id': 7, 'surname': 'Кузнецов', 'name': 'Пётр', 'sex': 'Мужчина',
         'birthday': None, 'start_number': 103, 'category': 'М18-29'},
    ]


def test_removes_pii_and_keeps_sex_category():
    out, key_map = anonymize(_rows(), seed=1)
    real_surnames = {'Петров', 'Сидорова', 'Кузнецов'}
    for r in out:
        assert r['surname'] not in real_surnames
        assert r['birthday'] is None and r['client_id'] is None
    assert [r['sex'] for r in out] == ['Мужчина', 'Женщина', 'Мужчина']
    assert [r['category'] for r in out] == ['М30-39', 'Ж30-39', 'М18-29']
    assert out[1]['surname'].endswith('а')


def test_ids_renumbered_bibs_permuted_names_unique():
    out, _ = anonymize(_rows(), seed=1)
    assert [r['id'] for r in out] == [1, 2, 3]
    assert sorted(r['start_number'] for r in out) == [101, 102, 103]
    assert len({(r['surname'], r['name']) for r in out}) == 3


def test_deterministic():
    assert anonymize(_rows(), seed=1) == anonymize(_rows(), seed=1)


def test_key_map_translates_hist_keys():
    out, key_map = anonymize(_rows(), seed=1)
    assert key_map['ПЕТРОВ|ИВАН|1990-01-01'] == f"{out[0]['surname']}|{out[0]['name']}|".upper()
