# Siberman: рейтинг и рекорды — план реализации (план 2 из 4)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Два блока для Тильды из БД вместо ручных таблиц на siberman515.com/results: рейтинг за все годы (`/hall/rating`) и таблица рекордов с историей (`/hall/records`).

**Architecture:** Пакет `src/siberman/hall/`: загрузка архива в простые записи (`data.py` — по строке участника, команды эстафет), чистые расчёты рекордов (`records.py`) и рейтинга (`rating.py`), снимок в памяти воркера на 60 с (`service.py`), страницы и API (`router.py`). Человек (ссылка на страницу спортсмена, «N-й финиш») — из реестра плана 1 (`siberman_person_links`). Медали — одно правило в `src/siberman/medals.py`. Фронт — ванильный JS + общий CSS, высота iframe через `postMessage`, как у жеребьёвки.

**Tech Stack:** Python 3.13, FastAPI 0.104, mysql-connector, Jinja2, ванильный JS, pytest, Playwright (`channel="chrome"`).

**Спецификация:** `docs/superpowers/specs/2026-10-18-siberman-hall-ratings-records-design.md` §2, §4, §5, §9, §11, §12. Макеты (согласованы): `.superpowers/brainstorm/36-1792309228/content/rating-v4.html`, `records-v8.html` (в основном репозитории).

**Правила для исполнителя:**
- Работать в worktree `.worktrees/siberman-hall` (ветка `feature/siberman-hall`, там же реестр людей плана 1).
- Не печатать `.env`, `.env.local`, пароли, cookie. ФИО и даты рождения из БД в отчёт не выводить — только числа и пары (год, номер).
- pytest запускать напрямую: `C:\Users\podbo\miniconda3\python.exe -m pytest … -q -p no:cacheprovider` (у субагентов `conda run` зависает).
- Если тест сверки с организаторами или сайтом падает — тест НЕ подгонять: сообщить расхождения (клетка, наше значение, их значение).

**Принятые правила (из спецификации и проверки архива):**
- Финиш личника = статус `active` и есть официальный итог `overall_results.total_s` (на архиве 2016–2025 — 196 финишей, М 184, Ж 12, как на сайте).
- Итог эстафеты = сумма этапов (плавание + вело д1 + вело д2 + бег), никто не сошёл и каждый дошёл до последней КТ своих этапов — как в протоколе года (`get_results_for_year`). Финиш личника — официальный итог и последняя КТ каждого этапа: в живом году итоги пишутся и у идущих по дистанции (Task 4a).
- В рекорды по отрезкам (плавание, вело, бег) — только не сошедшие и дошедшие до последней КТ этапа своего года (как живые рекорды трекера, `_recompute_records`).
- Ссылки из iframe (страница спортсмена, карточка года) открываются в новой вкладке (`target="_blank"`), чтобы страница Тильды осталась на месте.

---

## Карта файлов

| Файл | Что делает |
|---|---|
| `src/siberman/medals.py` (новый) | номер финиша → медаль (ключ, название, цвет) |
| `src/siberman/hall/__init__.py` (новый) | пакет |
| `src/siberman/hall/data.py` (новый) | `Entry`, `Team`, `load_entries`, `build_teams`, `race_time`, `segment_time` |
| `src/siberman/hall/records.py` (новый) | клетки таблицы, кандидаты, история и текущие рекорды |
| `src/siberman/hall/rating.py` (новый) | строки рейтинга личников и эстафет |
| `src/siberman/hall/service.py` (новый) | снимок архива на 60 с |
| `src/siberman/hall/router.py` (новый) | `/hall/rating`, `/hall/records`, `/api/siberman/hall/*` |
| `templates/siberman/hall_rating.html`, `hall_records.html` (новые) | страницы блоков |
| `static/css/siberman-hall.css` (новый) | стили обоих блоков |
| `static/js/siberman-hall.js`, `siberman-hall-rating.js`, `siberman-hall-records.js` (новые) | общие помощники и логика блоков |
| `docs/siberman/hall-tilda-snippet.md` (новый) | вставка в Тильду |
| `src/krasmarafon/router.py`, `app.py`, `deploy/nginx.conf` (изм.) | подключение, техработы, пути nginx |
| `tests/unit/test_siberman_hall.py`, `tests/integration/test_siberman_hall.py` (новые) | тесты |

---

### Task 1: Медали

**Files:**
- Create: `src/siberman/medals.py`
- Test: `tests/unit/test_siberman_hall.py`

- [ ] **Step 1: Тест**

Создать `tests/unit/test_siberman_hall.py`:
```python
from src.siberman.medals import medal_for


def test_medals_by_finish_number():
    assert [medal_for(n)["key"] for n in range(1, 8)] == [
        "silver", "black", "gold", "copper", "chameleon", "hex_black", "hex_silver_red"]
    assert medal_for(12)["key"] == "hex_silver_red"
    assert medal_for(0) is None and medal_for(None) is None
    assert medal_for(None, relay=True)["key"] == "relay_silver"
    assert set(medal_for(3)) == {"key", "name", "color"}
```

- [ ] **Step 2: Тест падает**

Run: `C:\Users\podbo\miniconda3\python.exe -m pytest tests/unit/test_siberman_hall.py -q -p no:cacheprovider`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.siberman.medals'`.

- [ ] **Step 3: Реализация**

`src/siberman/medals.py`:
```python
"""Медали Siberman за финиши (спецификация hall §9) — одно место для правила «N-й финиш → медаль».
8-й и дальше — пока как 7-й. Картинки медалей добавит страница спортсмена (план 4)."""
from typing import Optional

INDIVIDUAL = {
    1: ("silver", "Античное серебро", "#a9a9a9"),
    2: ("black", "Матовая чёрная", "#222222"),
    3: ("gold", "Золотая", "#d4a017"),
    4: ("copper", "Античная медь", "#b06a3b"),
    5: ("chameleon", "Хамелеон", "linear-gradient(135deg, #6a3cbc, #1fa3a3, #c2b21f)"),
    6: ("hex_black", "Чёрный шестигранник", "#111111"),
}
SEVENTH_AND_LATER = ("hex_silver_red", "Серебряный шестигранник с красной плашкой", "#c0c0c0")
RELAY = ("relay_silver", "Античное серебро 70 мм (эстафета)", "#a9a9a9")


def medal_for(finish_no: Optional[int], relay: bool = False) -> Optional[dict]:
    """Медаль за finish_no-й финиш в личном зачёте; relay=True — эстафетная. Нет финиша → None."""
    if relay:
        key, name, color = RELAY
    elif not finish_no or finish_no < 1:
        return None
    else:
        key, name, color = INDIVIDUAL.get(finish_no, SEVENTH_AND_LATER)
    return {"key": key, "name": name, "color": color}
```

- [ ] **Step 4: Тест проходит**

Run: та же команда. Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add src/siberman/medals.py tests/unit/test_siberman_hall.py
git commit -m "feat(siberman/hall): медали за финиши — одно правило"
```

---

### Task 2: Архив — записи и команды (`hall/data.py`)

**Files:**
- Create: `src/siberman/hall/__init__.py` (пустой), `src/siberman/hall/data.py`
- Test: `tests/unit/test_siberman_hall.py` (дописать)

- [ ] **Step 1: Тесты (дописать в `tests/unit/test_siberman_hall.py`)**

```python
from src.siberman.hall.data import Entry, build_teams, race_time, segment_time

ALL = frozenset({"swim", "bike_day1", "bike_day2", "run"})


def ind(year, bib, surname, g="M", total=100, swim=10, b1=30, b2=40, run=20, status="active",
        finished=ALL, pid=None, dnf_stage=None):
    return Entry(year=year, bib=str(bib), stage="none", format="individual", surname=surname, name="Тест",
                 gender=g, status=status, dnf_stage=dnf_stage, person_id=pid,
                 overall_s=total if status == "active" else None,
                 times={"swim": swim, "bike_day1": b1, "bike_day2": b2, "run": run}, finished=finished)


ROLE = {"swim": ("swim",), "bike": ("bike_day1", "bike_day2"), "run": ("run",)}


def rel(year, bib, role, surname, g="M", times=None, status="active", team="Команда", pid=None, finished=None):
    return Entry(year=year, bib=str(bib), stage=role, format="relay", surname=surname, name="Тест", gender=g,
                 status=status, team=team, person_id=pid, times=times or {s: 10 for s in ROLE[role]},
                 finished=frozenset(ROLE[role]) if finished is None else finished)


def team(year, bib, g="M", swim=10, b1=20, b2=30, run=15, status="active", name="Команда"):
    return [rel(year, bib, "swim", "Пловцов", g, {"swim": swim}, status, name),
            rel(year, bib, "bike", "Велосипедов", g, {"bike_day1": b1, "bike_day2": b2}, team=name),
            rel(year, bib, "run", "Бегунов", g, {"run": run}, team=name)]


def test_race_time_only_for_finished_individual():
    assert race_time(ind(2020, 7, "А")) == 100
    assert race_time(ind(2020, 7, "А", status="dnf")) is None
    assert race_time(ind(2020, 7, "А", total=None)) is None


def test_segment_time_needs_last_checkpoint_and_active():
    e = ind(2020, 7, "А", finished=frozenset({"swim", "bike_day1"}))
    assert segment_time(e, ("swim",)) == 10
    assert segment_time(e, ("bike_day1",)) == 30
    assert segment_time(e, ("bike_day1", "bike_day2")) is None
    assert segment_time(ind(2020, 8, "Б", status="dnf"), ("swim",)) is None


def test_team_time_and_status():
    [t] = build_teams(team(2021, 101))
    assert (t.year, t.bib, t.name, t.status, t.time_s) == (2021, "101", "Команда", "active", 75)
    assert [m.stage for m in t.members] == ["swim", "bike", "run"]
    [t] = build_teams(team(2021, 102, status="dnf"))
    assert (t.status, t.time_s) == ("dnf", None)
    [t] = build_teams(team(2021, 103)[:2])
    assert t.time_s is None
    dns = [rel(2021, 104, r, "Х", status="dns") for r in ("swim", "bike", "run")]
    assert build_teams(dns)[0].status == "dns"
```

- [ ] **Step 2: Тесты падают**

Run: `C:\Users\podbo\miniconda3\python.exe -m pytest tests/unit/test_siberman_hall.py -q -p no:cacheprovider`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.siberman.hall'`.

- [ ] **Step 3: Реализация**

`src/siberman/hall/__init__.py` — пустой файл.

