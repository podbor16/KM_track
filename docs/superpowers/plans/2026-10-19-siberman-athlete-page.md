# Siberman: страница спортсмена и медали — план реализации (план 4 из 4)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Отдельная страница `/athlete/{person_id}` на live.siberman515.com — всё о человеке за все годы (шапка, сводка, медали, лучшие результаты, все участия, рекорды); на неё уже ведут ссылки ФИ из рейтинга, рекордов и географии. Медали — кружки-заглушки, картинка подхватывается, если файл есть.

**Architecture:** Чистый модуль `src/siberman/hall/athlete.py` строит страницы всех людей реестра из того же снимка, что рейтинг и рекорды (`service._build`, кэш 60 с): записи, команды, история рекордов, места года, города людей. API `/api/siberman/athlete/{id}` отдаёт страницу из снимка; HTML-страница — шаблон + JS по образцу блоков hall (`siberman-hall.js`, `siberman-hall.css`), но не iframe.

**Tech Stack:** Python 3.13, FastAPI 0.104, pytest; JS без библиотек; Onest, `siberman-hall.css`.

**Спецификация:** `docs/superpowers/specs/2026-10-18-siberman-hall-ratings-records-design.md` §8 (страница), §9 (медали), §10 («следующая медаль» — возможно уберём, пока оставляем), §11–§12. Макет: `.superpowers/brainstorm/36-1792309228/content/athlete-v2.html` (основной репозиторий).

**Рабочее место:** worktree `.worktrees/siberman-hall`, ветка `feature/siberman-hall` (планы 1–3 там, HEAD a0d4247 или новее). Тесты: `C:\Users\podbo\miniconda3\python.exe -m pytest <файлы> -q -p no:cacheprovider` из корня worktree (`conda run` зависает). До плана: unit 979, интеграционные hall 7 + persons 23.

---

## Принятые правила

- Страница есть у человека реестра (`person_id`), у которого есть хоть один старт (`data.is_start`). Нет такого — 404-страница Siberman («Спортсмен не найден»); нечисловой id — тоже 404. Чужой домен — 404 (как блоки hall).
- **Шапка:** ФИ последнего старта; город и страна — как на карте «География» (`geo.resolve_places`: ручной → последний старт с городом → заявка из справочника); «Siberman с {год первого старта}»; личный номер крупно, если есть `bib_individual`.
- **Сводка:** стартов (год+номер, человек на двух этапах одной команды — один старт), финишей лично (`race_time`), эстафет (стартов в эстафете), действующих рекордов (клетки, где человек — держатель или в составе команды-держателя).
- **Медали:** по порядку личных финишей `medal_for(n)` (1-й — серебро, 2-й — чёрная…); эстафетная — за каждый финиш команды, меньше; следующая — бледная `medal_for(финишей + 1)`. Картинка — `static/img/siberman/medals/{key}.webp`, если файл есть (`medal_for` отдаёт `image`), иначе кружок цвета медали (шестигранники — шестиугольник).
- **Лучшие результаты:** гонка (личный итог) и каждый отрезок (плавание, вело, вело д1, вело д2, бег) — лучшее время среди личных стартов и своего этапа эстафеты (`segment_time`, как рекорды); у гонки — место года; «РЕКОРД», если это время — действующий рекорд. Под ними — лучшее место (абсолют, год) и позиция в рейтинге «лучший на человека» (абсолют личников, сортировка время → год, как страница рейтинга) «N из M».
- **Все участия:** по годам (новые сверху), только старты. Личный: «N-й финиш», итог / DNF (этап) / DSQ / «на дистанции» (живой год), место абсолютное / среди своего пола, «РЕКОРД» у действующего рекорда гонки. Эстафета: этап, команда (ссылка на карточку команды года), время команды, место среди эстафет. Времена этапов — плавание / вело (д1+д2) / бег: этап пройден до последней КТ (и у сошедшего позже), иначе «—»; у эстафетчика — только свой этап. Ссылка «карточка» → `/participant/{номер}?year=`.
- **Места года:** личники-финишёры года по (итог, номер) — абсолютное и внутри пола; команды с итогом — по (итог, номер).
- **Рекорды:** все записи истории (`records.history`), где человек — держатель (личник или эстафетчик) или в составе команды-держателя; действующие сверху, затем по порядку клеток таблицы; у побитых — «побит в {год} ({время})» (следующая запись истории клетки).
- ПДн: в API нет `birthdate` — только то, что уже публично (ФИО, город, номера, времена).
- Выкладка планов 2–4 — вместе, только с разрешения пользователя (после merge жеребьёвки).

## Файлы

| Файл | Что |
|---|---|
| `src/siberman/medals.py` | + `image` (если файл картинки есть) |
| `src/siberman/hall/athlete.py` | новый: `build_athletes` |
| `src/siberman/hall/service.py`, `router.py` | снимок + `athlete()`; `/athlete/{id}`, `/api/siberman/athlete/{id}` |
| `app.py`, `deploy/nginx.conf` | префикс техработ `/athlete/`, путь `athlete/` в nginx |
| `templates/siberman/athlete.html`, `static/js/siberman-athlete.js`, `static/css/siberman-hall.css`, `static/js/siberman-hall.js`, `static/js/siberman-hall-stats.js` | страница; `hallPlural` — общий |
| Тесты | `tests/unit/test_siberman_hall_athlete.py` (новый), `tests/unit/test_siberman_hall.py` (медали), `tests/integration/test_siberman_hall.py` |

