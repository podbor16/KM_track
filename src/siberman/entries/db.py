"""Слой БД заявок Siberman — siberman_entries, siberman_entries_audit (миграция 018_entries.sql)."""
import json
from typing import Optional

FORM_FIELDS = ("formid", "format", "surname", "name", "gender", "birthdate", "city", "email", "phone", "team_name",
               "relay_swim", "relay_bike", "relay_run", "wildcard_reason", "results_text", "result_url")
LIST_FIELDS = ("id", "race_year", "tranid", "submitted_at", *FORM_FIELDS, "status", "comment",
               "status_updated_at", "status_by")


def upsert(conn, year: int, e: dict, submitted_at) -> bool:
    """True — новая заявка. Повтор того же tranid обновляет поля формы и raw; год, время подачи, статус и
    комментарий не трогает."""
    cols = ", ".join(FORM_FIELDS)
    cur = conn.cursor()
    cur.execute(
        f"INSERT INTO siberman_entries (race_year, tranid, submitted_at, raw, {cols}) "
        f"VALUES (%s, %s, %s, %s, {', '.join(['%s'] * len(FORM_FIELDS))}) "
        f"ON DUPLICATE KEY UPDATE {', '.join(f'{c}=VALUES({c})' for c in FORM_FIELDS)}, raw=VALUES(raw)",
        (year, e["tranid"], submitted_at, json.dumps(e["raw"], ensure_ascii=False), *[e[c] for c in FORM_FIELDS]))
    return cur.rowcount == 1          # MySQL: 1 — вставка, 2 — обновление, 0 — без изменений


def known_tranids(conn, tranids: list) -> set:
    if not tranids:
        return set()
    cur = conn.cursor()
    cur.execute(f"SELECT tranid FROM siberman_entries WHERE tranid IN ({', '.join(['%s'] * len(tranids))})", tranids)
    return {r[0] for r in cur.fetchall()}


def list_year(conn, year: int) -> list[dict]:
    cur = conn.cursor(dictionary=True)
    cur.execute(f"SELECT {', '.join(LIST_FIELDS)} FROM siberman_entries WHERE race_year=%s ORDER BY submitted_at, id",
                (year,))
    return cur.fetchall()


def get(conn, entry_id: int) -> Optional[dict]:
    cur = conn.cursor(dictionary=True)
    cur.execute(f"SELECT {', '.join(LIST_FIELDS)} FROM siberman_entries WHERE id=%s", (entry_id,))
    return cur.fetchone()


def years(conn) -> list[int]:
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT race_year FROM siberman_entries ORDER BY race_year")
    return [r[0] for r in cur.fetchall()]


def update(conn, entry_id: int, field: str, old: str, new: str, user: str) -> None:
    """status или comment + запись в журнал — одной транзакцией."""
    assert field in ("status", "comment")
    conn.start_transaction()
    try:
        cur = conn.cursor()
        if field == "status":
            cur.execute("UPDATE siberman_entries SET status=%s, status_updated_at=NOW(), status_by=%s WHERE id=%s",
                        (new, user[:64], entry_id))
        else:
            cur.execute("UPDATE siberman_entries SET comment=%s WHERE id=%s", (new, entry_id))
        cur.execute("INSERT INTO siberman_entries_audit (entry_id, action, old_value, new_value, admin_user, created_at) "
                    "VALUES (%s, %s, %s, %s, %s, NOW())", (entry_id, field, old, new, user[:64]))
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def audit(conn, entry_id: int) -> list[dict]:
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT action, old_value, new_value, admin_user, created_at FROM siberman_entries_audit "
                "WHERE entry_id=%s ORDER BY id", (entry_id,))
    return cur.fetchall()


def public_rows(conn, year: int) -> list[dict]:
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT id, surname, name, format, status FROM siberman_entries WHERE race_year=%s", (year,))
    return cur.fetchall()
