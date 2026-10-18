"""
География Siberman (спецификация hall §7). Город человека — введённый в админке; нет — последнего
старта с городом; нет — из заявки Тильды с той же ФИ и ДР. Название, страна и координаты —
из справочника data/siberman/cities.json по нормализованному написанию: в протоколах страна бывает
записана по-разному или с ошибкой. Города нет в справочнике — в списках как написан, без точки на карте.
"""
import datetime
import json
import logging
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from src.siberman.hall.data import is_start, person_of
from src.siberman.persons.linking import norm_city, plain_key

log = logging.getLogger(__name__)

CITIES_PATH = Path(__file__).resolve().parents[3] / "data" / "siberman" / "cities.json"


@dataclass(frozen=True)
class City:
    name: str
    country: str
    iso: str                       # ISO 3166-1 numeric страны, 3 цифры; '' — неизвестно
    lat: Optional[float]
    lon: Optional[float]


def load_cities(path: Path = CITIES_PATH) -> dict:
    """Нормализованное написание → City (название и все написания из aliases). Нет файла — пусто; файл
    испорчен (правится руками) — пусто и ошибка в логе: рейтинг и рекорды не должны падать из-за карты."""
    try:
        out = {}
        for r in json.loads(path.read_text(encoding="utf-8")):
            c = City(r["name"], r["country"], r.get("iso") or "", r.get("lat"), r.get("lon"))
            for s in (r["name"], *r.get("aliases", ())):
                out[norm_city(s)] = c
        return out
    except FileNotFoundError:
        return {}
    except (OSError, ValueError, KeyError, TypeError) as e:
        log.error("[siberman/hall] %s не прочитан, география без справочника: %s", path.name, e)
        return {}


def city_of(raw: str, country: str, directory: dict) -> Optional[City]:
    key = norm_city(raw)
    if not key:
        return None
    return directory.get(key) or City(" ".join(raw.split()), (country or "").strip(), "", None, None)


def applicant_cities(persons: list, applicants: list) -> dict:
    """person_id → город из заявки Тильды: ФИ (в любом порядке) и ДР заявки совпадают ровно с одним
    человеком реестра; из нескольких заявок — последняя поданная."""
    by_key = defaultdict(list)
    for p in persons:
        if p.birthdate:
            by_key[plain_key(p.surname, p.name)].append(p)
    out, when = {}, {}
    for a in applicants:
        if not a.birthdate or not norm_city(a.city):
            continue
        cands = {p.id for k in (plain_key(a.surname, a.name), plain_key(a.name, a.surname))
                 for p in by_key.get(k, ()) if p.birthdate == a.birthdate}
        if len(cands) != 1:
            continue
        pid, t = cands.pop(), a.submitted_at or datetime.datetime.min
        if pid not in when or t >= when[pid]:
            out[pid], when[pid] = a.city, t
    return out


def resolve_places(entries: list, persons: list, applicants: list, directory: dict) -> dict:
    """Человек (data.person_of) → City или None; люди — все, у кого есть старт (data.is_start). Город
    из админки или заявки получает страну, с которой этот город чаще пишут в протоколах."""
    found, proto = {}, defaultdict(Counter)
    for e in sorted(entries, key=lambda e: e.year):
        if norm_city(e.city) and e.country:
            proto[norm_city(e.city)][e.country] += 1
        if not is_start(e):
            continue
        k = person_of(e)
        found.setdefault(k, None)
        if norm_city(e.city):
            found[k] = (e.city, e.country)

    def with_country(city: str) -> tuple:
        c = proto.get(norm_city(city))
        return city, c.most_common(1)[0][0] if c else ""

    registry = {p.id: p for p in persons}
    from_apps = applicant_cities(persons, applicants)
    out = {}
    for k, place in found.items():
        p = registry.get(k) if isinstance(k, int) else None
        if p is not None and norm_city(p.city_manual):
            place = with_country(p.city_manual)
        elif place is None and k in from_apps:
            place = with_country(from_apps[k])
        out[k] = city_of(*place, directory) if place else None
    return out


def _last_starts(entries: list) -> dict:
    """Человек → его старты (data.is_start) по годам."""
    out = defaultdict(list)
    for e in sorted(entries, key=lambda e: e.year):
        if is_start(e):
            out[person_of(e)].append(e)
    return out


def build_geo(entries: list, places: dict) -> dict:
    """Люди по городам и странам: человек — один раз, по своему городу; ФИ и ссылка — последнего старта;
    разные написания одного города — одна строка."""
    starts = _last_starts(entries)
    cities, countries = {}, {}
    for k, c in places.items():
        if c is None:
            continue
        last = starts[k][-1]
        row = cities.setdefault((norm_city(c.name), c.country), {
            "name": c.name, "country": c.country, "iso": c.iso, "lat": c.lat, "lon": c.lon, "people": []})
        row["people"].append({"person_id": last.person_id, "fio": last.fio})
        countries.setdefault(c.country, {"name": c.country, "iso": c.iso, "count": 0})["count"] += 1
    for row in cities.values():
        row["people"].sort(key=lambda p: p["fio"])
        row["count"] = len(row["people"])
    return {"total": len(places), "known": sum(c is not None for c in places.values()),
            "countries": sorted(countries.values(), key=lambda r: (-r["count"], r["name"])),
            "cities": sorted(cities.values(), key=lambda r: (-r["count"], r["name"]))}


def missing_report(entries: list, places: dict) -> dict:
    """Для админки «Люди»: люди без известного города (с выступлениями) и города без координат."""
    starts = _last_starts(entries)
    people = [{"person_id": k if isinstance(k, int) else None, "fio": s[-1].fio,
               "starts": [{"year": e.year, "format": e.format, "stage": e.stage, "team": e.team} for e in s]}
              for k, s in starts.items() if places.get(k) is None]
    people.sort(key=lambda p: p["fio"])
    no_coords = {}
    for c in places.values():
        if c is not None and c.lat is None:
            row = no_coords.setdefault((norm_city(c.name), c.country), {"name": c.name, "country": c.country, "count": 0})
            row["count"] += 1
    return {"people": people, "no_coords": sorted(no_coords.values(), key=lambda r: (r["country"], r["name"]))}
