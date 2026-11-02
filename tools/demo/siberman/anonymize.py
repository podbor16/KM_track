"""Обезличивание песочницы siberman_demo (спека п. 2): ФИО, города, команды, номера."""
import random

from tools.demo.anonymize import _FEMALE, _MALE, _SURNAMES
from tools.demo.siberman.sandbox import assert_local

_STEMS = [
    "Бел", "Зар", "Лес", "Мор", "Тих", "Яс", "Бор", "Глух", "Дуб", "Ключ", "Луг", "Мед",
    "Нов", "Остр", "Пух", "Реч", "Сер", "Тёп", "Хмел", "Чёрн", "Шир", "Юр", "Ясн", "Кам",
]
_SUFFIXES = ["ов", "ев", "ин"]
_EXTRA = [s + x for s in _STEMS for x in _SUFFIXES]
GENERATOR_SURNAMES = ({s.lower() for s in _SURNAMES + _EXTRA}
                      | {s.lower() + 'а' for s in _SURNAMES + _EXTRA})
GENERATOR_NAMES = {n.lower() for n in _MALE + _FEMALE}


def norm(s) -> str:
    return ' '.join(str(s or '').strip().upper().replace('Ё', 'Е').split())


def _base(surname: str) -> str:
    s = norm(surname)
    return s[:-1] if s.endswith('А') else s


def build_person_map(rows: list[dict], seed: int) -> dict:
    """rows: [{key, surname, name, sex('M'|'F')}] -> {key: (фейк_фамилия, фейк_имя)}.
    Пол сохранён (женская фамилия = мужская + «а»), пары уникальны, фамилии не совпадают с реальными."""
    rnd = random.Random(seed)
    real = {_base(r['surname']) for r in rows}
    surnames = [s for s in dict.fromkeys(_SURNAMES + _EXTRA) if norm(s) not in real]
    rnd.shuffle(surnames)
    names = {'M': list(_MALE), 'F': list(_FEMALE)}
    sexes = {}
    for r in rows:
        sexes.setdefault(r['key'], r.get('sex') or 'M')
    used, result = set(), {}
    for i, key in enumerate(sorted(sexes, key=repr)):
        sex = 'F' if sexes[key] == 'F' else 'M'
        base = surnames[i % len(surnames)]
        while True:
            surname = base + 'а' if sex == 'F' else base
            name = rnd.choice(names[sex])
            if (surname, name) not in used:
                break
            base = surnames[rnd.randrange(len(surnames))]
        used.add((surname, name))
        result[key] = (surname, name)
    return result


def remap_bibs(bibs, seed: int) -> dict:
    """Перестановка множества номеров: {старый: новый}; одинаковые старые -> одинаковый новый, без неподвижных точек."""
    vals = sorted({str(b) for b in bibs}, key=lambda b: (len(b), b))
    if len(vals) < 2:
        return {v: v for v in vals}
    rnd = random.Random(seed)
    while True:
        perm = vals[:]
        rnd.shuffle(perm)
        if all(a != b for a, b in zip(vals, perm)):
            return dict(zip(vals, perm))


