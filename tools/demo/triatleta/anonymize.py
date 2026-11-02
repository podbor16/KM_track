"""Обезличивание песочницы triatleta_24h_demo: ФИО, команды (эстафета), даты рождения, номера."""
import random

from tools.demo.sandbox import assert_local
from tools.demo.siberman.anonymize import build_person_map, norm, remap_bibs

MIXED = 'mixed'


def split_members(name: str) -> list[tuple[str, str]]:
    """'Фамилия Имя, Фамилия Имя' -> [(фамилия, имя), ...]."""
    out = []
    for part in (name or '').split(','):
        words = part.split()
        if words:
            out.append((words[0], ' '.join(words[1:])))
    return out


def guess_sex(surname: str) -> str:
    return 'F' if norm(surname).endswith(('А', 'Я')) else 'M'


def team_labels(team_ids, seed: int) -> dict:
    """{id команды: 'Команда N'} - детерминированная перемешанная нумерация."""
    ids = sorted(team_ids)
    random.Random(seed).shuffle(ids)
    return {i: f"Команда {n}" for n, i in enumerate(ids, 1)}


def group_bib_map(parts, seed: int) -> dict:
    """{(event_id, старый номер): новый} - перестановка внутри (событие, команда/личник),
    чтобы номера эстафет (1001+) остались в своём диапазоне."""
    out = {}
    groups = sorted({(r['event_id'], r['gender'] == MIXED) for r in parts})
    for ev, mixed in groups:
        bibs = [r['start_number'] for r in parts if r['event_id'] == ev and (r['gender'] == MIXED) == mixed]
        out.update({(ev, int(o)): int(n) for o, n in remap_bibs(bibs, seed).items()})
    return out


def anonymize_sandbox(conn, seed: int) -> dict:
    conn.autocommit = False
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT DATABASE() AS db, @@port AS port")
    info = cur.fetchone()
    if not info['db'] or not info['db'].endswith('_demo'):
        raise RuntimeError("Обезличивание разрешено только в БД *_demo")
    assert_local('127.0.0.1', info['port'])

    cur.execute("SELECT id, event_id, start_number, surname, name, gender FROM participants ORDER BY id")
    parts = cur.fetchall()
    real = {'real_surnames': set(), 'real_full_names': set(), 'real_teams': set(), 'real_cities': set()}

    def members(r):
        if r['gender'] == MIXED:
            return split_members(r['name'])
        return [(r['surname'], r['name'])]

    rows = []
    for r in parts:
        for s, n in members(r):
            real['real_surnames'].add(s)
            real['real_full_names'].update({f"{s} {n}", f"{n} {s}"})
            rows.append({'key': (norm(s), norm(n)), 'surname': s, 'name': n,
                         'sex': guess_sex(s) if r['gender'] == MIXED else ('F' if r['gender'] == 'Женщина' else 'M')})
        if r['gender'] == MIXED:
            real['real_teams'].add(r['surname'])
            real['real_full_names'].add(r['name'])
    pmap = build_person_map(rows, seed)
    labels = team_labels([r['id'] for r in parts if r['gender'] == MIXED], seed)

    for r in parts:
        if r['gender'] == MIXED:
            fake_members = [pmap[(norm(s), norm(n))] for s, n in members(r)]
            surname, name = labels[r['id']], ', '.join(f"{s} {n}" for s, n in fake_members)
        else:
            surname, name = pmap[(norm(r['surname']), norm(r['name']))]
        cur.execute("UPDATE participants SET surname=%s, name=%s, birthdate=NULL, team_name='' WHERE id=%s",
                    (surname, name, r['id']))

    # номера: двухфазно из-за UNIQUE(event_id, start_number)
    for (ev, old), new in group_bib_map(parts, seed).items():
        cur.execute("UPDATE participants SET start_number=%s WHERE event_id=%s AND start_number=%s",
                    (-new, ev, old))
    cur.execute("UPDATE participants SET start_number=-start_number WHERE start_number<0")
    conn.commit()
    return real