`src/siberman/hall/data.py`:
```python
"""
Архив Siberman для рейтинга и рекордов (спецификация hall §4–§5): одна запись на строку
participants за все годы — официальный итог, времена этапов, какие этапы пройдены до последней КТ
своего года, человек из реестра. Эстафеты собираются в команды (год, номер).
"""
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

import mysql.connector

STAGES = ("swim", "bike_day1", "bike_day2", "run")
ROLES = ("swim", "bike", "run")
ROLE_STAGES = {"swim": ("swim",), "bike": ("bike_day1", "bike_day2"), "run": ("run",)}


@dataclass
class Entry:
    year: int
    bib: str
    stage: str                       # 'none' — личник; 'swim' | 'bike' | 'run' — этап эстафетчика
    format: str                      # 'individual' | 'relay'
    surname: str
    name: str
    gender: Optional[str]            # 'M' | 'F' | None
    city: str = ""
    country: str = ""
    status: str = "active"           # active | dnf | dns | dsq
    dnf_stage: Optional[str] = None
    team: str = ""
    person_id: Optional[int] = None
    overall_s: Optional[int] = None  # официальный итог личника (overall_results)
    times: dict = field(default_factory=dict)    # swim / bike_day1 / bike_day2 / run → секунды (stage_totals)
    finished: frozenset = frozenset()            # этапы, где есть время последней КТ года

    @property
    def fio(self) -> str:
        return f"{self.surname} {self.name}".strip()


def race_time(e: Entry) -> Optional[int]:
    """Итог личника, финишировавшего всю гонку (статус active и есть официальный итог)."""
    return e.overall_s if e.format == "individual" and e.status == "active" and e.overall_s else None


def segment_time(e: Entry, stages: tuple) -> Optional[int]:
    """Время отрезка из этапов stages: участник не сошёл и дошёл до последней КТ каждого этапа."""
    if e.status != "active" or any(s not in e.finished or e.times.get(s) is None for s in stages):
        return None
    return sum(e.times[s] for s in stages)


@dataclass
class Team:
    year: int
    bib: str
    name: str
    members: list                    # Entry по порядку этапов: плавание, велосипед, бег

    def member(self, role: str) -> Optional[Entry]:
        return next((m for m in self.members if m.stage == role), None)

    @property
    def status(self) -> str:
        st = {m.status for m in self.members}
        if "dsq" in st:
            return "dsq"
        if st == {"dns"}:
            return "dns"
        if st & {"dnf", "dns"}:
            return "dnf"
        return "active"

    @property
    def time_s(self) -> Optional[int]:
        """Итог команды — сумма этапов (как в протоколе года): все три этапа на месте, никто не сошёл."""
        if self.status != "active":
            return None
        total = 0
        for role in ROLES:
            m = self.member(role)
            if m is None:
                return None
            for s in ROLE_STAGES[role]:
                if m.times.get(s) is None:
                    return None
                total += m.times[s]
        return total


def bib_order(bib: str) -> tuple:
    return (0, int(bib), "") if str(bib).isdigit() else (1, 0, str(bib))


def build_teams(entries: list) -> list:
    groups = defaultdict(list)
    for e in entries:
        if e.format == "relay":
            groups[(e.year, e.bib)].append(e)
    teams = []
    for (year, bib), members in groups.items():
        members.sort(key=lambda m: ROLES.index(m.stage) if m.stage in ROLES else len(ROLES))
        teams.append(Team(year=year, bib=bib, name=next((m.team for m in members if m.team), ""), members=members))
    teams.sort(key=lambda t: (t.year, bib_order(t.bib)))
    return teams


FINISHED_SQL = """
    SELECT ct.participant_id, c.stage
    FROM checkpoint_times ct
    JOIN checkpoints c ON c.id = ct.checkpoint_id
    JOIN (SELECT race_year, stage, MAX(seq) AS seq FROM checkpoints WHERE NOT sub_mark
          GROUP BY race_year, stage) lastcp
      ON lastcp.race_year = c.race_year AND lastcp.stage = c.stage AND lastcp.seq = c.seq
    WHERE ct.cumulative_s IS NOT NULL
"""

ENTRIES_SQL = """
    SELECT p.id, p.race_year, p.bib, p.relay_stage, p.format, p.surname, p.name, p.gender,
           p.city, p.country, p.status, p.dnf_stage, p.relay_team_name, o.total_s,
           sw.total_s AS swim, b1.total_s AS bike_day1, b2.total_s AS bike_day2, ru.total_s AS run
    FROM participants p
    LEFT JOIN overall_results o ON o.participant_id = p.id
    LEFT JOIN stage_totals sw ON sw.participant_id = p.id AND sw.stage = 'swim'
    LEFT JOIN stage_totals b1 ON b1.participant_id = p.id AND b1.stage = 'bike_day1'
    LEFT JOIN stage_totals b2 ON b2.participant_id = p.id AND b2.stage = 'bike_day2'
    LEFT JOIN stage_totals ru ON ru.participant_id = p.id AND ru.stage = 'run'
    ORDER BY p.race_year, p.bib, p.relay_stage
"""


def _person_ids(conn) -> dict:
    """(год, номер, этап) → человек реестра; без таблиц реестра (миграция 014) — пусто."""
    try:
        cur = conn.cursor(dictionary=True, buffered=True)
        cur.execute("SELECT race_year, bib, relay_stage, person_id FROM siberman_person_links")
    except mysql.connector.Error:
        return {}
    return {(int(r["race_year"]), str(r["bib"]), r["relay_stage"]): r["person_id"] for r in cur.fetchall()}


def load_entries(conn) -> list:
    cur = conn.cursor(dictionary=True, buffered=True)
    cur.execute(FINISHED_SQL)
    finished = defaultdict(set)
    for r in cur.fetchall():
        finished[r["participant_id"]].add(r["stage"])
    persons = _person_ids(conn)
    cur.execute(ENTRIES_SQL)
    out = []
    for r in cur.fetchall():
        year, bib, stage = int(r["race_year"]), str(r["bib"]), r["relay_stage"]
        out.append(Entry(
            year=year, bib=bib, stage=stage, format=r["format"], surname=r["surname"] or "", name=r["name"] or "",
            gender=r["gender"] if r["gender"] in ("M", "F") else None,
            city=r["city"] or "", country=r["country"] or "", status=r["status"], dnf_stage=r["dnf_stage"],
            team=r["relay_team_name"] or "", person_id=persons.get((year, bib, stage)), overall_s=r["total_s"],
            times={s: r[s] for s in STAGES}, finished=frozenset(finished.get(r["id"], ()))))
    return out
```

- [ ] **Step 4: Тесты проходят**

Run: та же команда. Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/siberman/hall/__init__.py src/siberman/hall/data.py tests/unit/test_siberman_hall.py
git commit -m "feat(siberman/hall): архив — записи участников и команды эстафет"
```

---

### Task 3: Рекорды (`hall/records.py`)

**Files:**
- Create: `src/siberman/hall/records.py`
- Test: `tests/unit/test_siberman_hall.py` (дописать)

- [ ] **Step 1: Тесты**

```python
from src.siberman.hall.records import build_records, cell_keys


def recs(entries):
    return build_records(entries, build_teams(entries))


def test_cell_keys_like_organizers_table():
    keys = cell_keys()
    assert len(keys) == 35 and "race:relay:X" in keys and "race:relay:M" not in keys
    assert keys[0] == "race:individual:M" and keys[-1] == "run:absolute:F"


def test_race_absolute_men_includes_relays_women_do_not():
    entries = [ind(2020, 7, "Мужчинов", "M", total=100), ind(2020, 8, "Женщинова", "F", total=90),
               *team(2020, 101, "M"), *team(2020, 102, "F", swim=5, b1=20, b2=20, run=15)]
    cur = recs(entries)["current"]
    assert cur["race:individual:M"]["time_s"] == 100
    assert cur["race:relay:X"]["time_s"] == 60 and cur["race:relay:X"]["holder"]["type"] == "team"
    # вариант А: абсолют М в «гонке» — мужчины-личники и все эстафеты (у эстафеты на гонке нет пола)
    assert cur["race:absolute:M"]["time_s"] == 60 and cur["race:absolute:M"]["holder"]["bib"] == "102"
    assert cur["race:absolute:F"]["time_s"] == 90


def test_stage_absolute_mixes_individuals_and_relay_of_same_gender():
    entries = [ind(2020, 7, "Личников", swim=10), *team(2020, 101, swim=8)]
    cur = recs(entries)["current"]
    assert cur["swim:individual:M"]["time_s"] == 10
    assert cur["swim:relay:M"]["time_s"] == 8
    holder = cur["swim:absolute:M"]["holder"]
    assert cur["swim:absolute:M"]["time_s"] == 8 and holder["team"] == "Команда" and holder["type"] == "person"
    assert cur["bike:relay:M"]["time_s"] == 50 and cur["bike1:relay:M"]["time_s"] == 20
    assert cur["swim:relay:F"] is None


def test_history_improvements_delta_and_new_flag():
    entries = [ind(2019, 7, "А", total=120), ind(2020, 8, "Б", total=130), ind(2021, 9, "В", total=100)]
    r = recs(entries)
    h = r["history"]["race:individual:M"]
    assert [(x["year"], x["time_s"], x["delta_s"]) for x in h] == [(2019, 120, None), (2021, 100, 20)]
    assert r["current"]["race:individual:M"]["new"] is True and r["last_year"] == 2021
    r2 = recs(entries + [ind(2022, 10, "Г", total=150)])
    assert r2["current"]["race:individual:M"]["new"] is False


def test_tie_keeps_first_holder_and_dnf_never_counts():
    entries = [ind(2019, 7, "А", total=100), ind(2020, 8, "Б", total=100), ind(2021, 9, "В", total=50, status="dnf")]
    h = recs(entries)["history"]["race:individual:M"]
    assert [(x["year"], x["holder"]["bib"]) for x in h] == [(2019, "7")]


def test_stage_without_last_checkpoint_is_not_a_record():
    entries = [ind(2020, 7, "А", swim=5, finished=frozenset({"bike_day1", "bike_day2", "run"})),
               ind(2020, 8, "Б", swim=9)]
    assert recs(entries)["current"]["swim:individual:M"]["holder"]["bib"] == "8"
```

- [ ] **Step 2: Тесты падают**

Run: та же команда. Expected: 6 failed (`ImportError: cannot import name 'build_records'`), 4 passed.

- [ ] **Step 3: Реализация**

`src/siberman/hall/records.py`:
```python
"""
Рекорды Siberman из архива (спецификация hall §5): таблица как у организаторов и история — кто и
когда улучшал. Строки: гонка, плавание, вело всего, вело д1, вело д2, бег. Столбцы: личный зачёт
М/Ж, эстафета М/Ж (в строке «гонка» — одна клетка без пола, X), абсолютно лучшее М/Ж.
Абсолютно лучшее (вариант А): в отрезках — личники и эстафетчики своего пола; в «гонке» М —
личники-мужчины и эстафеты, Ж — личницы. В рекорды отрезков — только не сошедшие и дошедшие до
последней КТ этапа (как живые рекорды трекера). Ничья рекорд не меняет.
"""
from src.siberman.hall.data import Entry, Team, bib_order, race_time, segment_time

SEGMENTS = ("race", "swim", "bike", "bike1", "bike2", "run")
SEG_STAGES = {"swim": ("swim",), "bike": ("bike_day1", "bike_day2"), "bike1": ("bike_day1",),
              "bike2": ("bike_day2",), "run": ("run",)}
SEG_ROLE = {"swim": "swim", "bike": "bike", "bike1": "bike", "bike2": "bike", "run": "run"}
COLUMNS = ("individual", "relay", "absolute")
GENDERS = ("M", "F")


def cell_keys() -> list:
    keys = []
    for seg in SEGMENTS:
        for col in COLUMNS:
            if seg == "race" and col == "relay":
                keys.append("race:relay:X")
            else:
                keys += [f"{seg}:{col}:{g}" for g in GENDERS]
    return keys


def person_holder(e: Entry) -> dict:
    return {"type": "person", "person_id": e.person_id, "fio": e.fio, "bib": e.bib, "year": e.year,
            "team": e.team if e.format == "relay" else None}


def team_holder(t: Team) -> dict:
    return {"type": "team", "name": t.name, "bib": t.bib, "year": t.year,
            "members": [{"stage": m.stage, "fio": m.fio, "person_id": m.person_id} for m in t.members]}


