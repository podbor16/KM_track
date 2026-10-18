"""SQL реестра людей Siberman (миграция 014). Соединение autocommit; транзакции открывает service."""
import datetime
import json
from typing import Iterable, Optional

from src.siberman.persons.linking import Applicant, Person

PERSON_FIELDS = ("surname", "name", "gender", "birthdate", "bib_individual", "city", "country")
LINK_ON = "l.race_year=p.race_year AND l.bib=p.bib AND l.relay_stage=p.relay_stage"


def _cur(conn):
    return conn.cursor(dictionary=True, buffered=True)


def _keys_where(keys: list, prefix: str = "") -> tuple:
    clause = " OR ".join([f"({prefix}race_year=%s AND {prefix}bib=%s AND {prefix}relay_stage=%s)"] * len(keys))
    return f"({clause})", [v for k in keys for v in (int(k[0]), str(k[1]), str(k[2]))]


def _in(ids) -> tuple:
    ids = [int(i) for i in ids]
    return ",".join(["%s"] * len(ids)), ids


# ── люди ─────────────────────────────────────────────────────────────────────

def load_persons(conn) -> list:
    cur = _cur(conn)
    cur.execute("SELECT id, surname, name, gender, birthdate, bib_individual, city FROM siberman_persons")
    return [Person(id=r["id"], surname=r["surname"], name=r["name"], gender=r["gender"],
                   birthdate=r["birthdate"], bib_individual=r["bib_individual"], city=r["city"])
            for r in cur.fetchall()]


def get_persons(conn, ids) -> dict:
    ids = sorted({int(i) for i in ids if i is not None})
    if not ids:
        return {}
    marks, args = _in(ids)
    cur = _cur(conn)
    cur.execute(f"SELECT id, {', '.join(PERSON_FIELDS)} FROM siberman_persons WHERE id IN ({marks})", args)
    return {r["id"]: r for r in cur.fetchall()}


def get_person(conn, person_id: int) -> Optional[dict]:
    return get_persons(conn, [person_id]).get(int(person_id))


def person_by_bib(conn, bib: str) -> Optional[dict]:
    cur = _cur(conn)
    cur.execute(f"SELECT id, {', '.join(PERSON_FIELDS)} FROM siberman_persons WHERE bib_individual=%s", (str(bib),))
    return cur.fetchone()


def insert_person(conn, fields: dict) -> int:
    """fields — подмножество PERSON_FIELDS (+ 'id' при восстановлении удалённого отменой)."""
    cols = [c for c in ("id", *PERSON_FIELDS) if c in fields]
    cur = conn.cursor()
    cur.execute(f"INSERT INTO siberman_persons ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))})",
                [fields[c] for c in cols])
    return int(fields.get("id") or cur.lastrowid)


def update_person(conn, person_id: int, fields: dict) -> None:
    if not fields:
        return
    bad = set(fields) - set(PERSON_FIELDS)
    if bad:
        raise ValueError(f"нельзя менять поля: {sorted(bad)}")
    cur = conn.cursor()
    cur.execute(f"UPDATE siberman_persons SET {', '.join(f'{k}=%s' for k in fields)} WHERE id=%s",
                [*fields.values(), int(person_id)])


def delete_person(conn, person_id: int) -> None:
    conn.cursor().execute("DELETE FROM siberman_persons WHERE id=%s", (int(person_id),))


def delete_orphans(conn, ids) -> list:
    """Удалить людей из ids, у которых не осталось выступлений. → удалённые id."""
    ids = sorted({int(i) for i in ids if i is not None})
    if not ids:
        return []
    marks, args = _in(ids)
    cur = _cur(conn)
    cur.execute(f"SELECT s.id FROM siberman_persons s LEFT JOIN siberman_person_links l ON l.person_id=s.id "
                f"WHERE s.id IN ({marks}) AND l.person_id IS NULL AND NOT EXISTS (SELECT 1 FROM "
                "siberman_person_reviews r WHERE r.status <> 'resolved' AND "
                "(r.person_id = s.id OR FIND_IN_SET(s.id, r.other_person_ids)))", args)
    gone = [r["id"] for r in cur.fetchall()]
    for pid in gone:
        delete_person(conn, pid)
    return gone


