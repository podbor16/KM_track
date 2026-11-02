"""Обезличивание песочницы duathlon_222_demo: ФИО, город/страна, номера."""
from tools.demo.sandbox import assert_local
from tools.demo.siberman.anonymize import build_person_map, norm, remap_bibs


def anonymize_sandbox(conn, seed: int) -> dict:
    conn.autocommit = False
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT DATABASE() AS db, @@port AS port")
    info = cur.fetchone()
    if not info['db'] or not info['db'].endswith('_demo'):
        raise RuntimeError("Обезличивание разрешено только в БД *_demo")
    assert_local('127.0.0.1', info['port'])

    cur.execute("SELECT id, event_id, start_number, surname, name, gender, city, country "
                "FROM participants ORDER BY id")
    parts = cur.fetchall()
    real = {'real_surnames': set(), 'real_full_names': set(), 'real_teams': set(), 'real_cities': set()}
    rows = []
    for r in parts:
        s, n = r['surname'], r['name']
        real['real_surnames'].add(s)
        real['real_full_names'].update({f"{s} {n}", f"{n} {s}"})
        for col in ('city', 'country'):
            if r[col]:
                real['real_cities'].add(r[col])
        rows.append({'key': (norm(s), norm(n)), 'surname': s, 'name': n, 'sex': r['gender']})
    pmap = build_person_map(rows, seed)

    for r in parts:
        s, n = pmap[(norm(r['surname']), norm(r['name']))]
        cur.execute("UPDATE participants SET surname=%s, name=%s, city='', country='' WHERE id=%s",
                    (s, n, r['id']))

    for ev in sorted({r['event_id'] for r in parts}):
        bmap = remap_bibs([r['start_number'] for r in parts if r['event_id'] == ev], seed)
        for old, new in bmap.items():
            cur.execute("UPDATE participants SET start_number=%s WHERE event_id=%s AND start_number=%s",
                        (-int(new), ev, int(old)))
        cur.execute("UPDATE participants SET start_number=-start_number WHERE event_id=%s AND start_number<0", (ev,))
    conn.commit()
    return real