def _individual(entries: list, seg: str, g: str):
    for e in entries:
        if e.format == "individual" and e.gender == g:
            v = race_time(e) if seg == "race" else segment_time(e, SEG_STAGES[seg])
            if v is not None:
                yield (v, 0, bib_order(e.bib)), person_holder(e)


def _relay_members(entries: list, seg: str, g: str):
    for e in entries:
        if e.format == "relay" and e.gender == g and e.stage == SEG_ROLE[seg]:
            v = segment_time(e, SEG_STAGES[seg])
            if v is not None:
                yield (v, 1, bib_order(e.bib)), person_holder(e)


def _teams(teams: list):
    for t in teams:
        if t.time_s is not None:
            yield (t.time_s, 1, bib_order(t.bib)), team_holder(t)


def candidates(key: str, entries: list, teams: list) -> list:
    """[((время, 0 — личник / 1 — эстафета, номер), держатель)] одного года для клетки key."""
    seg, col, g = key.split(":")
    if seg == "race":
        if col == "relay":
            return list(_teams(teams))
        individual = list(_individual(entries, seg, g))
        return individual + list(_teams(teams)) if col == "absolute" and g == "M" else individual
    if col == "individual":
        return list(_individual(entries, seg, g))
    if col == "relay":
        return list(_relay_members(entries, seg, g))
    return list(_individual(entries, seg, g)) + list(_relay_members(entries, seg, g))


def build_records(entries: list, teams: list) -> dict:
    """→ {'current': {клетка: запись | None}, 'history': {клетка: [записи по годам]}, 'last_year'}.
    Запись: {'time_s', 'year', 'holder', 'delta_s'}; у текущей ещё 'new' — поставлен в последнем году."""
    years = sorted({e.year for e in entries})
    entries_by_year = {y: [e for e in entries if e.year == y] for y in years}
    teams_by_year = {y: [t for t in teams if t.year == y] for y in years}
    history = {k: [] for k in cell_keys()}
    for y in years:
        for key, h in history.items():
            cands = candidates(key, entries_by_year[y], teams_by_year[y])
            if not cands:
                continue
            (value, _, _), holder = min(cands, key=lambda c: c[0])
            if not h or value < h[-1]["time_s"]:
                h.append({"time_s": value, "year": y, "holder": holder,
                          "delta_s": h[-1]["time_s"] - value if h else None})
    last_year = max((e.year for e in entries if e.finished or race_time(e)), default=None)
    current = {k: ({**h[-1], "new": h[-1]["year"] == last_year} if h else None) for k, h in history.items()}
    return {"current": current, "history": history, "last_year": last_year}
```

- [ ] **Step 4: Тесты проходят**

Run: та же команда. Expected: 10 passed.

- [ ] **Step 5: Commit**

```bash
git add src/siberman/hall/records.py tests/unit/test_siberman_hall.py
git commit -m "feat(siberman/hall): рекорды из архива — таблица организаторов и история улучшений"
```

---

### Task 4: Рейтинг (`hall/rating.py`)

**Files:**
- Create: `src/siberman/hall/rating.py`
- Test: `tests/unit/test_siberman_hall.py` (дописать)

- [ ] **Step 1: Тесты**

```python
from src.siberman.hall.rating import build_rating


def rating_of(entries):
    teams = build_teams(entries)
    return build_rating(entries, teams, build_records(entries, teams))


def test_finish_numbers_medals_and_dnf_rows():
    entries = [ind(2019, 7, "Петров", total=130, pid=5), ind(2020, 7, "Петров", status="dnf", dnf_stage="run", pid=5),
               ind(2021, 7, "Петров", total=120, pid=5), ind(2022, 7, "Петров", total=110, pid=5),
               ind(2022, 8, "Новиков", status="dns"), ind(2022, 9, "Идущий", total=None)]
    rows = {(r["year"], r["bib"]): r for r in rating_of(entries)["individual"]}
    assert set(rows) == {(2019, "7"), (2020, "7"), (2021, "7"), (2022, "7")}     # dns и «ещё на дистанции» — нет
    assert [rows[(y, "7")]["finish_no"] for y in (2019, 2021, 2022)] == [1, 2, 3]
    assert rows[(2022, "7")]["medal"]["key"] == "gold"
    dnf = rows[(2020, "7")]
    assert (dnf["status"], dnf["dnf_stage"], dnf["finish_no"], dnf["medal"], dnf["time_s"]) == ("dnf", "run", None, None, None)


def test_finish_numbers_without_registry_use_name():
    entries = [ind(2019, 7, "Петров", total=130), ind(2021, 7, "Петров", total=120)]
    assert [r["finish_no"] for r in rating_of(entries)["individual"]] == [2, 1]   # по времени: 120 (2021), 130 (2019)


def test_rows_sorted_by_time_dnf_last_and_record_marks():
    entries = [ind(2019, 7, "А", total=130), ind(2020, 8, "Б", total=100), ind(2020, 9, "В", "F", total=140),
               ind(2021, 10, "Г", status="dsq")]
    rows = rating_of(entries)["individual"]
    assert [r["bib"] for r in rows] == ["8", "7", "9", "10"]
    assert [r["record"] for r in rows] == ["M", None, "F", None]


def test_relay_rating_rows():
    entries = [*team(2020, 101, name="Быстрые"), *team(2021, 102, status="dnf", name="Сошедшие")]
    r = rating_of(entries)
    first, second = r["relay"]
    assert (first["team"], first["time_s"], first["status"], first["record"]) == ("Быстрые", 75, "finished", True)
    assert [m["stage"] for m in first["members"]] == ["swim", "bike", "run"]
    assert (second["status"], second["time_s"], second["record"]) == ("dnf", None, False)
    assert r["years"] == [2021, 2020]
```

- [ ] **Step 2: Тесты падают**

Run: та же команда. Expected: 4 failed (`ImportError: cannot import name 'build_rating'`), 10 passed.

- [ ] **Step 3: Реализация**

`src/siberman/hall/rating.py`:
```python
"""
Рейтинг Siberman за все годы (спецификация hall §4): личники — финиш (официальный итог) с номером
финиша человека и медалью, DNF/DSQ в конце; эстафеты — команда года с составом по этапам.
Не стартовавшие и ещё идущие по дистанции (живой год) не показываются. Вкладки, «лучший на
человека», год, поиск и места внутри выборки считает страница.
"""
from collections import defaultdict

from src.siberman.hall.data import Entry, bib_order, race_time
from src.siberman.medals import medal_for
from src.siberman.persons.linking import plain_key


def person_key(e: Entry) -> tuple:
    """Человек из реестра; выступление ещё не привязано (или нет миграции 014) — по ФИ."""
    return ("p", e.person_id) if e.person_id else ("n", plain_key(e.surname, e.name))


def _holder_at(current: dict, key: str):
    rec = current.get(key)
    return (rec["holder"]["year"], rec["holder"]["bib"]) if rec else None


def _order(row: dict) -> tuple:
    return (row["time_s"] is None, row["time_s"] or 0, row["year"], bib_order(row["bib"]))


def build_rating(entries: list, teams: list, records: dict) -> dict:
    current = records["current"]
    record_individual = {g: _holder_at(current, f"race:individual:{g}") for g in ("M", "F")}
    record_team = _holder_at(current, "race:relay:X")
    finished_years = defaultdict(list)
    for e in entries:
        if race_time(e) is not None:
            finished_years[person_key(e)].append(e.year)

    individual = []
    for e in entries:
        if e.format != "individual":
            continue
        t = race_time(e)
        if t is None and e.status not in ("dnf", "dsq"):
            continue
        n = sum(1 for y in finished_years[person_key(e)] if y <= e.year) if t is not None else None
        individual.append({
            "year": e.year, "bib": e.bib, "person_id": e.person_id, "surname": e.surname, "name": e.name,
            "gender": e.gender, "city": e.city, "status": "finished" if t is not None else e.status,
            "dnf_stage": e.dnf_stage, "time_s": t, "finish_no": n, "medal": medal_for(n) if n else None,
            "record": e.gender if t is not None and (e.year, e.bib) == record_individual.get(e.gender) else None,
        })

    relay = []
    for tm in teams:
        t, status = tm.time_s, tm.status
        if t is None and status not in ("dnf", "dsq"):
            continue
        relay.append({
            "year": tm.year, "bib": tm.bib, "team": tm.name, "time_s": t,
            "status": "finished" if t is not None else status,
            "members": [{"stage": m.stage, "surname": m.surname, "name": m.name, "person_id": m.person_id}
                        for m in tm.members],
            "record": t is not None and (tm.year, tm.bib) == record_team,
        })

    individual.sort(key=_order)
    relay.sort(key=_order)
    years = sorted({r["year"] for r in individual} | {r["year"] for r in relay}, reverse=True)
    return {"individual": individual, "relay": relay, "years": years}
```

- [ ] **Step 4: Тесты проходят**

Run: та же команда. Expected: 14 passed. Затем `tests/unit/` целиком — 944 + 14 = 958 passed.

- [ ] **Step 5: Commit**

```bash
git add src/siberman/hall/rating.py tests/unit/test_siberman_hall.py
git commit -m "feat(siberman/hall): рейтинг — личники с номером финиша и медалью, эстафеты с составом"
```

---

После Task 4 добавлен коммит f7ca7b0: время этапа ≤ 0 — не время отрезка (IRONSTAR 2017 после перезагрузки 2017 года с `OFFICIAL_FINISH_FIXES`); unit 959, в файле 15 тестов.

### Task 4a: Ревью задач 1–4 — живой год, IRONSTAR, финиши непривязанных

1. **Critical — живой год.** Во время гонки `overall_results.total_s` и `stage_totals` пишутся и у идущих по дистанции (сумма последних пройденных КТ). Без проверки последней КТ каждого этапа промежуточное время попадало в рейтинг как финиш и в рекорды «гонки» как «НОВЫЙ». Теперь финиш личника и итог команды требуют последней КТ каждого этапа (как живые рекорды трекера). На архиве 2016–2025 числа те же: 196 и 71 (проверено ревью). Исключение из «Принятых правил» про команду без последней КТ больше не нужно — оно было из-за локальной базы до исправления IRONSTAR.
2. **IRONSTAR 2017 №13:** архив кладёт весь велоэтап на 2-й день (1-й = 0). Значит, и «2-й день» у них — не время дня: отрезки отдельных дней у участника с нулевым днём не считаются; итог команды (= официальный 31:53:51) — считается.
3. **Финиши непривязанных** (`person_id` нет — синхронизация реестра не прошла) считаются по ФИ среди ВСЕХ выступлений, как трекер (`finish_count_for`).
4. Тесты: живой год, IRONSTAR, ничья личник/эстафета, DNF эстафетчика в отрезках, один dns в команде, человек на двух этапах.

**Files:** Modify `src/siberman/hall/data.py`, `src/siberman/hall/rating.py`, `tests/unit/test_siberman_hall.py`.

- [ ] **Step 1: Тесты.** В `tests/unit/test_siberman_hall.py` тест `test_zero_segment_time_is_not_a_time` заменить на `test_ironstar_bike_days_are_not_separate_times_but_team_total_counts`, добавить в конец остальные:
```python
def test_ironstar_bike_days_are_not_separate_times_but_team_total_counts():
    """IRONSTAR 2017: в протоколе нет времени велоэтапа, архив кладёт весь велоэтап на 2-й день,
    1-й = 0 — ни 1-й, ни 2-й день не время дня; итог команды — официальный."""
    team_entries = [rel(2017, 13, "swim", "Пловцов", times={"swim": 11920}),
                    rel(2017, 13, "bike", "Велосипедов", times={"bike_day1": 0, "bike_day2": 73560}),
                    rel(2017, 13, "run", "Бегунов", times={"run": 29351})]
    bike = team_entries[1]
    assert segment_time(bike, ("bike_day1",)) is None
    assert segment_time(bike, ("bike_day2",)) is None
    assert segment_time(bike, ("bike_day1", "bike_day2")) is None
    assert build_teams(team_entries)[0].time_s == 11920 + 73560 + 29351


