"""Слой БД жеребьёвки — таблицы draw_* (миграция src/siberman/migrations/013_draw.sql)."""
import datetime
from typing import Optional

import mysql.connector
from mysql.connector import errorcode

from src.siberman.db import get_finished_years_by_name, get_finished_years_by_person
from src.siberman.finish_counts import person_key
from src.siberman.persons.linking import plain_key

CONFIG_INT_FIELDS = ("capacity_men", "capacity_women", "capacity_relay", "quota_repeat", "quota_novice")
APPLICANT_COLUMNS = ("format", "surname", "name", "gender", "city", "pool", "is_wildcard", "chances",
                     "starts_individual", "starts_relay", "draw_accumulated", "is_local",
                     "duathlon_222", "race_24h", "tattoo", "relay_swim", "relay_bike", "relay_run",
                     "wildcard_reason", "results_text", "entry_id", "person_id")


def ensure_config(conn, year: int) -> None:
    """Строка настроек года; автопередача ⏳ по умолчанию до 1 января года перед гонкой."""
    cur = conn.cursor()
    cur.execute("INSERT IGNORE INTO draw_config (draw_year, auto_invite_until) VALUES (%s, %s)",
                (year, datetime.date(year - 1, 1, 1)))


def load_config(conn, year: int) -> dict:
    ensure_config(conn, year)
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM draw_config WHERE draw_year=%s", (year,))
    return cur.fetchone()


def get_config(conn, year: int) -> Optional[dict]:
    """Настройки года без создания строки (публичное чтение не пишет в БД)."""
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM draw_config WHERE draw_year=%s", (year,))
    return cur.fetchone()


def lock_config(conn, year: int) -> dict:
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM draw_config WHERE draw_year=%s FOR UPDATE", (year,))
    return cur.fetchone()


def get_version(conn, year: int) -> int:
    cur = conn.cursor()
    cur.execute("SELECT version FROM draw_config WHERE draw_year=%s", (year,))
    row = cur.fetchone()
    return row[0] if row else 0


def bump_version(conn, year: int) -> None:
    conn.cursor().execute("UPDATE draw_config SET version=version+1 WHERE draw_year=%s", (year,))


def _linked_applicants(conn, condition: str, year: int) -> list[dict]:
    cur = conn.cursor(dictionary=True)
    cur.execute(f"""
        SELECT a.*, CASE WHEN e.birthdate IS NOT NULL AND p.birthdate IS NOT NULL
                         AND e.birthdate<>p.birthdate THEN NULL ELSE a.person_id END AS verified_person_id
        FROM draw_applicants a
        LEFT JOIN siberman_entries e ON e.id=a.entry_id
        LEFT JOIN siberman_persons p ON p.id=a.person_id
        WHERE a.draw_year {condition} %s ORDER BY a.draw_year, a.surname, a.name, a.id
    """, (year,))
    rows = cur.fetchall()
    for r in rows:
        r["is_wildcard"] = bool(r["is_wildcard"])
        r["person_id"] = r.pop("verified_person_id")
    return rows


def load_applicants(conn, year: int) -> list[dict]:
    return _linked_applicants(conn, "=", year)


def load_external_start_links(conn) -> dict[int, dict[str, set[tuple[int, int]]]]:
    with conn.cursor(dictionary=True, buffered=True) as cur:
        cur.execute("SELECT person_id, source, event_id, result_id FROM siberman_external_start_links")
        rows = cur.fetchall()
    links = {}
    for row in rows:
        sources = links.setdefault(row["person_id"], {})
        sources.setdefault(row["source"], set()).add((row["event_id"], row["result_id"]))
    return links


def load_chance_history(conn, before_year: int) -> dict:
    """Past draw snapshots needed for the accumulated-chance draft (read-only)."""
    cur = conn.cursor(dictionary=True, buffered=True)
    applicants = _linked_applicants(conn, "<", before_year)
    cur.execute("SELECT * FROM draw_picks WHERE draw_year < %s ORDER BY draw_year, position_key, id", (before_year,))
    picks = cur.fetchall()
    cur.execute("SELECT draw_year, capacity_men, capacity_women, capacity_relay FROM draw_config "
                "WHERE draw_year < %s ORDER BY draw_year", (before_year,))
    configs = {r["draw_year"]: r for r in cur.fetchall()}
    cur.execute("SELECT draw_year, applicant_id FROM draw_audit WHERE draw_year < %s AND action='auto_invite'",
                (before_year,))
    offered = {(r["draw_year"], r["applicant_id"]) for r in cur.fetchall()}
    by_year = {}
    for row in applicants:
        by_year.setdefault(int(row["draw_year"]), {"applicants": [], "picks": [], "config": {}, "offered": set()})
        by_year[int(row["draw_year"])]["applicants"].append(row)
    for row in picks:
        by_year.setdefault(int(row["draw_year"]), {"applicants": [], "picks": [], "config": {}, "offered": set()})
        by_year[int(row["draw_year"])]["picks"].append(row)
    for year, value in by_year.items():
        value["config"] = configs.get(year) or {}
        value["offered"] = {aid for y, aid in offered if y == year}
    return by_year


