# Siberman hall: статистика и география — план реализации (план 3 из 4)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Блоки `/hall/stats` («Siberman в цифрах» + таблица по годам) и `/hall/geo` (карта мира с городами и закрашенными странами + списки) для iframe в Тильде из БД; во вкладке «Люди» админки — список «Без города» и ввод города человеку.

**Architecture:** Пакет `src/siberman/hall/` из плана 2 дополняется чистыми модулями `geo.py` (город человека → справочник `data/siberman/cities.json` → агрегаты) и `stats.py`; снимок `service._build` считает их вместе с рейтингом и рекордами (тот же кэш 60 с). Фронт — по образцу блоков плана 2 (`siberman-hall.js`: экранирование, загрузка, автовысота). Leaflet уже скачивается при деплое в `static/lib/` (`deploy/download_static_libs.py`) — туда же добавляются markercluster, topojson-client и границы стран.

**Tech Stack:** Python 3.13, FastAPI 0.104, mysql-connector, pytest; Leaflet 1.9.4, leaflet.markercluster 1.5.3, topojson-client 3.1.0, world-atlas 2.0.2 (countries-110m), Esri World Light Gray; Nominatim (один раз, скрипт справочника).

**Спецификация:** `docs/superpowers/specs/2026-10-18-siberman-hall-ratings-records-design.md` §6, §7 (обновлён 2026-10-19), §10–§12. Макет: `.superpowers/brainstorm/36-1792309228/content/stats-geo-v10.html` (основной репозиторий).

**Рабочее место:** worktree `.worktrees/siberman-hall`, ветка `feature/siberman-hall` (планы 1–2 уже там, HEAD 90977d9). Тесты: `C:\Users\podbo\miniconda3\python.exe -m pytest <файлы> -q -p no:cacheprovider` из корня worktree (`conda run` зависает). До плана: unit 966, интеграционные `tests/integration/test_siberman_hall.py tests/integration/test_siberman_persons.py` — 25.

---

## Принятые правила (из спецификации и обсуждения 2026-10-19)

- **Человек** — `person_id` реестра; выступление без привязки — `plain_key(фамилия, имя)` (как рейтинг и трекер). Функция `data.person_of(e)`.
- **Старт** — выступление со статусом не `dns`; **финиш личника** — `race_time(e)` (статус active, итог и последняя КТ каждого этапа); **команда стартовала** — `Team.status != "dns"`, **финишировала** — `Team.time_s` не None.
- Пол человека — пол последнего личного старта. «Людей в составах эстафет» — участники стартовавших команд со своим статусом не `dns`. «Всего людей» — все, у кого есть старт (лично или в эстафете). **Новичок года** — первый старт человека в Siberman (любой формат) в этом году. Лучшее время года — лучший итог личника. Год без стартов в статистику не попадает.
- Сверка на архиве 2016–2025 (локальная БД, проверено 2026-10-19): стартов 204 / финишей 196; людей 170 / 165; мужчин 156, женщин 14; мужских стартов 189 / 184; женских 15 / 12; команд 73 / 71; людей всего 337 — совпадает с сайтом. Расхождения — сообщить, тест не подгонять.
- **Город человека** (с Task 5a): введён в админке (`siberman_persons.city_manual`, главнее протокола — решение пользователя 2026-10-19) → последнего старта с городом → заявка Тильды, у которой ФИ (в любом порядке) и ДР совпадают ровно с одним человеком реестра (из нескольких — последняя поданная). Иначе город неизвестен.
- В протоколах эстафет города нет (0 из 219 строк архива), страна у всех «Россия» по умолчанию. **Решение пользователя 2026-10-19:** на карте и в списках — только люди с известным городом, без переключателя «Все / Личный / Эстафеты», подпись «город известен у N из M». Неизвестные города пользователь уточнит — ввод во вкладке «Люди» → «Без города» (открытый вопрос, спецификация §10).
- **Справочник** `data/siberman/cities.json`: каноническое название, страна, ISO 3166-1 numeric страны (3 цифры), широта, долгота, написания (`aliases`). Поиск по `norm_city` (нижний регистр, ё→е, без «г.», дефис = пробел). **Страна — из справочника**, не из протокола (в протоколе «Киргизия» / «Кыргызстан» / «Germany», «Апрелевка — Украина»). Города нет в справочнике — в списках как написан, страна из протокола, без точки на карте; админка показывает «города без координат». Справочник заполняет скрипт через Nominatim и проверяет глазами пользователь.
- `refresh_display` реестра больше не стирает город и страну, если в последнем выступлении города нет (иначе город, введённый в админке, пропадал при следующей эстафете).
- Библиотеки карты — в `static/lib/` через `deploy/download_static_libs.py` (как Leaflet трекера; в git не хранятся). В спецификации было `static/vendor/` — отступление ради единого механизма; на проде всё равно грузится с нашего сервера.
- Скачивание библиотек (Task 7) и запросы к Nominatim (Task 6) — **только после «да» пользователя** (координатор спрашивает перед задачей).
- ПДн: в ответах API нет `birthdate`; в отчётах субагентов — только числа (названия городов можно, ФИО нельзя).

## Файлы

| Файл | Что |
|---|---|
| `src/siberman/hall/data.py` | + `person_of`, `load_people` |
| `src/siberman/hall/geo.py` | новый: `City`, `load_cities`, `city_of`, `applicant_cities`, `resolve_places`, `build_geo`, `missing_report` |
| `src/siberman/hall/stats.py` | новый: `build_stats` |
| `src/siberman/hall/service.py`, `router.py` | снимок + `stats()`, `geography()`; `/hall/stats`, `/hall/geo`, API |
| `src/siberman/persons/db.py` | `refresh_display` не стирает город |
| `src/siberman/persons/service.py`, `router.py` | `set_city`, `no_city`; `POST {API}/{id}/city`, `GET {API}/no-city` |
| `scripts/siberman_geocode_cities.py`, `data/siberman/cities.json` | справочник городов |
| `deploy/download_static_libs.py` | markercluster, topojson-client, world-atlas |
| `templates/siberman/hall_stats.html`, `hall_geo.html`, `static/js/siberman-hall-stats.js`, `siberman-hall-geo.js`, `static/css/siberman-hall.css` | фронт блоков |
| `templates/siberman/people_admin.html`, `static/js/siberman-people-admin.js` | вкладка «Без города», город в карточке |
| `docs/siberman/hall-tilda-snippet.md` | блоки 3–4 |
| Тесты | `tests/unit/test_siberman_hall_geo.py`, `tests/unit/test_siberman_hall_stats.py` (новые), `tests/integration/test_siberman_hall.py`, `tests/integration/test_siberman_persons.py` |

---

### Task 1: Город человека — справочник, заявки, приоритет

**Files:**
- Modify: `src/siberman/hall/data.py`
- Create: `src/siberman/hall/geo.py`, `tests/unit/test_siberman_hall_geo.py`

- [ ] **Step 1: Тесты** — `tests/unit/test_siberman_hall_geo.py`:
```python
import datetime
from types import SimpleNamespace as NS

from src.siberman.hall.data import Entry
from src.siberman.hall.geo import City, applicant_cities, city_of, resolve_places

SPB = City("Санкт-Петербург", "Россия", "643", 59.94, 30.31)
KRS = City("Красноярск", "Россия", "643", 56.01, 92.85)
ALA = City("Алматы", "Казахстан", "398", 43.24, 76.95)
DIR = {"санкт петербург": SPB, "красноярск": KRS, "алматы": ALA, "алма аты": ALA}
BD = datetime.date(1985, 5, 5)


def start(year, surname, city="", country="Россия", pid=None, fmt="individual", stage="none", status="active",
          team=""):
    return Entry(year=year, bib="1", stage=stage, format=fmt, surname=surname, name="Тест", gender="M",
                 city=city, country=country, status=status, team=team, person_id=pid)


def person(pid, surname, city="", bd=None):
    return NS(id=pid, surname=surname, name="Тест", birthdate=bd, city=city)


def app(surname, city, bd, when=datetime.datetime(2025, 1, 1), name="Тест"):
    return NS(surname=surname, name=name, birthdate=bd, city=city, submitted_at=when)


def test_city_spellings_and_unknown_city():
    assert city_of("г. Санкт Петербург", "Россия", DIR) is SPB
    assert city_of("Алма-Аты", "Казахстан", DIR) is ALA
    unknown = city_of("  Вантаа ", "Финляндия", DIR)
    assert (unknown.name, unknown.country, unknown.iso, unknown.lat) == ("Вантаа", "Финляндия", "", None)
    assert city_of("-", "Россия", DIR) is None and city_of("", "Россия", DIR) is None


def test_applicant_city_needs_same_birthdate_and_one_person():
    persons = [person(1, "Иванов", bd=BD), person(2, "Петров", bd=BD), person(3, "Петров", bd=BD),
               person(4, "Сидоров"), person(5, "Кузнецов", bd=BD)]
    apps = [app("Иванов", "Абакан", BD, datetime.datetime(2024, 1, 1)),
            app("Иванов", "Красноярск", BD, datetime.datetime(2025, 3, 1)),   # последняя заявка
            app("Петров", "Омск", BD),                                        # два Петрова с той же ДР
            app("Сидоров", "Омск", BD),                                       # у человека нет ДР
            app("Иванов", "Чита", datetime.date(1990, 1, 1)),                 # другая ДР
            app("Тест", "Тула", BD, name="Кузнецов")]                         # ФИ наоборот
    assert applicant_cities(persons, apps) == {1: "Красноярск", 5: "Тула"}


def test_place_priority_last_start_then_registry_then_applicant():
    entries = [start(2019, "Первый", "Красноярск", pid=1),
               start(2023, "Первый", fmt="relay", stage="swim", pid=1),       # эстафета без города
               start(2024, "Второй", fmt="relay", stage="run", pid=2),        # город введён в админке
               start(2024, "Третий", fmt="relay", stage="run", pid=3),        # город из заявки
               start(2024, "Четвёртый", fmt="relay", stage="run", pid=4),     # неизвестно
               start(2024, "Пятый", "Алма-Аты", "Казахстан", pid=5, status="dns"),   # не стартовал
               start(2024, "Шестой", "Санкт Петербург")]                      # без реестра — по ФИ
    persons = [person(1, "Первый", "Москва"), person(2, "Второй", "Красноярск"), person(3, "Третий", bd=BD),
               person(4, "Четвёртый")]
    places = resolve_places(entries, persons, [app("Третий", "Санкт-Петербург", BD)], DIR)
    assert {k: (c.name if c else None) for k, c in places.items()} == {
        1: "Красноярск", 2: "Красноярск", 3: "Санкт-Петербург", 4: None, "шестой тест": "Санкт-Петербург"}
```

