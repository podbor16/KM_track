"""Срок публичной доступности результатов: 30 лет от даты старта."""

from datetime import date, datetime
from functools import lru_cache
from zoneinfo import ZoneInfo

from src.analytics.db_pool import get_pooled_connection


def local_today() -> date:
    return datetime.now(ZoneInfo("Asia/Krasnoyarsk")).date()


def is_within_publication_term(event_date: date | None, today: date | None = None) -> bool:
    """В день 30-й годовщины публикация уже прекращается."""
    if event_date is None:
        return False
    if isinstance(event_date, datetime):
        event_date = event_date.date()
    today = today or local_today()
    try:
        expires = event_date.replace(year=event_date.year + 30)
    except ValueError:  # 29 февраля в невисокосном году
        expires = event_date.replace(year=event_date.year + 30, day=28)
    return today < expires


@lru_cache(maxsize=1024)
def _event_dates(event_id: int, today: date) -> tuple[date, ...]:
    conn = get_pooled_connection()
    if not conn:
        raise RuntimeError("Не удалось проверить срок публикации: БД недоступна")
    try:
        cur = conn.cursor()
        cur.execute("SELECT event_date FROM events WHERE id = %s", (event_id,))
        rows = cur.fetchall()
        cur.close()
        return tuple(row[0] for row in rows)
    finally:
        conn.close()


def event_is_public(event_id: int, today: date | None = None) -> bool:
    today = today or local_today()
    dates = _event_dates(int(event_id), today)
    return bool(dates) and all(is_within_publication_term(d, today) for d in dates)


@lru_cache(maxsize=512)
def _name_year_dates(name: str, year: int, today: date) -> tuple[date, ...]:
    conn = get_pooled_connection()
    if not conn:
        raise RuntimeError("Не удалось проверить срок публикации: БД недоступна")
    try:
        cur = conn.cursor()
        cur.execute("SELECT e.event_date FROM events e WHERE e.event_name = %s AND e.event_year = %s "
                    "AND (e.event_date IS NOT NULL OR EXISTS "
                    "(SELECT 1 FROM results r WHERE r.event_id = e.id))", (name, year))
        rows = cur.fetchall()
        cur.close()
        return tuple(row[0] for row in rows)
    finally:
        conn.close()


def event_name_year_is_public(name: str, year: int, today: date | None = None) -> bool:
    today = today or local_today()
    dates = _name_year_dates(name, int(year), today)
    return bool(dates) and all(is_within_publication_term(d, today) for d in dates)


def event_name_is_public(name: str | None, today: date | None = None) -> bool:
    """Legacy-статистика не разделена по годам: скрываем весь ответ при старых строках."""
    today = today or local_today()
    conn = get_pooled_connection()
    if not conn:
        raise RuntimeError("Не удалось проверить срок публикации: БД недоступна")
    try:
        cur = conn.cursor()
        if name:
            cur.execute("SELECT e.event_date FROM events e WHERE e.event_name = %s "
                        "AND EXISTS (SELECT 1 FROM results r WHERE r.event_id = e.id)", (name,))
        else:
            cur.execute("SELECT e.event_date FROM events e "
                        "WHERE EXISTS (SELECT 1 FROM results r WHERE r.event_id = e.id)")
        dates = [row[0] for row in cur.fetchall()]
        cur.close()
        return bool(dates) and all(is_within_publication_term(d, today) for d in dates)
    finally:
        conn.close()


def _result_event_id(result_id: int) -> int | None:
    conn = get_pooled_connection()
    if not conn:
        raise RuntimeError("Не удалось проверить срок публикации: БД недоступна")
    try:
        cur = conn.cursor()
        cur.execute("SELECT event_id FROM results WHERE id = %s", (result_id,))
        row = cur.fetchone()
        cur.close()
        return int(row[0]) if row else None
    finally:
        conn.close()


def result_is_public(result_id: int, today: date | None = None) -> bool:
    event_id = _result_event_id(int(result_id))
    return event_id is not None and event_is_public(event_id, today)


PUBLIC_EVENT_SQL = "(e.event_date IS NOT NULL AND DATE_ADD(e.event_date, INTERVAL 30 YEAR) > %s)"