---

### Task 1: Медали — картинка, если файл есть

**Files:** Modify `src/siberman/medals.py`, `tests/unit/test_siberman_hall.py`.

- [ ] **Step 1: Тесты.** В `test_medals_by_finish_number` строку `assert set(medal_for(3)) == {"key", "name", "color"}` заменить на `assert set(medal_for(3)) == {"key", "name", "color", "image"}`. После теста:
```python
def test_medal_image_only_when_file_exists(tmp_path, monkeypatch):
    from src.siberman import medals
    monkeypatch.setattr(medals, "MEDALS_DIR", tmp_path)
    (tmp_path / "gold.webp").write_bytes(b"x")
    assert medal_for(3)["image"] == "/static/img/siberman/medals/gold.webp"
    assert medal_for(1)["image"] is None and medal_for(None, relay=True)["image"] is None
```
- [ ] **Step 2: Красный прогон** — `tests/unit/test_siberman_hall.py`: 2 failed.
- [ ] **Step 3: `medals.py`.** Докстринг модуля, вторая фраза: «8-й и дальше — пока как 7-й. Картинка — static/img/siberman/medals/{key}.webp, если файл есть; иначе страница рисует кружок цвета медали.» Импорт `from pathlib import Path`, после импортов `MEDALS_DIR = Path(__file__).resolve().parents[2] / "static" / "img" / "siberman" / "medals"`. Конец `medal_for`:
```python
    image = f"/static/img/siberman/medals/{key}.webp" if (MEDALS_DIR / f"{key}.webp").exists() else None
    return {"key": key, "name": name, "color": color, "image": image}
```
- [ ] **Step 4: Зелёный прогон** — файл зелёный; `tests/unit/` — 980.
- [ ] **Step 5: Commit** — `feat(siberman): медаль с картинкой, если файл есть`.

---

### Task 2: Данные страницы спортсмена

**Files:** Create `src/siberman/hall/athlete.py`, `tests/unit/test_siberman_hall_athlete.py`.

- [ ] **Step 1: Тесты** — `tests/unit/test_siberman_hall_athlete.py`:
```python
from types import SimpleNamespace as NS

from src.siberman.hall.athlete import build_athletes
from src.siberman.hall.data import Entry, build_teams
from src.siberman.hall.geo import City
from src.siberman.hall.records import build_records

ALL = frozenset({"swim", "bike_day1", "bike_day2", "run"})
STAGES = {"swim": ("swim",), "bike": ("bike_day1", "bike_day2"), "run": ("run",)}
KRS = City("Красноярск", "Россия", "643", 56.01, 92.85)


def ind(year, bib, pid, total, times, status="active", finished=ALL, dnf_stage=None):
    sw, b1, b2, ru = times
    return Entry(year=year, bib=str(bib), stage="none", format="individual", surname=f"Личник{pid}", name="Тест",
                 gender="M", status=status, dnf_stage=dnf_stage, person_id=pid,
                 overall_s=total if status == "active" else None,
                 times={"swim": sw, "bike_day1": b1, "bike_day2": b2, "run": ru}, finished=finished, has_time=True)


def rel(year, bib, role, pid, times):
    return Entry(year=year, bib=str(bib), stage=role, format="relay", surname=f"Этапник{pid}", name="Тест", gender="M",
                 team="Столбы", person_id=pid, times=dict(zip(STAGES[role], times)), finished=frozenset(STAGES[role]),
                 has_time=True)


ENTRIES = [
    ind(2019, 7, 1, 200, (30, 50, 60, 60)),
    rel(2020, 101, "swim", 5, (25,)), rel(2020, 101, "bike", 6, (40, 50)), rel(2020, 101, "run", 1, (50,)),
    ind(2021, 7, 1, 180, (28, 45, 55, 52)), ind(2021, 8, 2, 170, (29, 44, 50, 47)),
    ind(2022, 7, 1, None, (27, 44, 54, 0), status="dnf", dnf_stage="run",
        finished=frozenset({"swim", "bike_day1", "bike_day2"})),
    ind(2022, 9, 3, 150, (20, 40, 45, 45)),
    ind(2022, 10, 4, None, (0, 0, 0, 0), status="dns", finished=frozenset()),   # не стартовал — страницы нет
    ind(2022, 11, None, 160, (21, 41, 46, 46)),                                   # не в реестре — страницы нет
]


def pages():
    teams = build_teams(ENTRIES)
    return build_athletes(ENTRIES, teams, build_records(ENTRIES, teams), {1: KRS}, [NS(id=1, bib_individual="7")])


def test_header_summary_and_medals():
    all_pages = pages()
    assert set(all_pages) == {1, 2, 3, 5, 6}
    p = all_pages[1]
    assert p["person"] == {"id": 1, "fio": "Личник1 Тест", "city": "Красноярск", "country": "Россия", "since": 2019, "bib": "7"}
    assert p["summary"] == {"starts": 4, "finishes": 2, "relays": 1, "records": 2}
    assert [(m["n"], m["year"], m["medal"]["key"]) for m in p["medals"]] == [(1, 2019, "silver"), (2, 2021, "black")]
    assert [(m["year"], m["team"], m["medal"]["key"]) for m in p["relay_medals"]] == [(2020, "Столбы", "relay_silver")]
    assert p["next_medal"]["key"] == "gold"


def test_participations_places_and_stage_times():
    rows = pages()[1]["participations"]
    assert [r["year"] for r in rows] == [2022, 2021, 2020, 2019]
    dnf, fin, relay, first = rows
    assert (dnf["status"], dnf["dnf_stage"], dnf["finish_no"], dnf["place"]) == ("dnf", "run", None, None)
    assert dnf["times"] == {"swim": 27, "bike": 98, "run": None}             # сошёл на беге: этапы до него есть
    assert (fin["time_s"], fin["finish_no"], fin["place"], fin["record"]) == (180, 2, {"abs": 2, "gender": 2}, False)
    assert (relay["stage"], relay["team"], relay["time_s"], relay["place"]) == ("run", "Столбы", 165, {"relay": 1})
    assert relay["times"] == {"run": 50} and relay["record"] is True       # действующий рекорд эстафеты гонки
    assert (first["place"], first["finish_no"]) == ({"abs": 1, "gender": 1}, 1)


def test_best_results_rating_and_records():
    p = pages()[1]
    best = {b["seg"]: b for b in p["best"]}
    assert (best["race"]["time_s"], best["race"]["year"], best["race"]["place"], best["race"]["record"]) == (180, 2021, 2, False)
    assert (best["swim"]["time_s"], best["swim"]["year"]) == (28, 2021)      # сход 2022 в рекорды и лучшие не идёт
    assert (best["run"]["time_s"], best["run"]["year"], best["run"]["record"]) == (50, 2020, True)
    assert p["best_place"] == {"place": 1, "year": 2019}
    assert p["rating"] == {"position": 4, "total": 4}                        # 150, 160 (вне реестра), 170, 180
    recs = p["records"]
    assert [r["cell"] for r in recs if r["current"]] == ["race:relay:X", "run:relay:M"]
    assert recs[0]["team"] == "Столбы"
    old = next(r for r in recs if r["cell"] == "race:individual:M")
    assert (old["year"], old["current"], old["beaten"]) == (2019, False, {"year": 2021, "time_s": 170})
```