def load_archive_results(conn, before_year: int) -> list[dict]:
    with conn.cursor(dictionary=True, buffered=True) as cur:
        cur.execute(
            "SELECT draw_year, source_group, position, participant_name, outcome, person_id "
            "FROM siberman_draw_archive_results WHERE draw_year < %s "
            "ORDER BY draw_year, source_group, position", (before_year,)
        )
        return cur.fetchall()


def load_balance_decisions(conn, entry_ids: list[int]) -> dict[int, dict]:
    if not entry_ids:
        return {}
    marks = ", ".join(["%s"] * len(entry_ids))
    with conn.cursor(dictionary=True, buffered=True) as cur:
        cur.execute(
            f"SELECT entry_id, balance, reason FROM siberman_draw_balance_decisions "
            f"WHERE entry_id IN ({marks})", entry_ids
        )
        return {row["entry_id"]: row for row in cur.fetchall()}


def load_picks(conn, year: int) -> list[dict]:
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT *, UNIX_TIMESTAMP(created_at) AS created_at_epoch "
                "FROM draw_picks WHERE draw_year=%s ORDER BY id", (year,))
    return cur.fetchall()


def insert_pick(conn, year: int, applicant_id: int, rnd: int, category: str,
                position_key: Optional[int] = None) -> int:
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO draw_picks (draw_year, applicant_id, round, category, position_key, created_at) "
        "VALUES (%s, %s, %s, %s, 0, NOW())",
        (year, applicant_id, rnd, category),
    )
    pick_id = cur.lastrowid
    cur.execute("UPDATE draw_picks SET position_key=%s WHERE id=%s", (position_key or pick_id, pick_id))
    return pick_id


def cancel_pick(conn, pick_id: int, replaced_by: Optional[int] = None) -> None:
    conn.cursor().execute(
        "UPDATE draw_picks SET cancelled_at=NOW(), replaced_by=%s WHERE id=%s AND cancelled_at IS NULL",
        (replaced_by, pick_id),
    )


def update_payment(conn, applicant_id: int, status: str, comment: str) -> None:
    conn.cursor().execute(
        "UPDATE draw_applicants SET payment_status=%s, payment_comment=%s, payment_updated_at=NOW() WHERE id=%s",
        (status, comment[:500], applicant_id),
    )


def update_payment_status(conn, applicant_id: int, status: str) -> None:
    """Только статус (автопередача/сброс): комментарий директора не трогаем."""
    conn.cursor().execute(
        "UPDATE draw_applicants SET payment_status=%s, payment_updated_at=NOW() WHERE id=%s",
        (status, applicant_id),
    )


def audit(conn, year: int, applicant_id: int, action: str, old: str, new: str,
          ref_applicant_id: Optional[int], user: str) -> None:
    conn.cursor().execute(
        "INSERT INTO draw_audit (draw_year, applicant_id, action, old_value, new_value, "
        "ref_applicant_id, admin_user, created_at) VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())",
        (year, applicant_id, action, old, new, ref_applicant_id, user or ""),
    )


def load_year_audit(conn, year: int) -> list[dict]:
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT applicant_id, action, old_value, new_value, ref_applicant_id, admin_user, created_at "
                "FROM draw_audit WHERE draw_year=%s ORDER BY id", (year,))
    return cur.fetchall()


def load_audit(conn, year: int, applicant_id: int) -> list[dict]:
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT action, old_value, new_value, admin_user, created_at FROM draw_audit "
                "WHERE draw_year=%s AND applicant_id=%s ORDER BY id", (year, applicant_id))
    return cur.fetchall()


