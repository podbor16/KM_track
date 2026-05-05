"""
SQL-запросы для страницы бизнес-аналитики.
Читает данные из существующих таблиц: events, results.
"""

import logging
import time
from typing import Any

from .db_pool import get_pooled_connection

logger = logging.getLogger(__name__)

_business_cache: dict = {}
_business_cache_ts: dict = {}
BUSINESS_CACHE_TTL = 300  # 5 минут — данные не live


def _cached(key: str, fn):
    now = time.time()
    if key in _business_cache and (now - _business_cache_ts.get(key, 0)) < BUSINESS_CACHE_TTL:
        return _business_cache[key]
    result = fn()
    _business_cache[key] = result
    _business_cache_ts[key] = now
    return result


def get_event_summary() -> list[dict[str, Any]]:
    """Сводная таблица всех событий: участники, финишировавшие, дистанция, год."""
    def _query():
        conn = get_pooled_connection()
        if not conn:
            return []
        try:
            cur = conn.cursor(dictionary=True, buffered=True)
            cur.execute("""
                SELECT
                    e.id AS event_id,
                    e.event_name,
                    e.event_year,
                    e.event_distance,
                    e.event_date,
                    COUNT(r.id)                                               AS total,
                    COALESCE(SUM(r.race_status = 'Finished'), 0)           AS finished,
                    COALESCE(SUM(r.race_status NOT IN ('Finished', 'DNS')), 0) AS dnf,
                    COALESCE(SUM(r.race_status = 'DNS'), 0)                AS dns
                FROM events e
                LEFT JOIN results r ON r.event_id = e.id
                GROUP BY e.id, e.event_name, e.event_year, e.event_distance, e.event_date
                ORDER BY e.event_year DESC, e.event_name ASC, e.event_distance ASC
            """)
            rows = [dict(r) for r in cur.fetchall()]
            cur.close()
            return rows
        except Exception as e:
            logger.error(f"get_event_summary error: {e}")
            return []
        finally:
            try:
                conn.close()
            except Exception:
                pass

    return _cached("event_summary", _query)


def get_participants_by_year() -> list[dict[str, Any]]:
    """Динамика числа участников по годам и дистанциям."""
    def _query():
        conn = get_pooled_connection()
        if not conn:
            return []
        try:
            cur = conn.cursor(dictionary=True, buffered=True)
            cur.execute("""
                SELECT
                    e.event_year    AS year,
                    e.event_name    AS event_name,
                    e.event_distance AS distance,
                    COUNT(r.id)                                    AS total,
                    COALESCE(SUM(r.race_status = 'Finished'), 0)  AS finished
                FROM events e
                LEFT JOIN results r ON r.event_id = e.id
                GROUP BY e.event_year, e.event_name, e.event_distance
                ORDER BY e.event_year ASC, e.event_name ASC
            """)
            rows = [dict(r) for r in cur.fetchall()]
            cur.close()
            return rows
        except Exception as e:
            logger.error(f"get_participants_by_year error: {e}")
            return []
        finally:
            try:
                conn.close()
            except Exception:
                pass

    return _cached("participants_by_year", _query)


def get_top_cities(limit: int = 15) -> list[dict[str, Any]]:
    """Топ городов участников по числу регистраций."""
    def _query():
        conn = get_pooled_connection()
        if not conn:
            return []
        try:
            cur = conn.cursor(dictionary=True, buffered=True)
            cur.execute("""
                SELECT
                    TRIM(r.city)          AS city,
                    COUNT(r.id)           AS count
                FROM results r
                WHERE r.city IS NOT NULL AND TRIM(r.city) != ''
                GROUP BY TRIM(r.city)
                ORDER BY count DESC
                LIMIT %s
            """, (limit,))
            rows = [dict(r) for r in cur.fetchall()]
            cur.close()
            return rows
        except Exception as e:
            logger.error(f"get_top_cities error: {e}")
            return []
        finally:
            try:
                conn.close()
            except Exception:
                pass

    return _cached(f"top_cities_{limit}", _query)


def get_gender_breakdown() -> list[dict[str, Any]]:
    """Соотношение полов по каждому событию."""
    def _query():
        conn = get_pooled_connection()
        if not conn:
            return []
        try:
            cur = conn.cursor(dictionary=True, buffered=True)
            cur.execute("""
                SELECT
                    e.event_name,
                    e.event_year,
                    e.event_distance,
                    COALESCE(SUM(r.sex IN ('мужчина', 'male', 'м', 'M', 'Мужской')), 0) AS male_count,
                    COALESCE(SUM(r.sex IN ('женщина', 'female', 'ж', 'F', 'Женский')), 0) AS female_count,
                    COUNT(r.id) AS total
                FROM events e
                LEFT JOIN results r ON r.event_id = e.id
                GROUP BY e.id, e.event_name, e.event_year, e.event_distance
                ORDER BY e.event_year DESC, e.event_name ASC
            """)
            rows = [dict(r) for r in cur.fetchall()]
            cur.close()
            return rows
        except Exception as e:
            logger.error(f"get_gender_breakdown error: {e}")
            return []
        finally:
            try:
                conn.close()
            except Exception:
                pass

    return _cached("gender_breakdown", _query)
