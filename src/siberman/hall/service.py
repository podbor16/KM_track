"""
Рейтинг, рекорды, статистика и география Siberman: снимок архива в памяти воркера на CACHE_TTL_S (спецификация hall §2).
Архив меняется только загрузкой результатов; во время гонки снимок обновляется раз в минуту.
БД недоступна — отдаём прошлый снимок, если он есть, и пробуем снова не раньше чем через RETRY_S
(без снимка до этого сразу 503), чтобы запросы не ждали БД друг за другом под блокировкой.
"""
import logging
import threading
import time
from typing import Optional

import mysql.connector

from src.siberman.db import get_siberman_connection
from src.siberman.hall import data as hdata
from src.siberman.hall import geo as hgeo
from src.siberman.hall.rating import build_rating
from src.siberman.hall.records import build_records
from src.siberman.hall.stats import build_stats

log = logging.getLogger(__name__)

CACHE_TTL_S = 60
RETRY_S = 10


class HallUnavailable(Exception):
    """БД недоступна и снимка нет — роутер отвечает 503."""


_lock = threading.Lock()
_cache = {"at": 0.0, "snap": None, "fail_at": None}


def _build() -> dict:
    conn = get_siberman_connection()
    if conn is None:
        raise HallUnavailable("Данные временно недоступны")
    try:
        entries = hdata.load_entries(conn)
        persons, applicants = hdata.load_people(conn)
    finally:
        conn.close()
    teams = hdata.build_teams(entries)
    records = build_records(entries, teams)
    geo = hgeo.build_geo(entries, hgeo.resolve_places(entries, persons, applicants, hgeo.load_cities()))
    return {"records": records, "rating": build_rating(entries, teams, records),
            "stats": build_stats(entries, teams, geo), "geo": geo}


def _snapshot() -> dict:
    with _lock:
        snap, now = _cache["snap"], time.monotonic()
        if snap is not None and now - _cache["at"] < CACHE_TTL_S:
            return snap
        if snap is None and _cache["fail_at"] is not None and now - _cache["fail_at"] < RETRY_S:
            raise HallUnavailable("Данные временно недоступны")
        try:
            snap = _build()
        except (HallUnavailable, mysql.connector.Error) as e:
            log.warning("[siberman/hall] снимок не обновлён: %s", e)
            _cache["fail_at"] = now
            if _cache["snap"] is not None:
                _cache["at"] = now - CACHE_TTL_S + RETRY_S       # следующая попытка через RETRY_S
                return _cache["snap"]
            raise HallUnavailable("Данные временно недоступны") from None
        _cache.update(at=now, snap=snap, fail_at=None)
        return snap


def clear_cache() -> None:
    with _lock:
        _cache.update(at=0.0, snap=None, fail_at=None)


def rating() -> dict:
    return _snapshot()["rating"]


def records() -> dict:
    r = _snapshot()["records"]
    return {"current": r["current"], "last_year": r["last_year"]}


def record_history(cell: str) -> Optional[list]:
    return _snapshot()["records"]["history"].get(cell)


def stats() -> dict:
    return _snapshot()["stats"]


def geography() -> dict:
    return _snapshot()["geo"]
