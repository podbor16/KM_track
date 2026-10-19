"""Слой БД жеребьёвки — таблицы draw_* (миграция src/siberman/migrations/013_draw.sql)."""
import datetime
from typing import Optional

from src.siberman.db import get_finished_years_by_name
from src.siberman.finish_counts import person_key

CONFIG_INT_FIELDS = ("capacity_men", "capacity_women", "capacity_relay", "quota_repeat_men",
                     "quota_repeat_women", "quota_novice_men", "quota_novice_women")
APPLICANT_COLUMNS = ("format", "surname", "name", "gender", "city", "pool", "is_wildcard", "chances",
                     "starts_individual", "starts_relay", "draw_accumulated", "is_local",
                     "duathlon_222", "race_24h", "tattoo", "relay_swim", "relay_bike", "relay_run",
                     "wildcard_reason", "results_text")


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


def load_applicants(conn, year: int) -> list[dict]:
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM draw_applicants WHERE draw_year=%s ORDER BY surname, name", (year,))
    rows = cur.fetchall()
    for r in rows:
        r["is_wildcard"] = bool(r["is_wildcard"])
    return rows


def load_picks(conn, year: int) -> list[dict]:
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM draw_picks WHERE draw_year=%s ORDER BY id", (year,))
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
        [(year, *[a[c] for c in APPLICANT_COLUMNS]) for a in apps],
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
    key = person_key(surname, name)
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT race_year, format, surname, name FROM participants")
    years: dict[str, set] = {"individual": set(), "relay": set()}
    for r in cur.fetchall():
        if person_key(r["surname"], r["name"]) == key:
            years[r["format"]].add(r["race_year"])
    finished = get_finished_years_by_name(conn).get(key, set())
    return {"individual": sorted(years["individual"]), "relay": sorted(years["relay"]),
            "finished": sorted(finished)}