def search_persons(conn, q: str, limit: int = 30) -> list:
    q = " ".join(q.split())
    cur = _cur(conn)
    base = ("SELECT s.id, s.surname, s.name, s.bib_individual, s.birthdate, s.city, "
            "GROUP_CONCAT(DISTINCT l.race_year ORDER BY l.race_year SEPARATOR ', ') AS years "
            "FROM siberman_persons s LEFT JOIN siberman_person_links l ON l.person_id=s.id "
            f"LEFT JOIN participants p ON {LINK_ON} ")
    if q.isdigit():
        cur.execute(base + "WHERE s.id=%s OR s.bib_individual=%s GROUP BY s.id ORDER BY s.id LIMIT %s",
                    (int(q), q, limit))
    else:
        like = f"%{q}%"
        cur.execute(base + "WHERE CONCAT(s.surname,' ',s.name) LIKE %s OR CONCAT(s.name,' ',s.surname) LIKE %s "
                           "OR CONCAT(p.surname,' ',p.name) LIKE %s "
                           "GROUP BY s.id ORDER BY s.surname, s.name, s.id LIMIT %s", (like, like, like, limit))
    return cur.fetchall()


# ── выступления и привязки ──────────────────────────────────────────────────

def load_participant_rows(conn) -> list:
    cur = _cur(conn)
    cur.execute("SELECT race_year, bib, relay_stage, surname, name, gender, format, city, country FROM participants")
    return cur.fetchall()


def load_links(conn) -> dict:
    """{(год, номер, этап): (person_id, manual, name_key)} — формат, который ждёт link_participants."""
    cur = _cur(conn)
    cur.execute("SELECT race_year, bib, relay_stage, person_id, manual, name_key FROM siberman_person_links")
    return {(int(r["race_year"]), str(r["bib"]), str(r["relay_stage"])): (r["person_id"], r["manual"], r["name_key"])
            for r in cur.fetchall()}


def protocol_fingerprint(conn) -> tuple:
    """Отпечаток протокола: меняется при вставке, удалении или правке ФИ, пола, формата строки."""
    cur = _cur(conn)
    cur.execute("SELECT COUNT(*) AS n, BIT_XOR(CRC32(CONCAT_WS('|', race_year, bib, relay_stage, surname, name, "
                "gender, format))) AS x FROM participants")
    r = cur.fetchone()
    return (int(r["n"]), int(r["x"] or 0))


def set_links(conn, items: Iterable, manual: bool) -> None:
    """items — [((год, номер, этап), person_id, name_key)]; name_key — plain_key ФИ строки сейчас."""
    rows = [(int(k[0]), str(k[1]), str(k[2]), int(pid), int(manual), name_key) for k, pid, name_key in items]
    if rows:
        conn.cursor().executemany(
            "INSERT INTO siberman_person_links (race_year, bib, relay_stage, person_id, manual, name_key) "
            "VALUES (%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE person_id=VALUES(person_id), "
            "manual=VALUES(manual), name_key=VALUES(name_key)", rows)


def delete_links(conn, keys: list) -> None:
    if keys:
        where, args = _keys_where(keys)
        conn.cursor().execute(f"DELETE FROM siberman_person_links WHERE {where}", args)


def links_for_keys(conn, keys: list) -> dict:
    if not keys:
        return {}
    where, args = _keys_where(keys)
    cur = _cur(conn)
    cur.execute(f"SELECT race_year, bib, relay_stage, person_id, manual, name_key FROM siberman_person_links "
                f"WHERE {where}", args)
    return {(int(r["race_year"]), str(r["bib"]), str(r["relay_stage"])):
            {"person_id": r["person_id"], "manual": r["manual"], "name_key": r["name_key"]} for r in cur.fetchall()}


def links_of_person(conn, person_id: int) -> list:
    cur = _cur(conn)
    cur.execute("SELECT race_year, bib, relay_stage FROM siberman_person_links WHERE person_id=%s "
                "ORDER BY race_year, bib, relay_stage", (int(person_id),))
    return [(int(r["race_year"]), str(r["bib"]), str(r["relay_stage"])) for r in cur.fetchall()]


def move_links(conn, source_id: int, target_id: int) -> None:
    """Слияние: привязки переходят как есть — ручными становятся только явно выбранные выступления
    (reassign), иначе после слияния замена этапника перестала бы проверяться."""
    conn.cursor().execute("UPDATE siberman_person_links SET person_id=%s WHERE person_id=%s",
                          (int(target_id), int(source_id)))


