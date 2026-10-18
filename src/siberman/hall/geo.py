"""
География Siberman (спецификация hall §7). Город человека — последнего старта с городом; нет — из
реестра (введён в админке); нет — из заявки Тильды с той же ФИ и ДР. Название, страна и координаты —
из справочника data/siberman/cities.json по нормализованному написанию: в протоколах страна бывает
записана по-разному или с ошибкой. Города нет в справочнике — в списках как написан, без точки на карте.
"""
import datetime
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from src.siberman.hall.data import person_of
from src.siberman.persons.linking import norm_city, plain_key

CITIES_PATH = Path(__file__).resolve().parents[3] / "data" / "siberman" / "cities.json"


@dataclass(frozen=True)
class City:
    name: str
    country: str
    iso: str                       # ISO 3166-1 numeric страны, 3 цифры; '' — неизвестно
    lat: Optional[float]
    lon: Optional[float]


def load_cities(path: Path = CITIES_PATH) -> dict:
    """Нормализованное написание → City (название и все написания из aliases); нет файла — пусто."""
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    out = {}
    for r in rows:
        c = City(r["name"], r["country"], r.get("iso") or "", r.get("lat"), r.get("lon"))
        for s in (r["name"], *r.get("aliases", ())):
            out[norm_city(s)] = c
    return out


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
    """Человек (data.person_of) → City или None; люди — все, у кого есть старт (не dns)."""
    found = {}
    for e in sorted(entries, key=lambda e: e.year):
        if e.status == "dns":
            continue
        k = person_of(e)
        found.setdefault(k, None)
        if norm_city(e.city):
            found[k] = (e.city, e.country)
    registry = {p.id: p for p in persons}
    from_apps = applicant_cities(persons, applicants)
    out = {}
    for k, place in found.items():
        if place is None and isinstance(k, int):
            p = registry.get(k)
            if p is not None and norm_city(p.city):
                place = (p.city, "")
            elif k in from_apps:
                place = (from_apps[k], "")
        out[k] = city_of(*place, directory) if place else None
    return out
