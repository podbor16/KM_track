"""Личный кабинет (этап А): заявки, оформленные с почты (leads.email или ma_email), по людям —
задел под этап Б, где человек заявит карточку. Правила — спецификация 2026-11-03-athlete-login-design."""

import datetime as dt
from typing import Optional
from urllib.parse import quote

from src.analytics.db_pool import get_pooled_connection
from src.config import settings

_SQL = """
    SELECT l.id, l.client_id, l.surname, l.name, l.event_id, l.start_number, l.refund,
           l.event_name, l.event_distance, l.event_year, e.event_date,
           r.race_status, r.time_clear_finish, r.time_gun_finish, r.rank_category, r.rank_category_clean
    FROM leads l
    LEFT JOIN events e ON e.id = l.event_id
    LEFT JOIN results r ON r.event_id = l.event_id AND r.start_number = l.start_number
    WHERE (LOWER(l.email) = %s OR LOWER(l.ma_email) = %s) AND l.is_duplicate = 0
    ORDER BY l.id
"""


def fetch_leads(email: str) -> list[dict]:
    """Заявки почты; при двух результатах с одним номером — одна строка на заявку."""
    conn = get_pooled_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(_SQL, (email, email))
        rows = {}
        for row in cur.fetchall():
            rows.setdefault(row["id"], row)
        cur.close()
        return list(rows.values())
    finally:
        conn.close()


def _norm(s: Optional[str]) -> str:
    return (s or "").strip().lower().replace("ё", "е")


def fmt_time(td: Optional[dt.timedelta]) -> Optional[str]:
    if td is None:
        return None
    s = int(td.total_seconds())
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}"


def protocol_url(event_name: str, year: int, surname: str, codes: dict) -> Optional[str]:
    code = codes.get(event_name)
    if not code:
        return None
    return f"/results?event={code}&year={year}&search={quote(surname or '')}"


def finish_info(r: dict) -> tuple[bool, Optional[dt.timedelta], Optional[int]]:
    """(финиш?, время, место в категории) строки с полями результата. Время — чистое, иначе по выстрелу;
    место — «чистое» только при чистом времени."""
    clean = r["time_clear_finish"] is not None
    td = r["time_clear_finish"] if clean else r["time_gun_finish"]
    finished = r["race_status"] == "Finished" and td is not None
    place = ((r["rank_category_clean"] or r["rank_category"]) if clean else r["rank_category"]) if finished else None
    return finished, td, place


def is_upcoming(date: Optional[dt.date], year: Optional[int], today: dt.date) -> bool:
    """Предстоящая: дата ≥ сегодня, а если даты нет — год пустой или ≥ текущего."""
    if date is None:
        return not year or year >= today.year
    return date >= today


def _entry(r: dict, codes: dict) -> dict:
    finished, td, place = finish_info(r)
    return {
        "lead_id": r["id"],
        "event_id": r["event_id"],
        "event_name": r["event_name"],
        "distance": r["event_distance"],
        "date": r["event_date"],
        "year": r["event_year"],
        "start_number": r["start_number"],
        "refund": bool(r["refund"]),
        "time": fmt_time(td) if finished else None,
        "place": place,
        "protocol_url": protocol_url(r["event_name"], r["event_year"], r["surname"], codes) if finished else None,
    }


def _past_key(e: dict) -> dt.date:
    return e["date"] or dt.date(e["year"] or 1, 1, 1)


def group_by_person(rows: list[dict], today: dt.date, codes: Optional[dict] = None) -> list[dict]:
    """[{title, upcoming: [...], past: [...]}] в порядке показа."""
    codes = codes or {}
    groups: dict = {}
    for r in sorted(rows, key=lambda r: r["id"]):
        key = ("c", r["client_id"]) if r["client_id"] else ("n", _norm(r["surname"]), _norm(r["name"]))
        g = groups.setdefault(key, {"upcoming": [], "past": []})
        g["title"] = f"{r['surname'] or ''} {r['name'] or ''}".strip()  # перезаписывается — останется самая новая
        e = _entry(r, codes)
        (g["upcoming"] if is_upcoming(e["date"], e["year"], today) else g["past"]).append(e)
    far = dt.date.max
    for g in groups.values():
        g["upcoming"].sort(key=lambda e: e["date"] or far)
        g["past"].sort(key=_past_key, reverse=True)

    def order(g):
        if g["upcoming"]:
            return (0, (g["upcoming"][0]["date"] or far).toordinal())
        return (1, -_past_key(g["past"][0]).toordinal())

    return sorted(groups.values(), key=order)


def cabinet(email: str, today: Optional[dt.date] = None) -> list[dict]:
    codes = {ev.name: ev.code for ev in settings.EVENTS.values()}
    return group_by_person(fetch_leads(email), today or dt.date.today(), codes)