def delete_stale(conn) -> tuple:
    """Автопривязки к исчезнувшим строкам и люди без выступлений, на которых не ссылаются
    нерешённые записи «проверить» (их держим, чтобы админ мог слить обратно). → (привязок, людей)."""
    cur = conn.cursor()
    cur.execute(f"DELETE l FROM siberman_person_links l LEFT JOIN participants p ON {LINK_ON} "
                "WHERE p.id IS NULL AND l.manual=0")
    links = cur.rowcount
    cur.execute("DELETE s FROM siberman_persons s LEFT JOIN siberman_person_links l ON l.person_id=s.id "
                "WHERE l.person_id IS NULL AND NOT EXISTS (SELECT 1 FROM siberman_person_reviews r "
                "WHERE r.status <> 'resolved' AND (r.person_id = s.id OR FIND_IN_SET(s.id, r.other_person_ids)))")
    return links, cur.rowcount


def participants_by_keys(conn, keys: list) -> list:
    if not keys:
        return []
    where, args = _keys_where(keys, "p.")
    cur = _cur(conn)
    cur.execute("SELECT p.id, p.race_year, p.bib, p.relay_stage, p.surname, p.name, p.gender, p.format, "
                f"p.relay_team_name, p.status, p.city, p.country FROM participants p WHERE {where}", args)
    return cur.fetchall()


def participations(conn, person_ids) -> dict:
    """person_id → [выступления по годам] (с итоговым временем и флагом ручной привязки)."""
    ids = sorted({int(i) for i in person_ids if i is not None})
    if not ids:
        return {}
    marks, args = _in(ids)
    cur = _cur(conn)
    cur.execute("SELECT l.person_id, l.manual, p.race_year, p.bib, p.relay_stage, p.format, p.relay_team_name, "
                "p.surname, p.name, p.gender, p.status, p.city, p.country, o.total_s "
                f"FROM siberman_person_links l JOIN participants p ON {LINK_ON} "
                "LEFT JOIN overall_results o ON o.participant_id=p.id "
                f"WHERE l.person_id IN ({marks}) ORDER BY p.race_year, p.relay_stage", args)
    out: dict = {}
    for r in cur.fetchall():
        out.setdefault(r["person_id"], []).append(r)
    return out


def refresh_display(conn, person_ids) -> None:
    """ФИ, пол, город, страна человека — по последнему выступлению."""
    for pid, rows in participations(conn, person_ids).items():
        last = max(rows, key=lambda r: (r["race_year"], r["format"] == "individual"))
        fields = {"surname": last["surname"], "name": last["name"],
                  "city": last["city"] or "", "country": last["country"] or ""}
        if last["gender"] in ("M", "F"):
            fields["gender"] = last["gender"]
        update_person(conn, pid, fields)


# ── заявки ───────────────────────────────────────────────────────────────────

def load_applicants(conn) -> list:
    cur = _cur(conn)
    cur.execute("SELECT tranid, surname, name, gender, birthdate, city, submitted_at, claimed_starts "
                "FROM siberman_applicants")
    return [Applicant(**r) for r in cur.fetchall()]


def upsert_applicants(conn, apps: list) -> int:
    rows = [(a.tranid, a.surname, a.name, a.gender, a.birthdate, a.city, a.submitted_at, a.claimed_starts)
            for a in apps]
    if rows:
        conn.cursor().executemany(
            "INSERT INTO siberman_applicants (tranid, surname, name, gender, birthdate, city, submitted_at, "
            "claimed_starts) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE surname=VALUES(surname), "
            "name=VALUES(name), gender=VALUES(gender), birthdate=VALUES(birthdate), city=VALUES(city), "
            "submitted_at=VALUES(submitted_at), claimed_starts=VALUES(claimed_starts)",
            rows)
    return len(rows)


def get_applicants(conn, tranids) -> dict:
    tranids = sorted({t for t in tranids if t})
    if not tranids:
        return {}
    cur = _cur(conn)
    cur.execute(f"SELECT tranid, surname, name, gender, birthdate, city FROM siberman_applicants "
                f"WHERE tranid IN ({','.join(['%s'] * len(tranids))})", tranids)
    return {r["tranid"]: r for r in cur.fetchall()}


# ── «проверить» ──────────────────────────────────────────────────────────────

def add_reviews(conn, reviews: list) -> int:
    cur, n = conn.cursor(), 0
    for r in reviews:
        y, b, s = r.natkey if r.natkey else (None, None, None)
        cur.execute(
            "INSERT IGNORE INTO siberman_person_reviews "
            "(kind, dedupe_key, race_year, bib, relay_stage, person_id, other_person_ids, detail) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
            (r.kind, r.dedupe_key(), y, b, s, r.person.id if r.person else None,
             ",".join(str(o.id) for o in r.others), r.detail[:255]))
        n += cur.rowcount
    return n


def get_review(conn, review_id: int) -> Optional[dict]:
    cur = _cur(conn)
    cur.execute("SELECT * FROM siberman_person_reviews WHERE id=%s", (int(review_id),))
    return cur.fetchone()