- [ ] **Step 2: Красный прогон** — `tests/unit/test_siberman_hall_geo.py`. Expected: ошибка сбора (`ModuleNotFoundError: No module named 'src.siberman.hall.geo'`).

- [ ] **Step 3: `data.py`.** Импорты: после `import mysql.connector` добавить
```python
from src.siberman.persons import db as pdb
from src.siberman.persons.linking import plain_key
```
В конец файла:
```python
def person_of(e: Entry):
    """Человек выступления: id реестра; без привязки — 'фамилия имя' (как рейтинг и трекер)."""
    return e.person_id or plain_key(e.surname, e.name)


def load_people(conn) -> tuple:
    """Люди реестра и заявки Тильды — для города человека; без таблиц реестра (миграция 014) — пусто."""
    try:
        return pdb.load_persons(conn), pdb.load_applicants(conn)
    except mysql.connector.Error:
        return [], []
```

- [ ] **Step 4: `geo.py`:**
```python
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
```

- [ ] **Step 5: Зелёный прогон** — тот же файл: 3 passed; `tests/unit/` — 969 passed.

- [ ] **Step 6: Commit** — `feat(siberman/hall): город человека — справочник, реестр, заявки с той же ДР`.

---

### Task 2: Агрегаты географии и отчёт «без города»

**Files:** Modify `src/siberman/hall/geo.py`, `tests/unit/test_siberman_hall_geo.py`.

- [ ] **Step 1: Тесты** — импорт в начале файла заменить на `from src.siberman.hall.geo import City, applicant_cities, build_geo, city_of, missing_report, resolve_places`; в конец:
```python
def test_geo_counts_people_once_by_last_city():
    entries = [start(2019, "Первый", "Красноярск", pid=1), start(2023, "Первый", "Красноярск", pid=1),
               start(2023, "Второй", "Алма-Аты", "Казахстан", pid=2), start(2024, "Третий", "Вантаа", "Финляндия", pid=3),
               start(2024, "Четвёртый", fmt="relay", stage="run", pid=4)]
    g = build_geo(entries, resolve_places(entries, [], [], DIR))
    assert (g["total"], g["known"]) == (4, 3)
    assert [(c["name"], c["iso"], c["count"]) for c in g["countries"]] == [
        ("Казахстан", "398", 1), ("Россия", "643", 1), ("Финляндия", "", 1)]
    krs = next(c for c in g["cities"] if c["name"] == "Красноярск")
    assert (krs["count"], krs["lat"], krs["people"]) == (1, 56.01, [{"person_id": 1, "fio": "Первый Тест"}])
    assert next(c for c in g["cities"] if c["name"] == "Вантаа")["lat"] is None


def test_missing_report_people_without_city_and_cities_without_coords():
    entries = [start(2023, "Второй", fmt="relay", stage="run", pid=2, team="Команда"),
               start(2024, "Третий", "Вантаа", "Финляндия", pid=3),
               start(2024, "Шестой", fmt="relay", stage="swim", team="Без реестра")]
    rep = missing_report(entries, resolve_places(entries, [], [], DIR))
    assert [(p["person_id"], p["fio"]) for p in rep["people"]] == [(2, "Второй Тест"), (None, "Шестой Тест")]
    assert rep["people"][0]["starts"] == [{"year": 2023, "format": "relay", "stage": "run", "team": "Команда"}]
    assert rep["no_coords"] == [{"name": "Вантаа", "country": "Финляндия", "count": 1}]
```

- [ ] **Step 2: Красный прогон** — ошибка импорта `build_geo`.

- [ ] **Step 3: `geo.py`, в конец:**
```python
def _last_starts(entries: list) -> dict:
    """Человек → его старты (не dns) по годам."""
    out = defaultdict(list)
    for e in sorted(entries, key=lambda e: e.year):
        if e.status != "dns":
            out[person_of(e)].append(e)
    return out


def build_geo(entries: list, places: dict) -> dict:
    """Люди по городам и странам: человек — один раз, по своему городу; ФИ и ссылка — последнего старта."""
    starts = _last_starts(entries)
    cities, countries = {}, {}
    for k, c in places.items():
        if c is None:
            continue
        last = starts[k][-1]
        row = cities.setdefault((c.name, c.country), {"name": c.name, "country": c.country, "iso": c.iso,
                                                      "lat": c.lat, "lon": c.lon, "people": []})
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
    no_coords = defaultdict(int)
    for c in places.values():
        if c is not None and c.lat is None:
            no_coords[(c.name, c.country)] += 1
    return {"people": people,
            "no_coords": [{"name": n, "country": ct, "count": v} for (n, ct), v in sorted(no_coords.items())]}
```

- [ ] **Step 4: Зелёный прогон** — файл: 5 passed; `tests/unit/` — 971.

- [ ] **Step 5: Commit** — `feat(siberman/hall): география — люди по городам и странам, отчёт «без города»`.

---

### Task 3: Статистика

**Files:** Create `src/siberman/hall/stats.py`, `tests/unit/test_siberman_hall_stats.py`.

- [ ] **Step 1: Тесты:**
```python
from src.siberman.hall.data import Entry, build_teams
from src.siberman.hall.stats import build_stats

ALL = frozenset({"swim", "bike_day1", "bike_day2", "run"})
ROLE = {"swim": ("swim",), "bike": ("bike_day1", "bike_day2"), "run": ("run",)}
GEO = {"countries": [{"name": "Россия", "iso": "643", "count": 3}, {"name": "Казахстан", "iso": "398", "count": 1}],
       "cities": [{"name": "Красноярск"}, {"name": "Москва"}, {"name": "Алматы"}]}


def ind(year, pid, g="M", status="active", total=100):
    return Entry(year=year, bib=str(pid), stage="none", format="individual", surname=f"Личник{pid}", name="Тест",
                 gender=g, status=status, person_id=pid, overall_s=total if status == "active" else None,
                 times={"swim": 1, "bike_day1": 1, "bike_day2": 1, "run": 1},
                 finished=ALL if status == "active" else frozenset())


def rel(year, bib, role, pid, status="active"):
    return Entry(year=year, bib=str(bib), stage=role, format="relay", surname=f"Этапник{pid}", name="Тест",
                 gender="M", status=status, team="Команда", person_id=pid, times={s: 10 for s in ROLE[role]},
                 finished=frozenset(ROLE[role]))


def team(year, bib, pids, swim_status="active"):
    return [rel(year, bib, r, p, swim_status if r == "swim" else "active") for r, p in zip(("swim", "bike", "run"), pids)]


def stats(entries):
    return build_stats(entries, build_teams(entries), GEO)


def test_individual_people_and_starts():
    entries = [ind(2020, 1), ind(2021, 1, total=90), ind(2021, 2, "F", status="dnf"), ind(2022, 2, "F"),
               ind(2022, 3, status="dns"), ind(2022, 4, status="dnf")]
    s = stats(entries)["individual"]
    assert (s["people"], s["people_finished"], s["people_men"], s["people_women"]) == (3, 2, 2, 1)
    assert (s["starts"], s["finishes"]) == (5, 3)
    assert (s["starts_men"], s["finishes_men"], s["starts_women"], s["finishes_women"]) == (3, 2, 2, 1)


def test_relay_people_total_countries_and_cities():
    entries = [ind(2021, 1), *team(2021, 101, (1, 5, 6)), *team(2022, 102, (7, 8, 9), swim_status="dnf"),
               *[rel(2022, 103, r, p, "dns") for r, p in zip(("swim", "bike", "run"), (10, 11, 12))]]
    s = stats(entries)
    assert s["relay"] == {"teams": 2, "finished": 1, "people": 6}
    assert (s["people_total"], s["countries"], s["cities"]) == (6, 2, 3)


def test_by_year_newcomers_best_time_and_years_without_starts():
    entries = [ind(2020, 1, total=100), ind(2021, 1, total=90), ind(2021, 2, "F", total=120),
               *team(2021, 101, (2, 5, 6)), ind(2022, 3, status="dns")]
    s = stats(entries)
    assert (s["first_year"], s["last_year"]) == (2020, 2021)
    assert [r["year"] for r in s["years"]] == [2021, 2020]
    assert s["years"][0] == {"year": 2021, "ind_start": 2, "ind_fin": 2, "men": 1, "women": 1, "relay_start": 1,
                             "relay_fin": 1, "newcomers": 3, "best_s": 90}
```

- [ ] **Step 2: Красный прогон** — `ModuleNotFoundError: ... hall.stats`.

