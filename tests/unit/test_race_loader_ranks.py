"""Тест тай-брейка мест по мс — регрессия на баг: двое финишировавших в
пределах одной и той же целой секунды получали одинаковое место, хотя
Copernico различает их с точностью до миллисекунд (см. load_race_results.py
RaceLoader._finish_sort_key/_assign_ranks)."""
from load_race_results import RaceLoader


def test_finish_sort_key_appends_ms_suffix():
    assert RaceLoader._finish_sort_key('00:23:37', 1417800) == '00:23:37.800'


def test_finish_sort_key_defaults_to_000_when_ms_missing():
    """Записи, ещё не обновлённые после фикса (ms=None) — тот же ключ, что
    и раньше (без тай-брейка), поведение не хуже, чем до фикса."""
    assert RaceLoader._finish_sort_key('00:23:37', None) == '00:23:37.000'


def test_finish_sort_key_none_for_missing_time():
    assert RaceLoader._finish_sort_key(None, 1417800) is None


def test_assign_ranks_breaks_tie_by_ms_instead_of_duplicating_place():
    """Роман Блажко и Екатерина Гутарева — оба финишируют в 00:23:37 (одна
    и та же целая секунда), но с разными мс. Без тай-брейка оба получали бы
    место 129 (найденный баг). С тай-брейком — идут последовательно."""
    runners = [
        {'id': 61, 'time_gun_finish': '00:23:37', 'time_gun_finish_ms': 1417100},
        {'id': 239, 'time_gun_finish': '00:23:37', 'time_gun_finish_ms': 1417800},
    ]
    for r in runners:
        r['_gun_key'] = RaceLoader._finish_sort_key(r['time_gun_finish'], r['time_gun_finish_ms'])

    ranks = RaceLoader._assign_ranks(runners, '_gun_key')
    assert ranks[61] != ranks[239], 'ничья не должна возникать при разных мс внутри одной секунды'
    assert sorted(ranks.values()) == [1, 2]
    assert ranks[61] == 1, 'Блажко финишировал раньше (меньше мс) — должен быть первым'


def test_assign_ranks_still_ties_when_ms_truly_identical():
    """Настоящая ничья (одинаковые мс, не только одинаковая секунда) —
    поведение не меняется: одно и то же место, следующее место пропускается."""
    runners = [
        {'id': 1, 'time_gun_finish': '00:20:00', 'time_gun_finish_ms': 1200000},
        {'id': 2, 'time_gun_finish': '00:20:00', 'time_gun_finish_ms': 1200000},
        {'id': 3, 'time_gun_finish': '00:20:05', 'time_gun_finish_ms': 1205000},
    ]
    for r in runners:
        r['_gun_key'] = RaceLoader._finish_sort_key(r['time_gun_finish'], r['time_gun_finish_ms'])

    ranks = RaceLoader._assign_ranks(runners, '_gun_key')
    assert ranks[1] == ranks[2] == 1
    assert ranks[3] == 3, 'третье место пропускает 2 — стандартное поведение при ничьей'


def test_assign_ranks_backward_compatible_without_ms():
    """Записи без ms (существовавшие до фикса, ms=None у обоих) — ведут
    себя ровно как раньше: ничья при одинаковой целой секунде."""
    runners = [
        {'id': 61, 'time_gun_finish': '00:23:37', 'time_gun_finish_ms': None},
        {'id': 239, 'time_gun_finish': '00:23:37', 'time_gun_finish_ms': None},
    ]
    for r in runners:
        r['_gun_key'] = RaceLoader._finish_sort_key(r['time_gun_finish'], r['time_gun_finish_ms'])

    ranks = RaceLoader._assign_ranks(runners, '_gun_key')
    assert ranks[61] == ranks[239]
