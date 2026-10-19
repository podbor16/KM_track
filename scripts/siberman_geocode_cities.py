"""
Справочник городов Siberman (data/siberman/cities.json) для географии: дописывает города людей,
которых в справочнике нет, через Nominatim (OpenStreetMap; 1 запрос в секунду, свой User-Agent).
Найденный город с тем же названием, что уже в справочнике, — только новое написание в aliases.
Не найден — запись без координат (в списках есть, на карте нет). Город из заявки Тильды (в поле «город»
бывает что угодно, в том числе ФИО) записывается, только если Nominatim нашёл населённый пункт ровно
с этим названием; иначе не записывается и не печатается. После запуска — проверить глазами
(тёзки-города: Железногорск, Радужный и т. п.) и поправить вручную.

    python scripts/siberman_geocode_cities.py            # дописать и сохранить
    python scripts/siberman_geocode_cities.py --dry-run  # только показать
"""
import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")
load_dotenv(ROOT / ".env.local", override=True)

from src.siberman.db import get_siberman_connection  # noqa: E402
from src.siberman.hall import data as hdata  # noqa: E402
from src.siberman.hall import geo as hgeo  # noqa: E402
from src.siberman.persons.linking import norm_city  # noqa: E402

UA = "KM_track Siberman geography (live.siberman515.com)"
PLACE_TYPES = ("city", "town", "village", "hamlet")
# ISO 3166-1 alpha-2 → numeric (как id стран в world-atlas); нет в списке — iso пустой, страна не закрашивается
ISO = {"ru": "643", "by": "112", "kz": "398", "kg": "417", "ua": "804", "de": "276", "fi": "246", "ee": "233",
       "lv": "428", "lt": "440", "am": "051", "az": "031", "ge": "268", "uz": "860", "tj": "762", "tm": "795",
       "md": "498", "mn": "496", "cn": "156", "ae": "784", "nl": "528", "us": "840", "gb": "826", "fr": "250",
       "it": "380", "es": "724", "pl": "616", "cz": "203", "at": "040", "ch": "756", "se": "752", "no": "578",
       "dk": "208", "il": "376", "tr": "792", "th": "764", "rs": "688", "ca": "124", "au": "036", "cy": "196",
       "me": "499", "bg": "100", "gr": "300", "pt": "620", "be": "056", "ie": "372", "hu": "348", "sk": "703",
       "jp": "392", "kr": "410", "in": "356", "vn": "704", "id": "360", "eg": "818", "ar": "032", "br": "076"}


def nominatim(q: str):
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(
        {"q": q, "format": "jsonv2", "limit": 1, "addressdetails": 1, "accept-language": "ru"})
    time.sleep(1)
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=30) as r:
        rows = json.loads(r.read().decode("utf-8"))
    return rows[0] if rows else None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    path = hgeo.CITIES_PATH
    rows = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    conn = get_siberman_connection()
    try:
        entries = hdata.load_entries(conn)
        persons, applicants = hdata.load_people(conn)
    finally:
        conn.close()
    directory = hgeo.load_cities(path)
    places = hgeo.resolve_places(entries, persons, applicants, directory)
    todo = {}
    for c in places.values():   # нет в справочнике (запись «не найден» уже есть — правится вручную)
        if c is not None and norm_city(c.name) not in directory:
            todo.setdefault(norm_city(c.name), c)
    from_apps = {}              # города из заявок, которых нет в справочнике (в places их нет: resolve_places)
    for raw in hgeo.applicant_cities(persons, applicants).values():
        if norm_city(raw) and norm_city(raw) not in directory and norm_city(raw) not in todo:
            from_apps.setdefault(norm_city(raw), raw)
    by_name = {(r["name"], r["country"]): r for r in rows}
    print(f"В справочнике: {len(rows)}; новых написаний: {len(todo)}; из заявок: {len(from_apps)}")
    for c in todo.values():
        hit = nominatim(f"{c.name}, {c.country}" if c.country else c.name) or (c.country and nominatim(c.name))
        if not hit:
            rows.append({"name": c.name, "country": c.country, "iso": "", "lat": None, "lon": None, "aliases": []})
            print(f"  НЕ НАЙДЕН  {c.name} ({c.country})")
            continue
        addr = hit.get("address", {})
        name, country = hit.get("name") or c.name, addr.get("country", c.country)
        iso = ISO.get(addr.get("country_code", ""), "")
        old = by_name.get((name, country))
        if old:
            if norm_city(c.name) != norm_city(name):
                old.setdefault("aliases", []).append(c.name)
            print(f"  написание {c.name} → {name}, {country}")
            continue
        row = {"name": name, "country": country, "iso": iso, "lat": round(float(hit["lat"]), 4),
               "lon": round(float(hit["lon"]), 4), "aliases": [c.name] if norm_city(c.name) != norm_city(name) else []}
        rows.append(row)
        by_name[(name, country)] = row
        print(f"  {c.name} ({c.country}) → {name}, {country} [{iso or 'нет ISO'}] {row['lat']}, {row['lon']} · "
              f"{hit.get('display_name', '')}")
    for raw in from_apps.values():
        hit = nominatim(raw)
        addr = (hit or {}).get("address", {})
        name, country = (hit or {}).get("name") or "", addr.get("country", "")
        if (not hit or hit.get("addresstype") not in PLACE_TYPES or not country
                or norm_city(name) != norm_city(raw)):
            print("  из заявки: не найдено или не совпало — не записано")
            continue
        if (name, country) in by_name:
            print(f"  (заявка) → {name}, {country} — уже в справочнике")
            continue
        row = {"name": name, "country": country, "iso": ISO.get(addr.get("country_code", ""), ""),
               "lat": round(float(hit["lat"]), 4), "lon": round(float(hit["lon"]), 4), "aliases": []}
        rows.append(row)
        by_name[(name, country)] = row
        print(f"  (заявка) → {name}, {country} [{row['iso'] or 'нет ISO'}] {row['lat']}, {row['lon']} · "
              f"{hit.get('display_name', '')}")
    if args.dry_run:
        return
    rows.sort(key=lambda r: (r["country"] != "Россия", r["country"], r["name"]))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("[\n" + ",\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n]\n", encoding="utf-8")
    print(f"Сохранено: {path} ({len(rows)})")


if __name__ == "__main__":
    main()