- [ ] **Step 3: `stats.py`:**
```python
"""
Статистика Siberman (спецификация hall §6): люди и старты личного зачёта, эстафеты, всего людей,
страны и города (по людям с известным городом — из build_geo), таблица по годам. Старт — статус не
dns; финиш личника — race_time; пол человека — последнего личного старта; новичок года — первый
старт человека в Siberman (лично или в эстафете).
"""
from src.siberman.hall.data import person_of, race_time


def build_stats(entries: list, teams: list, geo: dict) -> dict:
    started = sorted((e for e in entries if e.status != "dns"), key=lambda e: e.year)
    ind = [e for e in started if e.format == "individual"]
    fin = [e for e in ind if race_time(e) is not None]
    gender = {}
    for e in ind:
        gender[person_of(e)] = e.gender or gender.get(person_of(e))
    people, people_fin = {person_of(e) for e in ind}, {person_of(e) for e in fin}
    first = {}
    for e in started:
        first.setdefault(person_of(e), e.year)
    tstart = [t for t in teams if t.status != "dns"]
    years = sorted({e.year for e in started}, reverse=True)
    rows = []
    for y in years:
        yi = [e for e in ind if e.year == y]
        yt = [t for t in tstart if t.year == y]
        times = [race_time(e) for e in yi if race_time(e) is not None]
        rows.append({"year": y, "ind_start": len(yi), "ind_fin": len(times),
                     "men": sum(e.gender == "M" for e in yi), "women": sum(e.gender == "F" for e in yi),
                     "relay_start": len(yt), "relay_fin": sum(t.time_s is not None for t in yt),
                     "newcomers": sum(1 for v in first.values() if v == y), "best_s": min(times, default=None)})
    return {
        "first_year": years[-1] if years else None, "last_year": years[0] if years else None,
        "individual": {
            "people": len(people), "people_finished": len(people_fin),
            "people_men": sum(gender[k] == "M" for k in people), "people_women": sum(gender[k] == "F" for k in people),
            "starts": len(ind), "finishes": len(fin),
            "starts_men": sum(e.gender == "M" for e in ind), "finishes_men": sum(e.gender == "M" for e in fin),
            "starts_women": sum(e.gender == "F" for e in ind), "finishes_women": sum(e.gender == "F" for e in fin)},
        "relay": {"teams": len(tstart), "finished": sum(t.time_s is not None for t in tstart),
                  "people": len({person_of(m) for t in tstart for m in t.members if m.status != "dns"})},
        "people_total": len({person_of(e) for e in started}),
        "countries": sum(1 for c in geo["countries"] if c["name"]), "cities": len(geo["cities"]),
        "years": rows,
    }
```

- [ ] **Step 4: Зелёный прогон** — файл: 3 passed; `tests/unit/` — 974.

- [ ] **Step 5: Commit** — `feat(siberman/hall): статистика — люди, старты, эстафеты, таблица по годам`.

---

### Task 4: Реестр — город не стирается, ввод города, список «без города»

**Files:** Modify `src/siberman/persons/db.py`, `src/siberman/persons/service.py`, `src/siberman/persons/router.py`, `tests/integration/test_siberman_persons.py`.

- [ ] **Step 1: Тесты** — в конец `tests/integration/test_siberman_persons.py`:
```python
def test_city_survives_relay_start_and_is_undoable(conn):
    _ins(conn, YEAR, 9101, "Тестреестрова", "Анна", fmt="relay", stage="swim", gender="F", team="Тест", city="")
    service.sync(conn)
    pid = _pid(conn, YEAR, 9101, "swim")
    res = service.set_city(pid, "  Абакан ", "test")
    assert pdb.get_person(conn, pid)["city"] == "Абакан"
    _ins(conn, Y2, 9102, "Тестреестрова", "Анна", fmt="relay", stage="run", gender="F", team="Тест", city="")
    service.sync(conn)
    assert _pid(conn, Y2, 9102, "run") == pid
    assert pdb.get_person(conn, pid)["city"] == "Абакан"          # эстафета без города не стирает
    service.undo(res["audit_id"], "test")
    assert pdb.get_person(conn, pid)["city"] == ""


def test_no_city_list_and_api(conn):
    from fastapi.testclient import TestClient
    from app import app
    from src.core.auth import api_require_auth
    _ins(conn, YEAR, 9101, "Тестреестрова", "Анна", fmt="relay", stage="swim", gender="F", team="Тест", city="")
    service.sync(conn)
    pid = _pid(conn, YEAR, 9101, "swim")
    assert pid in [p["person_id"] for p in service.no_city()["people"]]
    client = TestClient(app)
    assert client.get("/api/siberman/admin/people/no-city").status_code == 401
    app.dependency_overrides[api_require_auth] = lambda: "test"
    try:
        assert client.post(f"/api/siberman/admin/people/{pid}/city", json={"city": "Абакан"}).status_code == 200
        people = client.get("/api/siberman/admin/people/no-city").json()["people"]
        assert pid not in [p["person_id"] for p in people]
        assert client.post(f"/api/siberman/admin/people/{pid}/city", json={"city": "х" * 101}).status_code == 409
    finally:
        app.dependency_overrides.clear()
```

- [ ] **Step 2: Красный прогон** — оба теста: `AttributeError: module ... has no attribute 'set_city'` / `'no_city'`.

- [ ] **Step 3: `db.py` → `refresh_display`:**
```python
def refresh_display(conn, person_ids) -> None:
    """ФИ, пол, город, страна человека — по последнему выступлению. В протоколах эстафет города нет —
    тогда город и страна остаются прежними (из прошлых стартов или введённые в админке)."""
    for pid, rows in participations(conn, person_ids).items():
        last = max(rows, key=lambda r: (r["race_year"], r["format"] == "individual"))
        fields = {"surname": last["surname"], "name": last["name"]}
        if last["city"]:
            fields.update(city=last["city"], country=last["country"] or "")
        if last["gender"] in ("M", "F"):
            fields["gender"] = last["gender"]
        update_person(conn, pid, fields)
```

- [ ] **Step 4: `service.py`.** Импорты: после `from src.siberman.db import get_siberman_connection` добавить
```python
from src.siberman.hall import data as hdata
from src.siberman.hall import geo as hgeo
```
После `set_birthdate`:
```python
def set_city(person_id: int, city: str, user: str) -> dict:
    """Город человека для карты «География» (в протоколах эстафет города нет). Пишется в журнал."""
    city = " ".join((city or "").split())
    if len(city) > 100:
        raise PersonsError("Слишком длинное название города")
    with _connection() as conn, _locked_tx(conn):
        p = pdb.get_person(conn, person_id)
        if not p:
            raise PersonsError("Человек не найден")
        snap = _snapshot(conn, [person_id], [])
        pdb.update_person(conn, person_id, {"city": city})
        audit_id = _record(conn, "city", f"Город {_fio(p)} (id {person_id}): {p['city'] or '—'} → {city or '—'}",
                           snap, user)
    return {"ok": True, "audit_id": audit_id}


def no_city() -> dict:
    """Вкладка «Без города»: люди без известного города и города без координат — по свежим данным."""
    with _connection() as conn:
        entries = hdata.load_entries(conn)
        persons, applicants = hdata.load_people(conn)
    places = hgeo.resolve_places(entries, persons, applicants, hgeo.load_cities())
    return hgeo.missing_report(entries, places)
```
Докстринг модуля: «ручные решения админки (слить, перенести выступления, ДР, город, статус «проверить»)…».

- [ ] **Step 5: `router.py`.** После `BirthdateIn`:
```python
class CityIn(BaseModel):
    city: str = ""
```
Перед `@router.get(f"{API}/{{person_id}}")` (статичный путь — раньше параметра):
```python
@router.get(f"{API}/no-city")
def api_no_city(user: str = Depends(api_require_auth)):
    return _run(service.no_city)
```
После `api_birthdate`:
```python
@router.post(f"{API}/{{person_id}}/city")
def api_city(person_id: int, body: CityIn, user: str = Depends(api_require_auth)):
    return _run(service.set_city, person_id, body.city, user)
```

- [ ] **Step 6: Прогоны** — `tests/integration/test_siberman_persons.py`: 22 passed; `tests/unit/` — 974.

- [ ] **Step 7: Commit** — `feat(siberman/persons): город человека — ввод с отменой, список «без города»; эстафета не стирает город`.

---

### Task 5: Снимок, API, страницы, сверка на архиве

**Files:** Modify `src/siberman/hall/service.py`, `src/siberman/hall/router.py`, `tests/integration/test_siberman_hall.py`. Create `templates/siberman/hall_stats.html`, `templates/siberman/hall_geo.html` (заглушки — наполняются в Task 8–9).

- [ ] **Step 1: Тесты** (`tests/integration/test_siberman_hall.py`):
  - импорты: `from src.siberman.hall import geo as hgeo`, `from src.siberman.hall.stats import build_stats`;
  - фикстура `archive`: внутри `try` после `entries = …` — `persons, applicants = hdata.load_people(conn)`; перед `return` — `geo = hgeo.build_geo(entries, hgeo.resolve_places(entries, persons, applicants, hgeo.load_cities()))`; в словарь — `"geo": geo`;
  - новые тесты после `test_rating_marks_current_records`:
```python
def test_stats_match_site(archive):
    s = build_stats(archive["entries"], archive["teams"], archive["geo"])
    i = s["individual"]
    got = (i["starts"], i["finishes"], i["people"], i["people_finished"], i["people_men"], i["people_women"],
           i["starts_men"], i["finishes_men"], i["starts_women"], i["finishes_women"],
           s["relay"]["teams"], s["relay"]["finished"], s["people_total"])
    assert got == (204, 196, 170, 165, 156, 14, 189, 184, 15, 12, 73, 71, 337), f"наше: {got}"
    assert (s["first_year"], s["last_year"], len(s["years"])) == (2016, 2025, 10)


def test_geo_on_archive(archive):
    g = archive["geo"]
    assert g["total"] == 337 and 168 <= g["known"] < g["total"]
    assert sum(c["count"] for c in g["cities"]) == g["known"] == sum(c["count"] for c in g["countries"])
```
  - в `test_api_and_pages` перед проверками страниц:
