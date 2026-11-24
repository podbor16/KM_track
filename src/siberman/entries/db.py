"""Слой БД заявок Siberman — siberman_entries, siberman_entries_audit (миграция 018_entries.sql)."""
import json
from typing import Optional

FORM_FIELDS = ("formid", "format", "surname", "name", "gender", "birthdate", "city", "email", "phone", "team_name",
               "relay_swim", "relay_bike", "relay_run", "wildcard_reason", "results_text", "result_url")
LIST_FIELDS = ("id", "race_year", "tranid", "submitted_at", *FORM_FIELDS, "status", "comment",
               "status_updated_at", "status_by")


def upsert(conn, year: int, e: dict, submitted_at) -> bool:
    """True — новая заявка. Повтор того же tranid обновляет поля формы непустыми значениями (пустые/отсутствующие
    не затирают сохранённые), raw сливается (JSON_MERGE_PATCH); год, время подачи, статус и комментарий не трогает."""
    cols = ", ".join(FORM_FIELDS)
    keep = ", ".join(f"{c}=COALESCE(VALUES({c}), {c})" if c == "birthdate" else   # DATE: NULLIF с '' недопустим
                     f"{c}=COALESCE(NULLIF(VALUES({c}), ''), {c})" for c in FORM_FIELDS)
    cur = conn.cursor()
    cur.execute(
        f"INSERT INTO siberman_entries (race_year, tranid, submitted_at, raw, {cols}) "
        f"VALUES (%s, %s, %s, %s, {', '.join(['%s'] * len(FORM_FIELDS))}) "
        f"ON DUPLICATE KEY UPDATE {keep}, raw=JSON_MERGE_PATCH(COALESCE(raw, JSON_OBJECT()), VALUES(raw))",
        (year, e["tranid"], submitted_at, json.dumps(e["raw"], ensure_ascii=False), *[e[c] for c in FORM_FIELDS]))
    return cur.rowcount == 1          # MySQL: 1 — вставка, 2 — обновление, 0 — без изменений


def known_tranids(conn, tranids: list) -> dict:
    """{tranid: race_year} для уже сохранённых заявок."""
    if not tranids:
        return {}
    cur = conn.cursor()
    cur.execute(f"SELECT tranid, race_year FROM siberman_entries "
                f"WHERE tranid IN ({', '.join(['%s'] * len(tranids))})", tranids)
    return {r[0]: r[1] for r in cur.fetchall()}


def list_year(conn, year: int) -> list[dict]:
    cur = conn.cursor(dictionary=True)
    cur.execute(f"SELECT {', '.join(LIST_FIELDS)} FROM siberman_entries WHERE race_year=%s ORDER BY submitted_at, id",
                (year,))
    return cur.fetchall()


def admitted_for_draw(conn, race_year: int) -> list[dict]:
    """Минимальные поля одобренных заявок для чернового расчёта жеребьёвки."""
    cur = conn.cursor(dictionary=True)
    cur.execute(
        "SELECT id, race_year, format, surname, name, gender, birthdate, city, team_name, "
        "relay_swim, relay_bike, relay_run, raw FROM siberman_entries "
        "WHERE race_year=%s AND status='admitted' ORDER BY submitted_at, id",
        (race_year,),
    )
    rows = cur.fetchall()
    for row in rows:
        raw = row.get("raw")
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except (ValueError, TypeError):
                raw = {}
        row["raw"] = raw if isinstance(raw, dict) else {}
    return rows


def identity_rows(conn, race_years: list[int]) -> list[dict]:
    """Names, birth dates and entry status used only to disambiguate historical draw identities."""
    years = sorted({int(y) for y in race_years})
    if not years:
        return []
    marks = ", ".join(["%s"] * len(years))
    cur = conn.cursor(dictionary=True, buffered=True)
    cur.execute(f"SELECT race_year, format, surname, name, birthdate, status "
                f"FROM siberman_entries WHERE race_year IN ({marks})", years)
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
        try:
            conn.rollback()
        except Exception:
            pass                              # соединение оборвалось — не скрываем исходную ошибку
        raise


def audit(conn, entry_id: int) -> list[dict]:
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT action, old_value, new_value, admin_user, created_at FROM siberman_entries_audit "
                "WHERE entry_id=%s ORDER BY id", (entry_id,))
    return cur.fetchall()


def record_identity(conn, entry_id: int, previous: int | None, person_id: int | None, is_new: bool, user: str) -> None:
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO siberman_entry_person_links (entry_id, person_id, is_new) VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE person_id=VALUES(person_id), is_new=VALUES(is_new)
        """, (entry_id, person_id, is_new))
        cur.execute("""
            INSERT INTO siberman_entries_audit (entry_id, action, old_value, new_value, admin_user, created_at)
            VALUES (%s, 'identity', %s, %s, %s, NOW())
        """, (entry_id, None if previous is None else str(previous),
              None if person_id is None else str(person_id), user[:64]))
        # Rows survive until the next Excel import and see this decision immediately.
        cur.execute("""
            UPDATE draw_config c JOIN draw_applicants a ON a.draw_year=c.draw_year
            SET c.version=c.version+1, a.person_id=%s WHERE a.entry_id=%s
        """, (person_id, entry_id))


def draw_identity_conflict(conn, entry_id: int, person_id: int) -> bool:
    with conn.cursor(buffered=True) as cur:
        cur.execute("""
            SELECT 1 FROM draw_applicants a JOIN draw_applicants b ON a.draw_year=b.draw_year AND a.id<>b.id
            WHERE a.entry_id=%s AND b.person_id=%s LIMIT 1
        """, (entry_id, person_id))
        return cur.fetchone() is not None


def update_source_contacts(conn, entry_id: int, source: dict) -> None:
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE siberman_entries SET email=COALESCE(NULLIF(%s,''),email),
              phone=COALESCE(NULLIF(%s,''),phone), wildcard_reason=COALESCE(NULLIF(%s,''),wildcard_reason),
              results_text=COALESCE(NULLIF(%s,''),results_text) WHERE id=%s
        """, (source["email"], source["phone"], source["wildcard_reason"], source["results_text"], entry_id))


def public_rows(conn, year: int) -> list[dict]:
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT id, surname, name, format, status FROM siberman_entries WHERE race_year=%s", (year,))
    return cur.fetchall()