def last_auto_invite(conn, year: int, ref_applicant_id: int) -> Optional[int]:
    """Кому поставили ⏳ автоматически из-за неоплаты ref_applicant_id (последний раз)."""
    cur = conn.cursor()
    cur.execute("SELECT applicant_id FROM draw_audit WHERE draw_year=%s AND action='auto_invite' "
                "AND ref_applicant_id=%s ORDER BY id DESC LIMIT 1", (year, ref_applicant_id))
    row = cur.fetchone()
    return row[0] if row else None


def set_round(conn, year: int, rnd: int) -> None:
    conn.cursor().execute("UPDATE draw_config SET current_round=%s WHERE draw_year=%s", (rnd, year))


def save_config(conn, year: int, values: dict) -> None:
    allowed = (*CONFIG_INT_FIELDS, "auto_invite_until")
    keys = [k for k in values if k in allowed]
    if not keys:
        return
    ensure_config(conn, year)
    conn.cursor().execute(
        f"UPDATE draw_config SET {', '.join(f'{k}=%s' for k in keys)} WHERE draw_year=%s",
        (*[values[k] for k in keys], year),
    )


def replace_applicants(conn, year: int, apps: list[dict]) -> None:
    """Заявки года целиком заменяются (журнал и аудит — тоже, каскадом/явно)."""
    ensure_config(conn, year)
    cur = conn.cursor()
    cur.execute("DELETE FROM draw_audit WHERE draw_year=%s", (year,))
    cur.execute("DELETE FROM draw_applicants WHERE draw_year=%s", (year,))
    cur.executemany(
        f"INSERT INTO draw_applicants (draw_year, {', '.join(APPLICANT_COLUMNS)}) "
        f"VALUES (%s, {', '.join(['%s'] * len(APPLICANT_COLUMNS))})",
        [(year, *[a.get(c) if c in ("entry_id", "person_id") else a[c] for c in APPLICANT_COLUMNS]) for a in apps],
    )
    cur.execute("UPDATE draw_config SET imported_at=NOW(), current_round=0 WHERE draw_year=%s", (year,))


def reset_draw(conn, year: int) -> None:
    """После репетиции: журнал, аудит и статусы оплаты года — с нуля, раунд 0."""
    cur = conn.cursor()
    cur.execute("DELETE FROM draw_picks WHERE draw_year=%s", (year,))
    cur.execute("DELETE FROM draw_audit WHERE draw_year=%s", (year,))
    cur.execute("UPDATE draw_applicants SET payment_status='none', payment_comment='', "
                "payment_updated_at=NULL WHERE draw_year=%s", (year,))
    cur.execute("UPDATE draw_config SET current_round=0 WHERE draw_year=%s", (year,))


def siberman_history(conn, surname: str, name: str) -> dict:
    """Годы стартов (лично/эстафета) и личных финишей Siberman — из архива 2016+ (participants)."""
    return siberman_histories(conn, [{"id": 0, "surname": surname, "name": name}])[0]


def siberman_histories(conn, apps: list[dict]) -> dict:
    """То же для многих заявок (страница ведущих) — архив читается один раз: {id заявки: история}."""
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT race_year, format, surname, name FROM participants")
    years: dict[str, dict] = {}
    for r in cur.fetchall():
        years.setdefault(person_key(r["surname"], r["name"]), {"individual": set(), "relay": set()})[r["format"]].add(
            r["race_year"])
    finished = get_finished_years_by_name(conn)
    out = {}
    for a in apps:
        key = person_key(a["surname"], a["name"])
        y = years.get(key, {"individual": set(), "relay": set()})
        out[a["id"]] = {"individual": sorted(y["individual"]), "relay": sorted(y["relay"]),
                        "finished": sorted(finished.get(key, set()))}
    return out