- [ ] **Step 2: Красный прогон** — `ModuleNotFoundError: ... hall.athlete`.

- [ ] **Step 3: `athlete.py`:**
```python
"""
Страница спортсмена Siberman (спецификация hall §8): всё о человеке за все годы — шапка, сводка,
медали по порядку личных финишей, лучшие результаты гонки и отрезков, все участия с местами и
временами этапов, рекорды действующие и побитые. Строится для всех людей реестра сразу, в снимке.
"""
from collections import defaultdict

from src.siberman.hall.data import bib_order, is_start, person_of, race_time, segment_time
from src.siberman.hall.records import SEG_ROLE, SEG_STAGES, SEGMENTS, cell_keys
from src.siberman.medals import medal_for

SHOWN = {"swim": ("swim",), "bike": ("bike_day1", "bike_day2"), "run": ("run",)}   # столбцы «Плавание / Вело / Бег»


def _done(e, stages: tuple):
    """Время этапа, пройденного до последней КТ (и у сошедшего позже); иначе None."""
    if any(s not in e.finished or (e.times.get(s) or 0) <= 0 for s in stages):
        return None
    return sum(e.times[s] for s in stages)


def _times(e) -> dict:
    roles = ("swim", "bike", "run") if e.format == "individual" else (e.stage,)
    return {r: _done(e, SHOWN[r]) for r in roles}


def _places(entries: list, teams: list) -> dict:
    """('i', год, номер) → {'abs', 'gender'} у личников-финишёров; ('r', год, номер) → {'relay'} у команд с итогом."""
    out, years = {}, defaultdict(list)
    for e in entries:
        t = race_time(e)
        if t is not None:
            years[e.year].append((t, bib_order(e.bib), e))
    for rows in years.values():
        rows.sort(key=lambda r: r[:2])
        in_gender = defaultdict(int)
        for i, (_, _, e) in enumerate(rows, 1):
            in_gender[e.gender] += 1
            out[("i", e.year, e.bib)] = {"abs": i, "gender": in_gender[e.gender]}
    by_year = defaultdict(list)
    for t in teams:
        if t.time_s is not None:
            by_year[t.year].append(t)
    for rows in by_year.values():
        rows.sort(key=lambda t: (t.time_s, bib_order(t.bib)))
        for i, t in enumerate(rows, 1):
            out[("r", t.year, t.bib)] = {"relay": i}
    return out


def _rating_positions(entries: list) -> dict:
    """Человек (data.person_of) → место в рейтинге «лучший на человека» (абсолют личников: время, год)."""
    best = {}
    for e in entries:
        t = race_time(e)
        if t is not None:
            k = person_of(e)
            if k not in best or (t, e.year) < best[k]:
                best[k] = (t, e.year)
    order = sorted(best, key=lambda k: best[k])
    return {k: {"position": i, "total": len(order)} for i, k in enumerate(order, 1)}


def _held_records(history: dict) -> dict:
    """person_id → записи истории рекордов, где человек — держатель или в составе команды-держателя."""
    out = defaultdict(list)
    for cell, h in history.items():
        for i, r in enumerate(h):
            holder = r["holder"]
            if holder["type"] == "team":
                pids, team = {m["person_id"] for m in holder["members"]}, holder["name"]
            else:
                pids, team = {holder["person_id"]}, holder["team"]
            nxt = h[i + 1] if i + 1 < len(h) else None
            for pid in pids - {None}:
                out[pid].append({"cell": cell, "time_s": r["time_s"], "year": r["year"], "bib": holder["bib"],
                                 "team": team or None, "current": nxt is None,
                                 "beaten": {"year": nxt["year"], "time_s": nxt["time_s"]} if nxt else None})
    order = {k: i for i, k in enumerate(cell_keys())}
    for recs in out.values():
        recs.sort(key=lambda r: (not r["current"], order[r["cell"]], r["year"]))
    return out


def _page(pid: int, starts: list, team_of: dict, places: dict, rating: dict, bib, city, recs: list) -> dict:
    finishes = [e for e in starts if race_time(e) is not None]
    finish_no = {(e.year, e.bib): i for i, e in enumerate(finishes, 1)}
    relays = {(e.year, e.bib): team_of[(e.year, e.bib)] for e in starts if e.format == "relay"}
    current = [r for r in recs if r["current"]]

    def race_record(e) -> bool:
        return any(r["cell"].startswith("race:") and (r["year"], r["bib"]) == (e.year, e.bib) for r in current)

    def outcome(time_s, status) -> str:
        return "finished" if time_s is not None else status if status in ("dnf", "dsq") else "racing"

    rows = []
    for e in sorted(starts, key=lambda e: (-e.year, e.format != "individual", e.stage)):
        row = {"year": e.year, "bib": e.bib, "format": e.format, "stage": e.stage, "dnf_stage": e.dnf_stage,
               "times": _times(e), "record": race_record(e)}
        if e.format == "individual":
            t = race_time(e)
            row.update(gender=e.gender, time_s=t, status=outcome(t, e.status),
                       finish_no=finish_no.get((e.year, e.bib)), place=places.get(("i", e.year, e.bib)))
        else:
            tm = relays[(e.year, e.bib)]
            row.update(team=tm.name, time_s=tm.time_s, status=outcome(tm.time_s, tm.status),
                       place=places.get(("r", e.year, e.bib)))
        rows.append(row)

    best = []
    for seg in SEGMENTS:
        cands = []
        for e in starts:
            if seg == "race":
                v = race_time(e)
            elif e.format == "individual" or e.stage == SEG_ROLE[seg]:
                v = segment_time(e, SEG_STAGES[seg])
            else:
                v = None
            if v is not None:
                cands.append((v, e.year, e))
        if cands:
            v, y, e = min(cands, key=lambda c: c[:2])
            best.append({"seg": seg, "time_s": v, "year": y,
                         "place": (places.get(("i", y, e.bib)) or {}).get("abs") if seg == "race" else None,
                         "record": any(r["cell"].startswith(seg + ":") and (r["time_s"], r["year"]) == (v, y)
                                       for r in current)})
    placed = [(places[("i", e.year, e.bib)]["abs"], e.year) for e in finishes]
    return {
        "person": {"id": pid, "fio": starts[-1].fio, "city": city.name if city else "",
                   "country": city.country if city else "", "since": starts[0].year, "bib": bib},
        "summary": {"starts": len({(e.year, e.bib) for e in starts}), "finishes": len(finishes),
                    "relays": len(relays), "records": len(current)},
        "medals": [{"n": i, "year": e.year, "medal": medal_for(i)} for i, e in enumerate(finishes, 1)],
        "relay_medals": [{"year": t.year, "team": t.name, "medal": medal_for(None, relay=True)}
                         for t in relays.values() if t.time_s is not None],
        "next_medal": medal_for(len(finishes) + 1),
        "best": best,
        "best_place": {"place": min(placed)[0], "year": min(placed)[1]} if placed else None,
        "rating": rating.get(pid),
        "participations": rows,
        "records": recs,
    }


def build_athletes(entries: list, teams: list, records: dict, places: dict, persons: list) -> dict:
    """person_id → страница спортсмена: люди реестра, у кого есть старт (data.is_start). places — город
    человека (geo.resolve_places), persons — реестр (личный номер)."""
    team_of = {(t.year, t.bib): t for t in teams}
    year_places = _places(entries, teams)
    rating = _rating_positions(entries)
    bibs = {p.id: p.bib_individual for p in persons}
    held = _held_records(records["history"])
    starts = defaultdict(list)
    for e in sorted(entries, key=lambda e: e.year):
        if e.person_id and is_start(e):
            starts[e.person_id].append(e)
    return {pid: _page(pid, es, team_of, year_places, rating, bibs.get(pid), places.get(pid), held.get(pid, []))
            for pid, es in starts.items()}
```

