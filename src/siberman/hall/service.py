"""
Рейтинг и рекорды Siberman: снимок архива в памяти воркера на CACHE_TTL_S (спецификация hall §2).
Архив меняется только загрузкой результатов; во время гонки снимок обновляется раз в минуту.
БД недоступна — отдаём прошлый снимок, если он есть.
"""
import threading
import time
from typing import Optional

import mysql.connector

from src.siberman.db import get_siberman_connection
from src.siberman.hall import data as hdata
from src.siberman.hall.rating import build_rating
from src.siberman.hall.records import build_records

CACHE_TTL_S = 60


class HallUnavailable(Exception):
    """БД недоступна и снимка нет — роутер отвечает 503."""


_lock = threading.Lock()
_cache = {"at": 0.0, "snap": None}


def _build() -> dict:
    conn = get_siberman_connection()
    if conn is None:
        raise HallUnavailable("Данные временно недоступны")
    try:
        entries = hdata.load_entries(conn)
    finally:
        conn.close()
    teams = hdata.build_teams(entries)
    records = build_records(entries, teams)
    return {"records": records, "rating": build_rating(entries, teams, records)}


def _snapshot() -> dict:
    with _lock:
        snap = _cache["snap"]
        if snap is not None and time.monotonic() - _cache["at"] < CACHE_TTL_S:
            return snap
        try:
            snap = _build()
        except (HallUnavailable, mysql.connector.Error):
            if _cache["snap"] is not None:
                return _cache["snap"]
            raise HallUnavailable("Данные временно недоступны") from None
        _cache.update(at=time.monotonic(), snap=snap)
        return snap


def clear_cache() -> None:
    with _lock:
        _cache.update(at=0.0, snap=None)


def rating() -> dict:
    return _snapshot()["rating"]


def records() -> dict:
    r = _snapshot()["records"]
    return {"current": r["current"], "last_year": r["last_year"]}


def record_history(cell: str) -> Optional[list]:
    return _snapshot()["records"]["history"].get(cell)