def list_reviews(conn, status: str) -> list:
    cur = _cur(conn)
    cur.execute("SELECT * FROM siberman_person_reviews WHERE status=%s ORDER BY id", (status,))
    return cur.fetchall()


def set_review_status(conn, review_id: int, status: str, user: str) -> bool:
    """False — записи нет. (rowcount MySQL считает только изменённые строки — не годится.)"""
    cur = conn.cursor(buffered=True)
    cur.execute("SELECT id FROM siberman_person_reviews WHERE id=%s", (int(review_id),))
    if not cur.fetchone():
        return False
    cur.execute("UPDATE siberman_person_reviews SET status=%s, resolved_at=%s, resolved_by=%s WHERE id=%s",
                (status, None if status == "open" else datetime.datetime.now(), None if status == "open" else user,
                 int(review_id)))
    return True


def reviews_for_person(conn, person_id: int) -> list:
    cur = _cur(conn)
    cur.execute("SELECT id, kind, status FROM siberman_person_reviews WHERE status='open' "
                "AND (person_id=%s OR FIND_IN_SET(%s, other_person_ids)) ORDER BY id", (int(person_id), str(person_id)))
    return cur.fetchall()


REVIEW_STATE = ("person_id", "other_person_ids", "status", "resolved_at", "resolved_by")


def reviews_state(conn, person_ids, review_ids=()) -> list:
    """Состояние записей «проверить», затронутых действием: где человек — основной или кандидат,
    плюс явно названные записи. Для снимка отмены."""
    ids = sorted({int(i) for i in person_ids if i is not None})
    rids = sorted({int(i) for i in review_ids if i is not None})
    conds, args = [], []
    for i in ids:
        conds.append("(person_id=%s OR FIND_IN_SET(%s, other_person_ids))")
        args += [i, str(i)]
    if rids:
        conds.append(f"id IN ({','.join(['%s'] * len(rids))})")
        args += rids
    if not conds:
        return []
    cur = _cur(conn)
    cur.execute(f"SELECT id, {', '.join(REVIEW_STATE)} FROM siberman_person_reviews WHERE {' OR '.join(conds)}", args)
    return cur.fetchall()


def restore_reviews(conn, rows: list) -> None:
    cur = conn.cursor()
    for r in rows:
        cur.execute(f"UPDATE siberman_person_reviews SET {', '.join(f'{k}=%s' for k in REVIEW_STATE)} WHERE id=%s",
                    [r[k] for k in REVIEW_STATE] + [int(r["id"])])


def move_reviews(conn, source_id: int, target_id: int) -> None:
    """Слияние: открытые и отложенные записи исходного человека — на целевого (FK обнулил бы их)."""
    conn.cursor().execute("UPDATE siberman_person_reviews SET person_id=%s WHERE person_id=%s AND status <> 'resolved'",
                          (int(target_id), int(source_id)))


# ── журнал ───────────────────────────────────────────────────────────────────

def add_audit(conn, action: str, summary: str, payload: dict, scope: set, user: str) -> int:
    cur = conn.cursor()
    cur.execute("INSERT INTO siberman_person_audit (action, summary, payload, scope, created_by) VALUES (%s,%s,%s,%s,%s)",
                (action, summary[:255], json.dumps(payload, ensure_ascii=False, default=str),
                 ",".join(sorted(scope)), user or ""))
    return cur.lastrowid


def get_audit(conn, audit_id: int) -> Optional[dict]:
    cur = _cur(conn)
    cur.execute("SELECT * FROM siberman_person_audit WHERE id=%s", (int(audit_id),))
    return cur.fetchone()


def list_audit(conn, limit: int = 100) -> list:
    cur = _cur(conn)
    cur.execute("SELECT id, action, summary, created_at, created_by, undone_at, undone_by "
                "FROM siberman_person_audit ORDER BY id DESC LIMIT %s", (limit,))
    return cur.fetchall()


def later_conflicts(conn, audit_id: int, scope: set) -> list:
    cur = _cur(conn)
    cur.execute("SELECT id, scope FROM siberman_person_audit WHERE id>%s AND undone_at IS NULL", (int(audit_id),))
    return [r["id"] for r in cur.fetchall() if scope & set(filter(None, r["scope"].split(",")))]


def mark_undone(conn, audit_id: int, user: str) -> None:
    conn.cursor().execute("UPDATE siberman_person_audit SET undone_at=%s, undone_by=%s WHERE id=%s",
                          (datetime.datetime.now(), user, int(audit_id)))
