import re

import pytest

from tools.demo.siberman import sandbox


def _db_ok():
    try:
        sandbox.connect('siberman').close()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _db_ok(), reason="нет локальной БД siberman (.env.local)")


def test_sandbox_anonymized():
    from tools.demo.siberman.anonymize import GENERATOR_SURNAMES, anonymize_sandbox, norm
    sandbox.recreate()
    src = sandbox.connect('siberman')
    dst = sandbox.connect('siberman_demo')
    real = anonymize_sandbox(dst, seed=42, race_year=2026)

    s, d = src.cursor(), dst.cursor()
    s.execute("SELECT COUNT(*) FROM participants")
    d.execute("SELECT COUNT(*) FROM participants")
    assert s.fetchone() == d.fetchone()

    surn = {x.lower() for x in real['real_surnames'] if len(x) >= 4} - GENERATOR_SURNAMES
    surn_forms = surn | {x[:-1] for x in surn if x.endswith('а')}
    full = {x.lower() for x in real['real_full_names']}
    exact = {x.lower() for x in real['real_teams'] | real['real_cities'] if x}

    d.execute("SELECT table_name, column_name FROM information_schema.columns "
              "WHERE table_schema='siberman_demo' AND data_type IN ('varchar','char','text','mediumtext')")
    bad = 0
    for t, c in d.fetchall():
        d.execute(f"SELECT DISTINCT `{c}` FROM `siberman_demo`.`{t}` WHERE `{c}` IS NOT NULL AND `{c}`<>''")
        for (v,) in d.fetchall():
            low = str(v).lower()
            if low in exact or any(f in low for f in full):
                bad += 1
            elif set(re.findall(r'[а-яёa-z]+', low)) & surn_forms:
                bad += 1
    assert bad == 0

    # бейдж рекорда 2026: держатель, бывший участником 2026, остаётся участником 2026
    # под тем же фейковым именем в формате фронта «Фамилия Имя» (norm = trim+lower+пробелы)
    s.execute("SELECT id, holder_name FROM siberman_records WHERE year_set=2026")
    src_h = {i: norm(h) for i, h in s.fetchall()}
    s.execute("SELECT surname, name FROM participants WHERE race_year=2026")
    src26 = {norm(f"{a} {b}") for a, b in s.fetchall()}
    d.execute("SELECT id, holder_name FROM siberman_records WHERE year_set=2026")
    dst_h = {i: norm(h) for i, h in d.fetchall()}
    d.execute("SELECT surname, name FROM participants WHERE race_year=2026")
    dst26 = {norm(f"{a} {b}") for a, b in d.fetchall()}
    checked = 0
    for i, h in src_h.items():
        if h in src26:
            assert dst_h[i] in dst26
            checked += 1
    assert checked > 0
    src.close()
    dst.close()


def test_windows_2026():
    from tools.demo.siberman.timeline import abs_ms, abs_to_compact, day_windows, stage_day, total_compact_s
    c = sandbox.connect('siberman')
    cur = c.cursor()
    cur.execute("SELECT race_start, bike2_start, run_start FROM race_config WHERE race_year=2026")
    rs, b2, run = cur.fetchone()
    midnight = b2.replace(hour=0, minute=0, second=0, microsecond=0)
    cur.execute("""SELECT cp.stage, t.cumulative_s, p.bike_day2_handicap_s
                   FROM checkpoint_times t JOIN checkpoints cp ON cp.id=t.checkpoint_id
                   JOIN participants p ON p.id=t.participant_id
                   WHERE cp.race_year=2026 AND p.race_year=2026 AND t.cumulative_s IS NOT NULL""")
    marks = []
    for stage, cum, h in cur.fetchall():
        if stage == 'bike_day2' and h is None:
            continue
        m = abs_ms(stage, cum, race_start=rs, bike2_day_midnight=midnight, handicap_s=h, run_start=run)
        marks.append((stage_day(stage), m))
    cur.execute("SELECT MIN(bike_day2_handicap_s) FROM participants WHERE race_year=2026")
    first = abs_ms('bike_day2', 0, race_start=rs, bike2_day_midnight=midnight,
                   handicap_s=cur.fetchone()[0], run_start=run)
    w = day_windows(marks, dict(race_start=rs, bike2_start=b2, run_start=run, bike2_first_start=first))
    print("окна (дни, часы):", [(x['day'], round((x['end_ms'] - x['start_ms']) / 3600000, 2)) for x in w],
          "всего ч:", round(total_compact_s(w) / 3600, 2),
          "отметок:", {d: sum(1 for k, _ in marks if k == d) for d in (1, 2, 3)})
    assert [x['day'] for x in w] == [1, 2, 3]
    for a, b in zip(w, w[1:]):
        assert a['end_ms'] < b['start_ms']
    by_day = {x['day']: x for x in w}
    for d, m in marks:
        assert by_day[d]['start_ms'] <= m <= by_day[d]['end_ms']
        assert abs_to_compact(m, w) >= 0