```python
    stats = client.get("/api/siberman/hall/stats").json()
    assert {"individual", "relay", "years", "people_total", "countries", "cities"} <= set(stats)
    geo = client.get("/api/siberman/hall/geo")
    assert geo.status_code == 200 and {"total", "known", "countries", "cities"} <= set(geo.json())
    assert "birthdate" not in geo.text
```
    и в конце:
```python
    for page in ("/hall/stats", "/hall/geo"):
        assert client.get(page, headers=SIBERMAN).status_code == 200
        assert client.get(page).status_code == 404
```

- [ ] **Step 2: Красный прогон** — `tests/integration/test_siberman_hall.py`: 1 failed (`test_api_and_pages` — `/api/siberman/hall/stats` 404, маршрута ещё нет), 6 passed (сверки уже проходят: модули из Task 1–3).

- [ ] **Step 3: `service.py`.** Импорты `from src.siberman.hall import geo as hgeo`, `from src.siberman.hall.stats import build_stats`. Докстринг модуля, первая строка: «Рейтинг, рекорды, статистика и география Siberman: снимок архива в памяти воркера на CACHE_TTL_S (спецификация hall §2).» `_build`:
```python
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
```
В конец:
```python
def stats() -> dict:
    return _snapshot()["stats"]


def geography() -> dict:
    return _snapshot()["geo"]
```

- [ ] **Step 4: `router.py`.** Докстринг: «Рейтинг, рекорды, статистика и география Siberman: блоки для iframe в Тильде (/hall/rating, /hall/records, /hall/stats, /hall/geo) и их API. …». Страницы — после `hall_records_page`:
```python
@router.get("/hall/stats", response_class=HTMLResponse)
async def hall_stats_page(request: Request):
    return _page(request, "siberman/hall_stats.html")


@router.get("/hall/geo", response_class=HTMLResponse)
async def hall_geo_page(request: Request):
    return _page(request, "siberman/hall_geo.html")
```
API — в конец:
```python
@router.get("/api/siberman/hall/stats")
def api_hall_stats():
    return _json(service.stats)


@router.get("/api/siberman/hall/geo")
def api_hall_geo():
    return _json(service.geography)
```

- [ ] **Step 5: Заглушки шаблонов** (полный вид — Task 8–9). `templates/siberman/hall_stats.html`:
```html
<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Siberman — статистика</title>
<link rel="stylesheet" href="/static/css/siberman-hall.css?v={{ v }}">
</head>
<body>
<div class="hall" id="stats"><div class="state-msg">Загрузка…</div></div>
</body>
</html>
```
`hall_geo.html` — то же с `<title>Siberman — география</title>` и `<div class="hall" id="geo">`.

- [ ] **Step 6: Прогоны** — интеграционные hall: 7 passed (сверка — без подгонки: число не сошлось → стоп, сообщить); `tests/unit/` — 974 (в т.ч. `test_siberman_hall_service.py` — `_build` подменяется, не затронут).

- [ ] **Step 7: Commit** — `feat(siberman/hall): API и страницы статистики и географии, сверка с сайтом`.

---

### Task 5a: Ревью задач 1–5 — старт без отметок, страна и дубли городов, ручной город, битый справочник

1. **Старт.** Статус `dns` в живом году не ставится (Copernico переводит неявившихся в active), стартовый протокол загружен до гонки → «N стартов, новички, 2016–2026». Старт = `dnf`/`dsq` или `active` с хоть одной отметкой КТ (`data.is_start`). На архиве — те же 204 / 337 (у всех не-dns строк архива есть отметка, проверено ревью).
2. **Страна города из заявки / админки** — та, с которой этот город чаще пишут в протоколах (было: пустая → строка «» в странах, дубли «Москва / Москва»). Строки городов ключуются по `norm_city` (разные написания одного города — одна строка, название — первое встреченное).
3. **Ручной город** — отдельная колонка `siberman_persons.city_manual` (решение пользователя 2026-10-19: ручной главнее протокола). Город: введён в админке → последнего старта с городом → заявка. `persons.city` — снова только из протоколов: последнего выступления **с городом**. Слияние сохраняет ручной город; без изменений `set_city` в журнал не пишет.
4. **Битый `cities.json`** (правится руками) — не роняет рейтинг и рекорды: справочник пропускается с ошибкой в логе.

**Files:** Modify `src/siberman/migrations/014_persons.sql`, `src/siberman/persons/linking.py`, `src/siberman/persons/db.py`, `src/siberman/persons/service.py`, `src/siberman/hall/data.py`, `src/siberman/hall/geo.py`, `src/siberman/hall/stats.py`, `tests/unit/test_siberman_hall_geo.py`, `tests/unit/test_siberman_hall_stats.py`, `tests/integration/test_siberman_persons.py`, `tests/integration/test_siberman_hall.py`.

- [ ] **Step 1: Колонка.** В `014_persons.sql` после строки `country …`:
```sql
  city_manual     VARCHAR(100) NOT NULL DEFAULT '',  -- введён в админке; для карты главнее протокола
```
Локальная БД (таблица уже есть) — один раз скриптом из scratchpad (`.env.local` через dotenv): если в `SHOW COLUMNS FROM siberman_persons` нет `city_manual` → `ALTER TABLE siberman_persons ADD COLUMN city_manual VARCHAR(100) NOT NULL DEFAULT '' AFTER country`. На проде миграции 014 ещё нет — хватит правки файла.

- [ ] **Step 2: Тесты.**
  - `tests/unit/test_siberman_hall_geo.py`:
    - импорт: `from src.siberman.hall.geo import City, applicant_cities, build_geo, city_of, load_cities, missing_report, resolve_places`;
    - `start(...)` — параметр `has_time=True` в конце сигнатуры и `has_time=has_time` в `Entry(...)`;
    - `person` заменить на
```python
def person(pid, surname, manual="", bd=None):
    return NS(id=pid, surname=surname, name="Тест", birthdate=bd, city="", city_manual=manual)
```
    - в `test_place_priority_last_start_then_registry_then_applicant`: переименовать в `test_place_priority_manual_then_last_start_then_applicant`, комментарий у второго старта — `# эстафета без города`, у `Второй` — `# город введён в админке`, а ожидание для 1 — `1: "Москва"` (ручной главнее старта; Москвы в DIR нет — как написан);
    - в конец:
```python
def test_no_marks_is_not_a_start_and_country_from_protocol():
    entries = [start(2026, "Неявка", "Омск", pid=7, has_time=False),    # стартовый протокол живого года
               start(2025, "Сосед", "Абакан", pid=8),
               start(2025, "Эстафетчик", fmt="relay", stage="run", pid=9),
               start(2025, "Сошедший", "Омск", pid=10, status="dnf", has_time=False)]
    places = resolve_places(entries, [person(9, "Эстафетчик", "абакан")], [], DIR)
    assert 7 not in places and places[10].name == "Омск"
    assert (places[9].name, places[9].country) == ("абакан", "Россия")      # страна — как у Абакана в протоколах
    g = build_geo(entries, places)
    assert [(c["name"], c["country"], c["count"]) for c in g["cities"]] == [("Абакан", "Россия", 2), ("Омск", "Россия", 1)]


def test_broken_or_missing_cities_json_is_ignored(tmp_path):
    bad = tmp_path / "cities.json"
    bad.write_text("[{", encoding="utf-8")
    assert load_cities(bad) == {} and load_cities(tmp_path / "нет.json") == {}
```
  - `tests/unit/test_siberman_hall_stats.py`:
    - `ind(year, pid, g="M", status="active", total=100, has_time=True)`; в `Entry(...)`: `overall_s=total if status == "active" and has_time else None`, `finished=ALL if status == "active" and has_time else frozenset()`, `has_time=has_time`;
    - `rel(year, bib, role, pid, status="active", has_time=True)` → `has_time=has_time`, `finished=frozenset(ROLE[role]) if has_time else frozenset()`;
    - `team(year, bib, pids, swim_status="active", has_time=True)` → передаёт `has_time` в `rel`;
    - в конец:
```python
def test_live_year_start_list_without_marks_is_not_counted():
    entries = [ind(2025, 1), ind(2026, 2, has_time=False), *team(2026, 101, (3, 4, 5), has_time=False)]
    s = stats(entries)
    assert (s["last_year"], s["people_total"], s["relay"]["teams"], s["relay"]["people"]) == (2025, 1, 0, 0)
```
  - `tests/integration/test_siberman_persons.py`: `test_city_survives_relay_start_and_is_undoable` заменить на