- [ ] **Step 4: Зелёный прогон** — файл: 3 passed; `tests/unit/` — 983.

- [ ] **Step 5: Commit** — `feat(siberman/hall): данные страницы спортсмена — сводка, медали, лучшие, участия, рекорды`.

---

### Task 3: Снимок, API, страница, маршрутизация + архив

**Files:** Modify `src/siberman/hall/service.py`, `src/siberman/hall/router.py`, `app.py`, `deploy/nginx.conf`, `tests/integration/test_siberman_hall.py`. Create `templates/siberman/athlete.html` (полная разметка — здесь; JS и CSS — Task 4).

- [ ] **Step 1: Тесты** (`tests/integration/test_siberman_hall.py`):
  - импорт `from src.siberman.hall.athlete import build_athletes`;
  - фикстура `archive`: `places = hgeo.resolve_places(entries, persons, applicants, hgeo.load_cities())`, `geo = hgeo.build_geo(entries, places)` (вместо одной строки), в словарь — `"athletes": build_athletes(entries, teams, records, places, persons)`;
  - новый тест:
```python
def test_athlete_pages_on_archive(archive):
    pages, holder = archive["athletes"], archive["records"]["current"]["race:individual:M"]["holder"]
    assert len(pages) == 337
    p = pages[holder["person_id"]]
    assert p["person"]["bib"] == holder["bib"] and p["summary"]["records"] >= 1
    assert any(r["cell"] == "race:individual:M" and r["current"] for r in p["records"])
    assert sorted(x["rating"]["position"] for x in pages.values() if x["rating"]) == list(range(1, 166))
    assert sum(len(x["medals"]) for x in pages.values()) == 196
```
  - в `test_api_and_pages` в конце:
```python
    pid = records["current"]["race:individual:M"]["holder"]["person_id"]
    a = client.get(f"/api/siberman/athlete/{pid}")
    assert a.status_code == 200 and a.json()["person"]["id"] == pid and "birthdate" not in a.text
    assert client.get("/api/siberman/athlete/999999").status_code == 404
    assert client.get(f"/athlete/{pid}", headers=SIBERMAN).status_code == 200
    for bad in ("/athlete/999999", "/athlete/abc"):
        r = client.get(bad, headers=SIBERMAN)
        assert r.status_code == 404 and "Спортсмен не найден" in r.text
    assert client.get(f"/athlete/{pid}").status_code == 404
```

- [ ] **Step 2: Красный прогон** — hall: 1 failed (`test_api_and_pages` — маршрутов ещё нет), 7 passed (`athlete.py` есть с Task 2).

- [ ] **Step 3: `service.py`.** Импорт `from src.siberman.hall.athlete import build_athletes`. В `_build` вместо строки `geo = …`:
```python
    places = hgeo.resolve_places(entries, persons, applicants, hgeo.load_cities())
    geo = hgeo.build_geo(entries, places)
    return {"records": records, "rating": build_rating(entries, teams, records),
            "stats": build_stats(entries, teams, geo), "geo": geo,
            "athletes": build_athletes(entries, teams, records, places, persons)}
```
  В конец:
```python
def athlete(person_id: int) -> Optional[dict]:
    return _snapshot()["athletes"].get(person_id)
```
  Докстринг модуля: «Рейтинг, рекорды, статистика, география и страницы спортсменов Siberman: …».

- [ ] **Step 4: `router.py`.** Докстринг: «… и страница спортсмена /athlete/{id} (отдельная, не iframe) …». После страниц hall:
```python
@router.get("/athlete/{person_id}", response_class=HTMLResponse)
def athlete_page(request: Request, person_id: str):
    """Страница спортсмена (не iframe). Нет такого человека или id не число — 404-страница Siberman;
    БД недоступна — страница, которая сама покажет «временно недоступны»."""
    if getattr(request.state, "domain", "") != "siberman":
        raise HTTPException(status_code=404)
    pid = int(person_id) if person_id.isdigit() else None
    try:
        found = pid is not None and service.athlete(pid) is not None
    except HallUnavailable:
        found = True
    return templates.TemplateResponse("siberman/athlete.html", {"request": request, "person_id": pid, "found": found},
                                      status_code=200 if found else 404)
```
  API — в конец:
```python
@router.get("/api/siberman/athlete/{person_id}")
def api_athlete(person_id: int):
    return _json(service.athlete, person_id)
```

- [ ] **Step 5: Маршрутизация.** `app.py` → `_MAINTENANCE_ALLOWED_PREFIXES`: после `"/api/siberman/hall",` — `"/api/siberman/athlete",`, после `"/hall/",` — `"/athlete/",` (без API-префикса при техработах страница открывается, а данные — 503). `deploy/nginx.conf`, server live.siberman515.com: регэксп `…|draw/|hall/)` → `…|draw/|hall/|athlete/)`; в комментарии над ним — «/athlete/{id} — страница спортсмена (2026-10)».

- [ ] **Step 6: Шаблон** `templates/siberman/athlete.html`:
```html
<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Siberman — спортсмен</title>
<link rel="icon" href="/static/images/siberman/favicon.ico" sizes="any">
<link rel="stylesheet" href="/static/css/siberman-hall.css?v={{ v }}">
</head>
<body>
<div class="ath-top"><a href="https://siberman515.com/results">← Результаты Siberman</a></div>
{% if found %}
<div class="hall ath" id="athlete" data-id="{{ person_id }}"><div class="state-msg">Загрузка…</div></div>
<script src="/static/js/siberman-hall.js?v={{ v }}"></script>
<script src="/static/js/siberman-athlete.js?v={{ v }}"></script>
{% else %}
<div class="hall ath"><div class="state-msg">Спортсмен не найден — возможно, ссылка устарела.
  Найдите себя в <a href="https://siberman515.com/results">рейтинге Siberman</a>.</div></div>
{% endif %}
</body>
</html>
```

- [ ] **Step 7: Прогоны** — hall: 8 passed (`len(pages) == 337`, 165 позиций, 196 медалей — без подгонки; не сошлось → стоп); unit 983; persons 23.

