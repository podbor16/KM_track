"""Read started rows from the external 222 and 24-hour race protocols."""
from __future__ import annotations

import logging
import re
import mysql.connector

from src.duathlon222.db import get_duathlon_connection
from src.race_triatleta.db import get_tri_connection

log = logging.getLogger(__name__)

SOURCES = {"duathlon_222", "race_24h"}


def _started_duathlon(row: dict) -> bool:
    return (row["status"] in ("finished", "dnf", "dsq")
            or any(row.get(k) is not None for k in ("run1_s", "bike_s", "run2_s"))
            or int(row.get("checkpoints") or 0) > 0)


def _six_hour(row: dict) -> bool:
    category = str(row.get("category") or "").lower()
    return int(row.get("duration_hours") or 0) == 6 or bool(
        re.search(r"(?:^|\D)6\s*(?:-?\s*(?:час(?:а|ов)?|h))", category)
    )


def _eligible_24h(row: dict) -> bool:
    return not _six_hour(row) and (
        int(row.get("laps") or 0) > 0 or row["status"] in ("finished", "dnf", "dsq")
    )


def _display(row: dict) -> str:
    return " ".join(str(row.get(k) or "").strip() for k in ("surname", "name") if row.get(k)).strip()


def _duathlon_rows() -> list[dict] | None:
    conn = get_duathlon_connection()
    if conn is None:
        return None
    try:
        cur = conn.cursor(dictionary=True, buffered=True)
        cur.execute("""
            SELECT e.id AS event_id, p.id AS result_id, YEAR(e.gun_datetime) AS race_year,
                   p.start_number, p.surname, p.name, p.status, p.birthdate,
                   p.run1_s, p.bike_s, p.run2_s, COUNT(c.id) AS checkpoints
            FROM events e JOIN participants p ON p.event_id=e.id
            LEFT JOIN checkpoints c ON c.participant_id=p.id
            GROUP BY p.id, e.id, e.gun_datetime, p.start_number, p.surname, p.name,
                     p.status, p.birthdate, p.run1_s, p.bike_s, p.run2_s
        """)
        rows = []
        for source_row in cur.fetchall():
            if not _started_duathlon(source_row):
                continue
            row = dict(source_row)
            row.update(category="Личный зачёт", roster=[], participant=_display(row), is_team=False)
            rows.append(row)
        return rows
    except mysql.connector.Error as exc:
        log.warning("[siberman/draw] 222 database unavailable for chance draft: %s", exc)
        return None
    finally:
        conn.close()


def _roster(name: str) -> list[str]:
    return [value.strip() for value in re.split(r"[,/;\n]", name or "") if value.strip()]


def _24h_rows() -> list[dict] | None:
    conn = get_tri_connection()
    if conn is None:
        return None
    try:
        cur = conn.cursor(dictionary=True, buffered=True)
        cur.execute("""
            SELECT e.id AS event_id, p.id AS result_id, p.start_number,
                   COALESCE(e.archive_year, YEAR(e.gun_datetime)) AS race_year, e.duration_hours,
                   p.surname, p.name, p.birthdate, p.status, p.category, COUNT(l.id) AS laps
            FROM events e JOIN participants p ON p.event_id=e.id
            LEFT JOIN laps l ON l.participant_id=p.id AND l.event_id=e.id
            GROUP BY p.id, e.id, e.archive_year, e.gun_datetime, e.duration_hours,
                     p.start_number, p.surname, p.name, p.birthdate, p.status, p.category
        """)
        rows = []
        for source_row in cur.fetchall():
            if not _eligible_24h(source_row):
                continue
            row = dict(source_row)
            roster = _roster(row["name"]) if "эстафет" in (row["category"] or "").lower() else []
            is_team = len(roster) > 1
            row.update(roster=roster if is_team else [],
                       participant=(row["surname"] or "").strip() if is_team else _display(row),
                       is_team=is_team)
            rows.append(row)
        return rows
    except mysql.connector.Error as exc:
        log.warning("[siberman/draw] 24h database unavailable for chance draft: %s", exc)
        return None
    finally:
        conn.close()


def load_protocol(source: str) -> list[dict] | None:
    """Return eligible started source rows, or None when the source DB is unavailable.

    Each row includes stable source IDs and display metadata. Relay/team rows retain
    a roster instead of being expanded, so callers can review each member explicitly.
    """
    if source not in SOURCES:
        raise ValueError(f"unknown external protocol: {source}")
    if source == "duathlon_222":
        return _duathlon_rows()
    return _24h_rows()