```python
def test_manual_city_is_separate_and_undoable(conn):
    _ins(conn, YEAR, 9101, "Тестреестрова", "Анна", fmt="relay", stage="swim", gender="F", team="Тест", city="")
    _ins(conn, Y2, 9102, "Тестреестрова", "Анна", gender="F", city="Норильск")
    _ins(conn, Y3, 9103, "Тестреестрова", "Анна", fmt="relay", stage="run", gender="F", team="Тест", city="")
    service.sync(conn)
    pid = _pid(conn, YEAR, 9101, "swim")
    assert _pid(conn, Y2, 9102) == pid == _pid(conn, Y3, 9103, "run")
    assert pdb.get_person(conn, pid)["city"] == "Норильск"          # последнего выступления с городом
    res = service.set_city(pid, "  Абакан ", "test")
    p = pdb.get_person(conn, pid)
    assert (p["city_manual"], p["city"]) == ("Абакан", "Норильск")
    assert service.set_city(pid, "Абакан", "test")["audit_id"] is None   # без изменений — не в журнал
    service.undo(res["audit_id"], "test")
    assert pdb.get_person(conn, pid)["city_manual"] == ""


def test_merge_keeps_manual_city(conn):
    _ins(conn, YEAR, 9101, "Тестреестрова", "Анна", fmt="relay", stage="swim", gender="F", team="Тест", city="")
    _ins(conn, Y2, 9102, "Тестреестрова", "Аня", fmt="relay", stage="run", gender="F", team="Тест", city="")
    service.sync(conn)
    src, dst = _pid(conn, YEAR, 9101, "swim"), _pid(conn, Y2, 9102, "run")
    assert src != dst
    service.set_city(src, "Абакан", "test")
    service.merge(src, dst, "test")
    assert pdb.get_person(conn, dst)["city_manual"] == "Абакан"
```
    (если `_pid(conn, Y2, 9102) == pid` не выполняется из-за правил привязки личник ↔ эстафета — остановись и опиши, тест не подгоняй.)
  - `tests/integration/test_siberman_hall.py`, в `test_geo_on_archive`: импорт `from src.siberman.persons.linking import norm_city` и строка `assert len({norm_city(c["name"]) for c in g["cities"]}) == len(g["cities"])`.

- [ ] **Step 3: Красный прогон** — unit `test_siberman_hall_geo.py` + `test_siberman_hall_stats.py`: падают на `has_time` (`TypeError: ... unexpected keyword argument 'has_time'`); интеграционные — `KeyError: 'city_manual'` / несовпадения.

- [ ] **Step 4: `data.py`.**
  - После `FINISHED_SQL`: `STARTED_SQL = "SELECT DISTINCT participant_id FROM checkpoint_times WHERE cumulative_s IS NOT NULL"`.
  - `Entry`: после `finished` — `has_time: bool = False                       # есть хоть одна отметка КТ`.
  - После `race_time`:
```python
def is_start(e: Entry) -> bool:
    """Вышел на старт: сошёл / снят или есть хоть одна отметка КТ. Статус dns ставят не всегда: в живом
    году Copernico переводит неявившихся в active, а стартовый протокол загружен до гонки."""
    return e.status in ("dnf", "dsq") or (e.status == "active" and e.has_time)
```
  - `load_entries`: после цикла `finished` — `cur.execute(STARTED_SQL)` и `started = {r["participant_id"] for r in cur.fetchall()}`; в `Entry(...)` — `has_time=r["id"] in started`.

- [ ] **Step 5: `geo.py`.**
  - Импорты: `import logging`, `from collections import Counter, defaultdict`, `from src.siberman.hall.data import is_start, person_of`; после импортов `log = logging.getLogger(__name__)`.
  - Докстринг модуля, второе предложение: «Город человека — введённый в админке; нет — последнего старта с городом; нет — из заявки Тильды с той же ФИ и ДР.»
  - `load_cities`:
```python
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
```
  - `resolve_places`:
```python
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
```
  - `_last_starts`: условие `if is_start(e):` вместо `if e.status != "dns":`; докстринг «Человек → его старты (data.is_start) по годам.»
  - `build_geo`: ключ строки — `(norm_city(c.name), c.country)` вместо `(c.name, c.country)`; докстринг дополнить «; разные написания одного города — одна строка».
  - `missing_report`, часть про координаты:
```python
    no_coords = {}
    for c in places.values():
        if c is not None and c.lat is None:
            row = no_coords.setdefault((norm_city(c.name), c.country), {"name": c.name, "country": c.country, "count": 0})
            row["count"] += 1
    return {"people": people, "no_coords": sorted(no_coords.values(), key=lambda r: (r["country"], r["name"]))}
```

- [ ] **Step 6: `stats.py`.** Импорт `from src.siberman.hall.data import is_start, person_of, race_time`; `started = sorted((e for e in entries if is_start(e)), key=lambda e: e.year)`; `tstart = [t for t in teams if any(is_start(m) for m in t.members)]`; люди в составах — `… for m in t.members if is_start(m)`. В докстринге: «Старт — data.is_start (dnf/dsq или отметка КТ: dns в живом году не ставится)».

- [ ] **Step 7: Реестр.**
  - `linking.py`, `Person`: после `city: str = ""` — `city_manual: str = ""`.
  - `db.py`: `PERSON_FIELDS = ("surname", "name", "gender", "birthdate", "bib_individual", "city", "country", "city_manual")`; `load_persons` — в SELECT `city, city_manual` и `city_manual=r["city_manual"]` в `Person(...)`; `refresh_display`:
```python
def _recent(r: dict) -> tuple:
    return r["race_year"], r["format"] == "individual"


def refresh_display(conn, person_ids) -> None:
    """ФИ и пол — по последнему выступлению; город и страна — по последнему выступлению с городом (в
    протоколах эстафет города нет). Город, введённый в админке, хранится отдельно — city_manual."""
    for pid, rows in participations(conn, person_ids).items():
        last = max(rows, key=_recent)
        fields = {"surname": last["surname"], "name": last["name"]}
        with_city = [r for r in rows if r["city"]]
        if with_city:
            w = max(with_city, key=_recent)
            fields.update(city=w["city"], country=w["country"] or "")
        if last["gender"] in ("M", "F"):
            fields["gender"] = last["gender"]
        update_person(conn, pid, fields)
```
  - `service.py`:
    - `_restore`: кортеж полей `("surname", "name", "gender", "birthdate", "city", "country", "city_manual")`;
    - `merge`: в `update_person(conn, target_id, {...})` добавить `"city_manual": dst["city_manual"] or src["city_manual"]`;
    - `set_city`:
```python
def set_city(person_id: int, city: str, user: str) -> dict:
    """Город человека, введённый в админке (для карты главнее протокола; пусто — снова из протоколов).
    Пишется в журнал; без изменений — ничего не делает."""
    city = " ".join((city or "").split())
    if len(city) > 100:
        raise PersonsError("Слишком длинное название города")
    with _connection() as conn, _locked_tx(conn):
        p = pdb.get_person(conn, person_id)
        if not p:
            raise PersonsError("Человек не найден")
        if p["city_manual"] == city:
            return {"ok": True, "audit_id": None}
        snap = _snapshot(conn, [person_id], [])
        pdb.update_person(conn, person_id, {"city_manual": city})
        audit_id = _record(conn, "city", f"Город {_fio(p)} (id {person_id}): {p['city_manual'] or '—'} → {city or '—'}",
                           snap, user)
    return {"ok": True, "audit_id": audit_id}
```

- [ ] **Step 8: Прогоны.** unit `test_siberman_hall_geo.py` — 7, `test_siberman_hall_stats.py` — 4; `tests/unit/` — 977; интеграционные persons — 23, hall — 7 (сверка 204/196…/337 — без изменений; число не сошлось → стоп).

- [ ] **Step 9: Commit** — `fix(siberman/hall): старт — с отметкой КТ; страна города из протоколов, один город — одна строка; ручной город отдельно; битый справочник не роняет блоки`.

---

### Task 6: Справочник городов (Nominatim) — после «да» пользователя

**Files:** Create `scripts/siberman_geocode_cities.py`, `data/siberman/cities.json`.

Координатор перед задачей спрашивает пользователя: скрипт отправит в Nominatim (OpenStreetMap) ~70 названий городов (без ФИО), раз в секунду.

- [ ] **Step 1: Скрипт** `scripts/siberman_geocode_cities.py`:
```python
"""
Справочник городов Siberman (data/siberman/cities.json) для географии: дописывает города людей,
которых в справочнике нет, через Nominatim (OpenStreetMap; 1 запрос в секунду, свой User-Agent).
Найденный город с тем же названием, что уже в справочнике, — только новое написание в aliases.
Не найден — запись без координат (в списках есть, на карте нет). После запуска — проверить глазами
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
    by_name = {(r["name"], r["country"]): r for r in rows}
    print(f"В справочнике: {len(rows)}; новых написаний: {len(todo)}")
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
    if args.dry_run:
        return
    rows.sort(key=lambda r: (r["country"] != "Россия", r["country"], r["name"]))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("[\n" + ",\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n]\n", encoding="utf-8")
    print(f"Сохранено: {path} ({len(rows)})")


if __name__ == "__main__":
    main()
```
  Повторный запуск ищет только написания, которых нет в справочнике: запись «НЕ НАЙДЕН» уже в справочнике (без координат) — её правят вручную.

- [ ] **Step 2: Запуск** (после «да» пользователя): `C:\Users\podbo\miniconda3\python.exe scripts/siberman_geocode_cities.py`. В отчёт — полный вывод скрипта (названия городов — не ПДн).

- [ ] **Step 2b: Тест на настоящий справочник** — в конец `tests/unit/test_siberman_hall_geo.py`:
```python
def test_cities_json_is_consistent():
    import json
    import re
    from src.siberman.hall.geo import CITIES_PATH
    from src.siberman.persons.linking import norm_city
    seen = {}
    for r in json.loads(CITIES_PATH.read_text(encoding="utf-8")):
        assert set(r) == {"name", "country", "iso", "lat", "lon", "aliases"} and r["name"] and r["country"], r
        assert re.fullmatch(r"\d{3}", r["iso"]) or r["iso"] == "", r
        assert (r["lat"] is None) == (r["lon"] is None), r
        if r["lat"] is not None:
            assert -90 <= r["lat"] <= 90 and -180 <= r["lon"] <= 180, r
        for spelling in (r["name"], *r["aliases"]):    # одно написание — один город (Железногорск!)
            assert seen.setdefault(norm_city(spelling), (r["name"], r["country"])) == (r["name"], r["country"]), spelling
```
  и в `tests/integration/test_siberman_hall.py` → `test_geo_on_archive`: `assert all(c["name"] for c in g["countries"])` (со справочником у каждого города есть страна). Падение — править `cities.json` (страна «НЕ НАЙДЕН», дубль написания), не тест.

