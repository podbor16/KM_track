import re

import pytest

from tools.demo import sandbox


def _db_ok():
    try:
        sandbox.connect('triatleta_24h').close()
        sandbox.connect('duathlon_222').close()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _db_ok(), reason="нет локальных БД triatleta_24h/duathlon_222")


def _check(src_db, dst_db, real, extra_exact=()):
    from tools.demo.siberman.anonymize import GENERATOR_SURNAMES
    src, dst = sandbox.connect(src_db), sandbox.connect(dst_db)
    s, d = src.cursor(), dst.cursor()
    s.execute("SELECT COUNT(*) FROM participants")
    d.execute("SELECT COUNT(*) FROM participants")
    assert s.fetchone() == d.fetchone()
    surn = {x.lower() for x in real['real_surnames'] if len(x) >= 4} - GENERATOR_SURNAMES
    forms = surn | {x[:-1] for x in surn if x.endswith('а')}
    full = {x.lower() for x in real['real_full_names']}
    exact = {x.lower() for x in real['real_teams'] | real['real_cities'] if x}
    d.execute("SELECT table_name, column_name FROM information_schema.columns "
              f"WHERE table_schema='{dst_db}' AND data_type IN ('varchar','char','text','mediumtext')")
    bad = 0
    for t, c in d.fetchall():
        d.execute(f"SELECT DISTINCT `{c}` FROM `{dst_db}`.`{t}` WHERE `{c}` IS NOT NULL AND `{c}`<>''")
        for (v,) in d.fetchall():
            low = str(v).lower()
            if low in exact or any(f in low for f in full) or set(re.findall(r'[а-яёa-z]+', low)) & forms:
                bad += 1
    assert bad == 0
    src.close()
    dst.close()


def _standings_clean(module, real, expected):
    with sandbox.use_sandbox(module, module_attr[module.__name__], module_db[module.__name__]):
        rows = module.get_standings(1)
    assert len(rows) == expected
    text = ' '.join(str(v).lower() for r in rows for v in r.values())
    for s in real['real_surnames']:
        if len(s) >= 4:
            from tools.demo.siberman.anonymize import GENERATOR_SURNAMES
            if s.lower() not in GENERATOR_SURNAMES:
                assert s.lower() not in text


module_attr = {'src.race_triatleta.service': 'get_tri_connection',
               'src.duathlon222.service': 'get_duathlon_connection'}
module_db = {'src.race_triatleta.service': 'triatleta_24h_demo',
             'src.duathlon222.service': 'duathlon_222_demo'}


def test_triatleta_sandbox():
    from src.race_triatleta import service
    from tools.demo.triatleta.anonymize import anonymize_sandbox
    sandbox.recreate('triatleta_24h', 'triatleta_24h_demo')
    c = sandbox.connect('triatleta_24h_demo')
    real = anonymize_sandbox(c, seed=42)
    c.close()
    _check('triatleta_24h', 'triatleta_24h_demo', real)
    _standings_clean(service, real, 10)


def test_duathlon_sandbox():
    from src.duathlon222 import service
    from tools.demo.duathlon.anonymize import anonymize_sandbox
    sandbox.recreate('duathlon_222', 'duathlon_222_demo')
    c = sandbox.connect('duathlon_222_demo')
    real = anonymize_sandbox(c, seed=42)
    c.close()
    _check('duathlon_222', 'duathlon_222_demo', real)
    _standings_clean(service, real, 14)


def _sizes(rec):
    import gzip
    import json
    raw = json.dumps(rec, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    return len(raw), len(gzip.compress(raw, 9))


def test_triatleta_replay_matches_final():
    import time

    from tools.demo.replay_poll import normalize, state_at
    from tools.demo.triatleta import record
    from tools.demo.triatleta.anonymize import anonymize_sandbox

    sandbox.recreate('triatleta_24h', 'triatleta_24h_demo')
    conn = sandbox.connect('triatleta_24h_demo')
    try:
        anonymize_sandbox(conn, seed=42)
        final = record.load_final(conn)
        expected = normalize(record.snapshot())
        record.clear_results(conn)
        t0 = time.time()
        rec = record.replay(conn, final, step_s=30)
        dt = time.time() - t0
    finally:
        conn.close()
    meta = rec['meta']
    assert rec['initial']['laps']['laps'] == []
    assert all(r['laps_completed'] == 0 for r in rec['initial']['standings']['standings'])
    assert state_at(rec, meta['t_to']) == expected
    assert normalize(record.snapshot()) == expected
    # финальный статус — не раньше последнего круга участника
    for t_s, p in record.status_reveals(final):
        if t_s > 600:
            row = next(r for r in state_at(rec, t_s - 60)['standings']['standings']
                       if r['start_number'] == p['start_number'])
            assert row['status'] == record.RUNNING
    # «Финиш» показывает итог: последний круг уже учтён
    assert state_at(rec, meta['marks'][-1]['t_s']) == expected
    raw, gz = _sizes(rec)
    print(f"\nТриатлет: шагов {meta['steps']}, с изменениями {meta['steps_changed']}, {dt:.1f} с, "
          f"json {raw / 1e6:.2f} МБ, gzip {gz / 1e6:.2f} МБ")


def test_duathlon_replay_matches_final():
    import time

    from tools.demo.duathlon import record
    from tools.demo.duathlon.anonymize import anonymize_sandbox
    from tools.demo.replay_poll import normalize, state_at

    sandbox.recreate('duathlon_222', 'duathlon_222_demo')
    conn = sandbox.connect('duathlon_222_demo')
    try:
        anonymize_sandbox(conn, seed=42)
        record.prepare(conn)
        final = record.load_final(conn)
        bibs = sorted(p['start_number'] for p in final['participants'])
        expected = normalize(record.snapshot(bibs))
        record.clear_results(conn)
        t0 = time.time()
        rec = record.replay(conn, final, step_s=30)
        dt = time.time() - t0
    finally:
        conn.close()
    meta = rec['meta']
    assert set(rec['initial']) == set(expected) and len(expected) == 3 + len(bibs)
    init = rec['initial']
    assert all(r['current_mark_race_elapsed_s'] is None and r['status'] == 'notstarted'
               for r in init['standings']['standings'])
    assert all(not s['laps'] for n in bibs for s in init[f'participant/{n}']['stages'].values())
    assert state_at(rec, meta['t_to']) == expected
    assert normalize(record.snapshot(bibs)) == expected
    # до первого финиша гонки никто не finished; после — финишировавшие по run2_s
    mid = state_at(rec, meta['marks'][2]['t_s'])['standings']['standings']
    assert not any(r['status'] in ('finished', 'dnf', 'dsq') for r in mid)
    assert [m['label'] for m in meta['marks']] == ['Старт', 'Вело', 'Бег 42 км', 'Финиш']
    assert meta['marks'][1]['t_s'] < meta['loop_start_s'] < meta['marks'][2]['t_s']
    # «Финиш» показывает итог: все финишёры уже учтены
    assert state_at(rec, meta['marks'][-1]['t_s'])['standings'] == expected['standings']
    raw, gz = _sizes(rec)
    print(f"\nДуатлон: шагов {meta['steps']}, с изменениями {meta['steps_changed']}, {dt:.1f} с, "
          f"json {raw / 1e6:.2f} МБ, gzip {gz / 1e6:.2f} МБ")