- [ ] **Step 8: Commit** — `feat(siberman/hall): API и страница спортсмена /athlete/{id}, маршрутизация`.

---

### Task 4: Страница спортсмена — JS и CSS

**Files:** Modify `static/js/siberman-hall.js`, `static/js/siberman-hall-stats.js`, `static/css/siberman-hall.css`. Create `static/js/siberman-athlete.js`.

- [ ] **Step 1: `hallPlural` — общий.** В `siberman-hall.js` после `hallNorm`:
```js
function hallPlural(n, one, few, many) {
  const a = n % 10, b = n % 100;
  return a === 1 && b !== 11 ? one : a >= 2 && a <= 4 && (b < 12 || b > 14) ? few : many;
}
```
  В `siberman-hall-stats.js` удалить свою функцию `plural` и заменить вызовы `plural(` → `hallPlural(`. Докстринг `siberman-hall.js`: «Общие помощники блоков Siberman (рейтинг, рекорды, статистика, география, страница спортсмена): …».

- [ ] **Step 2: `siberman-athlete.js`:**
```js
'use strict';
// Страница спортсмена Siberman (/athlete/{id}): шапка, сводка, медали, лучшие результаты, все участия,
// рекорды (спецификация hall §8, макет athlete-v2). Данные — /api/siberman/athlete/{id}.

const SEG = { race: 'Гонка 515', swim: 'Плавание 10', bike: 'Вело 421', bike1: 'Вело, 1 день', bike2: 'Вело, 2 день', run: 'Бег 84' };
const COL = { individual: 'личный', relay: 'эстафета', absolute: 'абсолют' };
const SEX = { M: 'М', F: 'Ж' };
const root = document.getElementById('athlete');

function cellTitle(key) {
  const [seg, col, g] = key.split(':');
  return `${SEG[seg]} · ${COL[col]}${SEX[g] ? ' · ' + SEX[g] : ''}`;
}

function medal(m, label, caption, cls = '') {
  const shape = m.key.startsWith('hex') ? 'hex' : 'disc';
  const pic = m.image ? `<img src="${hallEsc(m.image)}" alt="${hallEsc(m.name)}">`
    : `<div class="${shape}" style="background:${m.color}">${label}</div>`;   // цвет — константа medals.py
  return `<div class="md ${cls}" title="${hallEsc(m.name)}">${pic}${caption}</div>`;
}

function medals(a) {
  const shortName = m => hallEsc(m.name.split(' (')[0]);
  const items = a.medals.map(x => medal(x.medal, x.n, `${x.n}-й финиш<br>${shortName(x.medal)} · ${x.year}`))
    .concat(a.relay_medals.map(x => medal(x.medal, 'Э', `эстафета<br>${x.year} · «${hallEsc(x.team)}»`, 'small')));
  if (a.next_medal) items.push(medal(a.next_medal, a.medals.length + 1, `следующая<br>${shortName(a.next_medal)}`, 'next'));
  return `<h2>Медали</h2><div class="medals">${items.join('')}</div>`;
}

function best(a) {
  if (!a.best.length) return '';
  const boxes = a.best.map(b => `<div class="bx">${SEG[b.seg]}<b>${hallTime(b.time_s)}</b>
    <span class="muted">${b.year}${b.place ? ' · ' + b.place + ' место' : ''}</span>${b.record ? ' <span class="rec">РЕКОРД</span>' : ''}</div>`).join('');
  const notes = [a.best_place ? `Лучшее место: ${a.best_place.place} (${a.best_place.year}).` : '',
                 a.rating ? `В общем рейтинге «лучший на человека»: ${a.rating.position} из ${a.rating.total}.` : '']
    .filter(Boolean).join(' ');
  return `<h2>Лучшие результаты</h2><div class="best">${boxes}</div>${notes ? `<div class="muted ath-note">${notes}</div>` : ''}`;
}

function outcome(r) {
  if (r.status === 'finished') {
    return `<b>${hallTime(r.time_s)}</b>${r.format === 'relay' ? ' <span class="muted">команда</span>' : ''}`
      + (r.record ? ' <span class="rec">РЕКОРД</span>' : '');
  }
  if (r.status === 'racing') return '<span class="muted">на дистанции</span>';
  const st = r.dnf_stage && HALL_STAGE[r.dnf_stage] ? ` (${HALL_STAGE[r.dnf_stage]})` : '';
  return r.status === 'dsq' ? 'DSQ' : `DNF${st}`;
}

function participations(a) {
  const time = (r, k) => (k in r.times ? (r.times[k] == null ? '—' : hallTime(r.times[k])) : '<span class="muted">—</span>');
  const rows = a.participations.map(r => {
    const fmt = r.format === 'individual'
      ? `Личный${r.finish_no ? ` · <b>${r.finish_no}-й финиш</b>` : ''}`
      : `Эстафета · ${HALL_STAGE[r.stage] || ''}<br>${hallCard(r.bib, r.year, '«' + hallEsc(r.team) + '»')}`;
    const place = !r.place ? '—' : r.format === 'individual' ? `${r.place.abs} / ${r.place.gender} ${SEX[r.gender] || ''}` : `${r.place.relay} эстаф.`;
    return `<tr class="${r.status === 'finished' || r.status === 'racing' ? '' : 'dnf'}"><td>${r.year}</td><td class="l">${fmt}</td>
      <td>${outcome(r)}</td><td>${place}</td><td>${time(r, 'swim')}</td><td>${time(r, 'bike')}</td><td>${time(r, 'run')}</td>
      <td>${hallCard(r.bib, r.year, 'карточка')}</td></tr>`;
  }).join('');
  return `<h2>Все участия</h2><div class="tbl"><table><tr><th>Год</th><th class="l">Формат</th><th>Итог</th><th>Место</th>
    <th>Плавание</th><th>Вело</th><th>Бег</th><th></th></tr>${rows}</table></div>`;
}

function records(a) {
  if (!a.records.length) return '';
  const rows = a.records.map(r => `<tr><td class="l${r.current ? '' : ' old'}">${cellTitle(r.cell)}${r.team ? ` · «${hallEsc(r.team)}»` : ''}</td>
    <td class="${r.current ? '' : 'old'}"><b>${hallTime(r.time_s)}</b></td><td class="${r.current ? '' : 'old'}">${r.year}</td>
    <td>${r.current ? '<span class="rec">действует</span>' : `<span class="muted">побит в ${r.beaten.year} (${hallTime(r.beaten.time_s)})</span>`}</td></tr>`).join('');
  return `<h2>Рекорды</h2><div class="tbl"><table><tr><th class="l">Рекорд</th><th>Время</th><th>Год</th><th>Статус</th></tr>${rows}</table></div>`;
}

function render(a) {
  const p = a.person, s = a.summary;
  document.title = `${p.fio} — Siberman`;
  const meta = [[p.city, p.country].filter(Boolean).join(', '), `Siberman с ${p.since}`].filter(Boolean).join(' · ');
  const stat = (n, one, few, many) => `<div><b>${n}</b>${hallPlural(n, one, few, many)}</div>`;
  root.innerHTML = `<div class="ath-head"><div><h1>${hallEsc(p.fio)}</h1><div class="ath-meta">${hallEsc(meta)}</div></div>
      ${p.bib ? `<div class="ath-bib"><span>№ ${hallEsc(p.bib)}</span><div>личный номер навсегда</div></div>` : ''}</div>
    <div class="ath-stats">${stat(s.starts, 'старт', 'старта', 'стартов')}${stat(s.finishes, 'финиш лично', 'финиша лично', 'финишей лично')}
      ${stat(s.relays, 'эстафета', 'эстафеты', 'эстафет')}${stat(s.records, 'рекорд сейчас', 'рекорда сейчас', 'рекордов сейчас')}</div>
    ${medals(a)}${best(a)}${participations(a)}${records(a)}`;
}

hallLoad(`/api/siberman/athlete/${encodeURIComponent(root.dataset.id)}`).then(render)
  .catch(err => { root.innerHTML = `<div class="state-msg">${hallEsc(err.message)}</div>`; });
```