- [ ] **Step 3: Проверка глазами (координатор + пользователь).** Пройти вывод: тёзки-города (Железногорск — ожидаемо Красноярский край, 56.25, 93.53; Радужный (Владимирская область); Королёв; Дзержинск), страны (Апрелевка → Россия), «НЕ НАЙДЕН». Правки — прямо в `cities.json` (координаты, страна, iso, перенос написания в `aliases` нужного города). Повторный `--dry-run` — «новых написаний: 0».

- [ ] **Step 4: Прогоны** — `tests/unit/` — 978; интеграционные hall (7): `known` не меняется, страны и города — по справочнику.

- [ ] **Step 5: Commit** — `feat(siberman/hall): справочник городов для географии (Nominatim + проверка)`.

---

### Task 7: Библиотеки карты — после «да» пользователя

**Files:** Modify `deploy/download_static_libs.py`.

Координатор перед задачей спрашивает пользователя: скачать 4 файла (unpkg / jsdelivr, ~70 КБ + границы стран ~105 КБ) в `static/lib/` (в git не попадают; на проде — тем же скриптом при деплое).

- [ ] **Step 1:** В `LIBS` после записей Leaflet:
```python
    # Siberman /hall/geo: кластеры городов и границы стран
    "https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js":
        "markercluster-1.5.3/leaflet.markercluster.js",
    "https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css":
        "markercluster-1.5.3/MarkerCluster.css",
    "https://unpkg.com/topojson-client@3.1.0/dist/topojson-client.min.js":
        "topojson-client-3.1.0/topojson-client.min.js",
    "https://cdn.jsdelivr.net/npm/world-atlas@2.0.2/countries-110m.json":
        "world-atlas-2.0.2/countries-110m.json",
```

- [ ] **Step 2: Запуск** (после «да»): из корня worktree `C:\Users\podbo\miniconda3\python.exe deploy/download_static_libs.py` → в worktree появятся `static/lib/leaflet-1.9.4/…` и 4 новых файла (OK). Проверка: `node -e "JSON.parse(require('fs').readFileSync('static/lib/world-atlas-2.0.2/countries-110m.json'))"` без ошибок.

- [ ] **Step 3: Commit** — `chore(deploy): библиотеки карты для географии Siberman`.

---

### Task 8: Блок «Статистика»

**Files:** Modify `templates/siberman/hall_stats.html`, `static/css/siberman-hall.css`. Create `static/js/siberman-hall-stats.js`.

- [ ] **Step 1: Шаблон** — `hall_stats.html` целиком:
```html
<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Siberman — статистика</title>
<link rel="stylesheet" href="/static/css/siberman-hall.css?v={{ v }}">
</head>
<body>
<div class="hall" id="stats"><div class="state-msg">Загрузка…</div></div>
<script src="/static/js/siberman-hall.js?v={{ v }}"></script>
<script src="/static/js/siberman-hall-stats.js?v={{ v }}"></script>
</body>
</html>
```

- [ ] **Step 2: `siberman-hall-stats.js`:**
```js
'use strict';
// Блок «Статистика» (/hall/stats): Siberman в цифрах — люди и старты личного зачёта, эстафеты,
// всего людей, страны и города, таблица по годам (макет stats-geo-v10).

function plural(n, one, few, many) {
  const a = n % 10, b = n % 100;
  return a === 1 && b !== 11 ? one : a >= 2 && a <= 4 && (b < 12 || b > 14) ? few : many;
}

function render(s) {
  const i = s.individual, r = s.relay;
  const span = s.first_year === s.last_year ? s.first_year : `${s.first_year}–${s.last_year}`;
  const rows = s.years.map(y => `<tr><td><b>${y.year}</b></td><td>${y.ind_start} / ${y.ind_fin}</td>
    <td>${y.men} / ${y.women}</td><td>${y.relay_start} / ${y.relay_fin}</td><td>${y.newcomers}</td>
    <td>${hallTime(y.best_s)}</td></tr>`).join('');
  document.getElementById('stats').innerHTML = `
    <h3>Siberman в цифрах · ${span}</h3><div class="sub-h">Личный зачёт</div>
    <div class="st-two">
      <div class="st-grp"><div class="st-cap">Люди</div><div class="st-big">${i.people}</div>
        <div class="st-sub">${plural(i.people, 'человек стартовал', 'человека стартовали', 'человек стартовали')}<br>
          ${i.people_finished} из них ${plural(i.people_finished, 'финишировал', 'финишировали', 'финишировали')}</div>
        <div class="st-mf"><div class="m">мужчин<b>${i.people_men}</b></div><div class="f">женщин<b>${i.people_women}</b></div></div></div>
      <div class="st-grp"><div class="st-cap">Старты</div><div class="st-big">${i.starts}</div>
        <div class="st-sub">${plural(i.starts, 'старт', 'старта', 'стартов')} за все годы<br>
          ${i.finishes} ${plural(i.finishes, 'закончился', 'закончились', 'закончились')} финишем</div>
        <div class="st-mf"><div class="m">мужских<b>${i.starts_men}</b><span class="st-fin">финиш ${i.finishes_men}</span></div>
          <div class="f">женских<b>${i.starts_women}</b><span class="st-fin">финиш ${i.finishes_women}</span></div></div></div>
    </div>
    <div class="st-rel">Эстафеты: <b>${r.teams}</b> ${plural(r.teams, 'команда', 'команды', 'команд')},
      <b>${r.finished}</b> ${plural(r.finished, 'финишировала', 'финишировали', 'финишировали')}
      · в составах <b>${r.people}</b> ${plural(r.people, 'человек', 'человека', 'человек')}</div>
    <div class="st-foot"><span>Всего людей в Siberman <b>${s.people_total}</b></span>
      <span>стран <b>${s.countries}</b></span><span>городов <b>${s.cities}</b></span></div>
    <div class="tbl"><table class="years-tbl">
      <tr><th>Год</th><th>Личный<br>старт / финиш</th><th>М / Ж</th><th>Эстафеты<br>старт / финиш</th>
        <th>Новичков</th><th>Лучшее время</th></tr>${rows}</table></div>
    <div class="note">«Новичков» — первый старт человека в Siberman (лично или в эстафете). Страны и города —
      по людям, у которых известен город.</div>`;
}

hallLoad('/api/siberman/hall/stats').then(render)
  .catch(err => { document.getElementById('stats').innerHTML = `<div class="state-msg">${hallEsc(err.message)}</div>`; });
```

- [ ] **Step 3: CSS** — в `siberman-hall.css` перед `@media (max-width: 640px)`:
```css
/* Статистика и география */
.hall h3 { margin: 0 0 4px; color: var(--navy); text-align: center; font-weight: 800; }
.sub-h { text-align: center; font-size: 13px; color: var(--muted); margin-bottom: 10px; }
.st-two { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.st-grp { border: 1px solid var(--line); border-radius: 10px; padding: 12px; text-align: center; }
.st-cap { font-size: 13px; color: var(--muted); text-transform: uppercase; letter-spacing: .5px; }
.st-big { font-size: 34px; font-weight: 800; color: var(--navy); line-height: 1.1; }
.st-sub { font-size: 14px; margin-bottom: 8px; }
.st-mf { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
.st-mf > div { border-radius: 8px; padding: 6px; font-size: 13px; }
.st-mf b { display: block; font-size: 18px; }
.st-mf .m { background: var(--m); } .st-mf .f { background: var(--f); }
.st-fin { display: block; color: #9a9a9a; font-size: 12px; }
.st-rel { margin-top: 12px; border: 1px solid var(--line); border-radius: 10px; padding: 10px; text-align: center; font-size: 14px; }
.st-rel b, .st-foot b { color: var(--navy); font-size: 18px; }
.st-foot { display: flex; justify-content: center; gap: 18px; flex-wrap: wrap; margin: 10px 0 4px; font-size: 14px; color: var(--muted); }
.years-tbl { white-space: nowrap; margin-top: 8px; }
.note { font-size: 12px; color: var(--muted); text-align: center; margin-top: 8px; }
```
В `@media (max-width: 640px)` добавить строку `  .st-two, .geo-cols { grid-template-columns: 1fr; }`.

- [ ] **Step 4: Проверка** — `node --check static/js/siberman-hall-stats.js`; `tests/unit/` — 978; интеграционные hall — 7.

- [ ] **Step 5: Commit** — `feat(siberman/hall): блок «Статистика»`.

---

### Task 9: Блок «География»

**Files:** Modify `templates/siberman/hall_geo.html`, `static/css/siberman-hall.css`. Create `static/js/siberman-hall-geo.js`.

- [ ] **Step 1: Шаблон** — `hall_geo.html` целиком:
```html
<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Siberman — география</title>
<link rel="stylesheet" href="/static/lib/leaflet-1.9.4/leaflet.css">
<link rel="stylesheet" href="/static/lib/markercluster-1.5.3/MarkerCluster.css">
<link rel="stylesheet" href="/static/css/siberman-hall.css?v={{ v }}">
</head>
<body>
<div class="hall" id="geo">
  <h3>География участников</h3>
  <div class="geo-map"><div id="map"></div><div class="map-hint" id="map-hint">Двигайте карту двумя пальцами</div></div>
  <div class="note" id="geo-note"></div>
  <div class="geo-cols"><div class="geo-lst" id="countries"></div><div class="geo-lst" id="cities"></div></div>
  <div class="note">Считаем людей, а не участия: человек с несколькими стартами — один раз, по городу последнего старта.</div>
</div>
<script src="/static/lib/leaflet-1.9.4/leaflet.js"></script>
<script src="/static/lib/markercluster-1.5.3/leaflet.markercluster.js"></script>
<script src="/static/lib/topojson-client-3.1.0/topojson-client.min.js"></script>
<script src="/static/js/siberman-hall.js?v={{ v }}"></script>
<script src="/static/js/siberman-hall-geo.js?v={{ v }}"></script>
</body>
</html>
```