def anonymize_sandbox(conn, seed: int, race_year: int) -> dict:
    conn.autocommit = False
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT DATABASE() AS db, @@port AS port")
    info = cur.fetchone()
    if not info['db'] or info['db'] == 'siberman' or not info['db'].endswith('_demo'):
        raise RuntimeError("Обезличивание разрешено только в БД *_demo")
    assert_local('127.0.0.1', info['port'])

    cur.execute("SELECT id, race_year, bib, relay_stage, surname, name, gender, city, country, "
                "relay_team_name FROM participants ORDER BY id")
    parts = cur.fetchall()
    cur.execute("SELECT id, surname, name, gender, city, country, city_manual FROM siberman_persons ORDER BY id")
    persons = cur.fetchall()
    cur.execute("SELECT race_year, bib, relay_stage, person_id FROM siberman_person_links")
    link_pid = {(l['race_year'], l['bib'], l['relay_stage']): l['person_id'] for l in cur.fetchall()}
    cur.execute("SELECT id, column_key, category, holder_name, holder_team, year_set, baseline_holder_name, "
                "baseline_holder_team, baseline_year_set FROM siberman_records ORDER BY id")
    records = cur.fetchall()
    person_by_id = {p['id']: p for p in persons}

    real = {'real_surnames': set(), 'real_full_names': set(), 'real_teams': set(), 'real_cities': set()}

    def note_name(s, n):
        if s:
            real['real_surnames'].add(s)
        if s and n:
            real['real_full_names'].update({f"{s} {n}", f"{n} {s}"})

    def sex_of(g):
        return 'F' if g == 'F' else 'M'

    rows, name2key, year_name2key, sex_by_key, part_key = [], {}, {}, {}, {}
    for p in persons:
        k = ('p', p['id'])
        sex_by_key[k] = sex_of(p['gender'])
        rows.append({'key': k, 'surname': p['surname'], 'name': p['name'], 'sex': sex_by_key[k]})
        name2key.setdefault(norm(f"{p['surname']} {p['name']}"), k)
        note_name(p['surname'], p['name'])
        for col in ('city', 'country', 'city_manual'):
            if p[col]:
                real['real_cities'].add(p[col])
    for r in parts:
        pid = link_pid.get((r['race_year'], r['bib'], r['relay_stage']))
        k = ('p', pid) if pid in person_by_id else ('n', norm(r['surname']), norm(r['name']))
        part_key[r['id']] = k
        if k not in sex_by_key:
            sex_by_key[k] = sex_of(r['gender'])
            rows.append({'key': k, 'surname': r['surname'], 'name': r['name'], 'sex': sex_by_key[k]})
        nk = norm(f"{r['surname']} {r['name']}")
        name2key.setdefault(nk, k)
        year_name2key.setdefault((r['race_year'], nk), k)
        note_name(r['surname'], r['name'])
        for col in ('city', 'country'):
            if r[col]:
                real['real_cities'].add(r[col])
        if r['relay_team_name']:
            real['real_teams'].add(r['relay_team_name'])

    def holder_key(name, year, category):
        nk = norm(name)
        k = year_name2key.get((year, nk)) or name2key.get(nk)
        if k is None:
            k = ('h', nk)
            name2key[nk] = k
            sex_by_key[k] = 'F' if str(category).startswith('female') else 'M'
            sur, _, nm = nk.partition(' ')
            rows.append({'key': k, 'surname': sur.capitalize(), 'name': nm, 'sex': sex_by_key[k]})
        return k

    rec_keys = []
    for rec in records:
        hk = holder_key(rec['holder_name'], rec['year_set'], rec['category'])
        bk = (holder_key(rec['baseline_holder_name'], rec['baseline_year_set'], rec['category'])
              if rec['baseline_holder_name'] else None)
        rec_keys.append((hk, bk))
        for nm in (rec['holder_name'], rec['baseline_holder_name']):
            if nm:
                real['real_full_names'].add(nm)
                real['real_surnames'].add(nm.split()[0])
        for t in (rec['holder_team'], rec['baseline_holder_team']):
            if t:
                real['real_teams'].add(t)

    pmap = build_person_map(rows, seed)

    team_map = {}
    for y in sorted({r['race_year'] for r in parts}):
        teams = sorted({r['relay_team_name'] for r in parts if r['race_year'] == y and r['relay_team_name']},
                       key=norm)
        random.Random(seed * 1000 + y).shuffle(teams)
        for i, t in enumerate(teams, 1):
            team_map[(y, norm(t))] = f"Команда {i}"

    for r in parts:
        s, n = pmap[part_key[r['id']]]
        team = team_map.get((r['race_year'], norm(r['relay_team_name']))) if r['relay_team_name'] else None
        cur.execute("UPDATE participants SET surname=%s, name=%s, city='', country='', relay_team_name=%s "
                    "WHERE id=%s", (s, n, team, r['id']))

    for p in persons:
        s, n = pmap[('p', p['id'])]
        cur.execute("UPDATE siberman_persons SET surname=%s, name=%s, birthdate=NULL, bib_individual=NULL, "
                    "city='', country='', city_manual='' WHERE id=%s", (s, n, p['id']))

    def fake_team(t, year):
        return team_map.get((year, norm(t))) if t and year else None

    for rec, (hk, bk) in zip(records, rec_keys):
        cur.execute(
            "UPDATE siberman_records SET holder_name=%s, holder_team=%s, baseline_holder_name=%s, "
            "baseline_holder_team=%s WHERE id=%s",
            (' '.join(pmap[hk]), fake_team(rec['holder_team'], rec['year_set']),
             ' '.join(pmap[bk]) if bk else None,
             fake_team(rec['baseline_holder_team'], rec['baseline_year_set']), rec['id']))

    # номера race_year: двухфазно из-за уникального ключа (race_year, bib, relay_stage)
    bmap = remap_bibs([r['bib'] for r in parts if r['race_year'] == race_year], seed)
    for tbl in ('participants', 'siberman_person_links'):
        for old, new in bmap.items():
            cur.execute(f"UPDATE {tbl} SET bib=%s WHERE race_year=%s AND bib=%s", ('~' + new, race_year, old))
        cur.execute(f"UPDATE {tbl} SET bib=SUBSTRING(bib, 2) WHERE race_year=%s AND bib LIKE '~%%'", (race_year,))
    cur.execute("UPDATE siberman_person_links SET name_key=''")
    conn.commit()
    return real