def test_live_year_partial_times_are_not_finishes():
    """Живой год: итог и этапы есть и у идущих по дистанции — без последней КТ каждого этапа это не
    финиш и не рекорд гонки; рекорд отрезка, пройденного до конца, — засчитывается."""
    going = ind(2026, 7, "Идущий", total=50, swim=5, finished=frozenset({"swim", "bike_day1", "bike_day2"}))
    entries = [ind(2025, 8, "Финишёр", total=100), going,
               rel(2026, 101, "swim", "Пловцов", times={"swim": 5}),
               rel(2026, 101, "bike", "Велосипедов", times={"bike_day1": 5, "bike_day2": 5}),
               rel(2026, 101, "run", "Бегунов", times={"run": 5}, finished=frozenset())]
    assert race_time(going) is None and build_teams(entries)[0].time_s is None
    r = rating_of(entries)
    assert [x["bib"] for x in r["individual"]] == ["8"] and r["relay"] == []
    cur = recs(entries)["current"]
    assert cur["race:individual:M"]["time_s"] == 100 and cur["race:individual:M"]["new"] is False
    assert cur["race:relay:X"] is None
    assert cur["swim:individual:M"]["holder"]["bib"] == "7" and cur["swim:individual:M"]["new"] is True


def test_tie_between_individual_and_relay_goes_to_individual():
    entries = [ind(2020, 7, "Личников", swim=8), *team(2020, 101, swim=8)]
    assert recs(entries)["current"]["swim:absolute:M"]["holder"]["team"] is None


def test_relay_dnf_member_is_not_in_records_and_one_dns_makes_team_dnf():
    entries = [*team(2020, 101, swim=5, status="dnf"), *team(2020, 102, swim=9)]
    assert recs(entries)["current"]["swim:relay:M"]["time_s"] == 9
    mixed = team(2021, 103)
    mixed[2] = rel(2021, 103, "run", "Бегунов", status="dns")
    assert build_teams(mixed)[0].status == "dnf"


def test_one_person_on_two_stages_of_a_team():
    entries = [rel(2020, 101, "swim", "Двоев", times={"swim": 10}, pid=9),
               rel(2020, 101, "bike", "Двоев", times={"bike_day1": 20, "bike_day2": 30}, pid=9),
               rel(2020, 101, "run", "Бегунов", times={"run": 15})]
    assert build_teams(entries)[0].time_s == 75
    assert [m["person_id"] for m in rating_of(entries)["relay"][0]["members"]] == [9, 9, None]


def test_unlinked_finish_counts_by_name_across_all_years():
    """Как трекер: выступление без человека из реестра — финиши по ФИ во всех годах."""
    entries = [ind(2019, 7, "Петров", total=130, pid=5), ind(2021, 7, "Петров", total=120)]
    rows = {r["year"]: r for r in rating_of(entries)["individual"]}
    assert rows[2021]["finish_no"] == 2
```

- [ ] **Step 2: Красный прогон** — падают ironstar, live, unlinked (остальные новые могут пройти — это проверка поведения, которое уже есть).

- [ ] **Step 3: `data.py`.**
```python
BIKE_DAYS = ("bike_day1", "bike_day2")


def race_time(e: Entry) -> Optional[int]:
    """Итог личника, финишировавшего всю гонку: статус active, есть официальный итог и последняя КТ
    каждого этапа (в живом году overall_results пишется и для идущих по дистанции)."""
    if e.format != "individual" or e.status != "active" or not e.overall_s or not set(STAGES) <= e.finished:
        return None
    return e.overall_s


def segment_time(e: Entry, stages: tuple) -> Optional[int]:
    """Время отрезка из этапов stages: участник не сошёл и дошёл до последней КТ каждого этапа.
    Время этапа 0 — не время (архив кладёт весь велоэтап IRONSTAR 2017 на 2-й день); у такого
    участника и «2-й день» — весь велоэтап, поэтому отрезки отдельных дней не считаются."""
    if e.status != "active" or any(s not in e.finished or (e.times.get(s) or 0) <= 0 for s in stages):
        return None
    if len(stages) == 1 and stages[0] in BIKE_DAYS and any((e.times.get(d) or 0) <= 0 for d in BIKE_DAYS):
        return None
    return sum(e.times[s] for s in stages)
```
`Team.time_s` — докстринг «Итог команды — сумма этапов: все три этапа на месте, никто не сошёл, каждый дошёл до последней КТ своих этапов (в живом году итоги этапов пишутся и у идущих).», условие в цикле:
```python
            for s in ROLE_STAGES[role]:
                if m.times.get(s) is None or s not in m.finished:
                    return None
                total += m.times[s]
```

- [ ] **Step 4: `rating.py`** — финиши по человеку, а у непривязанных по ФИ во всех годах. Удалить функцию `person_key`; в `build_rating` вместо `finished_years = defaultdict(list)` и цикла:
```python
    by_person, by_name = defaultdict(list), defaultdict(list)
    for e in entries:
        if race_time(e) is not None:
            by_name[plain_key(e.surname, e.name)].append(e.year)
            if e.person_id:
                by_person[e.person_id].append(e.year)
```
и в цикле личников:
```python
        years = by_person[e.person_id] if e.person_id else by_name[plain_key(e.surname, e.name)]
        n = sum(1 for y in years if y <= e.year) if t is not None else None
```
Докстринг модуля: «… номер финиша человека (из реестра; не привязано — по ФИ во всех годах, как трекер) …».

- [ ] **Step 5: Прогоны.** unit `test_siberman_hall.py` — 20 passed; `tests/unit/` — 964; интеграционные `test_siberman_hall.py` + `test_siberman_persons.py` — 25 passed (196 / 71 и 35 клеток — без изменений).

- [ ] **Step 6: Commit** — `fix(siberman/hall): финиш и итог команды — только с последней КТ каждого этапа; IRONSTAR; финиши непривязанных по ФИ`.

### Task 5: Снимок, API, страницы, подключение + сверка на архиве

**Files:**
- Create: `src/siberman/hall/service.py`, `src/siberman/hall/router.py`, `templates/siberman/hall_rating.html`, `templates/siberman/hall_records.html` (заглушки до Task 6–7)
- Modify: `src/krasmarafon/router.py`, `app.py` (`_MAINTENANCE_ALLOWED_PREFIXES`), `deploy/nginx.conf`
- Test: `tests/integration/test_siberman_hall.py`

- [ ] **Step 1: Интеграционные тесты**

`tests/integration/test_siberman_hall.py`:
```python
"""
Рейтинг и рекорды на локальном архиве siberman 2016–2025 (.env.local): сверка рекордов с таблицей
организаторов (лист «Рекорды», Online results Siberman.xlsx) и рейтинга — с цифрами сайта
siberman515.com/results; API и страницы блоков. Расхождения — сообщить, тест не подгонять.
"""
import pytest
from fastapi.testclient import TestClient

from app import app
from src.siberman.db import get_siberman_connection
from src.siberman.hall import data as hdata
from src.siberman.hall import service
from src.siberman.hall.rating import build_rating
from src.siberman.hall.records import build_records

SIBERMAN = {"host": "siberman.localhost"}

# Рекорды организаторов на 2025 год, секунды (времена — с листа «Рекорды»).
ORGANIZERS = {
    "race:individual:M": 71429, "race:individual:F": 95387, "race:relay:X": 76811,
    "race:absolute:M": 71429, "race:absolute:F": 95387,
    "swim:individual:M": 8647, "swim:individual:F": 12570, "swim:relay:M": 7588, "swim:relay:F": 9330,
    "swim:absolute:M": 7588, "swim:absolute:F": 9330,
    "bike:individual:M": 38943, "bike:individual:F": 51112, "bike:relay:M": 41071, "bike:relay:F": 47671,
    "bike:absolute:M": 38943, "bike:absolute:F": 47671,
    "bike1:individual:M": 13541, "bike1:individual:F": 17334, "bike1:relay:M": 13960, "bike1:relay:F": 15764,
    "bike1:absolute:M": 13541, "bike1:absolute:F": 15764,
    "bike2:individual:M": 25402, "bike2:individual:F": 33778, "bike2:relay:M": 27111, "bike2:relay:F": 31828,
    "bike2:absolute:M": 25402, "bike2:absolute:F": 31828,
    "run:individual:M": 22793, "run:individual:F": 29795, "run:relay:M": 21852, "run:relay:F": 28115,
    "run:absolute:M": 21852, "run:absolute:F": 28115,
}


@pytest.fixture(scope="module")
def archive():
    conn = get_siberman_connection()
    if conn is None:
        pytest.skip("Нет локальной БД siberman")
    try:
        entries = [e for e in hdata.load_entries(conn) if e.year <= 2025]
    finally:
        conn.close()
    if not any(e.year == 2016 for e in entries):
        pytest.skip("В локальной БД нет архива 2016–2025")
    teams = hdata.build_teams(entries)
    records = build_records(entries, teams)
    return {"entries": entries, "teams": teams, "records": records,
            "rating": build_rating(entries, teams, records)}


def test_records_match_organizers_table(archive):
    current = archive["records"]["current"]
    diffs = {k: ((current[k] or {}).get("time_s"), v) for k, v in ORGANIZERS.items()
             if (current[k] or {}).get("time_s") != v}
    assert diffs == {}, f"расхождения (наше, организаторы): {diffs}"


def test_history_ends_with_current_and_only_improves(archive):
    history, current = archive["records"]["history"], archive["records"]["current"]
    for key, h in history.items():
        assert h, key
        assert h[-1]["time_s"] == current[key]["time_s"]
        assert all(a["time_s"] > b["time_s"] for a, b in zip(h, h[1:])), key


def test_rating_counts_match_site(archive):
    rating = archive["rating"]
    finished = [r for r in rating["individual"] if r["status"] == "finished"]
    assert len(finished) == 196
    assert sum(r["gender"] == "M" for r in finished) == 184 and sum(r["gender"] == "F" for r in finished) == 12
    assert len(archive["teams"]) == 73
    assert sum(r["status"] == "finished" for r in rating["relay"]) == 71


def test_rating_marks_current_records(archive):
    rating = archive["rating"]
    assert sum(1 for r in rating["individual"] if r["record"]) == 2
    assert sum(1 for r in rating["relay"] if r["record"]) == 1


def test_api_and_pages():
    service.clear_cache()
    client = TestClient(app)
    r = client.get("/api/siberman/hall/rating")
    if r.status_code == 503:
        pytest.skip("Нет локальной БД siberman")
    assert r.status_code == 200 and {"individual", "relay", "years"} <= set(r.json())
    assert "birthdate" not in r.text
    records = client.get("/api/siberman/hall/records").json()
    assert "race:relay:X" in records["current"] and "history" not in records
    assert client.get("/api/siberman/hall/records/history", params={"cell": "run:absolute:M"}).status_code == 200
    assert client.get("/api/siberman/hall/records/history", params={"cell": "nope"}).status_code == 404
    assert client.get("/hall/rating", headers=SIBERMAN).status_code == 200
    assert client.get("/hall/records", headers=SIBERMAN).status_code == 200
    assert client.get("/hall/rating").status_code == 404