- [ ] **Step 3: CSS** — в `siberman-hall.css` перед `@media (max-width: 640px)`:
```css
/* Страница спортсмена (/athlete/{id}) — отдельная, не iframe */
.ath-top { max-width: 960px; margin: 0 auto; padding: 12px 16px 0; box-sizing: border-box; font-size: 14px; }
.ath-top a { color: var(--navy); text-decoration: none; }
.ath h1 { margin: 0; font-size: 28px; font-weight: 800; color: var(--ink); }
.ath h2 { font-size: 17px; margin: 18px 0 8px; color: var(--navy); }
.ath-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; flex-wrap: wrap; }
.ath-meta { color: var(--muted); margin-top: 4px; }
.ath-bib { text-align: right; font-size: 12px; color: var(--muted); }
.ath-bib span { display: inline-block; margin-bottom: 4px; padding: 4px 10px; border-radius: 6px; background: var(--navy); color: #fff; font-weight: 800; font-size: 20px; }
.ath-stats { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; margin: 14px 0; }
.ath-stats > div { border: 1px solid var(--line); border-radius: 8px; padding: 10px; text-align: center; font-size: 12px; color: var(--muted); }
.ath-stats b { display: block; font-size: 22px; color: var(--navy); }
.medals { display: flex; gap: 14px; flex-wrap: wrap; }
.md { width: 96px; text-align: center; font-size: 12px; color: var(--muted); }
.md .disc, .md .hex { width: 72px; height: 72px; margin: 0 auto 6px; display: flex; align-items: center; justify-content: center; color: #fff; font-weight: 800; font-size: 20px; }
.md .disc { border-radius: 50%; box-shadow: inset 0 0 0 3px rgba(255, 255, 255, .35); }
.md .hex { clip-path: polygon(25% 5%, 75% 5%, 100% 50%, 75% 95%, 25% 95%, 0 50%); }
.md img { display: block; width: 72px; height: 72px; margin: 0 auto 6px; object-fit: contain; }
.md.small .disc, .md.small .hex, .md.small img { width: 58px; height: 58px; margin-top: 7px; font-size: 16px; }
.md.next { opacity: .45; }
.best { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; }
.bx { border: 1px solid var(--line); border-radius: 8px; padding: 8px; text-align: center; font-size: 13px; }
.bx b { display: block; font-size: 16px; }
.ath .muted { color: var(--muted); font-size: 12px; }
.ath-note { margin-top: 6px; }
.ath td.old { color: var(--muted); }
```
  В `@media (max-width: 640px)`: `  .ath-stats, .best { grid-template-columns: repeat(2, minmax(0, 1fr)); }` и `  .ath h1 { font-size: 22px; }`.

