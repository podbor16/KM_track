"""
Рейтинг, рекорды, статистика, география и страницы спортсменов Siberman: снимок архива в памяти воркера на CACHE_TTL_S (спецификация hall §2).
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
from src.siberman.hall.athlete import build_athletes
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
    places = hgeo.resolve_places(entries, persons, applicants, hgeo.load_cities())
    geo = hgeo.build_geo(entries, places)
    rating = build_rating(entries, teams, records)
    athletes = build_athletes(entries, teams, records, places, persons)
    slugs = {p.id: p.bib_individual or f"r{p.id}" for p in persons}
    for part in (records, rating, geo):
        _add_slugs(part, slugs)
    for pid, page in athletes.items():
        page["person"]["slug"] = slugs.get(pid, f"r{pid}")
    return {"records": records, "rating": rating, "stats": build_stats(entries, teams, geo), "geo": geo,
            "athletes": athletes, "by_slug": {s: pid for pid, s in slugs.items()}}


def _add_slugs(obj, slugs: dict) -> None:
    """Каждой записи с person_id (рейтинг, рекорды, география) — slug для ссылки на страницу спортсмена:
    личный стартовый номер (закреплён за человеком навсегда), без него — r{id}; вне реестра — None."""
    if isinstance(obj, dict):
        if "person_id" in obj:
            obj["slug"] = slugs.get(obj["person_id"])
        for v in obj.values():
            _add_slugs(v, slugs)
    elif isinstance(obj, list):
        for v in obj:
            _add_slugs(v, slugs)


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


def athlete(person_id: int) -> Optional[dict]:
    return _snapshot()["athletes"].get(person_id)


def athlete_by_slug(slug: str) -> tuple:
    """Страница по адресу /athlete/{slug} → (страница или None, куда перенаправить или None). Адрес r{id}
    у человека с личным номером (эстафетчик потом вышел лично) перенаправляется на номер."""
    snap = _snapshot()
    if slug[:1] == "r" and slug[1:].isascii() and slug[1:].isdigit():
        page = snap["athletes"].get(int(slug[1:]))
        return page, (page["person"]["slug"] if page and page["person"]["slug"] != slug else None)
    pid = snap["by_slug"].get(slug)
    return (snap["athletes"].get(pid) if pid is not None else None), None


def athlete_page(slug: str) -> Optional[dict]:
    return athlete_by_slug(slug)[0]