```

- [ ] **Step 2: Тесты падают**

Run: `C:\Users\podbo\miniconda3\python.exe -m pytest tests/integration/test_siberman_hall.py -q -p no:cacheprovider`
Expected: FAIL — `ImportError: cannot import name 'service'`.

- [ ] **Step 3: Снимок**

`src/siberman/hall/service.py`:
```python
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
```

- [ ] **Step 4: Роутер и подключение**

`src/siberman/hall/router.py`:
```python
"""
Рейтинг и рекорды Siberman: блоки для iframe в Тильде (/hall/rating, /hall/records) и их API.
API — обычные def: блокирующий mysql-connector уходит в пул потоков. Страницы — только на домене
Siberman.
"""
from fastapi import APIRouter, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse, JSONResponse

from src.siberman.hall import service
from src.siberman.hall.service import HallUnavailable
from src.siberman.router import templates

router = APIRouter(tags=["Siberman hall"])
PUBLIC_CACHE = {"Cache-Control": "public, max-age=60"}


def _page(request: Request, template: str):
    if getattr(request.state, "domain", "") != "siberman":
        raise HTTPException(status_code=404)
    return templates.TemplateResponse(template, {"request": request})


def _json(fn, *args) -> JSONResponse:
    try:
        data = fn(*args)
    except HallUnavailable as e:
        return JSONResponse({"detail": str(e)}, status_code=503, headers={"Cache-Control": "no-store"})
    if data is None:
        raise HTTPException(status_code=404)
    return JSONResponse(jsonable_encoder(data), headers=PUBLIC_CACHE)


@router.get("/hall/rating", response_class=HTMLResponse)
async def hall_rating_page(request: Request):
    return _page(request, "siberman/hall_rating.html")


@router.get("/hall/records", response_class=HTMLResponse)
async def hall_records_page(request: Request):
    return _page(request, "siberman/hall_records.html")


@router.get("/api/siberman/hall/rating")
def api_hall_rating():
    return _json(service.rating)


@router.get("/api/siberman/hall/records")
def api_hall_records():
    return _json(service.records)


@router.get("/api/siberman/hall/records/history")
def api_hall_record_history(cell: str = ""):
    return _json(service.record_history, cell)
```

Временные шаблоны (заменятся в Task 6–7) — `templates/siberman/hall_rating.html` и `templates/siberman/hall_records.html`, оба:
```html
<!DOCTYPE html>
<html lang="ru"><head><meta charset="UTF-8"><title>Siberman</title></head><body><div class="hall"></div></body></html>
```

В `src/krasmarafon/router.py` после подключения `siberman_persons_router`:
```python
from src.siberman.hall.router import router as siberman_hall_router
router.include_router(siberman_hall_router)
```

В `app.py`, в `_MAINTENANCE_ALLOWED_PREFIXES` после `"/draw/",` добавить (блоки на сайте Siberman не должны падать при техработах Красмарафона):
```python
    "/api/siberman/hall",
    "/hall/",
