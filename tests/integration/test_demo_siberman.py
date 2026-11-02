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
