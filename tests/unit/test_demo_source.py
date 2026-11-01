import pytest

from src.analytics.db_connection_optimized import get_pooled_connection


def _db_ok():
    try:
        c = get_pooled_connection()
        if c is None:
            return False
        c.close()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _db_ok(), reason="нет локальной БД (.env.local)")


def test_final_state_matches_protocol():
    from tools.demo.source import build_race
    from tools.demo.record import state_at
    rec, rows = build_race("zhara_5")
    final = {r['id']: r for r in state_at(rec, rec['meta']['t_to'])}
    # id в записи = позиция строки + 1 (anonymize перенумеровывает по порядку)
    for i, real in enumerate(rows):
        got = final[i + 1]
        assert got['race_status'] == real['race_status']
        if real['race_status'] == 'Finished':
            assert got['rank_absolute'] == real['rank_absolute'], real['id']
            assert got['time_gun_finish'] == str(real['time_gun_finish'])