```

В `deploy/nginx.conf`, server `live.siberman515.com`, в регэкспе `location ~ ^/(api/siberman|admin|login|logout|participant/|siberman/test|draw/)` добавить `hall/`:
```nginx
        location ~ ^/(api/siberman|admin|login|logout|participant/|siberman/test|draw/|hall/) {
```
Перед правкой прочитать оба места; если в комментарии над `location` перечислены пути — дописать `/hall/…`.

- [ ] **Step 5: Тесты**

Run: `C:\Users\podbo\miniconda3\python.exe -m pytest tests/integration/test_siberman_hall.py -q -p no:cacheprovider`
Expected: 5 passed. Если `test_records_match_organizers_table` или `test_rating_counts_match_site` падает — НЕ подгонять ни тест, ни расчёт: прислать расхождения координатору (клетка, наше, их) и для рекордов — год и номер держателя нашего значения.
Run: `tests/unit/` — 964 passed.

- [ ] **Step 6: Commit**

```bash
git add src/siberman/hall/service.py src/siberman/hall/router.py templates/siberman/hall_rating.html templates/siberman/hall_records.html src/krasmarafon/router.py app.py deploy/nginx.conf tests/integration/test_siberman_hall.py
git commit -m "feat(siberman/hall): API рейтинга и рекордов, снимок на минуту, сверка с организаторами"
```

---

### Task 6: Блок «Рейтинг» (`/hall/rating`)

**Files:**
- Create: `static/css/siberman-hall.css`, `static/js/siberman-hall.js`, `static/js/siberman-hall-rating.js`
- Modify: `templates/siberman/hall_rating.html` (полная замена)

Макет: `rating-v4.html` (вкладки Абсолют / Мужчины / Женщины / Эстафеты; «Все финиши / Лучший на человека»; год; поиск по фамилии или номеру; столбцы Место, №, Участник, Пол (только «Абсолют»), Город, Время, Год, Финиш №; ФИ → страница спортсмена; время → карточка года; эстафеты — команда (→ карточка года), состав полными ФИ по этапам; DNF/DSQ в конце).

- [ ] **Step 1: Общий CSS**

`static/css/siberman-hall.css`:
```css
/* Рейтинг и рекорды Siberman (iframe в Тильде). Фирменный Onest, явные цвета (не зависят от темы). */
@font-face { font-family: 'Onest'; src: url('/static/fonts/siberman/Onest-Light.ttf') format('truetype'); font-weight: 300; font-display: swap; }
@font-face { font-family: 'Onest'; src: url('/static/fonts/siberman/Onest-ExtraBold.ttf') format('truetype'); font-weight: 800; font-display: swap; }
:root { --navy: #003D62; --red: #BE0A21; --ink: #111111; --muted: #5f5f5f; --line: #e6e6e6; --bg: #ffffff;
        --m: #eef4f9; --m2: #cfe0ee; --f: #fbeef0; --f2: #f4d3d8; }
html, body { margin: 0; background: var(--bg); color: var(--ink); font-family: 'Onest', Arial, sans-serif; }
.hall { position: relative; max-width: 960px; margin: 0 auto; padding: 12px 16px; box-sizing: border-box; }
.hall a { color: var(--navy); text-decoration: none; border-bottom: 1px dashed var(--navy); }
.tabs { display: flex; gap: 6px; flex-wrap: wrap; justify-content: center; margin-bottom: 10px; }
.tab { padding: 8px 14px; border-radius: 6px; border: 1px solid var(--navy); background: #fff; color: var(--navy); font: inherit; font-weight: 800; cursor: pointer; }
.tab.active { background: var(--navy); color: #fff; }
.bar { display: flex; gap: 8px; flex-wrap: wrap; justify-content: center; align-items: center; margin-bottom: 10px; font-size: 14px; }
.seg { display: inline-flex; border: 1px solid #bdbdbd; border-radius: 6px; overflow: hidden; }
.seg button { padding: 7px 12px; border: 0; background: #fff; color: var(--ink); font: inherit; cursor: pointer; }
.seg button.on { background: var(--ink); color: #fff; }
.bar select, .search { padding: 7px 10px; border: 1px solid #bdbdbd; border-radius: 6px; background: #fff; color: var(--ink); font: inherit; font-size: 14px; }
.search { min-width: 220px; }
.tbl { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: 15px; }
td, th { padding: 8px 6px; border-top: 1px solid var(--line); text-align: center; color: var(--ink); }
th { color: var(--muted); font-weight: 300; font-size: 13px; }
.l { text-align: left; }
.num { color: var(--muted); font-size: 13px; }
.rec { color: var(--red); font-size: 12px; margin-left: 6px; white-space: nowrap; }
.sx { display: inline-block; min-width: 18px; padding: 1px 4px; border-radius: 4px; font-size: 12px; font-weight: 800; }
.sx.m { background: var(--m); color: var(--navy); }
.sx.f { background: var(--f); color: var(--red); }
.dot { display: inline-block; width: 12px; height: 12px; border-radius: 50%; vertical-align: -1px; margin-right: 6px; }
.sec td { background: var(--navy); color: #fff; font-weight: 800; font-size: 13px; border: 0; }
.dnf td { color: #9a9a9a; }
.dnf a { color: #9a9a9a; border-color: #9a9a9a; }
.stage { text-align: left; font-size: 14px; line-height: 1.45; }
.stage .lbl { display: inline-block; width: 78px; color: var(--muted); font-size: 12px; }
.state-msg { padding: 24px; text-align: center; color: var(--muted); }
/* таблица рекордов */
.records td, .records th { border: 1px solid var(--line); vertical-align: top; font-size: 14px; }
.records th { background: var(--navy); color: #fff; font-weight: 800; }
.records th.m { background: var(--m2); color: var(--navy); }
.records th.f { background: var(--f2); color: var(--red); }
.records td.row { text-align: left; font-weight: 800; background: #f6f6f6; white-space: nowrap; }
.records td.m { background: var(--m); }
.records td.f { background: var(--f); }
.records td.x { background: #fff; }
[data-cell] { cursor: pointer; }
.t { font-weight: 800; font-size: 15px; }
.team, .yr { color: var(--muted); font-size: 12px; }
.new { color: var(--red); font-size: 11px; font-weight: 800; }
.mob { display: none; }
.rowt { font-weight: 800; margin: 14px 0 6px; text-align: center; }
.cards { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }
.card2 { border: 1px solid var(--line); border-radius: 8px; padding: 8px; font-size: 13px; text-align: center; background: #fff; }
.card2.m { background: var(--m); border-color: var(--m2); }
.card2.f { background: var(--f); border-color: var(--f2); }
.card2 .lbl2 { color: var(--ink); font-weight: 800; }
.pop { position: absolute; left: 50%; transform: translateX(-50%); width: min(560px, 94%); background: #fff; border-radius: 10px; box-shadow: 0 10px 30px rgba(0, 0, 0, .3); padding: 14px 16px; z-index: 10; box-sizing: border-box; }
.pop h4 { margin: 0 0 4px; color: var(--navy); }
.pop .x { position: absolute; right: 12px; top: 6px; font-size: 22px; color: var(--muted); cursor: pointer; }
.pop td { border: 0; border-top: 1px solid var(--line); text-align: left; font-size: 14px; }
.gain { color: var(--red); white-space: nowrap; }
@media (max-width: 640px) {
  td, th { padding: 6px 4px; font-size: 13px; }
  .city { display: none; }
  .search { min-width: 0; flex: 1 1 100%; }
  .desk { display: none; }
  .mob { display: block; }
}
```

- [ ] **Step 2: Общие помощники**

`static/js/siberman-hall.js`:
```js
'use strict';
// Общие помощники блоков «Рейтинг» и «Рекорды» Siberman (iframe в Тильде): экранирование, время,
// ссылки, загрузка API и высота содержимого для страницы Тильды (docs/siberman/hall-tilda-snippet.md).

function hallEsc(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function hallTime(s) {
  if (s == null) return '—';
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), x = s % 60;
  return `${h}:${String(m).padStart(2, '0')}:${String(x).padStart(2, '0')}`;
}

function hallNorm(s) { return String(s ?? '').toLowerCase().replace(/ё/g, 'е'); }

const HALL_STAGE = { swim: 'плавание', bike: 'велосипед', run: 'бег', bike_day1: 'вело, 1 день', bike_day2: 'вело, 2 день' };

// Ссылки из iframe — в новой вкладке: страница Тильды остаётся на месте.
function hallLink(href, html) { return `<a href="${href}" target="_blank" rel="noopener">${html}</a>`; }
function hallAthlete(personId, html) { return personId ? hallLink(`/athlete/${personId}`, html) : html; }
function hallCard(bib, year, html) { return hallLink(`/participant/${encodeURIComponent(bib)}?year=${year}`, html); }

async function hallLoad(path) {
  const r = await fetch(path, { cache: 'no-store' });
  if (!r.ok) throw new Error(r.status === 503 ? 'Данные временно недоступны — обновите страницу через минуту' : 'Не удалось загрузить данные');
  return r.json();
}

(function () {
  if (window.parent === window) return;
  // documentElement.scrollHeight не меньше окна iframe — iframe не сжимался бы; меряем сам блок
  const box = () => document.querySelector('.hall') || document.body;
  const send = () => window.parent.postMessage({ sibermanHallHeight: Math.ceil(box().getBoundingClientRect().height) + 8 }, '*');
  window.addEventListener('load', () => { new ResizeObserver(send).observe(box()); send(); });
  setInterval(send, 2000); // скрипт-слушатель Тильды может подключиться позже iframe
})();
```

- [ ] **Step 3: Страница**

`templates/siberman/hall_rating.html` (полная замена):
```html
<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Siberman — рейтинг</title>
<link rel="stylesheet" href="/static/css/siberman-hall.css?v={{ v }}">
</head>
<body>
<div class="hall">
  <div class="tabs" id="tabs">
    <button class="tab active" data-tab="abs">Абсолют</button>
    <button class="tab" data-tab="men">Мужчины</button>
    <button class="tab" data-tab="women">Женщины</button>
    <button class="tab" data-tab="relay">Эстафеты</button>
  </div>
  <div class="bar">
    <span class="seg" id="mode"><button class="on" data-mode="all">Все финиши</button><button data-mode="best">Лучший на человека</button></span>
    <select id="year"><option value="">Все годы</option></select>
    <input id="q" class="search" placeholder="Поиск по фамилии или номеру…" autocomplete="off">
  </div>
  <div class="tbl"><table id="table"><tr><td class="state-msg">Загрузка…</td></tr></table></div>
</div>
<script src="/static/js/siberman-hall.js?v={{ v }}"></script>
<script src="/static/js/siberman-hall-rating.js?v={{ v }}"></script>
</body>
</html>
```

- [ ] **Step 4: Логика рейтинга**

`static/js/siberman-hall-rating.js`:
```js
'use strict';
// Блок «Рейтинг» (/hall/rating): вкладки, «лучший на человека», год, поиск; места — внутри выборки
// (год и режим), поиск только находит строки и места не меняет. Данные — /api/siberman/hall/rating.

let data = null, tab = 'abs', mode = 'all', year = '', query = '';
const table = document.getElementById('table');
const DNF_STAGE = { swim: 'плавание', bike_day1: 'вело, 1 день', bike_day2: 'вело, 2 день', run: 'бег' };

function personKey(r) { return r.person_id ? 'p' + r.person_id : 'n' + hallNorm(`${r.surname} ${r.name}`); }
function fio(r) { return hallEsc(`${r.surname} ${r.name}`); }
function outcome(r) { return r.status === 'dsq' ? 'DSQ' : 'DNF' + (r.dnf_stage ? ` (${DNF_STAGE[r.dnf_stage] || hallEsc(r.dnf_stage)})` : ''); }

function matches(names, bib) {
  const q = hallNorm(query.trim());
  if (!q) return true;
  if (/^\d+$/.test(q)) return String(bib) === q;
  return names.some(n => hallNorm(n).includes(q));
}

function rank(fin) {
  fin.sort((a, b) => a.time_s - b.time_s || a.year - b.year);
  fin.forEach((r, i) => { r.place = i + 1; });
}

function pickIndividual() {
  const g = tab === 'men' ? 'M' : tab === 'women' ? 'F' : null;
  const rows = data.individual.filter(r => (!g || r.gender === g) && (!year || String(r.year) === year));
  let fin = rows.filter(r => r.status === 'finished'), out = rows.filter(r => r.status !== 'finished');
  if (mode === 'best') {
    const best = new Map();
    fin.forEach(r => { const k = personKey(r), b = best.get(k); if (!b || r.time_s < b.time_s) best.set(k, r); });
    fin = [...best.values()];
    const done = new Set(fin.map(personKey)), last = new Map();
    out.forEach(r => { const k = personKey(r); if (!done.has(k) && (!last.has(k) || r.year > last.get(k).year)) last.set(k, r); });
    out = [...last.values()];
  }
  rank(fin);
  out.sort((a, b) => b.year - a.year);
  return { fin, out };
}

function renderIndividual() {
  const { fin, out } = pickIndividual(), abs = tab === 'abs', cols = abs ? 8 : 7;
  const sex = r => abs ? `<td><span class="sx ${r.gender === 'F' ? 'f' : 'm'}">${r.gender === 'F' ? 'Ж' : 'М'}</span></td>` : '';
  const rec = r => r.record ? `<span class="rec">${abs && r.record === 'F' ? 'рекорд Ж' : 'рекорд'}</span>` : '';
  const medal = r => r.medal ? `<span class="dot" style="background:${r.medal.color}" title="${hallEsc(r.medal.name)}"></span>` : '';
  const found = r => matches([`${r.surname} ${r.name}`], r.bib);
  const row = r => `<tr><td>${r.place}</td><td class="num">${hallEsc(r.bib)}</td>
    <td class="l">${hallAthlete(r.person_id, fio(r))}${rec(r)}</td>${sex(r)}<td class="city">${hallEsc(r.city)}</td>
    <td>${hallCard(r.bib, r.year, '<b>' + hallTime(r.time_s) + '</b>')}</td><td>${r.year}</td><td>${medal(r)}${r.finish_no}</td></tr>`;
  const dnf = r => `<tr class="dnf"><td>—</td><td class="num">${hallEsc(r.bib)}</td>
    <td class="l">${hallAthlete(r.person_id, fio(r))}</td>${sex(r)}<td class="city">${hallEsc(r.city)}</td>
    <td>${hallCard(r.bib, r.year, outcome(r))}</td><td>${r.year}</td><td></td></tr>`;
  const f = fin.filter(found), o = out.filter(found);
  let html = `<tr><th>Место</th><th class="num">№</th><th class="l">Участник</th>${abs ? '<th>Пол</th>' : ''}
    <th class="city">Город</th><th>Время</th><th>Год</th><th>Финиш №</th></tr>`;
  html += f.map(row).join('') || `<tr><td colspan="${cols}" class="state-msg">Никого не нашлось</td></tr>`;
  if (o.length) html += `<tr class="sec"><td colspan="${cols}">Не финишировали</td></tr>` + o.map(dnf).join('');
  table.innerHTML = html;
}

function memberLine(m) {
  return `<span class="lbl">${HALL_STAGE[m.stage] || ''}</span>${hallAthlete(m.person_id, hallEsc(`${m.surname} ${m.name}`))}`;
}

function renderRelay() {
  const rows = data.relay.filter(r => !year || String(r.year) === year);
  const fin = rows.filter(r => r.status === 'finished'), out = rows.filter(r => r.status !== 'finished');
  rank(fin);
  out.sort((a, b) => b.year - a.year);
  const found = r => matches([r.team, ...r.members.map(m => `${m.surname} ${m.name}`)], r.bib);
  const name = r => hallCard(r.bib, r.year, `<b>${r.team ? '«' + hallEsc(r.team) + '»' : 'Команда №' + hallEsc(r.bib)}</b>`);
  const rec = r => r.record ? '<span class="rec">рекорд</span>' : '';
  const row = r => `<tr><td>${r.place}</td><td class="num">${hallEsc(r.bib)}</td><td class="l">${name(r)}${rec(r)}</td>
    <td class="stage">${r.members.map(memberLine).join('<br>')}</td>
    <td>${hallCard(r.bib, r.year, '<b>' + hallTime(r.time_s) + '</b>')}</td><td>${r.year}</td></tr>`;
  const dnf = r => `<tr class="dnf"><td>—</td><td class="num">${hallEsc(r.bib)}</td><td class="l">${name(r)}</td>
    <td class="stage">${r.members.map(memberLine).join('<br>')}</td><td>${r.status === 'dsq' ? 'DSQ' : 'DNF'}</td><td>${r.year}</td></tr>`;
  const f = fin.filter(found), o = out.filter(found);
  let html = '<tr><th>Место</th><th class="num">№</th><th class="l">Команда</th><th class="l">Состав</th><th>Время</th><th>Год</th></tr>';
  html += f.map(row).join('') || '<tr><td colspan="6" class="state-msg">Никого не нашлось</td></tr>';
  if (o.length) html += '<tr class="sec"><td colspan="6">Не финишировали</td></tr>' + o.map(dnf).join('');
  table.innerHTML = html;
}

function render() {
  if (!data) return;
  document.getElementById('mode').style.display = tab === 'relay' ? 'none' : '';
  document.getElementById('q').placeholder = tab === 'relay' ? 'Поиск по команде, фамилии или номеру…' : 'Поиск по фамилии или номеру…';
  if (tab === 'relay') renderRelay(); else renderIndividual();
}

document.getElementById('tabs').addEventListener('click', e => {
  const b = e.target.closest('.tab');
  if (!b) return;
  tab = b.dataset.tab;
  document.querySelectorAll('#tabs .tab').forEach(x => x.classList.toggle('active', x === b));
  render();
});
document.getElementById('mode').addEventListener('click', e => {
  const b = e.target.closest('button');
  if (!b) return;
  mode = b.dataset.mode;
  document.querySelectorAll('#mode button').forEach(x => x.classList.toggle('on', x === b));
  render();
});
document.getElementById('year').addEventListener('change', e => { year = e.target.value; render(); });
document.getElementById('q').addEventListener('input', e => { query = e.target.value; render(); });

hallLoad('/api/siberman/hall/rating').then(d => {
  data = d;
  document.getElementById('year').insertAdjacentHTML('beforeend', d.years.map(y => `<option value="${y}">${y}</option>`).join(''));
  render();
}).catch(err => { table.innerHTML = `<tr><td class="state-msg">${hallEsc(err.message)}</td></tr>`; });
```

- [ ] **Step 5: Синтаксис и тесты**

Run: `node --check static/js/siberman-hall.js` и `node --check static/js/siberman-hall-rating.js` — без вывода.
Run: интеграционные `tests/integration/test_siberman_hall.py` — 5 passed (шаблон теперь настоящий).

- [ ] **Step 6: Commit**

```bash
git add static/css/siberman-hall.css static/js/siberman-hall.js static/js/siberman-hall-rating.js templates/siberman/hall_rating.html
git commit -m "feat(siberman/hall): блок «Рейтинг» — вкладки, лучший на человека, год, поиск"
```

---

### Task 7: Блок «Рекорды» (`/hall/records`)

**Files:**
- Create: `static/js/siberman-hall-records.js`
- Modify: `templates/siberman/hall_records.html` (полная замена)

Макет: `records-v8.html` (вариант А): таблица 6 × (личный, эстафета, абсолют) × (М, Ж), строка «гонка» — эстафета одной белой клеткой; цвет столбцов по полу; в клетке время, ФИ (→ страница), у эстафетчика команда, год, «НОВЫЙ»; в абсолютной клетке отрезка у эстафетчика — «эстафета», с новой строки команда (→ карточка года); клик по ФИ/команде — переход, по остальной клетке — всплывающая история рядом с клеткой (× / клик мимо / Esc); телефон — блоки по дисциплинам, карточки 2×3 по центру, полные ФИ, названия зачётов жирным, цвет по полу.

- [ ] **Step 1: Страница**

`templates/siberman/hall_records.html` (полная замена):
```html
<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Siberman — рекорды</title>
<link rel="stylesheet" href="/static/css/siberman-hall.css?v={{ v }}">
</head>
<body>
<div class="hall">
  <div class="desk tbl"><table class="records" id="table"><tr><td class="state-msg">Загрузка…</td></tr></table></div>
  <div class="mob" id="cards"></div>
  <div class="pop" id="pop" hidden></div>
</div>
<script src="/static/js/siberman-hall.js?v={{ v }}"></script>
<script src="/static/js/siberman-hall-records.js?v={{ v }}"></script>
</body>
</html>
```

- [ ] **Step 2: Логика рекордов**

`static/js/siberman-hall-records.js`:
```js
'use strict';
// Блок «Рекорды» (/hall/records): таблица как у организаторов (вариант А), на телефоне — карточки;
// клик по ФИ / команде — переход, по остальной клетке — история рекорда во всплывающем окне рядом
// с клеткой (в iframe окно по центру всей высоты могло бы оказаться вне экрана).

const SEGS = [['race', 'Гонка 515'], ['swim', 'Плавание 10'], ['bike', 'Вело 421'],
              ['bike1', 'Вело, 1 день'], ['bike2', 'Вело, 2 день'], ['run', 'Бег 84']];
const COLS = [['individual', 'Личный зачёт'], ['relay', 'Эстафета'], ['absolute', 'Абсолютно лучшее время']];
const COL_TITLE = { individual: 'личный зачёт', relay: 'эстафета', absolute: 'абсолютно лучшее' };
let data = null;

function holderHtml(rec, key) {
  const h = rec.holder, col = key.split(':')[1];
  if (h.type === 'team') {
    return hallCard(h.bib, h.year, `<b>${h.name ? '«' + hallEsc(h.name) + '»' : 'Команда №' + hallEsc(h.bib)}</b>`);
  }
  const who = hallAthlete(h.person_id, hallEsc(h.fio));
  if (!h.team) return who;
  const team = hallCard(h.bib, h.year, '«' + hallEsc(h.team) + '»');
  return col === 'absolute' ? `${who}<div class="team">эстафета<br>${team}</div>` : `${who}<div class="team">${team}</div>`;
}

function body(key) {
  const rec = data.current[key];
  if (!rec) return '<div class="yr">—</div>';
  return `<div class="t">${hallTime(rec.time_s)}</div>${holderHtml(rec, key)}
    <div class="yr">${rec.year}${rec.new ? ' <span class="new">НОВЫЙ</span>' : ''}</div>`;
}

function renderTable() {
  let h = '<tr><th rowspan="2"></th>' + COLS.map(c => `<th colspan="2">${c[1]}</th>`).join('') + '</tr><tr>'
        + COLS.map(() => '<th class="m">Мужчины</th><th class="f">Женщины</th>').join('') + '</tr>';
  for (const [seg, label] of SEGS) {
    h += `<tr><td class="row">${label}</td>`;
    for (const [col] of COLS) {
      if (seg === 'race' && col === 'relay') {
        h += `<td class="x" colspan="2" data-cell="race:relay:X">${body('race:relay:X')}</td>`;
      } else {
        h += `<td class="m" data-cell="${seg}:${col}:M">${body(`${seg}:${col}:M`)}</td>`
           + `<td class="f" data-cell="${seg}:${col}:F">${body(`${seg}:${col}:F`)}</td>`;
      }
    }
    h += '</tr>';
  }
  document.getElementById('table').innerHTML = h;
}

function card(key, title, cls, wide) {
  return `<div class="card2 ${cls}" data-cell="${key}"${wide ? ' style="grid-column: span 2"' : ''}><b class="lbl2">${title}</b>${body(key)}</div>`;
}

function renderCards() {
  document.getElementById('cards').innerHTML = SEGS.map(([seg, label]) => {
    const relay = seg === 'race'
      ? card('race:relay:X', 'Эстафета', 'x', true)
      : card(`${seg}:relay:M`, 'Эстафета · М', 'm') + card(`${seg}:relay:F`, 'Эстафета · Ж', 'f');
    return `<div class="rowt">${label}</div><div class="cards">`
      + card(`${seg}:individual:M`, 'Личный · М', 'm') + card(`${seg}:individual:F`, 'Личный · Ж', 'f')
      + relay + card(`${seg}:absolute:M`, 'Абсолют · М', 'm') + card(`${seg}:absolute:F`, 'Абсолют · Ж', 'f') + '</div>';
  }).join('');
}

function cellTitle(key) {
  const [seg, col, g] = key.split(':');
  return `${SEGS.find(s => s[0] === seg)[1]} · ${COL_TITLE[col]}${g === 'M' ? ' · мужчины' : g === 'F' ? ' · женщины' : ''}`;
}

const pop = document.getElementById('pop'), hall = document.querySelector('.hall');

function place(anchor) {
  const a = anchor.getBoundingClientRect(), b = hall.getBoundingClientRect();
  pop.style.top = `${a.bottom - b.top + 6}px`;
  hall.style.minHeight = '';
  const need = pop.offsetTop + pop.offsetHeight + 16;   // окно не должно выходить за iframe
  if (need > hall.offsetHeight) hall.style.minHeight = `${need}px`;
}

function closePop() {
  pop.hidden = true;
  hall.style.minHeight = '';
}

async function openHistory(key, anchor) {
  pop.innerHTML = `<span class="x" data-close>×</span><h4>История рекорда</h4><div class="team">${hallEsc(cellTitle(key))}</div>
    <div class="state-msg" id="pop-body">Загрузка…</div>`;
  pop.hidden = false;
  place(anchor);
  try {
    const list = await hallLoad(`/api/siberman/hall/records/history?cell=${encodeURIComponent(key)}`);
    const rows = list.slice().reverse().map((e, i) => `<tr><td><b>${hallTime(e.time_s)}</b></td><td>${holderHtml(e, key)}</td>
      <td>${e.year}</td><td class="gain">${e.delta_s ? '−' + hallTime(e.delta_s) : ''}</td>
      <td class="team">${i === 0 ? 'текущий' : e.delta_s == null ? 'первый' : ''}</td></tr>`).join('');
    document.getElementById('pop-body').outerHTML = `<table>${rows}</table>`;
  } catch (err) {
    document.getElementById('pop-body').textContent = err.message;
  }
  place(anchor);
}

document.addEventListener('click', e => {
  if (e.target.closest('[data-close]')) return closePop();
  if (e.target.closest('a')) return;                       // ФИ / команда — обычный переход
  const cell = e.target.closest('[data-cell]');
  if (cell && !pop.contains(cell)) return openHistory(cell.dataset.cell, cell);
  if (!pop.contains(e.target)) closePop();
});
document.addEventListener('keydown', e => { if (e.key === 'Escape') closePop(); });

hallLoad('/api/siberman/hall/records').then(d => { data = d; renderTable(); renderCards(); })
  .catch(err => { document.getElementById('table').innerHTML = `<tr><td class="state-msg">${hallEsc(err.message)}</td></tr>`; });
```

- [ ] **Step 3: Синтаксис и тесты**

Run: `node --check static/js/siberman-hall-records.js` — без вывода. Интеграционные `test_siberman_hall.py` — 5 passed.

- [ ] **Step 4: Commit**

```bash
git add static/js/siberman-hall-records.js templates/siberman/hall_records.html
git commit -m "feat(siberman/hall): блок «Рекорды» — таблица, карточки на телефоне, история во всплывающем окне"
```

---

### Task 7a: Ревью задач 5–7 — сбой БД, окно истории, клавиатура

1. **Сбой БД.** Снимок не собрался → прошлый снимок отдаётся, но `at` не обновлялся: каждый запрос снова шёл в БД (≈2 с) под `_lock`, запросы вставали в очередь и занимали пул потоков. Теперь после ошибки следующая попытка — не раньше чем через `RETRY_S`; без снимка в это время сразу 503; ошибка — в лог.
2. **Окно истории.** Ответ для клетки A, пришедший после клика по B, писался в окно B; после закрытия окна во время загрузки вызывался `place()`. Теперь номер запроса `popSeq`.
3. **Клавиатура.** Клетки и карточки — `tabindex="0" role="button"`, Enter/пробел открывают историю; крестик — кнопка; окно — `role="dialog"`, фокус в окно и обратно на клетку.
4. Мелочи: заголовок `Cache-Control: public, max-age=60` убран (nginx в том же location ставит `no-store`, снимок и так в памяти); у поиска `type="search"` и `aria-label`, у вкладок и переключателя — `type="button"`; тест 404 для `/hall/records` на чужом домене.

**Files:** Modify `src/siberman/hall/service.py`, `src/siberman/hall/router.py`, `static/js/siberman-hall-records.js`, `static/css/siberman-hall.css`, `templates/siberman/hall_records.html`, `templates/siberman/hall_rating.html`, `tests/integration/test_siberman_hall.py`. Create `tests/unit/test_siberman_hall_service.py`.

- [ ] **Step 1: Тест сервиса** — `tests/unit/test_siberman_hall_service.py`:
```python
import mysql.connector
import pytest

from src.siberman.hall import service


@pytest.fixture
def clock(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(service.time, "monotonic", lambda: now[0])
    service.clear_cache()
    yield now
    service.clear_cache()


def test_db_failure_serves_old_snapshot_and_retries_not_before_retry_s(clock, monkeypatch):
    calls = []

    def build():
        calls.append(clock[0])
        if len(calls) > 1:
            raise mysql.connector.Error("down")
        return {"rating": "old", "records": {}}

    monkeypatch.setattr(service, "_build", build)
    assert service.rating() == "old"
    clock[0] += service.CACHE_TTL_S
    assert service.rating() == "old" and len(calls) == 2          # попытка была, отдали прошлый снимок
    clock[0] += service.RETRY_S - 1
    assert service.rating() == "old" and len(calls) == 2          # в БД не ходим до RETRY_S
    clock[0] += 1
    assert service.rating() == "old" and len(calls) == 3


def test_no_snapshot_fails_fast_until_retry_s(clock, monkeypatch):
    calls = []

    def build():
        calls.append(clock[0])
        raise service.HallUnavailable("x")

    monkeypatch.setattr(service, "_build", build)
    for _ in range(3):
        with pytest.raises(service.HallUnavailable):
            service.rating()
    assert len(calls) == 1
    clock[0] += service.RETRY_S
    with pytest.raises(service.HallUnavailable):
        service.rating()
    assert len(calls) == 2
```
Run: `C:\Users\podbo\miniconda3\python.exe -m pytest tests/unit/test_siberman_hall_service.py -q -p no:cacheprovider`. Expected: 2 failed (первый — `AttributeError: ... RETRY_S`, второй — `assert 3 == 1`).

- [ ] **Step 2: `service.py`.** Импорт `logging`, `log = logging.getLogger(__name__)`, `RETRY_S = 10` под `CACHE_TTL_S`, в докстринге модуля последнее предложение: «БД недоступна — отдаём прошлый снимок, если он есть, и пробуем снова не раньше чем через RETRY_S (без снимка до этого сразу 503), чтобы запросы не ждали БД друг за другом под блокировкой.»
```python
_cache = {"at": 0.0, "snap": None, "fail_at": None}


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
```
Run: тот же файл — 2 passed.

- [ ] **Step 3: `router.py`.** Удалить `PUBLIC_CACHE`; в `_json` последняя строка — `return JSONResponse(jsonable_encoder(data))`.

- [ ] **Step 4: интеграционный тест.** В `test_api_and_pages` после `assert client.get("/hall/rating").status_code == 404` добавить `assert client.get("/hall/records").status_code == 404`.

- [ ] **Step 5: `siberman-hall-records.js`.**
  - В `renderTable` у обеих веток `td` с `data-cell` и в `card` добавить ` tabindex="0" role="button"` сразу после `data-cell="…"`.
  - Окно и фокус:
```js
const pop = document.getElementById('pop'), hall = document.querySelector('.hall');
let popSeq = 0, popFrom = null;                      // номер последнего открытия; клетка, куда вернуть фокус
```
```js
function closePop() {
  if (pop.hidden) return;
  popSeq++;
  pop.hidden = true;
  hall.style.minHeight = '';
  if (popFrom) popFrom.focus();
  popFrom = null;
}

async function openHistory(key, anchor) {
  const seq = ++popSeq;
  popFrom = anchor;
  pop.innerHTML = `<button type="button" class="close" data-close aria-label="Закрыть">×</button>
    <h4 id="pop-title">История рекорда</h4><div class="team">${hallEsc(cellTitle(key))}</div>
    <div class="state-msg" id="pop-body">Загрузка…</div>`;
  pop.hidden = false;
  place(anchor);
  pop.querySelector('.close').focus();
  try {
    const list = await hallLoad(`/api/siberman/hall/records/history?cell=${encodeURIComponent(key)}`);
    if (seq !== popSeq) return;                      // открыли другую клетку или закрыли окно
    const rows = …                                   // без изменений
    document.getElementById('pop-body').outerHTML = `<table>${rows}</table>`;
  } catch (err) {
    if (seq !== popSeq) return;
    document.getElementById('pop-body').textContent = err.message;
  }
  place(anchor);
}
```
  - Обработчик клавиш вместо однострочного:
```js
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') return closePop();
  const cell = (e.key === 'Enter' || e.key === ' ') && e.target.closest && e.target.closest('[data-cell]');
  if (cell && e.target === cell) { e.preventDefault(); openHistory(cell.dataset.cell, cell); }
});
```
  (`e.target === cell` — Enter на ссылке ФИ внутри клетки остаётся переходом.)

- [ ] **Step 6: шаблоны и CSS.**
  - `hall_records.html`: `<div class="pop" id="pop" role="dialog" aria-labelledby="pop-title" hidden></div>`.
  - `hall_rating.html`: всем `<button` вкладок и переключателя режима — `type="button"`; поиск — `<input id="q" class="search" type="search" aria-label="Поиск по фамилии или номеру" placeholder="Поиск по фамилии или номеру…" autocomplete="off">`.
  - `siberman-hall.css`: строку `.pop .x { … }` заменить на
```css
.pop .close { position: absolute; right: 8px; top: 4px; font-size: 22px; line-height: 1; color: var(--muted); cursor: pointer; background: none; border: 0; padding: 4px 6px; }
[data-cell]:focus-visible, .pop .close:focus-visible { outline: 2px solid var(--navy); outline-offset: -2px; }
```

- [ ] **Step 7: Прогоны.** `node --check static/js/siberman-hall-records.js`; `tests/unit/` — 966 passed; интеграционные `test_siberman_hall.py` + `test_siberman_persons.py` — 25 passed.

- [ ] **Step 8: Commit** — `fix(siberman/hall): сбой БД без очереди под блокировкой; окно истории — последний клик, клавиатура и фокус`.

### Task 8: Вставка в Тильду, проверка в браузере, документы

**Files:**
- Create: `docs/siberman/hall-tilda-snippet.md`
- Modify (основной репозиторий): `.taskmaster/tasks/todo.md` — делает координатор

- [ ] **Step 1: Сниппет для Тильды**

`docs/siberman/hall-tilda-snippet.md`:
````markdown
# Рейтинг и рекорды Siberman — вставка в Тильду (siberman515.com/results)

Два HTML-блока **T123** («Другое → HTML-код») — вместо ручных таблиц T431: рейтинг — на месте
блоков «Мужчины / Женщины / Эстафетные команды», рекорды — на месте «Рекорды Siberman». Каждый блок
самодостаточен: iframe, якорь и скрипт автовысоты (страница блока сообщает высоту через
`postMessage`; если скрипт есть в обоих блоках — это не мешает).

Меню «Результаты»: ссылки «Личное участие» и «Эстафетные команды» → `#hall-rating`,
«Рекорды и итоги» → `#hall-records` (старые якоря `#rec…` принадлежали удаляемым блокам).

## Блок 1 — «Рейтинг»

```html
<a id="hall-rating" name="hall-rating"></a>
<iframe class="sbm-hall" src="https://live.siberman515.com/hall/rating" style="width:100%;border:0;height:1200px" title="Siberman — рейтинг за все годы"></iframe>
<script>
window.addEventListener('message', function (e) {
  if (e.origin !== 'https://live.siberman515.com' || !e.data || !e.data.sibermanHallHeight) return;
  document.querySelectorAll('iframe.sbm-hall').forEach(function (f) {
    if (f.contentWindow === e.source) f.style.height = e.data.sibermanHallHeight + 'px';
  });
});
</script>
```

## Блок 2 — «Рекорды»

```html
<a id="hall-records" name="hall-records"></a>
<iframe class="sbm-hall" src="https://live.siberman515.com/hall/records" style="width:100%;border:0;height:900px" title="Siberman — рекорды"></iframe>
<script>
window.addEventListener('message', function (e) {
  if (e.origin !== 'https://live.siberman515.com' || !e.data || !e.data.sibermanHallHeight) return;
  document.querySelectorAll('iframe.sbm-hall').forEach(function (f) {
    if (f.contentWindow === e.source) f.style.height = e.data.sibermanHallHeight + 'px';
  });
});
</script>
```

Ссылки внутри блоков (страница спортсмена, карточка года) открываются в новой вкладке.
Выкладывать только вместе с планом 4 (страница спортсмена `/athlete/{id}` и `athlete/` в nginx) — иначе ссылки ФИ ведут на 404.
Данные обновляются сами: блоки читают БД (снимок на минуту), ручная правка таблиц больше не нужна.
````

- [ ] **Step 2: Проверка в браузере**

Сервер: скрипт `serve.py` из scratchpad сессии (`C:\Users\podbo\AppData\Local\Temp\claude\c--Users-podbo--------------------KM-track\77cf03bd-db91-4aec-a7c4-dc1aa8f02b62\scratchpad`), запуск из корня worktree в фоне, порт 8011. Playwright-скрипт — в scratchpad, `channel="chrome"`, домен `siberman.localhost:8011`. Проверить и записать числа:

`/hall/rating` (десктоп 1100×900 и телефон 390×800, `is_mobile`, `has_touch`):
1. Нет `pageerror`, нет ответов 4xx/5xx у fetch.
2. «Абсолют»: строк финишей = 196, столбец «Пол» есть; «Мужчины» — 184, «Женщины» — 12, без «Пол»; «Эстафеты» — 71 финиш, переключатель режима скрыт.
3. «Лучший на человека» на «Абсолюте»: строк меньше 196, первые места те же; год 2023 — строки только 2023 года, места с 1.
4. Поиск по номеру (взять номер из первой строки) — 1 строка; поиск «zzz» — «Никого не нашлось».
5. У первой строки «Абсолюта» пометка «рекорд»; ссылка ФИ ведёт на `/athlete/<id>` с `target=_blank`, время — на `/participant/<номер>?year=<год>`.
6. Телефон: нет горизонтальной прокрутки страницы (`document.documentElement.scrollWidth <= innerWidth`).

`/hall/records` (десктоп и телефон):
7. Нет ошибок. Десктоп: таблица 6 строк, клетка `race:relay:X` с `colspan=2`; на телефоне таблица скрыта, карточек 6 блоков × 7 и 6 (первый блок — 5 карточек, остальные — 6).
8. Клик по времени в клетке `run:absolute:M` → окно истории видно, в нём ≥ 1 строка и «текущий»; Esc — окно скрыто; клик по ФИ в клетке не открывает окно.
9. Окно открыто у нижней строки («Бег 84») и у последней карточки на телефоне — нижний край окна в пределах `.hall` (min-height выросла); на скриншоте iframe-страницы окно не уходит за экран — иначе записать в замечания (`scrollIntoView` или открытие над клеткой).
10. Клавиатура: Tab до клетки → Enter открывает окно, фокус на крестике; Esc закрывает, фокус снова на клетке. Быстрый клик по клетке A, затем B — в окне заголовок и история B.

iframe (обе страницы): локальная HTML-страница в scratchpad с двумя iframe (`http://siberman.localhost:8011/hall/rating`, `/hall/records`) и скриптом из сниппета, в котором `e.origin` заменён на `http://siberman.localhost:8011` → высота iframe через 3 с > 600 и примерно равна высоте блока.

Скриншоты (десктоп и телефон, обе страницы, окно истории) — в scratchpad, посмотреть глазами. Сервер остановить, cookie не нужен (страницы публичные).

- [ ] **Step 3: Полный прогон**

Run: `tests/unit/` — 966 passed; `tests/integration/test_siberman_hall.py tests/integration/test_siberman_persons.py` — 25 passed.

- [ ] **Step 4: Commit**

```bash
git add docs/siberman/hall-tilda-snippet.md
git commit -m "docs(siberman/hall): вставка рейтинга и рекордов в Тильду"
```

- [ ] **Step 5: Отчёт координатору** — числа из Step 2–3, скриншоты (пути), замечания по виду.

---

## Self-review (сделан при написании плана)

- Спецификация §4 (рейтинг: вкладки, переключатель, год, поиск, DNF/DSQ в конце, номер, «N-й финиш» с медалью, ссылки, эстафеты без пола с составом и ссылкой на команду) — Task 4, 6; §5.1 (таблица, вариант А, эстафета «гонки» без пола, «эстафета» + команда в абсолютных клетках отрезков, «НОВЫЙ», только финишировавшие) — Task 3, 7; §5.2 (история, окно рядом с клеткой, переходы по ФИ/команде) — Task 3, 7; §5.3 (сверка с организаторами) — Task 5; §5.4 (цвета, телефон) — Task 6–7 (CSS), 7; §9 (медали одной функцией) — Task 1; §2 (блоки, API, снимок 60 с, nginx, сниппет, домен) — Task 5, 8; §11 (БД недоступна → прошлый снимок / 503, живой год) — Task 5, 4; §12 — Task 1–5, 8. Статистика, география, страница спортсмена — планы 3–4 (ссылки `/athlete/{id}` заработают после плана 4).
- Имена: `Entry`, `Team`, `build_teams`, `race_time`, `segment_time`, `bib_order` (data) используются в records/rating; `build_records(entries, teams)` → `current/history/last_year`; `build_rating(entries, teams, records)` → `individual/relay/years`; `service.rating/records/record_history/clear_cache`; JS: `hallEsc/hallTime/hallNorm/hallLink/hallAthlete/hallCard/hallLoad/HALL_STAGE`.
- Числа тестов: unit 944 → 945 (T1) → 948 (T2) → 954 (T3) → 958 (T4) → 959 (f7ca7b0) → 964 (T4a) → 966 (T7a); интеграционные hall — 5.