- [ ] **Step 4: Проверка** — `node --check` для `siberman-athlete.js`, `siberman-hall.js`, `siberman-hall-stats.js`; unit 983; hall 8.

- [ ] **Step 5: Commit** — `feat(siberman/hall): страница спортсмена — шапка, медали, лучшие, участия, рекорды`.

---

### Task 5: Проверка в браузере, документы

**Files:** Modify `docs/siberman/hall-tilda-snippet.md` (абзац про ссылки). Основной репозиторий: `.taskmaster/tasks/todo.md` — координатор.

- [ ] **Step 1: Сниппет.** Строку «Ссылки внутри блоков (страница спортсмена, карточка года) открываются в новой вкладке.» и следующую про выкладку заменить на: «Ссылки внутри блоков открываются в новой вкладке: ФИ — страница спортсмена `https://live.siberman515.com/athlete/{id}` (все годы, медали, рекорды), время и команда — карточка года. Планы 2–4 выкладываются вместе.»

- [ ] **Step 2: Браузер** — сервер `serve.py` из scratchpad в фоне из корня worktree, порт 8011; Playwright (python, `channel="chrome"`), `siberman.localhost:8011`, десктоп 1100×900 и телефон 390×800. `person_id` взять из API рекордов (держатель `race:individual:M`; держатель `race:relay:X` — участник команды). Числа записать:
1. Рекордсмен гонки: нет `pageerror` и 4xx/5xx; заголовок вкладки «<ФИ> — Siberman»; личный номер = номер держателя; «рекорда сейчас» ≥ 1; медалей = числу его личных финишей + эстафетных + 1 бледная; в «Лучших результатах» у гонки «РЕКОРД»; строк «Все участия» = стартов; в таблице «Рекорды» есть «действует».
2. Участник эстафеты-рекордсмена (`race:relay:X`, любой из состава): строка эстафеты со ссылкой на команду (`/participant/<номер>?year=`), «эстаф.» в месте, в «Рекордах» — «Гонка 515 · эстафета · «команда»» и «действует».
3. Человек с DNF (взять из API рейтинга строку `status: "dnf"` с `person_id`): строка «DNF (этап)» серым, время пройденных этапов есть.
4. Переход: на `/hall/rating` клик по ФИ первой строки открывает `/athlete/<id>` в новой вкладке, страница грузится.
5. `/athlete/999999` и `/athlete/abc` — 404 и текст «Спортсмен не найден».
6. Телефон: нет горизонтальной прокрутки страницы (`scrollWidth <= innerWidth`), таблицы прокручиваются внутри `.tbl`, сводка — 2×2.
Скриншоты (десктоп и телефон для п. 1–2, 404) — в scratchpad, посмотреть глазами. Сервер остановить.

- [ ] **Step 3: Полный прогон** — unit 983; интеграционные hall + persons 31.

- [ ] **Step 4: Commit** — `docs(siberman/hall): страница спортсмена в сниппете`.

- [ ] **Step 5: Отчёт координатору** — числа, скриншоты, замечания по виду; пункт не выполняется — код не чинить, описать.

---

### Task 6 (позже, по решению пользователя): картинки медалей

Код готов (Task 1): достаточно положить `static/img/siberman/medals/{key}.webp` (`silver`, `black`, `gold`, `copper`, `chameleon`, `hex_black`, `hex_silver_red`, `relay_silver`), 144×144, прозрачный фон, **без гравировки имён**. Источник — чистые фото у организаторов (спецификация §10) или вырезка из `Downloads/bear Medal 2026 reorder.pdf` (на фото — имена получателей: вырезать только медаль, проверить глазами; нужна библиотека PyMuPDF — установка с разрешения пользователя). Не входит в этот план.

---

## Self-review (сделан при написании плана)

- Спецификация §8: шапка (ФИ, город и страна, «Siberman с», личный номер) — Task 2, 4; сводка (старты, финиши лично, эстафеты, действующие рекорды) — Task 2, 4; медали по порядку финишей + эстафетная меньше + следующая бледная — Task 1, 2, 4; лучшие результаты (гонка и этапы, год, «РЕКОРД», лучшее место, позиция «лучший на человека») — Task 2, 4; все участия (формат, N-й финиш, итог/DNF с этапом, место абс / пол, эстафета — место среди эстафет, времена этапов, ссылка на карточку года) — Task 2, 4; рекорды действующие и прошлые («кем и когда побит» — год и время побившего) — Task 2, 4; несуществующий id → 404-страница — Task 3. §9: картинки `static/img/siberman/medals/*.webp`, нет — кружок — Task 1, 4, 6. §2: nginx `athlete/`, API — Task 3. §11: БД недоступна — `hallLoad` → «Данные временно недоступны»; живой год — «на дистанции». §12: unit (страница), integration (архив, API без `birthdate`), браузер — Task 2, 3, 5.
- Отступление: «кем побит» — год и время побившего, без ФИО (видно в истории рекорда на странице рекордов).
- Имена: `build_athletes(entries, teams, records, places, persons)`, `service.athlete(id)`; `medal_for(...)['image']`; JS — `hallPlural`, `hallEsc`, `hallTime`, `hallCard`, `hallLoad`, `HALL_STAGE`.
- Числа тестов: unit 979 → 980 (T1) → 983 (T2); интеграционные hall 7 → 8 (T3); hall + persons 30 → 31.