def linked_histories(conn, applicants: list[dict]) -> dict:
    """Archive starts, finishes and participation in draws by the resolved person ID."""
    histories = {a["id"]: {"individual": [], "relay": [], "finished": [], "draws": []} for a in applicants}
    people = {a["person_id"] for a in applicants if a.get("person_id") is not None}
    if not people:
        return histories
    marks = ", ".join(["%s"] * len(people))
    args = sorted(people)
    by_person = {pid: {"individual": set(), "relay": set(), "draws": set()} for pid in people}
    with conn.cursor(dictionary=True, buffered=True) as cur:
        cur.execute(f"""
            SELECT l.person_id,p.race_year,p.format
            FROM siberman_person_links l JOIN participants p
              ON p.race_year=l.race_year AND p.bib=l.bib AND p.relay_stage=l.relay_stage
            WHERE l.person_id IN ({marks})
              AND (p.status IN ('dnf','dsq') OR (p.status='active' AND EXISTS (
                   SELECT 1 FROM checkpoint_times t WHERE t.participant_id=p.id AND t.cumulative_s IS NOT NULL)))
        """, args)
        for row in cur.fetchall():
            by_person[row["person_id"]][row["format"]].add(row["race_year"])
        cur.execute(f"""
            SELECT a.person_id,a.draw_year FROM draw_applicants a
            LEFT JOIN siberman_entries e ON e.id=a.entry_id
            JOIN siberman_persons person ON person.id=a.person_id
            WHERE a.person_id IN ({marks})
              AND (e.birthdate IS NULL OR person.birthdate IS NULL OR e.birthdate=person.birthdate)
              AND EXISTS (
                SELECT 1 FROM draw_picks p WHERE p.draw_year=a.draw_year AND p.cancelled_at IS NULL)
            UNION SELECT person_id,draw_year FROM siberman_draw_archive_links WHERE person_id IN ({marks})
        """, args * 2)
        for row in cur.fetchall():
            by_person[row["person_id"]]["draws"].add(row["draw_year"])
    finished = get_finished_years_by_person(conn)
    for a in applicants:
        pid = a.get("person_id")
        if pid is not None:
            histories[a["id"]] = {**{k: sorted(v) for k, v in by_person[pid].items()},
                                   "finished": sorted(finished.get(pid, set()))}
    return histories


def entry_contacts(conn, year: int) -> dict:
    with conn.cursor(dictionary=True, buffered=True) as cur:
        cur.execute("""
            SELECT id,tranid,surname,name,format,email,phone,wildcard_reason,results_text
            FROM siberman_entries WHERE race_year=%s
        """, (year + 1,))
        return {r["id"]: r for r in cur.fetchall()}


def archive_draw_years(conn, before_year: int) -> dict:
    with conn.cursor(dictionary=True, buffered=True) as cur:
        cur.execute("SELECT person_id, draw_year FROM siberman_draw_archive_links "
                    "WHERE draw_year < %s AND person_id IS NOT NULL", (before_year,))
        result = {}
        for row in cur.fetchall():
            result.setdefault(row["person_id"], []).append(row["draw_year"])
        return result


def person_ids_by_key(conn) -> dict:
    """ФИ (persons.linking.plain_key) → id человека реестра; у тёзок с одним ФИ — None (не угадываем).
    Без реестра (миграция 014) — пусто."""
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT id, surname, name FROM siberman_persons")
    except mysql.connector.Error as e:
        if e.errno != errorcode.ER_NO_SUCH_TABLE:
            raise
        return {}
    out: dict = {}
    for r in cur.fetchall():
        key = plain_key(r["surname"], r["name"])
        out[key] = None if key in out else r["id"]
    return out


# ── Контакты для счетов (draw_contacts, миграция 016) ───────────────────────

def replace_contacts(conn, year: int, contacts: dict) -> None:
    """Контакты года целиком заменяются новой выгрузкой заявок Тильды."""
    cur = conn.cursor()
    cur.execute("DELETE FROM draw_contacts WHERE draw_year=%s", (year,))
    cur.executemany("INSERT INTO draw_contacts (draw_year, format, fio_key, email, phone, wildcard_reason, results_text) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    [(year, fmt, key, c["email"][:255], c["phone"][:64], c["wildcard_reason"], c["results_text"])
                     for (fmt, key), c in contacts.items()])


def load_contacts(conn, year: int) -> dict:
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT format, fio_key, email, phone, wildcard_reason, results_text FROM draw_contacts "
                "WHERE draw_year=%s", (year,))
    return {(r["format"], r["fio_key"]): {"email": r["email"], "phone": r["phone"],
                                          "wildcard_reason": r["wildcard_reason"] or "",
                                          "results_text": r["results_text"] or ""} for r in cur.fetchall()}


def update_texts(conn, rows: list[dict]) -> None:
    """[{id, wildcard_reason, results_text}] — тексты заявки Тильды в заявки жеребьёвки."""
    if rows:
        conn.cursor().executemany("UPDATE draw_applicants SET wildcard_reason=%(wildcard_reason)s, "
                                  "results_text=%(results_text)s WHERE id=%(id)s", rows)