- [ ] **Step 2: `siberman-hall-geo.js`:**
```js
'use strict';
// Блок «География» (/hall/geo): карта Leaflet + Esri Light Gray, закрашенные страны участников, кружки
// городов с числом людей (близкие объединяются, распадаются при приближении), списки стран и городов.
// Колесо мыши над картой — масштаб; телефон: одним пальцем — прокрутка страницы, двумя — карта. Макет stats-geo-v10.

const CITY_LIMIT = 10;
const touch = L.Browser.touch && L.Browser.mobile;
const map = L.map('map', { scrollWheelZoom: true, worldCopyJump: true, dragging: !touch, tap: false });
map.attributionControl.setPrefix(false);                  // без «Leaflet» и флага; «Esri» — по условиям Esri
L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}',
  { maxZoom: 16, attribution: 'Esri' }).addTo(map);

if (touch) {
  const hint = document.getElementById('map-hint');
  let timer;
  map.getContainer().addEventListener('touchstart', e => {
    clearTimeout(timer);
    hint.style.opacity = e.touches.length === 1 ? 1 : 0;
    if (e.touches.length === 1) timer = setTimeout(() => { hint.style.opacity = 0; }, 1200);
  }, { passive: true });
}

const size = n => Math.round(22 + Math.sqrt(n) * 3.2);
const label = c => (c.country && c.country !== 'Россия' ? `${c.name}, ${c.country}` : c.name);
const icon = n => { const d = size(n); return L.divIcon({ className: 'city-pt', iconSize: [d, d], html: `<span>${n}</span>` }); };

function peopleHtml(c) {
  return `<b>${hallEsc(label(c))}</b> · ${c.count}<div class="pop-people">`
    + c.people.map(p => hallAthlete(p.person_id, hallEsc(p.fio))).join('<br>') + '</div>';
}

function drawCities(cities) {
  const group = L.markerClusterGroup({
    maxClusterRadius: 45, showCoverageOnHover: false, spiderfyOnMaxZoom: false, zoomToBoundsOnClick: true,
    iconCreateFunction: cl => {
      const kids = cl.getAllChildMarkers(), n = kids.reduce((s, m) => s + m.options.count, 0);
      cl.bindTooltip(hallEsc(kids.map(m => m.options.city).join(', ')), { direction: 'top', offset: [0, -size(n) / 2] });
      return icon(n);
    },
  });
  const placed = cities.filter(c => c.lat != null && c.lon != null);
  placed.forEach(c => {
    L.marker([c.lat, c.lon], { count: c.count, city: label(c), icon: icon(c.count) })
      .bindTooltip(hallEsc(label(c)), { direction: 'top', offset: [0, -size(c.count) / 2] })
      .bindPopup(peopleHtml(c)).addTo(group);
  });
  group.addTo(map);
  if (map.getSize().x < 560 || !placed.length) map.setView([55, 62], 2);   // телефон — Евразия
  else map.fitBounds(placed.map(c => [c.lat, c.lon]), { padding: [20, 20] });
}

// Кольца через линию перемены дат (Чукотка, Алеуты): отрицательные долготы +360°, иначе полосы через карту.
function unwrap(ring) {
  const xs = ring.map(c => c[0]);
  if (Math.max(...xs) - Math.min(...xs) > 180) ring.forEach(c => { if (c[0] < 0) c[0] += 360; });
}

async function drawCountries(countries) {
  const have = new Map(countries.filter(c => c.iso).map(c => [c.iso.padStart(3, '0'), c]));
  if (!have.size) return;
  try {
    const topo = await (await fetch('/static/lib/world-atlas-2.0.2/countries-110m.json')).json();
    const fc = topojson.feature(topo, topo.objects.countries);
    fc.features = fc.features.filter(f => f.geometry && have.has(String(f.id).padStart(3, '0')));
    fc.features.forEach(f => {
      const g = f.geometry;
      (g.type === 'Polygon' ? [g.coordinates] : g.coordinates).forEach(p => p.forEach(unwrap));
    });
    L.geoJSON(fc, {
      style: { color: '#003D62', weight: 1, fillColor: '#003D62', fillOpacity: 0.18 },
      onEachFeature: (f, layer) => {
        const c = have.get(String(f.id).padStart(3, '0'));
        layer.bindTooltip(hallEsc(`${c.name} · ${c.count} чел.`), { sticky: true });
      },
    }).addTo(map).bringToBack();
  } catch (e) { /* без границ стран карта остаётся рабочей */ }
}

function renderCities(list, all) {
  const shown = all ? list : list.slice(0, CITY_LIMIT);
  const more = list.length > CITY_LIMIT
    ? `<button type="button" class="geo-more" id="geo-more">${all ? 'Свернуть' : `Все города (${list.length})`}</button>` : '';
  document.getElementById('cities').innerHTML = '<div class="geo-h">Города</div>'
    + shown.map(c => `<div><span>${hallEsc(c.name)}${c.country && c.country !== 'Россия' ? ` <i>${hallEsc(c.country)}</i>` : ''}</span>
      <b>${c.count}</b></div>`).join('') + more;
  const btn = document.getElementById('geo-more');
  if (btn) btn.onclick = () => renderCities(list, !all);
}

function drawLists(g) {
  document.getElementById('geo-note').textContent = `Город известен у ${g.known} из ${g.total} человек `
    + '(в протоколах эстафет города нет). Закрашены страны участников; число в кружке — сколько людей, нажмите — кто.';
  document.getElementById('countries').innerHTML = '<div class="geo-h">Страны</div>'
    + g.countries.map(c => `<div><span>${hallEsc(c.name || 'Страна не указана')}</span><b>${c.count}</b></div>`).join('');
  renderCities(g.cities, false);
}

hallLoad('/api/siberman/hall/geo').then(g => { drawCities(g.cities); drawCountries(g.countries); drawLists(g); })
  .catch(err => { document.querySelector('.geo-map').outerHTML = `<div class="state-msg">${hallEsc(err.message)}</div>`; });
```

- [ ] **Step 3: CSS** — после блока «Статистика и география» (Task 8):
```css
.geo-map { position: relative; }
#map { height: 380px; border-radius: 8px; }
.map-hint { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; padding: 0 20px; background: rgba(0, 0, 0, .45); color: #fff; font-weight: 800; text-align: center; border-radius: 8px; opacity: 0; transition: opacity .2s; pointer-events: none; z-index: 1000; }
.leaflet-container.leaflet-touch-zoom:not(.leaflet-touch-drag) { touch-action: pan-y; }
.leaflet-control-attribution { font-size: 10px; background: rgba(255, 255, 255, .6) !important; }
.hall .leaflet-bar a, .hall .leaflet-popup-close-button { border-bottom: 0; }
.city-pt { background: rgba(190, 10, 33, .85); border: 2px solid #fff; border-radius: 50%; box-shadow: 0 1px 4px rgba(0, 0, 0, .3); display: flex; align-items: center; justify-content: center; color: #fff; font-weight: 800; font-size: 12px; box-sizing: border-box; }
.city-pt span { line-height: 1; }
.pop-people { max-height: 220px; overflow: auto; margin-top: 4px; line-height: 1.6; }
.geo-cols { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-top: 12px; }
.geo-h { font-weight: 800; margin-bottom: 4px; }
.geo-lst { font-size: 14px; }
.geo-lst > div:not(.geo-h) { display: flex; justify-content: space-between; gap: 8px; border-top: 1px solid var(--line); padding: 6px 2px; }
.geo-lst b { color: var(--navy); }
.geo-lst i { font-style: normal; color: var(--muted); font-size: 12px; }
.geo-more { margin-top: 6px; padding: 5px 10px; border: 1px solid var(--navy); border-radius: 6px; background: #fff; color: var(--navy); font: inherit; font-size: 13px; cursor: pointer; }
```
В `@media (max-width: 640px)` добавить `  #map { height: 320px; }`.

- [ ] **Step 4: Проверка** — `node --check static/js/siberman-hall-geo.js`; `tests/unit/` — 978; интеграционные hall — 7.

- [ ] **Step 5: Commit** — `feat(siberman/hall): блок «География» — карта, страны, города`.

---

### Task 10: Админка «Люди» — вкладка «Без города», город в карточке

**Files:** Modify `templates/siberman/people_admin.html`, `static/js/siberman-people-admin.js`.

- [ ] **Step 1: Шаблон.** Вкладка — после «Журнал»: `<button class="admin-tab" data-tab="nocity">Без города <span id="nocity-count"></span></button>`. Секция — после `tab-journal`:
```html
  <section id="tab-nocity" class="tab-content">
    <p class="muted">Люди, у которых город неизвестен ни по протоколам, ни по заявкам (в протоколах эстафет города нет).
      Введённый город попадёт в блок «География» в течение минуты; действие отменяется в журнале.</p>
    <input id="nocity-q" class="search" placeholder="Фильтр по фамилии, году или команде" autocomplete="off">
    <table class="tbl" id="nocity"></table>
    <div id="nocoords"></div>
  </section>
```

- [ ] **Step 2: JS.**
  - После `let searchTimer = null;`: `let noCity = null;`
  - В `renderCard` после строки с датой рождения (`…${card.reviews.length ? … : ''}</div>`):
```js
    <div class="row">Город вручную <input id="city" value="${esc(p.city_manual || '')}" placeholder="${esc(p.city || '')}" maxlength="100" style="width:220px">
      <button class="btn-small" id="city-save">Сохранить</button>
      <span class="muted">для карты «География» главнее протокола; пусто — город из протоколов</span></div>
```
    и после обработчика `bd-save`:
```js
  document.getElementById('city-save').onclick = () =>
    act(() => post(`/${p.id}/city`, { city: document.getElementById('city').value }), 'Город сохранён');
```
  - Перед `async function refreshAll()`:
```js
const norm = s => String(s ?? '').toLowerCase().replace(/ё/g, 'е');

function startsText(r) {
  return r.starts.map(s => `${s.year} ${s.format === 'individual' ? 'личный' : STAGES[s.stage] + ' «' + s.team + '»'}`).join('; ');
}

function renderNoCity() {
  if (!noCity) return;
  const q = norm(document.getElementById('nocity-q').value.trim());
  const rows = noCity.people.filter(r => !q || norm(`${r.fio} ${startsText(r)}`).includes(q));
  document.getElementById('nocity').innerHTML = '<tr><th>ФИ</th><th>Выступления</th><th>Город</th></tr>'
    + rows.map(r => `<tr><td>${r.person_id ? `<a href="#" data-card="${r.person_id}">${esc(r.fio)}</a>` : esc(r.fio)}</td>
      <td>${esc(startsText(r))}</td>
      <td>${r.person_id ? `<input data-city-for="${r.person_id}" placeholder="Город" maxlength="100" style="width:160px">
        <button class="btn-small" data-city-save="${r.person_id}">Сохранить</button>` : '<span class="muted">не в реестре</span>'}</td></tr>`).join('');
  const nc = noCity.no_coords;
  document.getElementById('nocoords').innerHTML = nc.length ? `<div class="card"><h2>Города без координат (${nc.length})</h2>
    <p class="muted">В списках «Географии» есть, на карте нет. Добавить: <code>python scripts/siberman_geocode_cities.py</code>,
    проверить <code>data/siberman/cities.json</code> и выложить.</p>
    ${nc.map(c => `<div>${esc(c.name)}${c.country ? ', ' + esc(c.country) : ''} — ${c.count}</div>`).join('')}</div>` : '';
}

async function loadNoCity() {
  noCity = await api('/no-city');
  document.getElementById('nocity-count').textContent = noCity.people.length ? `(${noCity.people.length})` : '';
  renderNoCity();
}
```
  - В `refreshAll` после `await loadJournal();`: `await loadNoCity();`
  - В обработчике кликов перед `if (t.matches('[data-undo]'))`:
```js
  if (t.matches('[data-city-save]')) {
    const id = t.dataset.citySave, v = document.querySelector(`[data-city-for="${id}"]`).value.trim();
    if (!v) return msg('Введите город', 'error');
    act(() => post(`/${id}/city`, { city: v }), 'Город сохранён');
    return;
  }
```
  - После обработчика `search`: `document.getElementById('nocity-q').addEventListener('input', renderNoCity);`

- [ ] **Step 3: Проверка** — `node --check static/js/siberman-people-admin.js`; интеграционные persons — 23.

- [ ] **Step 4: Commit** — `feat(siberman/admin): вкладка «Без города» и город в карточке человека`.

---

### Task 11: Вставка в Тильду, проверка в браузере, документы

**Files:** Modify `docs/siberman/hall-tilda-snippet.md`. Основной репозиторий: `.taskmaster/tasks/todo.md` — координатор.

- [ ] **Step 1: Сниппет.** В `docs/siberman/hall-tilda-snippet.md`: в первом абзаце «Два HTML-блока» → «Четыре HTML-блока», добавить «статистика — на месте блока «Siberman в цифрах», география — на месте «География участников»»; в абзац про меню — «Рекорды и итоги» → `#hall-records` (как было), статистика и география — якоря `#hall-stats`, `#hall-geo` (если в меню есть отдельные пункты). После «Блок 2 — «Рекорды»» — два раздела по тому же образцу (тот же `<script>` со слушателем автовысоты):
  - «Блок 3 — «Статистика»»: `<a id="hall-stats" name="hall-stats"></a>` и `<iframe class="sbm-hall" src="https://live.siberman515.com/hall/stats" style="width:100%;border:0;height:900px" title="Siberman в цифрах"></iframe>`;
  - «Блок 4 — «География»»: `<a id="hall-geo" name="hall-geo"></a>` и `<iframe class="sbm-hall" src="https://live.siberman515.com/hall/geo" style="width:100%;border:0;height:800px" title="Siberman — география участников"></iframe>`.

- [ ] **Step 2: Проверка в браузере** — сервер `serve.py` из scratchpad сессии (`C:\Users\podbo\AppData\Local\Temp\claude\c--Users-podbo--------------------KM-track\77cf03bd-db91-4aec-a7c4-dc1aa8f02b62\scratchpad`) в фоне из корня worktree, порт 8011; Playwright (python, `channel="chrome"`), домен `siberman.localhost:8011`; десктоп 1100×900 и телефон 390×800 (`is_mobile`, `has_touch`). Скрипты и скриншоты — в scratchpad. Числа записать:

`/hall/stats`:
1. Нет `pageerror`, нет 4xx/5xx.
2. Заголовок «Siberman в цифрах · 2016–2025»; большие числа 170 и 204; «165 из них», «196 закончились»; мужчин 156, женщин 14; мужских 189 (финиш 184), женских 15 (финиш 12); эстафеты 73 / 71; всего людей 337; стран и городов — числа (записать).
3. Таблица по годам — 10 строк, сверху 2025; сумма «личный старт» по строкам = 204.
4. Телефон: колонки «Люди» / «Старты» друг под другом, страница без горизонтальной прокрутки (`scrollWidth <= innerWidth`); таблица по годам прокручивается внутри `.tbl`.

`/hall/geo`:
5. Нет ошибок; запросы к `/static/lib/…` и `countries-110m.json` — 200.
6. Кружков-кластеров и кружков-городов на карте > 0 (`.city-pt`); закрашенных стран (`path.leaflet-interactive` слоя стран) = числу стран с ISO в API.
7. Наведение на кружок — подсказка (название; у иностранного — «город, страна»); нажатие на одиночный город — всплывающий список людей, ссылки `/athlete/<id>` с `target=_blank`.
8. Колесо мыши над картой меняет масштаб (`map.getZoom()` до/после), колесо вне карты — прокручивает страницу и не меняет масштаб.
9. Телефон: `dragging` выключен, касание одним пальцем показывает подсказку «Двигайте карту двумя пальцами»; вид — Евразия (zoom 2); без горизонтальной прокрутки.
10. Подпись «Город известен у N из 337»; список стран, городов 10 + кнопка «Все города (N)» раскрывает и сворачивает.
11. Атрибуция: «Esri» есть, «Leaflet» — нет.

`/admin/people` (вход — cookie из `create_session_cookie`, пароль не вводить; как в проверке плана 1):
12. Вкладка «Без города (N)» — N = `total − known` из API geo; фильтр по команде сужает список; в карточке человека есть поле «Город». Город НЕ сохранять (данные локальной БД — не трогать; сохранение покрыто интеграционным тестом).

iframe: локальная страница в scratchpad с 4 iframe и скриптом из сниппета (origin заменён на `http://siberman.localhost:8011`) → высоты > 300 и ≈ высоте блоков; карта внутри iframe реагирует на колесо.

Скриншоты (десктоп и телефон обоих блоков, всплывающий список города, вкладка админки) — посмотреть глазами. Сервер остановить.

- [ ] **Step 3: Полный прогон** — `tests/unit/` — 978; интеграционные hall + persons — 30.

- [ ] **Step 4: Commit** — `docs(siberman/hall): вставка статистики и географии в Тильду`.

- [ ] **Step 5: Отчёт координатору** — числа Step 2–3, пути к скриншотам, замечания по виду. Если пункт не выполняется — код не чинить, описать.

---

## Self-review (сделан при написании плана)

- Спецификация §6 (две колонки «Люди» / «Старты», М/Ж, строка эстафет, всего людей, стран, городов, таблица по годам, «старт» без dns, сверка 204/196, 170/165, 156/14, 189/184, 15/12, 73/71) — Task 3, 5, 8. §7 (люди по реестру, город последнего старта → реестр → заявка; справочник с написаниями и ISO; Nominatim раз в секунду + проверка глазами; города без координат — в списках и в админке; Leaflet + Esri без «Leaflet»; закрашенные страны с подсказкой; Чукотка/Алеуты; кружок с числом, подсказка «город, страна», список людей по нажатию, markercluster; колесо над картой; телефон — два пальца, подсказка, Евразия; списки стран и городов; без переключателя, подпись «известен у N из M») — Task 1, 2, 6, 7, 9; ввод города в админке — Task 4, 10. §11 (503 → «Данные временно недоступны», год без стартов не попадает) — `hallLoad`, Task 3. §12 (unit: статистика, нормализация городов; integration: сверка статистики, нет `birthdate`; браузер: iframe, жесты карты) — Task 1–5, 11.
- Отступления от спецификации: библиотеки — `static/lib/` через `download_static_libs.py` (не `static/vendor/`); «города без координат» — во вкладке «Без города» админки.
- Имена: `person_of`, `load_people` (data) → geo, stats, persons.service; `City`, `load_cities`, `city_of`, `applicant_cities`, `resolve_places`, `build_geo`, `missing_report`, `CITIES_PATH` (geo); `build_stats(entries, teams, geo)`; `service.stats()`, `service.geography()`; `persons.service.set_city`, `no_city`; JS — `hallEsc`, `hallTime`, `hallAthlete`, `hallLoad` из `siberman-hall.js`.
- Числа тестов: unit 966 → 969 (T1) → 971 (T2) → 974 (T3) → 977 (T5a) → 978 (T6); интеграционные persons 20 → 22 (T4) → 23 (T5a), hall 5 → 7 (T5); hall + persons 25 → 30.
