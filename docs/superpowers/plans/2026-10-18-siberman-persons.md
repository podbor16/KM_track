# Siberman: реестр людей — план реализации (план 1 из 4)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Реестр людей Siberman: каждое выступление архива и новых лет привязано к человеку (с тёзками), даты рождения из заявок Тильды, вкладка «Люди» в админке с ручными решениями и отменой, счётчик финишей — по человеку.

**Architecture:** Пакет `src/siberman/persons/`: чистая логика привязки (`linking.py`) и разбор CSV заявок (`applicants.py`) без БД; SQL (`db.py`); сервис с транзакциями под `GET_LOCK`, журналом-снимками для отмены (`service.py`); роутер админки (`router.py`). Привязки хранятся в отдельной таблице `siberman_person_links` по естественному ключу выступления (год, номер, этап) — переживают перезагрузку года из Excel (`clear_race_year` удаляет строки `participants`). Синхронизация вызывается хвостом `recompute_totals_ranks_records()` (своё соединение, ошибки не ломают приём результатов).

**Tech Stack:** Python 3.13, FastAPI 0.104, mysql-connector (autocommit), pytest (conda base), ванильный JS, Playwright (`channel="chrome"`) для проверки в браузере.

**Спецификация:** `docs/superpowers/specs/2026-10-18-siberman-hall-ratings-records-design.md` §3. Остальные планы (рейтинг и рекорды; статистика и география; страница спортсмена и медали) пишутся после этого — они читают реестр.

**Отличие от спецификации (уточнение при планировании):** вместо колонки `participants.person_id` + `person_locked` — таблица `siberman_person_links (race_year, bib, relay_stage) → person_id, manual`. Причина: загрузка Excel делает `DELETE FROM participants WHERE race_year=…` и вставляет строки заново — колонка в `participants` теряла бы привязки (в т.ч. ручные) и id людей в адресах `/athlete/{id}` менялись бы. Таск 10 правит спецификацию.

**Правила для исполнителя:**
- Работать только в worktree `.worktrees/siberman-hall` (ветка `feature/siberman-hall`).
- Не печатать содержимое `.env`, `.env.local`, пароли, cookie. Не выводить ФИО/даты рождения из БД и CSV в отчёты — только числа.
- BOM в коде — только как `chr(0xFEFF)`, никогда литералом.
- Тесты: `conda run -n base python -m pytest …` из корня worktree.

---

## Карта файлов

| Файл | Что делает |
|---|---|
| `src/siberman/migrations/014_persons.sql` (новый) | таблицы реестра |
| `src/siberman/persons/__init__.py` (новый) | пакет |
| `src/siberman/persons/linking.py` (новый) | ключи ФИ, `Person`/`Review`/`Applicant`, `Registry`, `link_participants`, `attach_birthdates` |
| `src/siberman/persons/applicants.py` (новый) | CSV Тильды → `Applicant` |
| `src/siberman/persons/db.py` (новый) | весь SQL реестра |
| `src/siberman/persons/service.py` (новый) | `sync`, `sync_safe`, импорт заявок, merge/reassign/ДР/статус/undo, карточка, поиск, «проверить», журнал |
| `src/siberman/persons/router.py` (новый) | `/admin/people`, `/api/siberman/admin/people/*` |
| `templates/siberman/people_admin.html` (новый) | страница админки |
| `static/js/siberman-people-admin.js` (новый) | логика страницы |
| `scripts/siberman_persons_init.py` (новый) | первичное заполнение + загрузка заявок из файлов |
| `src/siberman/service.py` (изм.) | хвост `recompute_totals_ranks_records` → `sync_safe()` |
| `src/siberman/finish_counts.py`, `src/siberman/db.py` (изм.) | финиши по человеку |
| `src/krasmarafon/router.py` (изм.) | подключить роутер |
| `templates/siberman/admin.html`, `templates/siberman/draw_admin.html` (изм.) | вкладка «Люди» |
| `tests/conftest.py` (изм.) | в тестах `sync_safe` — no-op |
| `.github/workflows/migrate_siberman.yml` (изм.) | строка миграции 014 |
| `tests/unit/test_siberman_persons_linking.py`, `tests/unit/test_siberman_persons_applicants.py`, `tests/integration/test_siberman_persons.py` (новые) | тесты |

---

### Task 0: Worktree

- [ ] **Step 1: Создать worktree от ветки жеребьёвки (в ней миграция 013)**

Из корня основного репозитория:
```bash
cd "/c/Users/podbo/Работа/КРАСМАРАФОН/KM_track"
git worktree add .worktrees/siberman-hall -b feature/siberman-hall feature/siberman-draw-2028
cp .env .env.local .worktrees/siberman-hall/
cd .worktrees/siberman-hall && git log --oneline -1
```
Expected: последний коммит ветки жеребьёвки (`df334e6 style(siberman/draw): …` или новее). Содержимое `.env*` не выводить.

- [ ] **Step 2: Базовый прогон тестов**

Run: `conda run -n base python -m pytest tests/unit/ -q`
Expected: все PASS (число запомнить для сравнения в Task 10).

---

### Task 1: Миграция 014

**Files:**
- Create: `src/siberman/migrations/014_persons.sql`
- Modify: `.github/workflows/migrate_siberman.yml`

- [ ] **Step 1: Написать миграцию**

```sql
-- Реестр людей Siberman: кто есть кто за все годы, с тёзками. Спецификация:
-- docs/superpowers/specs/2026-10-18-siberman-hall-ratings-records-design.md §3.
-- Привязка выступления к человеку — по естественному ключу (год, номер, этап), а не по
-- participants.id: загрузка Excel удаляет и заново вставляет участников года.
CREATE TABLE IF NOT EXISTS siberman_persons (
  id              INT AUTO_INCREMENT PRIMARY KEY,
  surname         VARCHAR(100) NOT NULL,
  name            VARCHAR(100) NOT NULL DEFAULT '',
  gender          ENUM('M','F') DEFAULT NULL,
  birthdate       DATE DEFAULT NULL,          -- только админка, публично не отдаётся
  bib_individual  VARCHAR(10) DEFAULT NULL,   -- личный номер закреплён за человеком навсегда
  city            VARCHAR(100) NOT NULL DEFAULT '',
  country         VARCHAR(100) NOT NULL DEFAULT '',
  created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uq_bib_individual (bib_individual)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- manual=1 — поставлено вручную в админке; синхронизация такие привязки не трогает
-- и не удаляет даже если строки участника временно нет (перезагрузка года).
CREATE TABLE IF NOT EXISTS siberman_person_links (
  race_year    SMALLINT NOT NULL,
  bib          VARCHAR(10) NOT NULL,
  relay_stage  ENUM('none','swim','bike','run') NOT NULL,
  person_id    INT NOT NULL,
  manual       TINYINT(1) NOT NULL DEFAULT 0,
  PRIMARY KEY (race_year, bib, relay_stage),
  KEY idx_person (person_id),
  CONSTRAINT fk_link_person FOREIGN KEY (person_id) REFERENCES siberman_persons(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Из заявок Тильды берём только это: ФИ, пол, ДР, город, номер заявки, дату подачи.
-- Эстафетчики — tranid с суффиксом этапа: '59855:123:swim'.
CREATE TABLE IF NOT EXISTS siberman_applicants (
  tranid        VARCHAR(64) PRIMARY KEY,
  surname       VARCHAR(100) NOT NULL,
  name          VARCHAR(100) NOT NULL DEFAULT '',
  gender        ENUM('M','F') DEFAULT NULL,
  birthdate     DATE NOT NULL,
  city          VARCHAR(100) NOT NULL DEFAULT '',
  submitted_at  DATETIME DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- «Проверить»: выступление (race_year/bib/relay_stage) или человек + кандидаты.
-- dedupe_key не даёт повторной синхронизации плодить одинаковые записи.
CREATE TABLE IF NOT EXISTS siberman_person_reviews (
  id                INT AUTO_INCREMENT PRIMARY KEY,
  kind              VARCHAR(32) NOT NULL,
  dedupe_key        VARCHAR(190) NOT NULL,
  race_year         SMALLINT DEFAULT NULL,
  bib               VARCHAR(10) DEFAULT NULL,
  relay_stage       VARCHAR(5) DEFAULT NULL,
  person_id         INT DEFAULT NULL,
  other_person_ids  VARCHAR(255) NOT NULL DEFAULT '',
  detail            VARCHAR(255) NOT NULL DEFAULT '',
  status            ENUM('open','resolved','deferred') NOT NULL DEFAULT 'open',
  created_at        DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  resolved_at       DATETIME DEFAULT NULL,
  resolved_by       VARCHAR(100) DEFAULT NULL,
  UNIQUE KEY uq_review (dedupe_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Журнал ручных действий: payload — снимок «до» (люди и привязки), scope — что затронуто
-- ('p:12,k:2024/7/none'); отмена восстанавливает снимок, если позже это не трогали.
CREATE TABLE IF NOT EXISTS siberman_person_audit (
  id          INT AUTO_INCREMENT PRIMARY KEY,
  action      VARCHAR(32) NOT NULL,
  summary     VARCHAR(255) NOT NULL,
  payload     JSON NOT NULL,
  scope       TEXT NOT NULL,
  created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  created_by  VARCHAR(100) NOT NULL DEFAULT '',
  undone_at   DATETIME DEFAULT NULL,
  undone_by   VARCHAR(100) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

- [ ] **Step 2: Применить локально**

Сначала создать в scratchpad сессии скрипт `apply_014.py` (не в репозитории):
```python
import os, sys
sys.path.insert(0, os.getcwd())
from dotenv import load_dotenv
load_dotenv('.env.local', override=True)
from src.siberman.db import get_siberman_connection
sql = open('src/siberman/migrations/014_persons.sql', encoding='utf-8').read()
conn = get_siberman_connection()
cur = conn.cursor()
for stmt in [s.strip() for s in sql.split(';') if s.strip() and not all(l.startswith('--') for l in s.strip().splitlines())]:
    cur.execute(stmt)
cur.execute("SHOW TABLES LIKE 'siberman_person%'")
print(sorted(r[0] for r in cur.fetchall()))
```
Run (из корня worktree): `conda run -n base python <путь-к-scratchpad>/apply_014.py`
Expected: `['siberman_person_audit', 'siberman_person_links', 'siberman_person_reviews', 'siberman_persons']`. Повторный запуск — без ошибок (`IF NOT EXISTS`).

- [ ] **Step 3: Строка в workflow**

В `.github/workflows/migrate_siberman.yml` после блока 013 добавить:
```yaml
            # Реестр людей (кто есть кто за все годы, ДР из заявок, «проверить», журнал)
            mysql -u root siberman < /opt/km_track/src/siberman/migrations/014_persons.sql
```

- [ ] **Step 4: Commit**

```bash
git add src/siberman/migrations/014_persons.sql .github/workflows/migrate_siberman.yml
git commit -m "feat(siberman/persons): миграция 014 — реестр людей, привязки, заявки, «проверить», журнал"
```

---

### Task 2: Чистая логика привязки (`linking.py`)

**Files:**
- Create: `src/siberman/persons/__init__.py` (пустой)
- Create: `src/siberman/persons/linking.py`
- Test: `tests/unit/test_siberman_persons_linking.py`

- [ ] **Step 1: Написать тесты**

```python
import datetime

from src.siberman.persons.linking import (
    Applicant, Person, Registry, attach_birthdates, link_participants, norm_city, plain_key,
)


def row(year, bib, surname, name, fmt="individual", stage="none", gender="M", city="Красноярск"):
    return {"race_year": year, "bib": str(bib), "relay_stage": stage, "surname": surname, "name": name,
            "gender": gender, "format": fmt, "city": city, "country": "Россия"}


def relay(year, bib, stage, surname, name, gender="M"):
    return row(year, bib, surname, name, fmt="relay", stage=stage, gender=gender)


def run(rows, persons=(), links=None):
    reg = Registry(list(persons))
    new_links, reviews = link_participants(reg, rows, links or {})
    return reg, new_links, reviews


def key(r):
    return (r["race_year"], r["bib"], r["relay_stage"])


def test_plain_key_and_city():
    assert plain_key("ПЕЧЁНКИНА ", " Екатерина") == "печенкина екатерина"
    assert plain_key("Князева (Заволокина)", "Олеся") == "князева заволокина олеся"
    assert norm_city("г. Красноярск") == norm_city("красноярск") == "красноярск"
    assert norm_city("Ростов-на-Дону") == "ростов на дону"


def test_individual_same_bib_is_one_person_even_if_name_changes():
    a, b = row(2020, 7, "Иванова", "Анна", gender="F"), row(2024, 7, "Петрова (Иванова)", "Анна", gender="F")
    reg, links, reviews = run([a, b])
    assert links[key(a)] is links[key(b)]
    assert links[key(a)].bib_individual == "7"
    assert [r.kind for r in reviews] == ["bib_name_change"]
    assert reviews[0].natkey == key(b)


def test_namesakes_with_different_individual_bibs_are_two_people_without_review():
    a, b = row(2020, 7, "Кузнецов", "Олег"), row(2021, 58, "Кузнецов", "Олег")
    reg, links, reviews = run([a, b])
    assert links[key(a)] is not links[key(b)]
    assert reviews == []


def test_relay_member_two_stages_same_year_is_one_person():
    a, b = relay(2022, 101, "swim", "Смирнов", "Илья"), relay(2022, 101, "bike", "Смирнов", "Илья")
    reg, links, reviews = run([a, b])
    assert links[key(a)] is links[key(b)]
    assert reviews == []


def test_relay_namesakes_in_different_teams_same_year_are_two_people():
    a, b = relay(2022, 101, "swim", "Смирнов", "Илья"), relay(2022, 102, "run", "Смирнов", "Илья")
    reg, links, reviews = run([a, b])
    assert links[key(a)] is not links[key(b)]
    assert reviews == []


def test_relay_then_individual_links_and_asks_to_check():
    a, b = relay(2020, 101, "run", "Петров", "Андрей"), row(2021, 7, "Петров", "Андрей")
    reg, links, reviews = run([a, b])
    assert links[key(a)] is links[key(b)]
    assert links[key(b)].bib_individual == "7"
    assert [r.kind for r in reviews] == ["format_switch"]


def test_two_candidates_make_new_person_and_review():
    rows = [row(2020, 7, "Кузнецов", "Олег"), row(2021, 58, "Кузнецов", "Олег"),
            relay(2022, 103, "bike", "Кузнецов", "Олег")]
    reg, links, reviews = run(rows)
    third = links[key(rows[2])]
    assert third not in (links[key(rows[0])], links[key(rows[1])])
    assert [r.kind for r in reviews] == ["namesake_candidate"]
    assert reviews[0].person is third and len(reviews[0].others) == 2


def test_gender_mismatch_is_not_the_same_person():
    a, b = relay(2020, 101, "swim", "Белых", "Саша", gender="F"), relay(2021, 105, "run", "Белых", "Саша", gender="M")
    reg, links, reviews = run([a, b])
    assert links[key(a)] is not links[key(b)]


def test_existing_links_are_kept_and_used():
    p = Person(id=5, surname="Орлова", name="Мария", gender="F", bib_individual="23")
    a, b = row(2023, 23, "Орлова", "Мария", gender="F"), row(2024, 23, "Орлова", "Мария", gender="F")
    reg, links, reviews = run([a, b], persons=[p], links={key(a): 5})
    assert list(links) == [key(b)] and links[key(b)] is reg.by_id[5]
    assert reg.new == [] and reviews == []


def test_second_run_links_nothing():
    rows = [row(2020, 7, "Кузнецов", "Олег"), row(2021, 58, "Кузнецов", "Олег"),
            relay(2022, 101, "swim", "Смирнов", "Илья"), relay(2022, 101, "bike", "Смирнов", "Илья")]
    reg, links, _ = run(rows)
    for i, p in enumerate(reg.new, start=100):
        p.id = i
    persons = [Person(id=p.id, surname=p.surname, name=p.name, gender=p.gender,
                      bib_individual=p.bib_individual) for p in reg.new]
    saved = {k: p.id for k, p in links.items()}
    reg2, links2, reviews2 = run(rows, persons=persons, links=saved)
    assert links2 == {} and reg2.new == [] and reviews2 == []


def app(tranid, surname, name, bd, gender=None, city=""):
    return Applicant(tranid=tranid, surname=surname, name=name, gender=gender, birthdate=bd, city=city)


def test_birthdate_attached_to_single_match():
    p = Person(id=1, surname="Иванов", name="Алексей", gender="M", city="Москва")
    reg = Registry([p])
    updates, reviews = attach_birthdates(reg, [app("t1", "Иванов", "Алексей", datetime.date(1985, 5, 30), "M", "Москва")])
    assert updates == [(p, datetime.date(1985, 5, 30))] and p.birthdate == datetime.date(1985, 5, 30)
    assert reviews == []


def test_swapped_surname_and_name_still_match():
    p = Person(id=1, surname="Herinckx", name="Wijnand", gender="M")
    updates, _ = attach_birthdates(Registry([p]), [app("t1", "Wijnand", "Herinckx", datetime.date(1984, 5, 12))])
    assert updates and p.birthdate == datetime.date(1984, 5, 12)


def test_other_birthdate_makes_conflict_review():
    p = Person(id=1, surname="Иванов", name="Алексей", gender="M", birthdate=datetime.date(1985, 5, 30))
    updates, reviews = attach_birthdates(Registry([p]), [app("t2", "Иванов", "Алексей", datetime.date(1986, 5, 30))])
    assert updates == [] and [r.kind for r in reviews] == ["bd_conflict"]
    assert reviews[0].person is p and reviews[0].detail == "t2"


def test_ambiguous_applicant_between_namesakes():
    a = Person(id=1, surname="Иванов", name="Никита", gender="M")
    b = Person(id=2, surname="Иванов", name="Никита", gender="M")
    updates, reviews = attach_birthdates(Registry([a, b]), [app("t3", "Иванов", "Никита", datetime.date(1994, 7, 12))])
    assert updates == [] and [r.kind for r in reviews] == ["applicant_ambiguous"]
    assert set(reviews[0].others) == {a, b}


def test_namesake_with_matching_birthdate_needs_nothing():
    a = Person(id=1, surname="Иванов", name="Никита", gender="M", birthdate=datetime.date(1994, 7, 12))
    b = Person(id=2, surname="Иванов", name="Никита", gender="M")
    updates, reviews = attach_birthdates(Registry([a, b]), [app("t3", "Иванов", "Никита", datetime.date(1994, 7, 12))])
    assert updates == [] and reviews == []


def test_city_mismatch_is_not_attached():
    p = Person(id=1, surname="Иванов", name="Никита", gender="M", city="Томск")
    updates, reviews = attach_birthdates(Registry([p]), [app("t4", "Иванов", "Никита", datetime.date(1989, 8, 21), city="Красноярск")])
    assert updates == [] and [r.kind for r in reviews] == ["applicant_city_mismatch"]


def test_review_dedupe_keys():
    a = row(2024, 7, "Петрова", "Анна", gender="F")
    reg, links, _ = run([row(2020, 7, "Иванова", "Анна", gender="F"), a])
    p = links[key(a)]
    p.id = 42
    from src.siberman.persons.linking import Review
    assert Review("bib_name_change", natkey=key(a), person=p).dedupe_key() == "bib_name_change:2024:7:none"
    assert Review("bd_conflict", person=p, detail="t9").dedupe_key() == "bd_conflict:42:t9"
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `conda run -n base python -m pytest tests/unit/test_siberman_persons_linking.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.siberman.persons'`.

- [ ] **Step 3: Реализация**

`src/siberman/persons/__init__.py` — пустой файл.

`src/siberman/persons/linking.py`:
```python
"""
Реестр людей Siberman — чистая логика привязки выступлений к людям (без БД).

Спецификация hall §3: личник узнаётся по личному стартовому номеру (закреплён за человеком
навсегда, тот же номер = тот же человек даже при смене фамилии); эстафетчик — по ФИ среди
людей того же пола без противоречий. Неоднозначность → новый человек + запись «проверить».
Даты рождения приходят из заявок Тильды (attach_birthdates).
"""
import datetime
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

NatKey = tuple  # (race_year: int, bib: str, relay_stage: str) — строка participants


def plain_key(surname: str, name: str) -> str:
    """'фамилия имя': нижний регистр, ё→е, скобки → пробел, без лишних пробелов. Без псевдонимов —
    смену фамилии личника ловит номер, остальное решает админ."""
    raw = f"{surname} {name}".lower().replace("ё", "е").replace("(", " ").replace(")", " ")
    return " ".join(raw.split())


def norm_city(city: str) -> str:
    t = (city or "").lower().replace("ё", "е").strip()
    for prefix in ("г.", "г ", "город "):
        if t.startswith(prefix):
            t = t[len(prefix):]
    return " ".join(t.replace("-", " ").split())


def natkey(row: dict) -> NatKey:
    return (int(row["race_year"]), str(row["bib"]), str(row["relay_stage"]))


@dataclass(eq=False)
class Person:
    id: int                      # > 0 — в БД, < 0 — создан этим прогоном
    surname: str
    name: str
    gender: Optional[str] = None
    birthdate: Optional[datetime.date] = None
    bib_individual: Optional[str] = None
    city: str = ""
    usage: dict = field(default_factory=dict)    # год -> {номера}
    formats: set = field(default_factory=set)    # {'individual', 'relay'}
    keys: set = field(default_factory=set)       # все ФИ, под которыми выступал
    last_year: int = 0


@dataclass(eq=False)
class Review:
    kind: str
    natkey: Optional[NatKey] = None
    person: Optional[Person] = None
    others: tuple = ()
    detail: str = ""

    def dedupe_key(self) -> str:
        if self.natkey:
            y, b, s = self.natkey
            return f"{self.kind}:{y}:{b}:{s}"
        return f"{self.kind}:{self.person.id if self.person else ''}:{self.detail}"[:190]


@dataclass
class Applicant:
    tranid: str
    surname: str
    name: str
    gender: Optional[str]
    birthdate: datetime.date
    city: str = ""
    submitted_at: Optional[datetime.datetime] = None


def _gender_ok(a: Optional[str], b: Optional[str]) -> bool:
    return a is None or b is None or a == b


class Registry:
    """Люди в памяти + индексы по личному номеру и ФИ."""

    def __init__(self, persons: list):
        self.by_id = {p.id: p for p in persons}
        self.by_bib = {p.bib_individual: p for p in persons if p.bib_individual}
        self.by_key = defaultdict(list)
        for p in persons:
            self._index_key(p, plain_key(p.surname, p.name))
        self.new: list = []
        self.bib_assigned: list = []   # люди из БД, которым этот прогон записал личный номер
        self._next_tmp = -1

    def _index_key(self, p: Person, key: str) -> None:
        p.keys.add(key)
        if p not in self.by_key[key]:
            self.by_key[key].append(p)

    def add(self, surname: str, name: str, gender: Optional[str]) -> Person:
        p = Person(id=self._next_tmp, surname=surname, name=name, gender=gender)
        self._next_tmp -= 1
        self.by_id[p.id] = p
        self.new.append(p)
        self._index_key(p, plain_key(surname, name))
        return p

    def attach(self, p: Person, row: dict) -> None:
        """Учесть выступление row за человеком p."""
        year, bib = int(row["race_year"]), str(row["bib"])
        self._index_key(p, plain_key(row["surname"], row["name"]))
        p.usage.setdefault(year, set()).add(bib)
        p.formats.add(row["format"])
        if p.gender is None and row.get("gender") in ("M", "F"):
            p.gender = row["gender"]
        if year >= p.last_year:
            p.last_year = year
            p.city = row.get("city") or p.city
        if row["format"] == "individual" and not p.bib_individual and bib not in self.by_bib:
            p.bib_individual = bib
            self.by_bib[bib] = p
            if p.id > 0:
                self.bib_assigned.append(p)


def _resolve(reg: Registry, r: dict) -> tuple:
    """Человек для непривязанного выступления r и записи «проверить»."""
    year, bib, nk = int(r["race_year"]), str(r["bib"]), natkey(r)
    g = r.get("gender") if r.get("gender") in ("M", "F") else None
    key = plain_key(r["surname"], r["name"])
    if r["format"] == "individual":
        p = reg.by_bib.get(bib)
        if p is not None:
            return p, ([] if key in p.keys else [Review("bib_name_change", natkey=nk, person=p)])
    cands = []
    for p in reg.by_key.get(key, []):
        if not _gender_ok(g, p.gender):
            continue
        used = p.usage.get(year)
        if used and bib not in used:          # в этом году уже выступал под другим номером
            continue
        if r["format"] == "individual" and p.bib_individual and p.bib_individual != bib:
            continue                          # у человека свой личный номер — это тёзка
        cands.append(p)
    if len(cands) == 1:
        p = cands[0]
        switch = bool(p.formats) and r["format"] not in p.formats
        return p, ([Review("format_switch", natkey=nk, person=p)] if switch else [])
    p = reg.add(r["surname"], r["name"], g)
    return p, ([Review("namesake_candidate", natkey=nk, person=p, others=tuple(cands))] if cands else [])


def link_participants(reg: Registry, rows: list, links: dict) -> tuple:
    """rows — все строки participants; links — сохранённые привязки {natkey: person_id}.
    → ({natkey: Person} новых привязок, [Review]). Уже привязанные строки только наполняют индексы."""
    rows = sorted(rows, key=lambda r: (int(r["race_year"]), r["format"] != "individual",
                                       str(r["bib"]), str(r["relay_stage"])))
    for r in rows:
        pid = links.get(natkey(r))
        if pid in reg.by_id:
            reg.attach(reg.by_id[pid], r)
    new_links, reviews = {}, []
    for r in rows:
        k = natkey(r)
        if links.get(k) in reg.by_id:
            continue
        p, rv = _resolve(reg, r)
        reg.attach(p, r)
        new_links[k] = p
        reviews.extend(rv)
    return new_links, reviews


def _applicant_candidates(reg: Registry, a: Applicant) -> list:
    for key in (plain_key(a.surname, a.name), plain_key(a.name, a.surname)):
        c = [p for p in reg.by_key.get(key, []) if _gender_ok(a.gender, p.gender)]
        if c:
            return c
    return []


def attach_birthdates(reg: Registry, applicants: list) -> tuple:
    """ДР из заявок → ([(Person, дата)] новые ДР, [Review]). Заявка не ставит ДР, если ФИ подходит
    нескольким людям, у человека уже другая ДР или город заявки другой — тогда «проверить»."""
    updates, reviews = [], []
    for a in sorted(applicants, key=lambda x: x.tranid):
        cands = _applicant_candidates(reg, a)
        if not cands:
            continue
        if len(cands) > 1:
            if sum(1 for c in cands if c.birthdate == a.birthdate) != 1:
                reviews.append(Review("applicant_ambiguous", others=tuple(cands), detail=a.tranid))
            continue
        c = cands[0]
        if c.birthdate == a.birthdate:
            continue
        if c.birthdate is not None:
            reviews.append(Review("bd_conflict", person=c, detail=a.tranid))
            continue
        if a.city and c.city and norm_city(a.city) != norm_city(c.city):
            reviews.append(Review("applicant_city_mismatch", person=c, detail=a.tranid))
            continue
        c.birthdate = a.birthdate
        updates.append((c, a.birthdate))
    return updates, reviews
```

- [ ] **Step 4: Тесты проходят**

Run: `conda run -n base python -m pytest tests/unit/test_siberman_persons_linking.py -q`
Expected: 17 passed.

- [ ] **Step 5: Commit**

```bash
git add src/siberman/persons/__init__.py src/siberman/persons/linking.py tests/unit/test_siberman_persons_linking.py
git commit -m "feat(siberman/persons): привязка выступлений к людям — номер личника, тёзки, ДР из заявок"
```

---

### Task 3: Разбор заявок Тильды (`applicants.py`)

**Files:**
- Create: `src/siberman/persons/applicants.py`
- Test: `tests/unit/test_siberman_persons_applicants.py`

- [ ] **Step 1: Тесты**

```python
import datetime

import pytest

from src.siberman.persons.applicants import parse_applicants_csv, parse_birthdate

COLS = ("Email;Name;Phone;Date;city;format;tranid;formid;sex;surname;birthday;"
        "surname_swim;name_swim;birthday_swim;surname_bike;name_bike;birthday_bike;"
        "surname_run;name_run;birthday_run").split(";")
TODAY = datetime.date(2026, 10, 18)


def line(**kw):
    return ";".join(kw.get(c, "") for c in COLS)


def csv_bytes(*lines):
    return (chr(0xFEFF) + ";".join(COLS) + "\n" + "\n".join(lines)).encode("utf-8")


def test_individual_with_birthdate():
    apps, stats = parse_applicants_csv(csv_bytes(line(
        Email="a@x", Name="Анна", Date="2025-10-28 08:06:01", city="Красноярск", tranid="1:2",
        sex="Женский", surname="Тестова", birthday="20.01.1978")), today=TODAY)
    assert len(apps) == 1
    a = apps[0]
    assert (a.tranid, a.surname, a.name, a.gender, a.birthdate, a.city) == (
        "1:2", "Тестова", "Анна", "F", datetime.date(1978, 1, 20), "Красноярск")
    assert a.submitted_at == datetime.datetime(2025, 10, 28, 8, 6, 1)
    assert stats == {"rows": 1, "people": 1, "no_birthday": 0, "bad_birthday": 0}


def test_old_form_without_surname_is_skipped():
    apps, stats = parse_applicants_csv(csv_bytes(line(Name="Иван Тестов", Date="2023-11-24 00:01:40", tranid="1:1")),
                                       today=TODAY)
    assert apps == [] and stats["rows"] == 1 and stats["people"] == 0


def test_relay_members_get_own_records():
    apps, _ = parse_applicants_csv(csv_bytes(line(
        Name="Ирина", tranid="1:3", surname="Тестова", birthday="20.01.1978",
        surname_swim="Пловцова", name_swim="Элина", birthday_swim="01.02.2005",
        surname_bike="Велосипедов", name_bike="Андрей", birthday_bike="20-04-1977",
        surname_run="Бегунова", name_run="Ирина", birthday_run="")), today=TODAY)
    by_id = {a.tranid: a for a in apps}
    assert set(by_id) == {"1:3", "1:3:swim", "1:3:bike"}
    assert by_id["1:3:bike"].birthdate == datetime.date(1977, 4, 20)
    assert by_id["1:3:swim"].gender is None


def test_bad_and_too_young_dates_are_counted():
    apps, stats = parse_applicants_csv(csv_bytes(
        line(tranid="1:4", surname="Тестов", Name="А", birthday="31.02.1990"),
        line(tranid="1:5", surname="Тестов", Name="Б", birthday="09.01.2025"),
        line(tranid="1:6", surname="Тестов", Name="В", birthday="")), today=TODAY)
    assert apps == []
    assert stats["bad_birthday"] == 2 and stats["no_birthday"] == 1


def test_same_tranid_twice_keeps_last():
    apps, _ = parse_applicants_csv(csv_bytes(
        line(tranid="1:7", surname="Тестов", Name="Иван", birthday="01.01.1980"),
        line(tranid="1:7", surname="Тестов", Name="Иван", birthday="02.01.1980")), today=TODAY)
    assert len(apps) == 1 and apps[0].birthdate == datetime.date(1980, 1, 2)


def test_not_a_tilda_export():
    with pytest.raises(ValueError):
        parse_applicants_csv(b"a;b\n1;2", today=TODAY)


def test_parse_birthdate_formats():
    assert parse_birthdate("01.05.1981", TODAY) == datetime.date(1981, 5, 1)
    assert parse_birthdate("01-05-1981", TODAY) == datetime.date(1981, 5, 1)
    assert parse_birthdate("1981-05-01", TODAY) is None
    assert parse_birthdate("01.05.1920", TODAY) is None
```

- [ ] **Step 2: Тесты падают**

Run: `conda run -n base python -m pytest tests/unit/test_siberman_persons_applicants.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.siberman.persons.applicants'`.

- [ ] **Step 3: Реализация**

`src/siberman/persons/applicants.py`:
```python
"""
Выгрузка заявок Тильды (CSV: «;», UTF-8 с BOM) → даты рождения для реестра людей.

Берём только ФИ, пол, ДР, город, номер заявки (tranid) и дату подачи — телефоны, e-mail и
тексты заявок не читаем. ДР в форме есть с 15.10.2024 (форма 807405240 и следующие); у
эстафеты — у каждого этапника (surname_swim/name_swim/birthday_swim и т.д.). Старые формы
без колонки surname (ФИ одной строкой в Name, ДР нет) пропускаются.
"""
import csv
import datetime
import io
from typing import Optional

from src.siberman.persons.linking import Applicant

STAGES = ("swim", "bike", "run")
MIN_YEAR = 1930
MIN_AGE = 14


def _clean(v) -> str:
    return " ".join(str(v or "").split())


def parse_birthdate(raw: str, today: datetime.date) -> Optional[datetime.date]:
    """'дд.мм.гггг' или 'дд-мм-гггг'; невозможная дата, раньше 1930 или моложе 14 лет → None."""
    parts = _clean(raw).replace("-", ".").replace("/", ".").split(".")
    if len(parts) != 3 or not all(p.isdigit() for p in parts) or len(parts[2]) != 4:
        return None
    try:
        d = datetime.date(int(parts[2]), int(parts[1]), int(parts[0]))
    except ValueError:
        return None
    if d.year < MIN_YEAR or d.year > today.year - MIN_AGE:
        return None
    return d


def _parse_dt(raw) -> Optional[datetime.datetime]:
    try:
        return datetime.datetime.strptime(_clean(raw), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def parse_applicants_csv(data: bytes, today: Optional[datetime.date] = None) -> tuple:
    """→ ([Applicant], {'rows', 'people', 'no_birthday', 'bad_birthday'}). ValueError — не выгрузка Тильды."""
    today = today or datetime.date.today()
    text = data.decode("utf-8", errors="replace").lstrip(chr(0xFEFF))
    reader = csv.DictReader(io.StringIO(text), delimiter=";")
    if not reader.fieldnames or "tranid" not in reader.fieldnames:
        raise ValueError("Это не выгрузка заявок Тильды: нет колонки tranid")
    found: dict = {}
    stats = {"rows": 0, "people": 0, "no_birthday": 0, "bad_birthday": 0}
    for row in reader:
        stats["rows"] += 1
        tranid = _clean(row.get("tranid"))
        if not tranid:
            continue
        submitted = _parse_dt(row.get("Date"))
        gender = {"Мужской": "M", "Женский": "F"}.get(_clean(row.get("sex")))
        city = _clean(row.get("city") or row.get("city_2"))
        people = [(tranid, row.get("surname"), row.get("Name"), row.get("birthday"), gender, city)]
        for st in STAGES:
            people.append((f"{tranid}:{st}", row.get(f"surname_{st}"), row.get(f"name_{st}"),
                           row.get(f"birthday_{st}"), None, ""))
        for tid, surname, name, bd_raw, g, c in people:
            surname, name = _clean(surname), _clean(name)
            if not surname:
                continue
            bd = parse_birthdate(bd_raw, today)
            if bd is None:
                stats["bad_birthday" if _clean(bd_raw) else "no_birthday"] += 1
                continue
            found[tid] = Applicant(tranid=tid, surname=surname, name=name, gender=g, birthdate=bd,
                                   city=c, submitted_at=submitted)
    stats["people"] = len(found)
    return list(found.values()), stats
```

- [ ] **Step 4: Тесты проходят**

Run: `conda run -n base python -m pytest tests/unit/test_siberman_persons_applicants.py -q`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add src/siberman/persons/applicants.py tests/unit/test_siberman_persons_applicants.py
git commit -m "feat(siberman/persons): разбор выгрузки заявок Тильды — ФИ, пол, ДР, город"
```

---

### Task 3a: Исправления по ревью задач 1–3 (до SQL и сервиса)

Ревью нашло дефекты плана в логике определения людей. Закрываем до Task 4 — иначе пришлось бы менять уже готовую схему.

1. **Замена этапника при перезагрузке года** (Critical). Привязка по (год, номер, этап) переживала смену ФИ в строке: новый этапник молча оставался за прежним человеком, а его ФИ попадало в ключи прежнего. Теперь привязка хранит `name_key` (ФИ на момент привязки); автопривязка с другим ФИ разрешается заново. Ручные (`manual=1`) — не трогаются.
2. **ДР тёзке, который не подавал заявку** (Important). Заявка ставит ДР автоматически, только если заявитель сам указал старты на Siberman (`siberman_individual_starts`, `…_2`, `siberman_relay_starts` > 0); иначе — «проверить» (`applicant_unconfirmed`, одна кнопка «это он»). У этапников эстафеты стартов в заявке нет — всегда «проверить».
3. **Тихое раздвоение по полу** — запись `gender_mismatch`, если тёзки по ФИ отсеяны только полом (парсер Excel ставит `M` при пустом поле пола).
4. **Личный номер у другого пола** — запись `bib_gender_mismatch` вместо `bib_name_change` (почти наверняка другой человек).
5. **Строки без фамилии** не привязываются.
6. Мелочи: `;` в комментариях миграции (ломает построчные сплиттеры); FK `siberman_person_reviews.person_id → ON DELETE SET NULL`; номера сортируются как числа; заявки — по дате подачи; CSV в cp1251 (пересохранён Excel) читается, а не превращается в мусор; в эстафетной заявке основной заявитель не берётся (он либо этапник — дубль, либо не участник).

**Files:**
- Modify: `src/siberman/migrations/014_persons.sql` (полная замена)
- Modify: `src/siberman/persons/linking.py` (полная замена)
- Modify: `src/siberman/persons/applicants.py` (полная замена)
- Modify: `tests/unit/test_siberman_persons_linking.py`, `tests/unit/test_siberman_persons_applicants.py` (полная замена)

- [ ] **Step 1: Миграция (полная замена файла)**

```sql
-- Реестр людей Siberman: кто есть кто за все годы, с тёзками. Спецификация:
-- docs/superpowers/specs/2026-10-18-siberman-hall-ratings-records-design.md §3.
-- Привязка выступления к человеку — по естественному ключу (год, номер, этап), а не по
-- participants.id: загрузка Excel удаляет и заново вставляет участников года.
CREATE TABLE IF NOT EXISTS siberman_persons (
  id              INT AUTO_INCREMENT PRIMARY KEY,
  surname         VARCHAR(100) NOT NULL,
  name            VARCHAR(100) NOT NULL DEFAULT '',
  gender          ENUM('M','F') DEFAULT NULL,
  birthdate       DATE DEFAULT NULL,          -- только админка, публично не отдаётся
  bib_individual  VARCHAR(10) DEFAULT NULL,   -- личный номер закреплён за человеком навсегда
  city            VARCHAR(100) NOT NULL DEFAULT '',
  country         VARCHAR(100) NOT NULL DEFAULT '',
  created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uq_bib_individual (bib_individual)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- manual=1 — поставлено вручную в админке: синхронизация такие привязки не трогает
-- и не удаляет, даже если строки участника временно нет (перезагрузка года).
-- name_key — ФИ строки на момент привязки: если в перезагруженном протоколе на этом
-- номере и этапе другое ФИ (замена этапника), автопривязка разрешается заново.
CREATE TABLE IF NOT EXISTS siberman_person_links (
  race_year    SMALLINT NOT NULL,
  bib          VARCHAR(10) NOT NULL,
  relay_stage  ENUM('none','swim','bike','run') NOT NULL,
  person_id    INT NOT NULL,
  manual       TINYINT(1) NOT NULL DEFAULT 0,
  name_key     VARCHAR(201) NOT NULL DEFAULT '',
  PRIMARY KEY (race_year, bib, relay_stage),
  KEY idx_person (person_id),
  CONSTRAINT fk_link_person FOREIGN KEY (person_id) REFERENCES siberman_persons(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Из заявок Тильды берём только это: ФИ, пол, ДР, город, номер заявки, дату подачи и
-- сколько стартов на Siberman заявитель указал сам (NULL у этапников эстафеты).
-- Эстафетчики — tranid с суффиксом этапа: '59855:123:swim'.
CREATE TABLE IF NOT EXISTS siberman_applicants (
  tranid          VARCHAR(64) PRIMARY KEY,
  surname         VARCHAR(100) NOT NULL,
  name            VARCHAR(100) NOT NULL DEFAULT '',
  gender          ENUM('M','F') DEFAULT NULL,
  birthdate       DATE NOT NULL,
  city            VARCHAR(100) NOT NULL DEFAULT '',
  submitted_at    DATETIME DEFAULT NULL,
  claimed_starts  SMALLINT DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- «Проверить»: выступление (race_year/bib/relay_stage) или человек + кандидаты.
-- dedupe_key не даёт повторной синхронизации плодить одинаковые записи.
CREATE TABLE IF NOT EXISTS siberman_person_reviews (
  id                INT AUTO_INCREMENT PRIMARY KEY,
  kind              VARCHAR(32) NOT NULL,
  dedupe_key        VARCHAR(190) NOT NULL,
  race_year         SMALLINT DEFAULT NULL,
  bib               VARCHAR(10) DEFAULT NULL,
  relay_stage       VARCHAR(5) DEFAULT NULL,
  person_id         INT DEFAULT NULL,
  other_person_ids  VARCHAR(255) NOT NULL DEFAULT '',
  detail            VARCHAR(255) NOT NULL DEFAULT '',
  status            ENUM('open','resolved','deferred') NOT NULL DEFAULT 'open',
  created_at        DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  resolved_at       DATETIME DEFAULT NULL,
  resolved_by       VARCHAR(100) DEFAULT NULL,
  UNIQUE KEY uq_review (dedupe_key),
  CONSTRAINT fk_review_person FOREIGN KEY (person_id) REFERENCES siberman_persons(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Журнал ручных действий: payload — снимок «до» (люди и привязки), scope — что затронуто
-- (вида 'p:12,k:2024/7/none'). Отмена восстанавливает снимок, если позже это не трогали.
CREATE TABLE IF NOT EXISTS siberman_person_audit (
  id          INT AUTO_INCREMENT PRIMARY KEY,
  action      VARCHAR(32) NOT NULL,
  summary     VARCHAR(255) NOT NULL,
  payload     JSON NOT NULL,
  scope       TEXT NOT NULL,
  created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  created_by  VARCHAR(100) NOT NULL DEFAULT '',
  undone_at   DATETIME DEFAULT NULL,
  undone_by   VARCHAR(100) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

Пересоздать таблицы локально (данных в них ещё нет): в scratchpad-скрипте `apply_014.py` перед применением выполнить
`DROP TABLE IF EXISTS siberman_person_audit, siberman_person_reviews, siberman_person_links, siberman_applicants, siberman_persons`, затем применить файл. Проверка: `SHOW CREATE TABLE siberman_person_links` содержит `name_key`, `siberman_applicants` — `claimed_starts`, `siberman_person_reviews` — `fk_review_person`. В файле миграции не должно остаться `;` внутри комментариев: `grep -n "^--.*;" src/siberman/migrations/014_persons.sql` — пусто.

- [ ] **Step 2: Тесты `linking` (полная замена файла)**

```python
import datetime

from src.siberman.persons.linking import (
    Applicant, Person, Registry, Review, attach_birthdates, link_participants, norm_city, plain_key,
)


def row(year, bib, surname, name, fmt="individual", stage="none", gender="M", city="Красноярск"):
    return {"race_year": year, "bib": str(bib), "relay_stage": stage, "surname": surname, "name": name,
            "gender": gender, "format": fmt, "city": city, "country": "Россия"}


def relay(year, bib, stage, surname, name, gender="M"):
    return row(year, bib, surname, name, fmt="relay", stage=stage, gender=gender)


def key(r):
    return (r["race_year"], r["bib"], r["relay_stage"])


def saved(rows, new_links, manual=0):
    """Как сохранит service: {natkey: (person_id, manual, name_key)}."""
    names = {key(r): plain_key(r["surname"], r["name"]) for r in rows}
    return {k: (p.id, manual, names[k]) for k, p in new_links.items()}


def run(rows, persons=(), links=None):
    reg = Registry(list(persons))
    new_links, reviews = link_participants(reg, rows, links or {})
    return reg, new_links, reviews


def fresh(persons):
    return [Person(id=p.id, surname=p.surname, name=p.name, gender=p.gender, bib_individual=p.bib_individual)
            for p in persons]


def test_plain_key_and_city():
    assert plain_key("ПЕЧЁНКИНА ", " Екатерина") == "печенкина екатерина"
    assert plain_key("Князева (Заволокина)", "Олеся") == "князева заволокина олеся"
    assert norm_city("г. Красноярск") == norm_city("красноярск") == norm_city("Город Красноярск") == "красноярск"
    assert norm_city("Ростов-на-Дону") == "ростов на дону"


def test_individual_same_bib_is_one_person_even_if_name_changes():
    a, b = row(2020, 7, "Иванова", "Анна", gender="F"), row(2024, 7, "Петрова (Иванова)", "Анна", gender="F")
    reg, links, reviews = run([a, b])
    assert links[key(a)] is links[key(b)]
    assert links[key(a)].bib_individual == "7"
    assert [r.kind for r in reviews] == ["bib_name_change"]
    assert reviews[0].natkey == key(b)


def test_same_bib_other_gender_is_flagged_separately():
    a, b = row(2020, 7, "Иванов", "Саша", gender="M"), row(2024, 7, "Иванова", "Саша", gender="F")
    reg, links, reviews = run([a, b])
    assert links[key(a)] is links[key(b)]
    assert [r.kind for r in reviews] == ["bib_gender_mismatch"]


def test_namesakes_with_different_individual_bibs_are_two_people_without_review():
    a, b = row(2020, 7, "Кузнецов", "Олег"), row(2021, 58, "Кузнецов", "Олег")
    reg, links, reviews = run([a, b])
    assert links[key(a)] is not links[key(b)]
    assert reviews == []


def test_relay_member_two_stages_same_year_is_one_person():
    a, b = relay(2022, 101, "swim", "Смирнов", "Илья"), relay(2022, 101, "bike", "Смирнов", "Илья")
    reg, links, reviews = run([a, b])
    assert links[key(a)] is links[key(b)]
    assert reviews == []


def test_relay_namesakes_in_different_teams_same_year_are_two_people():
    a, b = relay(2022, 101, "swim", "Смирнов", "Илья"), relay(2022, 102, "run", "Смирнов", "Илья")
    reg, links, reviews = run([a, b])
    assert links[key(a)] is not links[key(b)]
    assert reviews == []


def test_individual_and_relay_namesakes_same_year_are_two_people():
    a, b = row(2022, 7, "Смирнов", "Илья"), relay(2022, 101, "run", "Смирнов", "Илья")
    reg, links, reviews = run([a, b])
    assert links[key(a)] is not links[key(b)]


def test_relay_then_individual_links_and_asks_to_check():
    a, b = relay(2020, 101, "run", "Петров", "Андрей"), row(2021, 7, "Петров", "Андрей")
    reg, links, reviews = run([a, b])
    assert links[key(a)] is links[key(b)]
    assert links[key(b)].bib_individual == "7"
    assert [r.kind for r in reviews] == ["format_switch"]


def test_individual_then_relay_links_and_asks_to_check():
    a, b = row(2020, 7, "Петров", "Андрей"), relay(2021, 101, "run", "Петров", "Андрей")
    reg, links, reviews = run([a, b])
    assert links[key(a)] is links[key(b)]
    assert [r.kind for r in reviews] == ["format_switch"]


def test_two_candidates_make_new_person_and_review():
    rows = [row(2020, 7, "Кузнецов", "Олег"), row(2021, 58, "Кузнецов", "Олег"),
            relay(2022, 103, "bike", "Кузнецов", "Олег")]
    reg, links, reviews = run(rows)
    third = links[key(rows[2])]
    assert third not in (links[key(rows[0])], links[key(rows[1])])
    assert [r.kind for r in reviews] == ["namesake_candidate"]
    assert reviews[0].person is third and len(reviews[0].others) == 2


def test_gender_mismatch_is_not_merged_but_flagged():
    a, b = relay(2020, 101, "swim", "Белых", "Саша", gender="F"), relay(2021, 105, "run", "Белых", "Саша", gender="M")
    reg, links, reviews = run([a, b])
    assert links[key(a)] is not links[key(b)]
    assert [r.kind for r in reviews] == ["gender_mismatch"]
    assert reviews[0].others == (links[key(a)],)


def test_rows_without_surname_are_not_linked():
    a, b = relay(2020, 101, "swim", "", ""), relay(2021, 105, "swim", " ", "")
    reg, links, reviews = run([a, b])
    assert links == {} and reg.new == []


def test_existing_links_are_kept_and_used():
    p = Person(id=5, surname="Орлова", name="Мария", gender="F", bib_individual="23")
    a, b = row(2023, 23, "Орлова", "Мария", gender="F"), row(2024, 23, "Орлова", "Мария", gender="F")
    reg, links, reviews = run([a, b], persons=[p], links={key(a): (5, 0, "орлова мария")})
    assert list(links) == [key(b)] and links[key(b)] is reg.by_id[5]
    assert reg.new == [] and reviews == []


def test_second_run_links_nothing():
    rows = [row(2020, 7, "Кузнецов", "Олег"), row(2021, 58, "Кузнецов", "Олег"),
            relay(2022, 101, "swim", "Смирнов", "Илья"), relay(2022, 101, "bike", "Смирнов", "Илья")]
    reg, links, _ = run(rows)
    for i, p in enumerate(reg.new, start=100):
        p.id = i
    reg2, links2, reviews2 = run(rows, persons=fresh(reg.new), links=saved(rows, links))
    assert links2 == {} and reg2.new == [] and reviews2 == []


def test_relay_member_replaced_on_reload_is_resolved_again():
    """Перезагрузка года: на номере 101 этап плавания теперь у другого человека. Прежняя
    автопривязка не должна молча отдать его выступление и его ФИ прежнему человеку."""
    old = [relay(2020, 101, "swim", "Иванов", "Иван")]
    reg, links, _ = run(old)
    links[key(old[0])].id = 1
    store = saved(old, links)
    new = [relay(2020, 101, "swim", "Петров", "Пётр"), relay(2021, 107, "swim", "Петров", "Пётр")]
    reg2, links2, _ = run(new, persons=fresh(reg.new), links=store)
    assert links2[key(new[0])] is not reg2.by_id[1]
    assert links2[key(new[0])] is links2[key(new[1])]
    assert "петров петр" not in reg2.by_id[1].keys


def test_manual_link_survives_name_change():
    p = Person(id=5, surname="Иванов", name="Иван", gender="M")
    r = relay(2020, 101, "swim", "Петров", "Пётр")
    reg, links, reviews = run([r], persons=[p], links={key(r): (5, 1, "иванов иван")})
    assert links == {} and reviews == []


def app(tranid, surname, name, bd, gender=None, city="", starts=1, submitted=None):
    return Applicant(tranid=tranid, surname=surname, name=name, gender=gender, birthdate=bd, city=city,
                     submitted_at=submitted, claimed_starts=starts)


def test_birthdate_attached_to_single_match_with_claimed_starts():
    p = Person(id=1, surname="Иванов", name="Алексей", gender="M", city="Москва")
    reg = Registry([p])
    updates, reviews = attach_birthdates(reg, [app("t1", "Иванов", "Алексей", datetime.date(1985, 5, 30), "M", "Москва")])
    assert updates == [(p, datetime.date(1985, 5, 30))] and p.birthdate == datetime.date(1985, 5, 30)
    assert reviews == []


def test_applicant_without_claimed_starts_is_only_suggested():
    p = Person(id=1, surname="Иванов", name="Алексей", gender="M")
    for starts in (0, None):
        updates, reviews = attach_birthdates(Registry([p]), [app("t1", "Иванов", "Алексей", datetime.date(1985, 5, 30),
                                                                 starts=starts)])
        assert updates == [] and [r.kind for r in reviews] == ["applicant_unconfirmed"]
        assert p.birthdate is None


def test_swapped_surname_and_name_still_match():
    p = Person(id=1, surname="Herinckx", name="Wijnand", gender="M")
    updates, _ = attach_birthdates(Registry([p]), [app("t1", "Wijnand", "Herinckx", datetime.date(1984, 5, 12))])
    assert updates and p.birthdate == datetime.date(1984, 5, 12)


def test_other_birthdate_makes_conflict_review():
    p = Person(id=1, surname="Иванов", name="Алексей", gender="M", birthdate=datetime.date(1985, 5, 30))
    updates, reviews = attach_birthdates(Registry([p]), [app("t2", "Иванов", "Алексей", datetime.date(1986, 5, 30))])
    assert updates == [] and [r.kind for r in reviews] == ["bd_conflict"]
    assert reviews[0].person is p and reviews[0].detail == "t2"


def test_ambiguous_applicant_between_namesakes():
    a = Person(id=1, surname="Иванов", name="Никита", gender="M")
    b = Person(id=2, surname="Иванов", name="Никита", gender="M")
    updates, reviews = attach_birthdates(Registry([a, b]), [app("t3", "Иванов", "Никита", datetime.date(1994, 7, 12))])
    assert updates == [] and [r.kind for r in reviews] == ["applicant_ambiguous"]
    assert set(reviews[0].others) == {a, b}


def test_namesake_with_matching_birthdate_needs_nothing():
    a = Person(id=1, surname="Иванов", name="Никита", gender="M", birthdate=datetime.date(1994, 7, 12))
    b = Person(id=2, surname="Иванов", name="Никита", gender="M")
    updates, reviews = attach_birthdates(Registry([a, b]), [app("t3", "Иванов", "Никита", datetime.date(1994, 7, 12))])
    assert updates == [] and reviews == []


def test_city_mismatch_is_not_attached():
    p = Person(id=1, surname="Иванов", name="Никита", gender="M", city="Томск")
    updates, reviews = attach_birthdates(Registry([p]), [app("t4", "Иванов", "Никита", datetime.date(1989, 8, 21),
                                                             city="Красноярск")])
    assert updates == [] and [r.kind for r in reviews] == ["applicant_city_mismatch"]


def test_earliest_application_wins():
    p = Person(id=1, surname="Иванов", name="Алексей", gender="M")
    early = app("9:1", "Иванов", "Алексей", datetime.date(1985, 5, 30), submitted=datetime.datetime(2024, 10, 20))
    late = app("10:1", "Иванов", "Алексей", datetime.date(1985, 5, 31), submitted=datetime.datetime(2025, 8, 1))
    updates, reviews = attach_birthdates(Registry([p]), [late, early])
    assert p.birthdate == datetime.date(1985, 5, 30)
    assert [(r.kind, r.detail) for r in reviews] == [("bd_conflict", "10:1")]


def test_review_dedupe_keys():
    a = row(2024, 7, "Петрова", "Анна", gender="F")
    reg, links, _ = run([row(2020, 7, "Иванова", "Анна", gender="F"), a])
    p = links[key(a)]
    p.id = 42
    assert Review("bib_name_change", natkey=key(a), person=p).dedupe_key() == "bib_name_change:2024:7:none"
    assert Review("bd_conflict", person=p, detail="t9").dedupe_key() == "bd_conflict:42:t9"
```

- [ ] **Step 3: `linking.py` (полная замена файла)**

```python
"""
Реестр людей Siberman — чистая логика привязки выступлений к людям (без БД).

Спецификация hall §3: личник узнаётся по личному стартовому номеру (закреплён за человеком
навсегда, тот же номер = тот же человек даже при смене фамилии); эстафетчик — по ФИ среди
людей того же пола без противоречий. Неоднозначность → новый человек + запись «проверить».
Даты рождения приходят из заявок Тильды (attach_birthdates).
"""
import datetime
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

NatKey = tuple  # (race_year: int, bib: str, relay_stage: str) — строка participants


def plain_key(surname: str, name: str) -> str:
    """'фамилия имя': нижний регистр, ё→е, скобки → пробел, без лишних пробелов. Без псевдонимов —
    смену фамилии личника ловит номер, остальное решает админ."""
    raw = f"{surname or ''} {name or ''}".lower().replace("ё", "е").replace("(", " ").replace(")", " ")
    return " ".join(raw.split())


def norm_city(city: str) -> str:
    t = (city or "").lower().replace("ё", "е").strip()
    for prefix in ("город ", "г.", "г "):
        if t.startswith(prefix):
            t = t[len(prefix):]
    return " ".join(t.replace("-", " ").split())


def natkey(row: dict) -> NatKey:
    return (int(row["race_year"]), str(row["bib"]), str(row["relay_stage"]))


def _bib_order(bib: str) -> tuple:
    return (0, int(bib), "") if bib.isdigit() else (1, 0, bib)


def _row_order(row: dict) -> tuple:
    return (int(row["race_year"]), row["format"] != "individual", _bib_order(str(row["bib"])), str(row["relay_stage"]))


@dataclass(eq=False)
class Person:
    id: int                      # > 0 — в БД, < 0 — создан этим прогоном
    surname: str
    name: str
    gender: Optional[str] = None
    birthdate: Optional[datetime.date] = None
    bib_individual: Optional[str] = None
    city: str = ""
    usage: dict = field(default_factory=dict)    # год -> {номера}
    formats: set = field(default_factory=set)    # {'individual', 'relay'}
    keys: set = field(default_factory=set)       # все ФИ, под которыми выступал
    last_year: int = 0


@dataclass(eq=False)
class Review:
    kind: str
    natkey: Optional[NatKey] = None
    person: Optional[Person] = None
    others: tuple = ()
    detail: str = ""

    def dedupe_key(self) -> str:
        if self.natkey:
            y, b, s = self.natkey
            return f"{self.kind}:{y}:{b}:{s}"
        return f"{self.kind}:{self.person.id if self.person else ''}:{self.detail}"[:190]


@dataclass
class Applicant:
    tranid: str
    surname: str
    name: str
    gender: Optional[str]
    birthdate: datetime.date
    city: str = ""
    submitted_at: Optional[datetime.datetime] = None
    claimed_starts: Optional[int] = None   # сколько стартов на Siberman указал сам; None — этапник эстафеты


def _gender_ok(a: Optional[str], b: Optional[str]) -> bool:
    return a is None or b is None or a == b


class Registry:
    """Люди в памяти + индексы по личному номеру и ФИ."""

    def __init__(self, persons: list):
        self.by_id = {p.id: p for p in persons}
        self.by_bib = {p.bib_individual: p for p in persons if p.bib_individual}
        self.by_key = defaultdict(list)
        for p in persons:
            self._index_key(p, plain_key(p.surname, p.name))
        self.new: list = []
        self.bib_assigned: list = []   # люди из БД, которым этот прогон записал личный номер
        self._next_tmp = -1

    def _index_key(self, p: Person, key: str) -> None:
        p.keys.add(key)
        if p not in self.by_key[key]:
            self.by_key[key].append(p)

    def add(self, surname: str, name: str, gender: Optional[str]) -> Person:
        p = Person(id=self._next_tmp, surname=surname, name=name, gender=gender)
        self._next_tmp -= 1
        self.by_id[p.id] = p
        self.new.append(p)
        self._index_key(p, plain_key(surname, name))
        return p

    def attach(self, p: Person, row: dict) -> None:
        """Учесть выступление row за человеком p."""
        year, bib = int(row["race_year"]), str(row["bib"])
        self._index_key(p, plain_key(row["surname"], row["name"]))
        p.usage.setdefault(year, set()).add(bib)
        p.formats.add(row["format"])
        if p.gender is None and row.get("gender") in ("M", "F"):
            p.gender = row["gender"]
        if year >= p.last_year:
            p.last_year = year
            p.city = row.get("city") or p.city
        if row["format"] == "individual" and not p.bib_individual and bib not in self.by_bib:
            p.bib_individual = bib
            self.by_bib[bib] = p
            if p.id > 0:
                self.bib_assigned.append(p)


def _resolve(reg: Registry, r: dict) -> tuple:
    """Человек для непривязанного выступления r и записи «проверить»."""
    year, bib, nk = int(r["race_year"]), str(r["bib"]), natkey(r)
    g = r.get("gender") if r.get("gender") in ("M", "F") else None
    key = plain_key(r["surname"], r["name"])
    if r["format"] == "individual":
        p = reg.by_bib.get(bib)
        if p is not None:
            if g and p.gender and g != p.gender:
                return p, [Review("bib_gender_mismatch", natkey=nk, person=p)]
            return p, ([] if key in p.keys else [Review("bib_name_change", natkey=nk, person=p)])
    cands, other_gender = [], []
    for p in reg.by_key.get(key, []):
        if not _gender_ok(g, p.gender):
            other_gender.append(p)
            continue
        used = p.usage.get(year)
        if used and bib not in used:          # в этом году уже выступал под другим номером
            continue
        if r["format"] == "individual" and p.bib_individual and p.bib_individual != bib:
            continue                          # у человека свой личный номер — это тёзка
        cands.append(p)
    if len(cands) == 1:
        p = cands[0]
        switch = bool(p.formats) and r["format"] not in p.formats
        return p, ([Review("format_switch", natkey=nk, person=p)] if switch else [])
    p = reg.add(r["surname"], r["name"], g)
    if cands:
        return p, [Review("namesake_candidate", natkey=nk, person=p, others=tuple(cands))]
    if other_gender:                          # тот же ФИ, другой пол (в Excel пусто → парсер ставит M)
        return p, [Review("gender_mismatch", natkey=nk, person=p, others=tuple(other_gender))]
    return p, []


def link_participants(reg: Registry, rows: list, links: dict) -> tuple:
    """rows — все строки participants; links — сохранённые привязки {natkey: (person_id, manual, name_key)}.
    Привязка действует, если она ручная или ФИ строки не изменилось с момента привязки; иначе
    (замена этапника, исправленный протокол) строка разрешается заново. Строки без фамилии
    не привязываются. → ({natkey: Person} новых и изменённых привязок, [Review])."""
    rows = sorted((r for r in rows if str(r["surname"] or "").strip()), key=_row_order)

    def kept_person(r):
        link = links.get(natkey(r))
        if not link or link[0] not in reg.by_id:
            return None
        person_id, manual, name_key = link
        return reg.by_id[person_id] if manual or name_key == plain_key(r["surname"], r["name"]) else None

    kept = set()
    for r in rows:
        p = kept_person(r)
        if p is not None:
            reg.attach(p, r)
            kept.add(natkey(r))
    new_links, reviews = {}, []
    for r in rows:
        k = natkey(r)
        if k in kept:
            continue
        p, rv = _resolve(reg, r)
        reg.attach(p, r)
        new_links[k] = p
        reviews.extend(rv)
    return new_links, reviews


def _applicant_candidates(reg: Registry, a: Applicant) -> list:
    for key in (plain_key(a.surname, a.name), plain_key(a.name, a.surname)):
        c = [p for p in reg.by_key.get(key, []) if _gender_ok(a.gender, p.gender)]
        if c:
            return c
    return []


def attach_birthdates(reg: Registry, applicants: list) -> tuple:
    """ДР из заявок → ([(Person, дата)] новые ДР, [Review]). Заявки — по дате подачи. ДР ставится
    автоматически, только если ФИ подходит одному человеку, у него нет другой ДР, город не
    противоречит и заявитель сам указал старты на Siberman; иначе — «проверить»."""
    updates, reviews = [], []
    order = sorted(applicants, key=lambda x: (x.submitted_at or datetime.datetime.min, x.tranid))
    for a in order:
        cands = _applicant_candidates(reg, a)
        if not cands:
            continue
        if len(cands) > 1:
            if sum(1 for c in cands if c.birthdate == a.birthdate) != 1:
                reviews.append(Review("applicant_ambiguous", others=tuple(cands), detail=a.tranid))
            continue
        c = cands[0]
        if c.birthdate == a.birthdate:
            continue
        if c.birthdate is not None:
            reviews.append(Review("bd_conflict", person=c, detail=a.tranid))
            continue
        if a.city and c.city and norm_city(a.city) != norm_city(c.city):
            reviews.append(Review("applicant_city_mismatch", person=c, detail=a.tranid))
            continue
        if not a.claimed_starts:              # не указал стартов на Siberman — может быть тёзкой
            reviews.append(Review("applicant_unconfirmed", person=c, detail=a.tranid))
            continue
        c.birthdate = a.birthdate
        updates.append((c, a.birthdate))
    return updates, reviews
```

- [ ] **Step 4: Тесты `applicants` (полная замена файла)**

```python
import datetime

import pytest

from src.siberman.persons.applicants import parse_applicants_csv, parse_birthdate

COLS = ("Email;Name;Phone;Date;city;format;tranid;formid;sex;surname;birthday;city_2;"
        "siberman_individual_starts;siberman_individual_starts_2;siberman_relay_starts;"
        "surname_swim;name_swim;birthday_swim;surname_bike;name_bike;birthday_bike;"
        "surname_run;name_run;birthday_run").split(";")
TODAY = datetime.date(2026, 10, 18)


def line(**kw):
    return ";".join(kw.get(c, "") for c in COLS)


def csv_bytes(*lines, encoding="utf-8", bom=True, sep="\n"):
    return ((chr(0xFEFF) if bom else "") + ";".join(COLS) + sep + sep.join(lines)).encode(encoding)


def test_individual_with_birthdate_and_claimed_starts():
    apps, stats = parse_applicants_csv(csv_bytes(line(
        Email="a@x", Name="Анна", Date="2025-10-28 08:06:01", city="Красноярск", tranid="1:2",
        format="Индивидуальное участие", sex="Женский", surname="Тестова", birthday="20.01.1978",
        siberman_individual_starts="1", siberman_relay_starts="2")), today=TODAY)
    assert len(apps) == 1
    a = apps[0]
    assert (a.tranid, a.surname, a.name, a.gender, a.birthdate, a.city, a.claimed_starts) == (
        "1:2", "Тестова", "Анна", "F", datetime.date(1978, 1, 20), "Красноярск", 3)
    assert a.submitted_at == datetime.datetime(2025, 10, 28, 8, 6, 1)
    assert stats == {"rows": 1, "people": 1, "no_birthday": 0, "bad_birthday": 0}


def test_men_gender_and_city_2_and_no_starts():
    apps, _ = parse_applicants_csv(csv_bytes(line(
        Name="Иван", tranid="1:8", sex="Мужской", surname="Тестов", birthday="01.01.1980", city_2="Томск",
        siberman_individual_starts_2="")), today=TODAY)
    assert (apps[0].gender, apps[0].city, apps[0].claimed_starts) == ("M", "Томск", 0)


def test_old_form_without_surname_is_skipped():
    apps, stats = parse_applicants_csv(csv_bytes(line(Name="Иван Тестов", Date="2023-11-24 00:01:40", tranid="1:1")),
                                       today=TODAY)
    assert apps == [] and stats["rows"] == 1 and stats["people"] == 0


def test_relay_members_get_own_records_and_captain_is_skipped():
    apps, _ = parse_applicants_csv(csv_bytes(line(
        Name="Ирина", tranid="1:3", format="Эстафетная команда", surname="Тестова", birthday="20.01.1978",
        surname_swim="Пловцова", name_swim="Элина", birthday_swim="01.02.2005",
        surname_bike="Велосипедов", name_bike="Андрей", birthday_bike="20-04-1977",
        surname_run="Бегунова", name_run="Ирина", birthday_run="")), today=TODAY)
    by_id = {a.tranid: a for a in apps}
    assert set(by_id) == {"1:3:swim", "1:3:bike"}
    assert by_id["1:3:bike"].birthdate == datetime.date(1977, 4, 20)
    assert by_id["1:3:swim"].gender is None and by_id["1:3:swim"].claimed_starts is None


def test_bad_and_too_young_dates_are_counted():
    apps, stats = parse_applicants_csv(csv_bytes(
        line(tranid="1:4", surname="Тестов", Name="А", birthday="31.02.1990"),
        line(tranid="1:5", surname="Тестов", Name="Б", birthday="09.01.2025"),
        line(tranid="1:6", surname="Тестов", Name="В", birthday="")), today=TODAY)
    assert apps == []
    assert stats["bad_birthday"] == 2 and stats["no_birthday"] == 1


def test_min_age_boundary():
    assert parse_birthdate("31.12.2012", TODAY) == datetime.date(2012, 12, 31)
    assert parse_birthdate("01.01.2013", TODAY) is None


def test_same_tranid_twice_keeps_last():
    apps, _ = parse_applicants_csv(csv_bytes(
        line(tranid="1:7", surname="Тестов", Name="Иван", birthday="01.01.1980"),
        line(tranid="1:7", surname="Тестов", Name="Иван", birthday="02.01.1980")), today=TODAY)
    assert len(apps) == 1 and apps[0].birthdate == datetime.date(1980, 1, 2)


def test_quoted_newline_crlf_and_cp1251():
    text_line = line(tranid="1:9", surname="Тестов", Name="Иван", birthday="01.01.1980")
    quoted = text_line.replace("1:9", '"1:9"', 1)
    for data in (csv_bytes(quoted, sep="\r\n"), csv_bytes(text_line, encoding="cp1251", bom=False)):
        apps, _ = parse_applicants_csv(data, today=TODAY)
        assert [(a.tranid, a.surname) for a in apps] == [("1:9", "Тестов")]
    multiline = line(tranid="1:10", surname="Тестов", Name="Иван", birthday="01.01.1980").replace(
        "a@x", "", 1)
    data = (";".join(COLS) + "\n" + multiline.replace(";;", ';"две\nстроки";', 1)).encode("utf-8")
    apps, _ = parse_applicants_csv(data, today=TODAY)
    assert [a.tranid for a in apps] == ["1:10"]


def test_not_a_tilda_export():
    with pytest.raises(ValueError):
        parse_applicants_csv(b"a;b\n1;2", today=TODAY)


def test_parse_birthdate_formats():
    assert parse_birthdate("01.05.1981", TODAY) == datetime.date(1981, 5, 1)
    assert parse_birthdate("01-05-1981", TODAY) == datetime.date(1981, 5, 1)
    assert parse_birthdate("1981-05-01", TODAY) is None
    assert parse_birthdate("01.05.1920", TODAY) is None
```

Примечание к `test_quoted_newline_crlf_and_cp1251`: третья часть вставляет в первое пустое поле строки значение в кавычках с переводом строки — разбор не должен развалиться. Если вставка попадает не в то поле и тест ломается из-за самой конструкции строки, упростить её (строка CSV с полем `"две\nстроки"` в колонке `Phone`), не меняя смысла проверки.

- [ ] **Step 5: `applicants.py` (полная замена файла)**

```python
"""
Выгрузка заявок Тильды (CSV: «;», UTF-8 с BOM, либо cp1251 после пересохранения в Excel) →
даты рождения для реестра людей.

Берём только ФИ, пол, ДР, город, номер заявки (tranid), дату подачи и сколько стартов на
Siberman заявитель указал сам — телефоны, e-mail и тексты заявок не читаем. ДР в форме есть
с 15.10.2024 (форма 807405240 и следующие). В эстафетной заявке берём только этапников
(surname_swim/name_swim/birthday_swim и т.д.): основной заявитель либо сам этапник (дубль),
либо не участник. Старые формы без колонки surname (ФИ одной строкой, ДР нет) пропускаются.
"""
import csv
import datetime
import io
from typing import Optional

from src.siberman.persons.linking import Applicant

STAGES = ("swim", "bike", "run")
STARTS_COLS = ("siberman_individual_starts", "siberman_individual_starts_2", "siberman_relay_starts")
MIN_YEAR = 1930
MIN_AGE = 14


def _clean(v) -> str:
    return " ".join(str(v or "").split())


def _int0(v) -> int:
    t = _clean(v)
    return int(t) if t.isdigit() else 0


def parse_birthdate(raw: str, today: datetime.date) -> Optional[datetime.date]:
    """'дд.мм.гггг' или 'дд-мм-гггг'; невозможная дата, раньше 1930 или моложе 14 лет → None."""
    parts = _clean(raw).replace("-", ".").replace("/", ".").split(".")
    if len(parts) != 3 or not all(p.isdigit() for p in parts) or len(parts[2]) != 4:
        return None
    try:
        d = datetime.date(int(parts[2]), int(parts[1]), int(parts[0]))
    except ValueError:
        return None
    if d.year < MIN_YEAR or d.year > today.year - MIN_AGE:
        return None
    return d


def _parse_dt(raw) -> Optional[datetime.datetime]:
    try:
        return datetime.datetime.strptime(_clean(raw), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def _decode(data: bytes) -> str:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = data.decode("cp1251", errors="strict")
    return text.lstrip(chr(0xFEFF))


def parse_applicants_csv(data: bytes, today: Optional[datetime.date] = None) -> tuple:
    """→ ([Applicant], {'rows', 'people', 'no_birthday', 'bad_birthday'}). ValueError — не выгрузка Тильды."""
    today = today or datetime.date.today()
    try:
        text = _decode(data)
    except UnicodeDecodeError:
        raise ValueError("Не удалось прочитать файл — сохраните выгрузку в UTF-8") from None
    reader = csv.DictReader(io.StringIO(text, newline=""), delimiter=";")
    if not reader.fieldnames or "tranid" not in reader.fieldnames:
        raise ValueError("Это не выгрузка заявок Тильды: нет колонки tranid")
    found: dict = {}
    stats = {"rows": 0, "people": 0, "no_birthday": 0, "bad_birthday": 0}
    for row in reader:
        stats["rows"] += 1
        tranid = _clean(row.get("tranid"))
        if not tranid:
            continue
        submitted = _parse_dt(row.get("Date"))
        people = []
        if not _clean(row.get("format")).startswith("Эстафет"):
            gender = {"Мужской": "M", "Женский": "F"}.get(_clean(row.get("sex")))
            city = _clean(row.get("city") or row.get("city_2"))
            starts = sum(_int0(row.get(c)) for c in STARTS_COLS)
            people.append((tranid, row.get("surname"), row.get("Name"), row.get("birthday"), gender, city, starts))
        for st in STAGES:
            people.append((f"{tranid}:{st}", row.get(f"surname_{st}"), row.get(f"name_{st}"),
                           row.get(f"birthday_{st}"), None, "", None))
        for tid, surname, name, bd_raw, g, c, starts in people:
            surname, name = _clean(surname), _clean(name)
            if not surname:
                continue
            bd = parse_birthdate(bd_raw, today)
            if bd is None:
                stats["bad_birthday" if _clean(bd_raw) else "no_birthday"] += 1
                continue
            found[tid] = Applicant(tranid=tid, surname=surname, name=name, gender=g, birthdate=bd,
                                   city=c, submitted_at=submitted, claimed_starts=starts)
    stats["people"] = len(found)
    return list(found.values()), stats
```

- [ ] **Step 6: Прогон**

Run: `conda run -n base python -m pytest tests/unit/test_siberman_persons_linking.py tests/unit/test_siberman_persons_applicants.py -q`
Expected: 25 + 10 = 35 passed.
Run: `conda run -n base python -m pytest tests/unit/ -q` — 903 + 35 = 938 passed.

- [ ] **Step 7: Commit**

```bash
git add src/siberman/migrations/014_persons.sql src/siberman/persons/linking.py src/siberman/persons/applicants.py tests/unit/test_siberman_persons_linking.py tests/unit/test_siberman_persons_applicants.py
git commit -m "fix(siberman/persons): замена этапника при перезагрузке, ДР только при указанных стартах, ревью по полу, cp1251"
```

---

### Task 3b: Повторное ревью — ручные привязки, стёртая фамилия, переразбор без следа

Повторное ревью 3a: прошлые замечания закрыты; найдены три обхода той же защиты от «не того человека».

1. **Ручная привязка не проверялась.** Слияние (`move_links`) делало ручными все выступления исходного человека, и после любого слияния замена этапника снова оставалась незамеченной. Теперь: ручная привязка с другим ФИ остаётся, но даёт запись `manual_name_changed`, а новое ФИ не попадает в ключи человека. `move_links` больше не трогает `manual` (Task 4).
2. **Стёртая фамилия.** Строка без фамилии отбрасывалась до проверки привязок — автопривязка к прежнему этапнику оставалась. Теперь такие автопривязки собираются в `Registry.dropped`, `sync` их удаляет (Task 5).
3. **Переразбор без следа.** Исправление опечатки в протоколе давало нового человека молча, прежний (с ручной ДР, с адресом `/athlete/{id}`) удалялся как сирота. Теперь — запись `relinked` (новый человек + прежний кандидатом), а `delete_stale` не удаляет людей, на которых ссылаются нерешённые записи «проверить» (Task 4).
4. Мелочь: у личника тёзка со своим личным номером отсеивается до проверки пола (лишний `gender_mismatch`). `count_unlinked` не считает строки без фамилии (Task 4).

**Files:**
- Modify: `src/siberman/persons/linking.py`
- Modify: `tests/unit/test_siberman_persons_linking.py`

- [ ] **Step 1: Тесты**

В `tests/unit/test_siberman_persons_linking.py` заменить `test_manual_link_survives_name_change` на:
```python
def test_manual_link_name_change_is_kept_but_flagged():
    p = Person(id=5, surname="Иванов", name="Иван", gender="M")
    r = relay(2020, 101, "swim", "Петров", "Пётр")
    reg, links, reviews = run([r], persons=[p], links={key(r): (5, 1, "иванов иван")})
    assert links == {}
    assert [(x.kind, x.person) for x in reviews] == [("manual_name_changed", reg.by_id[5])]
    assert "петров петр" not in reg.by_id[5].keys
```
и добавить в конец файла:
```python
def test_cleared_surname_drops_auto_link_only():
    p = Person(id=1, surname="Иванов", name="Иван", gender="M")
    auto, manual = relay(2020, 101, "swim", "", ""), relay(2020, 102, "swim", " ", "")
    reg, links, reviews = run([auto, manual], persons=[p],
                              links={key(auto): (1, 0, "иванов иван"), key(manual): (1, 1, "иванов иван")})
    assert reg.dropped == [key(auto)]
    assert links == {} and reviews == []


def test_relinked_after_typo_fix_keeps_trace():
    prev = Person(id=1, surname="Ивнов", name="Иван", gender="M")
    a, b = relay(2019, 100, "run", "Ивнов", "Иван"), relay(2020, 101, "swim", "Иванов", "Иван")
    reg, links, reviews = run([a, b], persons=[prev],
                              links={key(a): (1, 0, "ивнов иван"), key(b): (1, 0, "ивнов иван")})
    new = links[key(b)]
    assert new is not reg.by_id[1]
    assert [(x.kind, x.person, x.others) for x in reviews] == [("relinked", new, (reg.by_id[1],))]


def test_individual_namesake_with_own_bib_is_not_gender_mismatch():
    a, b = row(2020, 7, "Иванов", "Саша", gender="M"), row(2021, 8, "Иванов", "Саша", gender="F")
    reg, links, reviews = run([a, b])
    assert links[key(a)] is not links[key(b)]
    assert reviews == []
```

- [ ] **Step 2: Тесты падают**

Run: `conda run -n base python -m pytest tests/unit/test_siberman_persons_linking.py -q`
Expected: 4 failed (`manual_name_changed`, `dropped`, `relinked`, лишний `gender_mismatch`), остальные passed.

- [ ] **Step 3: Правки `linking.py`**

1. В `Registry.__init__` после `self.bib_assigned: list = []` добавить:
```python
        self.dropped: list = []        # автопривязки строк, у которых в протоколе стёрли фамилию
```
2. Сигнатуру `Registry.attach` и её первую строку тела заменить:
```python
    def attach(self, p: Person, row: dict, index_name: bool = True) -> None:
        """Учесть выступление row за человеком p. index_name=False — ФИ строки не добавлять
        в ключи человека (ручная привязка, у которой ФИ в протоколе изменилось)."""
        year, bib = int(row["race_year"]), str(row["bib"])
        if index_name:
            self._index_key(p, plain_key(row["surname"], row["name"]))
```
(остальное тело `attach` без изменений).
3. В `_resolve` цикл по кандидатам заменить (проверка личного номера — до проверки пола):
```python
    for p in reg.by_key.get(key, []):
        if r["format"] == "individual" and p.bib_individual and p.bib_individual != bib:
            continue                          # у человека свой личный номер — это тёзка
        if not _gender_ok(g, p.gender):
            other_gender.append(p)
            continue
        used = p.usage.get(year)
        if used and bib not in used:          # в этом году уже выступал под другим номером
            continue
        cands.append(p)
```
4. `link_participants` заменить целиком:
```python
def link_participants(reg: Registry, rows: list, links: dict) -> tuple:
    """rows — все строки participants; links — сохранённые привязки {natkey: (person_id, manual, name_key)}.
    Автопривязка действует, пока ФИ строки то же, что при привязке; иначе строка разрешается заново
    (замена этапника, исправленный протокол) и, если ушла к другому человеку, — запись «relinked».
    Ручная привязка действует всегда; другое ФИ — запись «manual_name_changed». Строки без фамилии
    не привязываются, их автопривязки — в reg.dropped (удалить).
    → ({natkey: Person} новых и изменённых привязок, [Review])."""
    ordered = sorted(rows, key=_row_order)
    named = []
    for r in ordered:
        if str(r["surname"] or "").strip():
            named.append(r)
            continue
        link = links.get(natkey(r))
        if link and not link[1]:
            reg.dropped.append(natkey(r))

    kept, reviews = set(), []
    for r in named:
        link = links.get(natkey(r))
        if not link or link[0] not in reg.by_id:
            continue
        person_id, manual, name_key = link
        p = reg.by_id[person_id]
        same = name_key == plain_key(r["surname"], r["name"])
        if same or manual:
            reg.attach(p, r, index_name=same)
            kept.add(natkey(r))
            if not same:
                reviews.append(Review("manual_name_changed", natkey=natkey(r), person=p))

    new_links = {}
    for r in named:
        k = natkey(r)
        if k in kept:
            continue
        p, rv = _resolve(reg, r)
        reg.attach(p, r)
        new_links[k] = p
        reviews.extend(rv)
        link = links.get(k)
        prev = reg.by_id.get(link[0]) if link else None
        if prev is not None and prev is not p:
            reviews.append(Review("relinked", natkey=k, person=p, others=(prev,)))
    return new_links, reviews
```

- [ ] **Step 4: Тесты проходят**

Run: `conda run -n base python -m pytest tests/unit/test_siberman_persons_linking.py tests/unit/test_siberman_persons_applicants.py -q`
Expected: 28 + 10 = 38 passed.
Run: `conda run -n base python -m pytest tests/unit/ -q` — 903 + 38 = 941 passed.

- [ ] **Step 5: Commit**

```bash
git add src/siberman/persons/linking.py tests/unit/test_siberman_persons_linking.py
git commit -m "fix(siberman/persons): ручная привязка с другим ФИ, стёртая фамилия, след переразбора, номер до пола"
```

---

### Task 3c: Третье ревью — повторные правки одного выступления

1. **Ключ записи «проверить» не менялся** (`kind:год:номер:этап`): вторая смена ФИ на том же месте давала тот же ключ, `INSERT IGNORE` её глотал — выступление молча уходило к третьему человеку. Теперь у `relinked` и `manual_name_changed` в `detail` — новый ключ ФИ строки, и он входит в ключ дедупликации.
2. **«Оставить привязку» только закрывало запись**: `name_key` оставался старым, подтверждённое ФИ не попадало в ключи человека. Теперь отдельное действие `keep_link` (Task 7/9) переписывает привязку с текущим ФИ.
3. Ручная привязка строки, у которой стёрли фамилию, — тоже `manual_name_changed`.

**Files:**
- Modify: `src/siberman/persons/linking.py`
- Modify: `tests/unit/test_siberman_persons_linking.py`

- [ ] **Step 1: Тесты**

В `tests/unit/test_siberman_persons_linking.py`:

1. В `test_cleared_surname_drops_auto_link_only` заменить последнюю строку `assert links == {} and reviews == []` на:
```python
    assert links == {}
    assert [(x.kind, x.natkey) for x in reviews] == [("manual_name_changed", key(manual))]
```
2. В `test_manual_link_name_change_is_kept_but_flagged` после строки с `assert [(x.kind, x.person) ...]` добавить:
```python
    assert reviews[0].detail == "петров петр"
```
3. В `test_review_dedupe_keys` в конец добавить:
```python
    first = Review("relinked", natkey=key(a), person=p, detail="петров петр").dedupe_key()
    second = Review("relinked", natkey=key(a), person=p, detail="петрова петра").dedupe_key()
    assert first == "relinked:2024:7:none:петров петр" and first != second
```
4. В `test_relinked_after_typo_fix_keeps_trace` после последнего `assert` добавить:
```python
    assert reviews[0].detail == "иванов иван"
```

- [ ] **Step 2: Тесты падают**

Run: `conda run -n base python -m pytest tests/unit/test_siberman_persons_linking.py -q`
Expected: 4 failed.

- [ ] **Step 3: Правки `linking.py`**

1. `Review.dedupe_key` заменить:
```python
    def dedupe_key(self) -> str:
        if self.natkey:
            y, b, s = self.natkey
            # detail (новое ФИ строки) различает повторные правки одного и того же выступления
            return (f"{self.kind}:{y}:{b}:{s}" + (f":{self.detail}" if self.detail else ""))[:190]
        return f"{self.kind}:{self.person.id if self.person else ''}:{self.detail}"[:190]
```
2. В `link_participants`, первый цикл (строки без фамилии) — ручная привязка тоже даёт запись:
```python
    for r in ordered:
        if str(r["surname"] or "").strip():
            named.append(r)
            continue
        link = links.get(natkey(r))
        if not link:
            continue
        if not link[1]:
            reg.dropped.append(natkey(r))
        elif link[0] in reg.by_id:
            reviews.append(Review("manual_name_changed", natkey=natkey(r), person=reg.by_id[link[0]]))
```
и перенести инициализацию `kept, reviews = set(), []` ПЕРЕД этим циклом (`reviews` нужен в нём). Во втором цикле:
```python
            if not same:
                reviews.append(Review("manual_name_changed", natkey=natkey(r), person=p,
                                      detail=plain_key(r["surname"], r["name"])))
```
3. В третьем цикле запись `relinked`:
```python
        if prev is not None and prev is not p:
            reviews.append(Review("relinked", natkey=k, person=p, others=(prev,),
                                  detail=plain_key(r["surname"], r["name"])))
```

- [ ] **Step 4: Тесты проходят**

Run: `conda run -n base python -m pytest tests/unit/test_siberman_persons_linking.py tests/unit/test_siberman_persons_applicants.py -q`
Expected: 38 passed. `tests/unit/` — 941 passed.

- [ ] **Step 5: Commit**

```bash
git add src/siberman/persons/linking.py tests/unit/test_siberman_persons_linking.py
git commit -m "fix(siberman/persons): повторные правки одного выступления — новая запись «проверить»"
```

---

### Task 4: SQL реестра (`db.py`)

**Files:**
- Create: `src/siberman/persons/db.py`

Отдельных unit-тестов нет (SQL проверяется интеграционными тестами Task 5 и Task 7).

- [ ] **Step 1: Реализация**

```python
"""SQL реестра людей Siberman (миграция 014). Соединение autocommit; транзакции открывает service."""
import datetime
import json
from typing import Iterable, Optional

from src.siberman.persons.linking import Applicant, Person

PERSON_FIELDS = ("surname", "name", "gender", "birthdate", "bib_individual", "city", "country")
LINK_ON = "l.race_year=p.race_year AND l.bib=p.bib AND l.relay_stage=p.relay_stage"


def _cur(conn):
    return conn.cursor(dictionary=True, buffered=True)


def _keys_where(keys: list, prefix: str = "") -> tuple:
    clause = " OR ".join([f"({prefix}race_year=%s AND {prefix}bib=%s AND {prefix}relay_stage=%s)"] * len(keys))
    return f"({clause})", [v for k in keys for v in (int(k[0]), str(k[1]), str(k[2]))]


def _in(ids) -> tuple:
    ids = [int(i) for i in ids]
    return ",".join(["%s"] * len(ids)), ids


# ── люди ─────────────────────────────────────────────────────────────────────

def load_persons(conn) -> list:
    cur = _cur(conn)
    cur.execute("SELECT id, surname, name, gender, birthdate, bib_individual, city FROM siberman_persons")
    return [Person(id=r["id"], surname=r["surname"], name=r["name"], gender=r["gender"],
                   birthdate=r["birthdate"], bib_individual=r["bib_individual"], city=r["city"])
            for r in cur.fetchall()]


def get_persons(conn, ids) -> dict:
    ids = sorted({int(i) for i in ids if i is not None})
    if not ids:
        return {}
    marks, args = _in(ids)
    cur = _cur(conn)
    cur.execute(f"SELECT id, {', '.join(PERSON_FIELDS)} FROM siberman_persons WHERE id IN ({marks})", args)
    return {r["id"]: r for r in cur.fetchall()}


def get_person(conn, person_id: int) -> Optional[dict]:
    return get_persons(conn, [person_id]).get(int(person_id))


def person_by_bib(conn, bib: str) -> Optional[dict]:
    cur = _cur(conn)
    cur.execute(f"SELECT id, {', '.join(PERSON_FIELDS)} FROM siberman_persons WHERE bib_individual=%s", (str(bib),))
    return cur.fetchone()


def insert_person(conn, fields: dict) -> int:
    """fields — подмножество PERSON_FIELDS (+ 'id' при восстановлении удалённого отменой)."""
    cols = [c for c in ("id", *PERSON_FIELDS) if c in fields]
    cur = conn.cursor()
    cur.execute(f"INSERT INTO siberman_persons ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))})",
                [fields[c] for c in cols])
    return int(fields.get("id") or cur.lastrowid)


def update_person(conn, person_id: int, fields: dict) -> None:
    if not fields:
        return
    bad = set(fields) - set(PERSON_FIELDS)
    if bad:
        raise ValueError(f"нельзя менять поля: {sorted(bad)}")
    cur = conn.cursor()
    cur.execute(f"UPDATE siberman_persons SET {', '.join(f'{k}=%s' for k in fields)} WHERE id=%s",
                [*fields.values(), int(person_id)])


def delete_person(conn, person_id: int) -> None:
    conn.cursor().execute("DELETE FROM siberman_persons WHERE id=%s", (int(person_id),))


def delete_orphans(conn, ids) -> list:
    """Удалить людей из ids, у которых не осталось выступлений. → удалённые id."""
    ids = sorted({int(i) for i in ids if i is not None})
    if not ids:
        return []
    marks, args = _in(ids)
    cur = _cur(conn)
    cur.execute(f"SELECT s.id FROM siberman_persons s LEFT JOIN siberman_person_links l ON l.person_id=s.id "
                f"WHERE s.id IN ({marks}) AND l.person_id IS NULL", args)
    gone = [r["id"] for r in cur.fetchall()]
    for pid in gone:
        delete_person(conn, pid)
    return gone


def search_persons(conn, q: str, limit: int = 30) -> list:
    q = " ".join(q.split())
    cur = _cur(conn)
    base = ("SELECT s.id, s.surname, s.name, s.bib_individual, s.birthdate, s.city, "
            "GROUP_CONCAT(DISTINCT l.race_year ORDER BY l.race_year SEPARATOR ', ') AS years "
            "FROM siberman_persons s LEFT JOIN siberman_person_links l ON l.person_id=s.id "
            f"LEFT JOIN participants p ON {LINK_ON} ")
    if q.isdigit():
        cur.execute(base + "WHERE s.id=%s OR s.bib_individual=%s GROUP BY s.id ORDER BY s.id LIMIT %s",
                    (int(q), q, limit))
    else:
        like = f"%{q}%"
        cur.execute(base + "WHERE CONCAT(s.surname,' ',s.name) LIKE %s OR CONCAT(s.name,' ',s.surname) LIKE %s "
                           "OR CONCAT(p.surname,' ',p.name) LIKE %s "
                           "GROUP BY s.id ORDER BY s.surname, s.name, s.id LIMIT %s", (like, like, like, limit))
    return cur.fetchall()


# ── выступления и привязки ──────────────────────────────────────────────────

def load_participant_rows(conn) -> list:
    cur = _cur(conn)
    cur.execute("SELECT race_year, bib, relay_stage, surname, name, gender, format, city, country FROM participants")
    return cur.fetchall()


def load_links(conn) -> dict:
    """{(год, номер, этап): (person_id, manual, name_key)} — формат, который ждёт link_participants."""
    cur = _cur(conn)
    cur.execute("SELECT race_year, bib, relay_stage, person_id, manual, name_key FROM siberman_person_links")
    return {(int(r["race_year"]), str(r["bib"]), str(r["relay_stage"])): (r["person_id"], r["manual"], r["name_key"])
            for r in cur.fetchall()}


def count_unlinked(conn) -> int:
    cur = _cur(conn)
    cur.execute(f"SELECT COUNT(*) AS n FROM participants p LEFT JOIN siberman_person_links l ON {LINK_ON} "
                "WHERE l.person_id IS NULL AND TRIM(p.surname) <> ''")
    return int(cur.fetchone()["n"])


def set_links(conn, items: Iterable, manual: bool) -> None:
    """items — [((год, номер, этап), person_id, name_key)]; name_key — plain_key ФИ строки сейчас."""
    rows = [(int(k[0]), str(k[1]), str(k[2]), int(pid), int(manual), name_key) for k, pid, name_key in items]
    if rows:
        conn.cursor().executemany(
            "INSERT INTO siberman_person_links (race_year, bib, relay_stage, person_id, manual, name_key) "
            "VALUES (%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE person_id=VALUES(person_id), "
            "manual=VALUES(manual), name_key=VALUES(name_key)", rows)


def delete_links(conn, keys: list) -> None:
    if keys:
        where, args = _keys_where(keys)
        conn.cursor().execute(f"DELETE FROM siberman_person_links WHERE {where}", args)


def links_for_keys(conn, keys: list) -> dict:
    if not keys:
        return {}
    where, args = _keys_where(keys)
    cur = _cur(conn)
    cur.execute(f"SELECT race_year, bib, relay_stage, person_id, manual, name_key FROM siberman_person_links "
                f"WHERE {where}", args)
    return {(int(r["race_year"]), str(r["bib"]), str(r["relay_stage"])):
            {"person_id": r["person_id"], "manual": r["manual"], "name_key": r["name_key"]} for r in cur.fetchall()}


def links_of_person(conn, person_id: int) -> list:
    cur = _cur(conn)
    cur.execute("SELECT race_year, bib, relay_stage FROM siberman_person_links WHERE person_id=%s "
                "ORDER BY race_year, bib, relay_stage", (int(person_id),))
    return [(int(r["race_year"]), str(r["bib"]), str(r["relay_stage"])) for r in cur.fetchall()]


def move_links(conn, source_id: int, target_id: int) -> None:
    """Слияние: привязки переходят как есть — ручными становятся только явно выбранные выступления
    (reassign), иначе после слияния замена этапника перестала бы проверяться."""
    conn.cursor().execute("UPDATE siberman_person_links SET person_id=%s WHERE person_id=%s",
                          (int(target_id), int(source_id)))


def delete_stale(conn) -> tuple:
    """Автопривязки к исчезнувшим строкам и люди без выступлений, на которых не ссылаются
    нерешённые записи «проверить» (их держим, чтобы админ мог слить обратно). → (привязок, людей)."""
    cur = conn.cursor()
    cur.execute(f"DELETE l FROM siberman_person_links l LEFT JOIN participants p ON {LINK_ON} "
                "WHERE p.id IS NULL AND l.manual=0")
    links = cur.rowcount
    cur.execute("DELETE s FROM siberman_persons s LEFT JOIN siberman_person_links l ON l.person_id=s.id "
                "WHERE l.person_id IS NULL AND NOT EXISTS (SELECT 1 FROM siberman_person_reviews r "
                "WHERE r.status <> 'resolved' AND (r.person_id = s.id OR FIND_IN_SET(s.id, r.other_person_ids)))")
    return links, cur.rowcount


def participants_by_keys(conn, keys: list) -> list:
    if not keys:
        return []
    where, args = _keys_where(keys, "p.")
    cur = _cur(conn)
    cur.execute("SELECT p.id, p.race_year, p.bib, p.relay_stage, p.surname, p.name, p.gender, p.format, "
                f"p.relay_team_name, p.status, p.city, p.country FROM participants p WHERE {where}", args)
    return cur.fetchall()


def participations(conn, person_ids) -> dict:
    """person_id → [выступления по годам] (с итоговым временем и флагом ручной привязки)."""
    ids = sorted({int(i) for i in person_ids if i is not None})
    if not ids:
        return {}
    marks, args = _in(ids)
    cur = _cur(conn)
    cur.execute("SELECT l.person_id, l.manual, p.race_year, p.bib, p.relay_stage, p.format, p.relay_team_name, "
                "p.surname, p.name, p.gender, p.status, p.city, p.country, o.total_s "
                f"FROM siberman_person_links l JOIN participants p ON {LINK_ON} "
                "LEFT JOIN overall_results o ON o.participant_id=p.id "
                f"WHERE l.person_id IN ({marks}) ORDER BY p.race_year, p.relay_stage", args)
    out: dict = {}
    for r in cur.fetchall():
        out.setdefault(r["person_id"], []).append(r)
    return out


def refresh_display(conn, person_ids) -> None:
    """ФИ, пол, город, страна человека — по последнему выступлению."""
    for pid, rows in participations(conn, person_ids).items():
        last = max(rows, key=lambda r: (r["race_year"], r["format"] == "individual"))
        fields = {"surname": last["surname"], "name": last["name"],
                  "city": last["city"] or "", "country": last["country"] or ""}
        if last["gender"] in ("M", "F"):
            fields["gender"] = last["gender"]
        update_person(conn, pid, fields)


# ── заявки ───────────────────────────────────────────────────────────────────

def load_applicants(conn) -> list:
    cur = _cur(conn)
    cur.execute("SELECT tranid, surname, name, gender, birthdate, city, submitted_at, claimed_starts "
                "FROM siberman_applicants")
    return [Applicant(**r) for r in cur.fetchall()]


def upsert_applicants(conn, apps: list) -> int:
    rows = [(a.tranid, a.surname, a.name, a.gender, a.birthdate, a.city, a.submitted_at, a.claimed_starts)
            for a in apps]
    if rows:
        conn.cursor().executemany(
            "INSERT INTO siberman_applicants (tranid, surname, name, gender, birthdate, city, submitted_at, "
            "claimed_starts) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE surname=VALUES(surname), "
            "name=VALUES(name), gender=VALUES(gender), birthdate=VALUES(birthdate), city=VALUES(city), "
            "submitted_at=VALUES(submitted_at), claimed_starts=VALUES(claimed_starts)",
            rows)
    return len(rows)


def get_applicants(conn, tranids) -> dict:
    tranids = sorted({t for t in tranids if t})
    if not tranids:
        return {}
    cur = _cur(conn)
    cur.execute(f"SELECT tranid, surname, name, gender, birthdate, city FROM siberman_applicants "
                f"WHERE tranid IN ({','.join(['%s'] * len(tranids))})", tranids)
    return {r["tranid"]: r for r in cur.fetchall()}


# ── «проверить» ──────────────────────────────────────────────────────────────

def add_reviews(conn, reviews: list) -> int:
    cur, n = conn.cursor(), 0
    for r in reviews:
        y, b, s = r.natkey if r.natkey else (None, None, None)
        cur.execute(
            "INSERT IGNORE INTO siberman_person_reviews "
            "(kind, dedupe_key, race_year, bib, relay_stage, person_id, other_person_ids, detail) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
            (r.kind, r.dedupe_key(), y, b, s, r.person.id if r.person else None,
             ",".join(str(o.id) for o in r.others), r.detail[:255]))
        n += cur.rowcount
    return n


def get_review(conn, review_id: int) -> Optional[dict]:
    cur = _cur(conn)
    cur.execute("SELECT * FROM siberman_person_reviews WHERE id=%s", (int(review_id),))
    return cur.fetchone()


def list_reviews(conn, status: str) -> list:
    cur = _cur(conn)
    cur.execute("SELECT * FROM siberman_person_reviews WHERE status=%s ORDER BY id", (status,))
    return cur.fetchall()


def set_review_status(conn, review_id: int, status: str, user: str) -> bool:
    """False — записи нет. (rowcount MySQL считает только изменённые строки — не годится.)"""
    cur = conn.cursor(buffered=True)
    cur.execute("SELECT id FROM siberman_person_reviews WHERE id=%s", (int(review_id),))
    if not cur.fetchone():
        return False
    cur.execute("UPDATE siberman_person_reviews SET status=%s, resolved_at=%s, resolved_by=%s WHERE id=%s",
                (status, None if status == "open" else datetime.datetime.now(), None if status == "open" else user,
                 int(review_id)))
    return True


def reviews_for_person(conn, person_id: int) -> list:
    cur = _cur(conn)
    cur.execute("SELECT id, kind, status FROM siberman_person_reviews WHERE status='open' "
                "AND (person_id=%s OR FIND_IN_SET(%s, other_person_ids)) ORDER BY id", (int(person_id), str(person_id)))
    return cur.fetchall()


# ── журнал ───────────────────────────────────────────────────────────────────

def add_audit(conn, action: str, summary: str, payload: dict, scope: set, user: str) -> int:
    cur = conn.cursor()
    cur.execute("INSERT INTO siberman_person_audit (action, summary, payload, scope, created_by) VALUES (%s,%s,%s,%s,%s)",
                (action, summary[:255], json.dumps(payload, ensure_ascii=False, default=str),
                 ",".join(sorted(scope)), user or ""))
    return cur.lastrowid


def get_audit(conn, audit_id: int) -> Optional[dict]:
    cur = _cur(conn)
    cur.execute("SELECT * FROM siberman_person_audit WHERE id=%s", (int(audit_id),))
    return cur.fetchone()


def list_audit(conn, limit: int = 100) -> list:
    cur = _cur(conn)
    cur.execute("SELECT id, action, summary, created_at, created_by, undone_at, undone_by "
                "FROM siberman_person_audit ORDER BY id DESC LIMIT %s", (limit,))
    return cur.fetchall()


def later_conflicts(conn, audit_id: int, scope: set) -> list:
    cur = _cur(conn)
    cur.execute("SELECT id, scope FROM siberman_person_audit WHERE id>%s AND undone_at IS NULL", (int(audit_id),))
    return [r["id"] for r in cur.fetchall() if scope & set(filter(None, r["scope"].split(",")))]


def mark_undone(conn, audit_id: int, user: str) -> None:
    conn.cursor().execute("UPDATE siberman_person_audit SET undone_at=%s, undone_by=%s WHERE id=%s",
                          (datetime.datetime.now(), user, int(audit_id)))
```

- [ ] **Step 2: Проверка импорта**

Run: `conda run -n base python -c "import src.siberman.persons.db"`
Expected: без ошибок.

- [ ] **Step 3: Commit**

```bash
git add src/siberman/persons/db.py
git commit -m "feat(siberman/persons): SQL реестра — люди, привязки, заявки, «проверить», журнал"
```

---

### Task 5: Синхронизация (`service.sync`, `sync_safe`, импорт заявок)

**Files:**
- Create: `src/siberman/persons/service.py`
- Test: `tests/integration/test_siberman_persons.py`

- [ ] **Step 1: Интеграционные тесты синхронизации**

```python
"""
Реестр людей на локальной БД siberman (.env.local): синхронизация, ДР из заявок, ручные решения
и отмена. Тестовые годы 2090–2099 (от PID), фамилии «Тестреестров…» — чистятся до и после.
Первый прогон привязывает и весь локальный архив — это и есть первичное заполнение.
Годы идут по возрастанию (YEAR < Y2 < Y3): привязка зависит от порядка лет.
"""
import datetime
import os

import pytest

from src.siberman.db import get_siberman_connection
from src.siberman.persons import db as pdb
from src.siberman.persons import service
from src.siberman.persons.linking import Applicant

YEAR = 2090 + os.getpid() % 8   # изоляция параллельных прогонов, YEAR..Y3 ≤ 2099
Y2, Y3 = YEAR + 1, YEAR + 2


def _ins(conn, year, bib, surname, name, fmt="individual", stage="none", gender="M", team=None, city="Красноярск"):
    conn.cursor().execute(
        "INSERT INTO participants (race_year, bib, surname, name, gender, country, city, format, "
        "relay_team_name, relay_stage, status) VALUES (%s,%s,%s,%s,%s,'Россия',%s,%s,%s,%s,'active')",
        (year, str(bib), surname, name, gender, city, fmt, team, stage))


def _clean(conn):
    cur = conn.cursor()
    cur.execute("DELETE FROM siberman_person_links WHERE race_year IN (%s,%s,%s)", (YEAR, Y2, Y3))
    cur.execute("DELETE FROM participants WHERE race_year IN (%s,%s,%s)", (YEAR, Y2, Y3))
    cur.execute("DELETE FROM siberman_person_reviews WHERE race_year IN (%s,%s,%s) OR detail LIKE 'test-%%'",
                (YEAR, Y2, Y3))
    cur.execute("DELETE FROM siberman_applicants WHERE tranid LIKE 'test-%%'")
    cur.execute("DELETE FROM siberman_person_audit WHERE summary LIKE '%%Тестреестров%%'")
    cur.execute("DELETE s FROM siberman_persons s LEFT JOIN siberman_person_links l ON l.person_id=s.id "
                "WHERE l.person_id IS NULL")


def _pid(conn, year, bib, stage="none"):
    cur = conn.cursor()
    cur.execute("SELECT person_id FROM siberman_person_links WHERE race_year=%s AND bib=%s AND relay_stage=%s",
                (year, str(bib), stage))
    row = cur.fetchone()
    return row[0] if row else None


@pytest.fixture
def conn():
    c = get_siberman_connection()
    if c is None:
        pytest.skip("Нет локальной БД siberman")
    cur = c.cursor()
    cur.execute("SHOW TABLES LIKE 'siberman_person_links'")
    if not cur.fetchone():
        c.close()
        pytest.skip("Миграция 014_persons не применена")
    _clean(c)
    yield c
    _clean(c)
    c.close()


def test_sync_links_and_is_idempotent(conn):
    _ins(conn, YEAR, 9001, "Тестреестров", "Олег")
    _ins(conn, Y2, 9001, "Тестреестров", "Олег")
    _ins(conn, YEAR, 9101, "Тестреестрова", "Анна", fmt="relay", stage="swim", gender="F", team="Тест")
    _ins(conn, YEAR, 9101, "Тестреестрова", "Анна", fmt="relay", stage="bike", gender="F", team="Тест")
    first = service.sync(conn)
    assert first["linked"] >= 4
    assert _pid(conn, YEAR, 9001) == _pid(conn, Y2, 9001)
    assert _pid(conn, YEAR, 9101, "swim") == _pid(conn, YEAR, 9101, "bike")
    assert pdb.get_person(conn, _pid(conn, YEAR, 9001))["bib_individual"] == "9001"
    second = service.sync(conn)
    assert second["linked"] == 0 and second["new_persons"] == 0


def test_namesakes_by_individual_bib(conn):
    _ins(conn, YEAR, 9001, "Тестреестров", "Иван")
    _ins(conn, Y2, 9002, "Тестреестров", "Иван")
    service.sync(conn)
    assert _pid(conn, YEAR, 9001) != _pid(conn, Y2, 9002)


def test_reload_of_year_keeps_person_ids(conn):
    _ins(conn, YEAR, 9001, "Тестреестров", "Олег")
    _ins(conn, YEAR, 9101, "Тестреестрова", "Анна", fmt="relay", stage="run", gender="F", team="Тест")
    service.sync(conn)
    before = (_pid(conn, YEAR, 9001), _pid(conn, YEAR, 9101, "run"))
    conn.cursor().execute("DELETE FROM participants WHERE race_year=%s", (YEAR,))   # как clear_race_year
    _ins(conn, YEAR, 9001, "Тестреестров", "Олег")
    _ins(conn, YEAR, 9101, "Тестреестрова", "Анна", fmt="relay", stage="run", gender="F", team="Тест")
    service.sync(conn)
    assert (_pid(conn, YEAR, 9001), _pid(conn, YEAR, 9101, "run")) == before


def test_birthdate_from_applicant_and_conflict(conn):
    _ins(conn, YEAR, 9001, "Тестреестров", "Олег")
    pdb.upsert_applicants(conn, [Applicant("test-1", "Тестреестров", "Олег", "M", datetime.date(1980, 5, 1), "Красноярск",
                                           claimed_starts=1)])
    service.sync(conn)
    pid = _pid(conn, YEAR, 9001)
    assert pdb.get_person(conn, pid)["birthdate"] == datetime.date(1980, 5, 1)
    pdb.upsert_applicants(conn, [Applicant("test-2", "Тестреестров", "Олег", "M", datetime.date(1981, 5, 1), "Красноярск",
                                           claimed_starts=1)])
    service.sync(conn)
    kinds = [r["kind"] for r in pdb.list_reviews(conn, "open") if r["person_id"] == pid]
    assert "bd_conflict" in kinds


def test_import_applicants_csv(conn):
    _ins(conn, YEAR, 9001, "Тестреестров", "Олег", city="Томск")
    cols = ["tranid", "Date", "surname", "Name", "sex", "birthday", "city", "siberman_individual_starts"]
    body = ";".join(cols) + "\n" + ";".join(["test-9", "2026-10-01 10:00:00", "Тестреестров", "Олег",
                                             "Мужской", "02.03.1979", "Томск", "1"])
    report = service.import_applicants((chr(0xFEFF) + body).encode("utf-8"))
    assert report["people"] == 1 and report["sync"]["birthdates"] >= 1
    assert pdb.get_person(conn, _pid(conn, YEAR, 9001))["birthdate"] == datetime.date(1979, 3, 2)
```

- [ ] **Step 2: Тесты падают**

Run: `conda run -n base python -m pytest tests/integration/test_siberman_persons.py -q`
Expected: FAIL — `ImportError: cannot import name 'service' from 'src.siberman.persons'`.

- [ ] **Step 3: Реализация `service.py` (часть 1 — синхронизация)**

```python
"""
Реестр людей Siberman: синхронизация после каждой загрузки результатов, импорт заявок Тильды,
ручные решения админки (слить, перенести выступления, ДР, статус «проверить»), журнал с отменой,
карточки и поиск. Все записи — под MySQL GET_LOCK (живой цикл Copernico и админка не
пересекаются) и в одной транзакции. Спецификация hall §3.
"""
import contextlib
import datetime
import json
import logging
from typing import Optional

from src.siberman.db import get_siberman_connection
from src.siberman.persons import db as pdb
from src.siberman.persons.applicants import parse_applicants_csv
from src.siberman.persons.linking import Registry, attach_birthdates, link_participants, natkey, plain_key

log = logging.getLogger(__name__)

LOCK_NAME = "siberman_persons"
REVIEW_STATUSES = ("open", "resolved", "deferred")
REVIEW_TITLES = {
    "namesake_candidate": "Одинаковые ФИ — тот же человек или тёзка?",
    "bib_name_change": "Тот же личный номер, другое ФИ",
    "format_switch": "Эстафета и личный зачёт связаны по совпадению ФИ",
    "bd_conflict": "В заявке другая дата рождения",
    "applicant_ambiguous": "Заявка подходит нескольким тёзкам",
    "applicant_city_mismatch": "Заявка с тем же ФИ, но из другого города",
    "applicant_unconfirmed": "Заявка с тем же ФИ без стартов на Siberman — это он?",
    "gender_mismatch": "Те же ФИ, другой пол — тот же человек?",
    "bib_gender_mismatch": "Личный номер у человека другого пола",
    "relinked": "ФИ в протоколе изменилось — выступление ушло к другому человеку",
    "manual_name_changed": "Ручная привязка, а ФИ в протоколе теперь другое",
}
APPLICANT_KINDS = ("bd_conflict", "applicant_ambiguous", "applicant_city_mismatch", "applicant_unconfirmed")


class PersonsError(Exception):
    """Ошибка, которую админ видит как есть."""


class PersonsUnavailable(PersonsError):
    """БД недоступна — роутер отвечает 503."""


@contextlib.contextmanager
def _connection():
    conn = get_siberman_connection()
    if conn is None:
        raise PersonsUnavailable("БД недоступна")
    try:
        yield conn
    finally:
        conn.close()


@contextlib.contextmanager
def _locked_tx(conn):
    cur = conn.cursor(buffered=True)
    cur.execute("SELECT GET_LOCK(%s, 10)", (LOCK_NAME,))
    if cur.fetchone()[0] != 1:
        raise PersonsError("Реестр занят другой операцией — повторите через несколько секунд")
    try:
        conn.start_transaction()
        try:
            yield
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
    finally:
        cur.execute("SELECT RELEASE_LOCK(%s)", (LOCK_NAME,))
        cur.fetchall()


def _fio(row: Optional[dict]) -> str:
    return f"{row['surname']} {row['name']}".strip() if row else "—"


# ── синхронизация ────────────────────────────────────────────────────────────

def sync(conn) -> dict:
    """Привязать новые выступления, записать ДР из заявок, убрать устаревшие автопривязки и людей
    без выступлений. Идемпотентна: повторный запуск ничего не меняет."""
    with _locked_tx(conn):
        reg = Registry(pdb.load_persons(conn))
        rows = pdb.load_participant_rows(conn)
        names = {natkey(r): plain_key(r["surname"], r["name"]) for r in rows}
        new_links, reviews = link_participants(reg, rows, pdb.load_links(conn))
        for p in reg.new:
            p.id = pdb.insert_person(conn, {"surname": p.surname, "name": p.name, "gender": p.gender,
                                            "bib_individual": p.bib_individual, "city": p.city})
        for p in reg.bib_assigned:
            pdb.update_person(conn, p.id, {"bib_individual": p.bib_individual})
        pdb.set_links(conn, [(k, p.id, names[k]) for k, p in new_links.items()], manual=False)
        pdb.delete_links(conn, reg.dropped)
        bd_updates, bd_reviews = attach_birthdates(reg, pdb.load_applicants(conn))
        for p, bd in bd_updates:
            pdb.update_person(conn, p.id, {"birthdate": bd})
        added = pdb.add_reviews(conn, reviews + bd_reviews)
        stale_links, orphans = pdb.delete_stale(conn)
        pdb.refresh_display(conn, {p.id for p in new_links.values()} | {p.id for p in reg.bib_assigned})
    return {"linked": len(new_links), "new_persons": len(reg.new), "birthdates": len(bd_updates),
            "reviews": added, "dropped": len(reg.dropped), "stale_links": stale_links, "orphans": orphans}


def sync_now() -> dict:
    with _connection() as conn:
        return sync(conn)


def sync_safe() -> None:
    """Хвост каждой загрузки результатов (recompute_totals_ranks_records). Своё соединение;
    ошибки реестра (в т.ч. не применённая миграция 014) приём данных гонки не ломают."""
    conn = get_siberman_connection()
    if conn is None:
        return
    try:
        if pdb.count_unlinked(conn):
            log.info("[persons] sync: %s", sync(conn))
    except Exception as e:
        log.warning(f"[persons] sync пропущен: {e}")
    finally:
        conn.close()


def import_applicants(data: bytes) -> dict:
    """CSV заявок Тильды → siberman_applicants, затем синхронизация (ДР людям)."""
    try:
        apps, stats = parse_applicants_csv(data)
    except ValueError as e:
        raise PersonsError(str(e)) from None
    with _connection() as conn:
        with _locked_tx(conn):
            pdb.upsert_applicants(conn, apps)
        return {**stats, "sync": sync(conn)}
```

- [ ] **Step 4: Тесты проходят**

Run: `conda run -n base python -m pytest tests/integration/test_siberman_persons.py -q`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add src/siberman/persons/service.py tests/integration/test_siberman_persons.py
git commit -m "feat(siberman/persons): синхронизация реестра и импорт заявок Тильды"
```

---

### Task 6: Хвост загрузки результатов + скрипт первичного заполнения

**Files:**
- Modify: `src/siberman/service.py` (конец `recompute_totals_ranks_records`)
- Modify: `tests/conftest.py`
- Create: `scripts/siberman_persons_init.py`

- [ ] **Step 1: В тестах `sync_safe` — no-op**

В `tests/conftest.py` после фикстуры `_no_real_notifications` добавить:
```python
@pytest.fixture(autouse=True)
def _no_persons_sync_on_recompute(monkeypatch):
    """recompute_totals_ranks_records() хвостом синхронизирует реестр людей Siberman своим
    соединением с БД — в unit-тестах с моками это лишнее. Тесты реестра вызывают service.sync()."""
    monkeypatch.setattr("src.siberman.persons.service.sync_safe", lambda: None)
```

- [ ] **Step 2: Хвост в `recompute_totals_ranks_records`**

В `src/siberman/service.py` последней строкой тела `recompute_totals_ranks_records` (после цикла записи рекордов, на уровне тела функции) добавить:
```python
    # Реестр людей: новые выступления года → к людям (спецификация hall §3.3). Своё соединение,
    # ошибки реестра приём результатов не ломают. Импорт внутри — без циклического импорта.
    from src.siberman.persons import service as persons_service
    persons_service.sync_safe()
```
Перед правкой прочитать функцию целиком и убедиться, что у неё нет ранних `return` (если есть — вставить вызов перед каждым).

- [ ] **Step 3: Скрипт первичного заполнения**

`scripts/siberman_persons_init.py`:
```python
"""
Реестр людей Siberman: первичное заполнение по архиву и загрузка выгрузок заявок Тильды.

    python scripts/siberman_persons_init.py                      # только синхронизация
    python scripts/siberman_persons_init.py заявки1.csv заявки2.csv

Печатает только числа (без ФИО и дат рождения).
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")
load_dotenv(ROOT / ".env.local", override=True)  # локально — MySQL на 3308, на проде файла нет

from src.siberman.persons import service  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("csv", nargs="*", help="CSV-выгрузки заявок Тильды")
    args = ap.parse_args()
    for path in args.csv:
        print(path, service.import_applicants(Path(path).read_bytes()))
    if not args.csv:
        print(service.sync_now())


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Unit-тесты не сломаны**

Run: `conda run -n base python -m pytest tests/unit/ -q`
Expected: всё PASS, число тестов = 903 + 38 = 941.

- [ ] **Step 5: Commit**

```bash
git add src/siberman/service.py tests/conftest.py scripts/siberman_persons_init.py
git commit -m "feat(siberman/persons): синхронизация реестра после каждой загрузки результатов + скрипт заполнения"
```

---

### Task 6a: Ревью задач 4–6 — синхронизация по отпечатку протокола, лок на перезапись года

1. **Critical.** `sync_safe` запускал синхронизацию только при непривязанных строках. Все пути загрузки сохраняют ключ (год, номер, этап) — переименование, стёртая фамилия, удалённая строка не давали непривязанных, и защиты 3a–3c срабатывали только по кнопке. Теперь — по отпечатку протокола (`COUNT` + `BIT_XOR(CRC32(...))` по участникам): изменился → синхронизация.
2. **Important.** Загрузка Excel удаляет строки года и вставляет заново (секунды, autocommit). Синхронизация из другого воркера в этот момент увидела бы полупустой протокол и через `delete_stale` удалила привязки и людей. Теперь `apply_to_db` держит лок реестра на время перезаписи (`protocol_rewrite`), а автосинхронизация лок не ждёт — пропускает цикл.
3. Мелочи: ожидание лока параметром (`wait_s`), предупреждение «таблиц нет» — один раз на воркер, очистка в тестах — только тестовые люди; `count_unlinked` больше не нужен.

**Files:**
- Modify: `src/siberman/persons/db.py`, `src/siberman/persons/service.py`, `src/siberman/service.py` (`apply_to_db`), `tests/integration/test_siberman_persons.py`

- [ ] **Step 1: Тесты**

В `tests/integration/test_siberman_persons.py`:
1. В `_clean` последнюю команду заменить на (не трогать людей вне тестов):
```python
    cur.execute("DELETE s FROM siberman_persons s LEFT JOIN siberman_person_links l ON l.person_id=s.id "
                "WHERE l.person_id IS NULL AND s.surname LIKE 'Тестреестров%%'")
```
2. В конец файла:
```python
def test_auto_sync_notices_renamed_relay_member(conn):
    _ins(conn, YEAR, 9101, "Тестреестрова", "Анна", fmt="relay", stage="swim", gender="F", team="Тест")
    service.sync(conn)
    old = _pid(conn, YEAR, 9101, "swim")
    service.auto_sync()                                   # запомнить отпечаток протокола
    assert service.auto_sync() is None                    # протокол не менялся — синхронизации нет
    conn.cursor().execute("UPDATE participants SET surname='Тестреестров', name='Пётр', gender='M' "
                          "WHERE race_year=%s AND bib='9101'", (YEAR,))
    assert service.auto_sync() is not None
    assert _pid(conn, YEAR, 9101, "swim") != old
    kinds = [r["kind"] for r in pdb.list_reviews(conn, "open") if r["race_year"] == YEAR]
    assert "relinked" in kinds


def test_auto_sync_skips_while_protocol_is_rewritten(conn):
    _ins(conn, YEAR, 9001, "Тестреестров", "Олег")
    other = get_siberman_connection()
    try:
        with service.protocol_rewrite(other):
            assert service.auto_sync() is None
            assert _pid(conn, YEAR, 9001) is None
    finally:
        other.close()
    assert service.auto_sync() is not None and _pid(conn, YEAR, 9001) is not None
```

- [ ] **Step 2: Тесты падают**

Run: `C:\Users\podbo\miniconda3\python.exe -m pytest tests/integration/test_siberman_persons.py -q -p no:cacheprovider`
Expected: 5 passed, 2 failed (`AttributeError: ... 'auto_sync'`).

- [ ] **Step 3: `db.py`**

Функцию `count_unlinked` удалить и на её место поставить:
```python
def protocol_fingerprint(conn) -> tuple:
    """Отпечаток протокола: меняется при вставке, удалении или правке ФИ, пола, формата строки."""
    cur = _cur(conn)
    cur.execute("SELECT COUNT(*) AS n, BIT_XOR(CRC32(CONCAT_WS('|', race_year, bib, relay_stage, surname, name, "
                "gender, format))) AS x FROM participants")
    r = cur.fetchone()
    return (int(r["n"]), int(r["x"] or 0))
```

- [ ] **Step 4: `persons/service.py`**

1. После класса `PersonsUnavailable` добавить:
```python
class PersonsBusy(PersonsError):
    """Реестр занят (перезапись протокола или другая синхронизация)."""
```
2. `_locked_tx` — ожидание лока параметром, занятый лок → `PersonsBusy`:
```python
@contextlib.contextmanager
def _locked_tx(conn, wait_s: int = 10):
    cur = conn.cursor(buffered=True)
    cur.execute("SELECT GET_LOCK(%s, %s)", (LOCK_NAME, wait_s))
    if cur.fetchone()[0] != 1:
        raise PersonsBusy("Реестр занят другой операцией — повторите через несколько секунд")
    try:
        conn.start_transaction()
        try:
            yield
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
    finally:
        cur.execute("SELECT RELEASE_LOCK(%s)", (LOCK_NAME,))
        cur.fetchall()
```
3. `sync` — сигнатура `def sync(conn, wait_s: int = 10) -> dict:` и `with _locked_tx(conn, wait_s):` (тело без изменений).
4. `sync_safe` заменить на:
```python
_last_fingerprint = None   # отпечаток протокола после последней успешной синхронизации (на воркер)
_warned = False


def auto_sync():
    """Синхронизация после загрузки результатов — только если протокол изменился с прошлого раза
    (вставки, удаления, правки ФИ) и реестр не занят. Ошибки — в лог (предупреждение один раз на воркер,
    например пока миграция 014 не применена). → результат sync или None."""
    global _last_fingerprint, _warned
    conn = get_siberman_connection()
    if conn is None:
        return None
    try:
        fp = pdb.protocol_fingerprint(conn)
        if fp == _last_fingerprint:
            return None
        result = sync(conn, wait_s=0)
        _last_fingerprint = fp
        log.info("[persons] sync: %s", result)
        return result
    except PersonsBusy:
        return None   # идёт перезапись протокола или другая синхронизация — следующий цикл доделает
    except Exception as e:
        (log.debug if _warned else log.warning)(f"[persons] sync пропущен: {e}")
        _warned = True
        return None
    finally:
        conn.close()


def sync_safe() -> None:
    """Хвост каждой загрузки результатов (recompute_totals_ranks_records); в тестах подменяется no-op."""
    auto_sync()


@contextlib.contextmanager
def protocol_rewrite(conn):
    """Держать реестр, пока строки года удаляются и вставляются заново (загрузка Excel): синхронизация
    из другого воркера не увидит полупустой протокол и не удалит привязки и людей. Лок не взят за
    30 с — загрузка всё равно идёт (результаты гонки важнее), просто без защиты."""
    cur = conn.cursor(buffered=True)
    cur.execute("SELECT GET_LOCK(%s, 30)", (LOCK_NAME,))
    got = cur.fetchone()[0] == 1
    try:
        yield
    finally:
        if got:
            cur.execute("SELECT RELEASE_LOCK(%s)", (LOCK_NAME,))
            cur.fetchall()
```

- [ ] **Step 5: `apply_to_db` (`src/siberman/service.py`)**

В `apply_to_db` взять в `with protocol_rewrite(conn):` участок от `clear_race_year(conn, result.race_year)` до конца цикла `for p in result.participants:` со вставкой участников, времён и транзитов (блок «Пересчитать тоталы/ранги/рекорды» и вызов `recompute_totals_ranks_records` — ВНЕ `with`: хвост синхронизации берёт лок своим соединением). Импорт — в начале тела функции, рядом с подключением:
```python
    from src.siberman.persons.service import protocol_rewrite  # внутри: без циклического импорта
```
Отступы участка увеличить на один уровень, логику не менять. Перед правкой прочитать функцию целиком.

- [ ] **Step 6: Тесты проходят**

Run: `C:\Users\podbo\miniconda3\python.exe -m pytest tests/integration/test_siberman_persons.py -q -p no:cacheprovider` — 7 passed.
Run: `C:\Users\podbo\miniconda3\python.exe -m pytest tests/unit/ -q -p no:cacheprovider` — 941 passed (тесты `apply_to_db` с моками не должны упасть; если упали из-за `protocol_rewrite` на мок-соединении — сообщить, не подгонять).

- [ ] **Step 7: Commit**

```bash
git add src/siberman/persons/db.py src/siberman/persons/service.py src/siberman/service.py tests/integration/test_siberman_persons.py
git commit -m "fix(siberman/persons): автосинхронизация по отпечатку протокола, лок реестра на перезапись года"
```

---

### Task 7: Ручные решения, отмена, карточки, поиск, «проверить»

**Files:**
- Modify: `src/siberman/persons/service.py` (дописать в конец)
- Modify: `tests/integration/test_siberman_persons.py` (дописать в конец)

- [ ] **Step 1: Тесты**

```python
def test_reassign_to_new_person_and_undo(conn):
    _ins(conn, YEAR, 9101, "Тестреестрова", "Анна", fmt="relay", stage="swim", gender="F", team="Тест")
    _ins(conn, Y2, 9102, "Тестреестрова", "Анна", fmt="relay", stage="run", gender="F", team="Тест")
    service.sync(conn)
    old = _pid(conn, YEAR, 9101, "swim")
    assert _pid(conn, Y2, 9102, "run") == old
    res = service.reassign([[Y2, "9102", "run"]], None, "test")
    assert _pid(conn, Y2, 9102, "run") == res["person_id"] != old
    card = service.person_card(res["person_id"])
    assert [p["manual"] for p in card["participations"]] == [1]
    service.undo(res["audit_id"], "test")
    assert _pid(conn, Y2, 9102, "run") == old
    assert pdb.get_person(conn, res["person_id"]) is None


def test_merge_and_undo(conn):
    _ins(conn, YEAR, 9101, "Тестреестрова", "Анна", fmt="relay", stage="swim", gender="F", team="Тест")
    _ins(conn, Y2, 9102, "Тестреестрова-Кузина", "Анна", fmt="relay", stage="run", gender="F", team="Тест")
    service.sync(conn)
    a, b = _pid(conn, YEAR, 9101, "swim"), _pid(conn, Y2, 9102, "run")
    assert a != b
    res = service.merge(b, a, "test")
    assert _pid(conn, Y2, 9102, "run") == a and pdb.get_person(conn, b) is None
    service.undo(res["audit_id"], "test")
    assert _pid(conn, Y2, 9102, "run") == b and pdb.get_person(conn, b)["surname"] == "Тестреестрова-Кузина"


def test_merge_refuses_two_individual_bibs(conn):
    _ins(conn, YEAR, 9001, "Тестреестров", "Иван")
    _ins(conn, Y2, 9002, "Тестреестров", "Иван")
    service.sync(conn)
    with pytest.raises(service.PersonsError):
        service.merge(_pid(conn, Y2, 9002), _pid(conn, YEAR, 9001), "test")


def test_undo_is_blocked_by_later_action_on_same_person(conn):
    _ins(conn, YEAR, 9001, "Тестреестров", "Олег")
    service.sync(conn)
    pid = _pid(conn, YEAR, 9001)
    first = service.set_birthdate(pid, datetime.date(1980, 1, 1), "test")
    second = service.set_birthdate(pid, datetime.date(1980, 1, 2), "test")
    with pytest.raises(service.PersonsError):
        service.undo(first["audit_id"], "test")
    service.undo(second["audit_id"], "test")
    service.undo(first["audit_id"], "test")
    assert pdb.get_person(conn, pid)["birthdate"] is None


def test_reviews_search_and_journal(conn):
    _ins(conn, YEAR, 9001, "Тестреестров", "Олег")
    _ins(conn, Y2, 9002, "Тестреестров", "Олег")
    _ins(conn, Y3, 9103, "Тестреестров", "Олег", fmt="relay", stage="bike", team="Тест")
    service.sync(conn)
    mine = [r for r in service.reviews("open") if r["participant"] and r["participant"]["year"] == Y3]
    assert [r["kind"] for r in mine] == ["namesake_candidate"]
    assert len(mine[0]["others"]) == 2 and mine[0]["title"]
    service.set_review_status(mine[0]["id"], "deferred", "test")
    assert all(r["id"] != mine[0]["id"] for r in service.reviews("open"))
    found = service.search("Тестреестров Олег")
    assert len(found) >= 3 and all("birthdate" in f for f in found)
    pid = _pid(conn, YEAR, 9001)
    service.set_birthdate(pid, datetime.date(1980, 1, 1), "test")
    assert any("Тестреестров" in j["summary"] for j in service.journal())


def test_keep_link_confirms_new_name(conn):
    _ins(conn, YEAR, 9101, "Тестреестрова", "Анна", fmt="relay", stage="swim", gender="F", team="Тест")
    service.sync(conn)
    pid = _pid(conn, YEAR, 9101, "swim")
    service.reassign([[YEAR, "9101", "swim"]], pid, "test")          # теперь привязка ручная
    conn.cursor().execute("UPDATE participants SET surname='Тестреестрова-Кузина' "
                          "WHERE race_year=%s AND bib='9101'", (YEAR,))
    service.sync(conn)

    def mine():
        return [r for r in service.reviews("open")
                if r["kind"] == "manual_name_changed" and r["participant"] and r["participant"]["year"] == YEAR]
    assert len(mine()) == 1 and _pid(conn, YEAR, 9101, "swim") == pid
    service.keep_link(mine()[0]["id"], "test")
    service.sync(conn)
    assert mine() == [] and _pid(conn, YEAR, 9101, "swim") == pid
```

- [ ] **Step 2: Тесты падают**

Run: `conda run -n base python -m pytest tests/integration/test_siberman_persons.py -q`
Expected: 7 passed, 6 failed (`AttributeError: module ... has no attribute 'reassign'` и т.п.).

- [ ] **Step 3: Реализация (дописать в `service.py`)**

```python
# ── журнал-снимки ────────────────────────────────────────────────────────────

def _plain(row: Optional[dict]) -> Optional[dict]:
    if row is None:
        return None
    return {k: (v.isoformat() if isinstance(v, (datetime.date, datetime.datetime)) else v) for k, v in row.items()}


def _snapshot(conn, person_ids, keys: list) -> dict:
    person_ids = sorted({int(i) for i in person_ids if i is not None})
    persons = pdb.get_persons(conn, person_ids)
    links = pdb.links_for_keys(conn, keys)
    return {"persons": {str(i): _plain(persons.get(i)) for i in person_ids},
            "links": [[k[0], k[1], k[2], links.get(tuple(k))] for k in keys]}


def _record(conn, action: str, summary: str, snap: dict, user: str) -> int:
    scope = {f"p:{i}" for i in snap["persons"]} | {f"k:{y}/{b}/{s}" for y, b, s, _ in snap["links"]}
    return pdb.add_audit(conn, action, summary, snap, scope, user)


def _restore(conn, snap: dict) -> None:
    """Вернуть людей и привязки к снимку «до»: сначала освободить личные номера (уникальность),
    затем люди, привязки, удалить созданных действием, вернуть номера."""
    persons = {int(k): v for k, v in snap["persons"].items()}
    now = pdb.get_persons(conn, persons)
    for pid in now:
        pdb.update_person(conn, pid, {"bib_individual": None})
    for pid, row in persons.items():
        if row is None:
            continue
        fields = {k: row[k] for k in ("surname", "name", "gender", "birthdate", "city", "country")}
        if pid in now:
            pdb.update_person(conn, pid, fields)
        else:
            pdb.insert_person(conn, {**fields, "id": pid})
    pdb.delete_links(conn, [(y, b, s) for y, b, s, link in snap["links"] if link is None])
    for y, b, s, link in snap["links"]:
        if link is not None:
            pdb.set_links(conn, [((y, b, s), link["person_id"], link["name_key"])], manual=bool(link["manual"]))
    for pid, row in persons.items():
        if row is None and pid in now:
            pdb.delete_person(conn, pid)
    for pid, row in persons.items():
        if row and row["bib_individual"]:
            pdb.update_person(conn, pid, {"bib_individual": row["bib_individual"]})


def undo(audit_id: int, user: str) -> dict:
    with _connection() as conn, _locked_tx(conn):
        a = pdb.get_audit(conn, audit_id)
        if not a:
            raise PersonsError("Действие не найдено")
        if a["undone_at"]:
            raise PersonsError("Действие уже отменено")
        later = pdb.later_conflicts(conn, audit_id, set(filter(None, a["scope"].split(","))))
        if later:
            raise PersonsError("Сначала отмените более поздние действия по этим людям: "
                               + ", ".join(f"#{i}" for i in later))
        payload = a["payload"]
        _restore(conn, json.loads(payload) if isinstance(payload, (str, bytes, bytearray)) else payload)
        pdb.mark_undone(conn, audit_id, user)
    return {"ok": True}


# ── ручные решения ───────────────────────────────────────────────────────────

def merge(source_id: int, target_id: int, user: str) -> dict:
    """Все выступления source → target, source удаляется (тот же человек под разными ФИ)."""
    if int(source_id) == int(target_id):
        raise PersonsError("Это один и тот же человек")
    with _connection() as conn, _locked_tx(conn):
        persons = pdb.get_persons(conn, [source_id, target_id])
        src, dst = persons.get(int(source_id)), persons.get(int(target_id))
        if not src or not dst:
            raise PersonsError("Человек не найден — обновите страницу")
        if src["bib_individual"] and dst["bib_individual"]:
            raise PersonsError(f"У обоих свой личный номер (№{src['bib_individual']} и №{dst['bib_individual']}) — "
                               "по правилам Siberman это разные люди")
        snap = _snapshot(conn, [source_id, target_id], pdb.links_of_person(conn, source_id))
        pdb.move_links(conn, source_id, target_id)
        pdb.delete_person(conn, source_id)
        pdb.update_person(conn, target_id, {"bib_individual": dst["bib_individual"] or src["bib_individual"],
                                            "birthdate": dst["birthdate"] or src["birthdate"]})
        pdb.refresh_display(conn, [target_id])
        audit_id = _record(conn, "merge", f"Слиты: {_fio(src)} (id {source_id}) → {_fio(dst)} (id {target_id})",
                           snap, user)
    return {"ok": True, "person_id": int(target_id), "audit_id": audit_id}


def reassign(keys: list, target_id: Optional[int], user: str) -> dict:
    """Выступления keys → человеку target_id или новому (target_id=None). Личный номер переходит
    вместе со стартами под ним."""
    keys = sorted({(int(k[0]), str(k[1]), str(k[2])) for k in keys})
    if not keys:
        raise PersonsError("Не выбраны выступления")
    with _connection() as conn, _locked_tx(conn):
        rows = pdb.participants_by_keys(conn, keys)
        if len(rows) != len(keys):
            raise PersonsError("Выступление не найдено — обновите страницу")
        before = pdb.links_for_keys(conn, keys)
        old_ids = sorted({v["person_id"] for v in before.values()})
        ind_bibs = sorted({b for _, b, s in keys if s == "none"})
        if len(ind_bibs) > 1:
            raise PersonsError("Выбраны личные старты под разными номерами — переносите по одному номеру")
        bib = ind_bibs[0] if ind_bibs else None
        holder = pdb.person_by_bib(conn, bib) if bib else None
        target = None
        if target_id is not None:
            target = pdb.get_person(conn, target_id)
            if not target:
                raise PersonsError(f"Человек id {target_id} не найден")
            if bib and target["bib_individual"] and target["bib_individual"] != bib:
                raise PersonsError(f"У человека id {target_id} другой личный номер (№{target['bib_individual']})")
        if holder and holder["id"] != target_id:
            rest = [k for k in pdb.links_of_person(conn, holder["id"]) if k[1] == bib and k[2] == "none" and k not in keys]
            if rest:
                raise PersonsError(f"Под №{bib} этот человек выступал и в {', '.join(str(k[0]) for k in rest)} — "
                                   "перенесите все годы с этим номером")
        snap = _snapshot(conn, old_ids + [target_id] + ([holder["id"]] if holder else []), keys)
        if holder and holder["id"] != target_id:
            pdb.update_person(conn, holder["id"], {"bib_individual": None})
        last = max(rows, key=lambda r: r["race_year"])
        if target_id is None:
            target_id = pdb.insert_person(conn, {"surname": last["surname"], "name": last["name"],
                                                 "gender": last["gender"] if last["gender"] in ("M", "F") else None,
                                                 "city": last["city"] or "", "country": last["country"] or ""})
            snap["persons"][str(target_id)] = None
        if bib:
            pdb.update_person(conn, target_id, {"bib_individual": bib})
        names = {(int(r["race_year"]), str(r["bib"]), r["relay_stage"]): plain_key(r["surname"], r["name"]) for r in rows}
        pdb.set_links(conn, [(k, target_id, names[k]) for k in keys], manual=True)
        gone = pdb.delete_orphans(conn, old_ids)
        pdb.refresh_display(conn, [i for i in set(old_ids) | {target_id} if i not in gone])
        audit_id = _record(conn, "reassign", f"{len(keys)} выступл. ({_fio(last)}) → id {target_id}", snap, user)
    return {"ok": True, "person_id": int(target_id), "audit_id": audit_id}


def set_birthdate(person_id: int, value: Optional[datetime.date], user: str) -> dict:
    with _connection() as conn, _locked_tx(conn):
        p = pdb.get_person(conn, person_id)
        if not p:
            raise PersonsError("Человек не найден")
        snap = _snapshot(conn, [person_id], [])
        pdb.update_person(conn, person_id, {"birthdate": value})
        audit_id = _record(conn, "birthdate",
                           f"ДР {_fio(p)} (id {person_id}): {p['birthdate'] or '—'} → {value or '—'}", snap, user)
    return {"ok": True, "audit_id": audit_id}


def set_review_status(review_id: int, status: str, user: str) -> dict:
    if status not in REVIEW_STATUSES:
        raise PersonsError(f"Неизвестный статус «{status}»")
    with _connection() as conn, _locked_tx(conn):
        if not pdb.set_review_status(conn, review_id, status, user):
            raise PersonsError("Запись не найдена")
    return {"ok": True}


def keep_link(review_id: int, user: str) -> dict:
    """«Оставить привязку» по записи о выступлении: привязка становится ручной с текущим ФИ строки
    (подтверждённое написание попадает в ключи человека, следующая смена ФИ снова будет замечена)."""
    with _connection() as conn, _locked_tx(conn):
        r = pdb.get_review(conn, review_id)
        if not r or not r["race_year"]:
            raise PersonsError("Запись не найдена")
        k = (int(r["race_year"]), str(r["bib"]), r["relay_stage"])
        rows = pdb.participants_by_keys(conn, [k])
        link = pdb.links_for_keys(conn, [k]).get(k)
        if not rows or not link:
            raise PersonsError("Выступление не найдено — обновите страницу")
        pdb.set_links(conn, [(k, link["person_id"], plain_key(rows[0]["surname"], rows[0]["name"]))], manual=True)
        pdb.set_review_status(conn, review_id, "resolved", user)
    return {"ok": True}


# ── чтение для админки ───────────────────────────────────────────────────────

def _start(r: dict) -> dict:
    return {"key": [r["race_year"], str(r["bib"]), r["relay_stage"]], "year": r["race_year"], "bib": str(r["bib"]),
            "format": r["format"], "stage": r["relay_stage"], "team": r.get("relay_team_name") or "",
            "fio": f"{r['surname']} {r['name']}".strip(), "status": r.get("status") or "",
            "city": r.get("city") or "", "overall_s": r.get("total_s"), "manual": r.get("manual", 0)}


def _brief(p: Optional[dict], parts: dict) -> Optional[dict]:
    if p is None:
        return None
    return {"id": p["id"], "fio": _fio(p), "bib": p["bib_individual"],
            "birthdate": p["birthdate"].isoformat() if p["birthdate"] else None,
            "city": p["city"], "starts": [_start(r) for r in parts.get(p["id"], [])]}


def reviews(status: str = "open") -> list:
    if status not in REVIEW_STATUSES:
        raise PersonsError(f"Неизвестный статус «{status}»")
    with _connection() as conn:
        rows = pdb.list_reviews(conn, status)
        ids = set()
        for r in rows:
            ids |= {r["person_id"]} | {int(x) for x in r["other_person_ids"].split(",") if x}
        persons = pdb.get_persons(conn, ids)
        parts = pdb.participations(conn, ids)
        keys = [(r["race_year"], r["bib"], r["relay_stage"]) for r in rows if r["race_year"]]
        prow = {(int(p["race_year"]), str(p["bib"]), p["relay_stage"]): p for p in pdb.participants_by_keys(conn, keys)}
        apps = pdb.get_applicants(conn, [r["detail"] for r in rows if r["kind"] in APPLICANT_KINDS])
    out = []
    for r in rows:
        nk = (int(r["race_year"]), str(r["bib"]), r["relay_stage"]) if r["race_year"] else None
        a = apps.get(r["detail"])
        out.append({
            "id": r["id"], "kind": r["kind"], "title": REVIEW_TITLES.get(r["kind"], r["kind"]),
            "status": r["status"], "created_at": r["created_at"],
            "person": _brief(persons.get(r["person_id"]), parts),
            "others": [_brief(persons.get(int(x)), parts) for x in r["other_person_ids"].split(",") if x],
            "participant": _start(prow[nk]) if nk in prow else None,
            "applicant": {"fio": f"{a['surname']} {a['name']}".strip(), "birthdate": a["birthdate"].isoformat(),
                          "city": a["city"]} if a else None,
        })
    return out


def person_card(person_id: int) -> dict:
    with _connection() as conn:
        p = pdb.get_person(conn, person_id)
        if not p:
            raise PersonsError("Человек не найден")
        parts = pdb.participations(conn, [person_id]).get(int(person_id), [])
        open_reviews = pdb.reviews_for_person(conn, person_id)
    return {"person": {"id": int(person_id), **_plain(p)}, "participations": [_start(r) for r in parts],
            "reviews": open_reviews}


def search(q: str) -> list:
    q = " ".join((q or "").split())
    if len(q) < 2 and not q.isdigit():
        return []
    with _connection() as conn:
        rows = pdb.search_persons(conn, q)
    return [{"id": r["id"], "fio": _fio(r), "bib": r["bib_individual"],
             "birthdate": r["birthdate"].isoformat() if r["birthdate"] else None,
             "city": r["city"], "years": r["years"] or ""} for r in rows]


def journal() -> list:
    with _connection() as conn:
        return pdb.list_audit(conn)
```

- [ ] **Step 4: Тесты проходят**

Run: `conda run -n base python -m pytest tests/integration/test_siberman_persons.py -q`
Expected: 13 passed.

- [ ] **Step 5: Commit**

```bash
git add src/siberman/persons/service.py tests/integration/test_siberman_persons.py
git commit -m "feat(siberman/persons): слить/перенести/ДР/статус «проверить», журнал с отменой, карточка и поиск"
```

---

### Task 7a: Ревью задачи 7 — отмена возвращает и записи «проверить», «Оставить привязку» в журнале

1. **Отмена слияния теряла запись «проверить».** FK `ON DELETE SET NULL` обнулял `person_id` записей исходного человека, а статус `resolved`, поставленный кнопкой, не возвращался — вопрос «тот же или тёзка» молча закрывался. Теперь снимок действия хранит и состояние затронутых записей «проверить» (`person_id`, кандидаты, статус), отмена их возвращает; `merge` переносит открытые записи исходного человека на целевого; решение по записи (`review_id`) ставится в той же транзакции, что и действие (`merge`, `reassign`, `set_birthdate`) — одна запись в журнале, одна отмена.
2. **`keep_link` не писался в журнал** — его нельзя было отменить, и он не блокировал отмену более раннего действия по той же привязке. Теперь пишется.
3. Мелочь: `reassign` не удаляет опустевших людей, на которых ссылаются нерешённые записи (как `delete_stale`).

**Files:**
- Modify: `src/siberman/persons/db.py`, `src/siberman/persons/service.py`, `tests/integration/test_siberman_persons.py`
(роутер и JS — в Task 9, их текст в плане уже обновлён под `review_id`)

- [ ] **Step 1: Тесты (в конец `tests/integration/test_siberman_persons.py`)**

```python
def test_undo_merge_reopens_review(conn):
    _ins(conn, YEAR, 9001, "Тестреестров", "Олег")
    _ins(conn, Y2, 9002, "Тестреестров", "Олег")
    _ins(conn, Y3, 9103, "Тестреестров", "Олег", fmt="relay", stage="bike", team="Тест")
    service.sync(conn)
    r = [x for x in service.reviews("open") if x["participant"] and x["participant"]["year"] == Y3][0]
    source, target = r["person"]["id"], r["others"][0]["id"]
    res = service.merge(source, target, "test", review_id=r["id"])
    assert all(x["id"] != r["id"] for x in service.reviews("open"))
    service.undo(res["audit_id"], "test")
    back = [x for x in service.reviews("open") if x["id"] == r["id"]]
    assert back and back[0]["person"]["id"] == source
    assert _pid(conn, Y3, 9103, "bike") == source


def test_keep_link_is_undoable_and_blocks_earlier_undo(conn):
    _ins(conn, YEAR, 9101, "Тестреестрова", "Анна", fmt="relay", stage="swim", gender="F", team="Тест")
    service.sync(conn)
    pid = _pid(conn, YEAR, 9101, "swim")
    first = service.reassign([[YEAR, "9101", "swim"]], pid, "test")
    conn.cursor().execute("UPDATE participants SET surname='Тестреестрова-Кузина' "
                          "WHERE race_year=%s AND bib='9101'", (YEAR,))
    service.sync(conn)
    rv = [r for r in service.reviews("open") if r["kind"] == "manual_name_changed"
          and r["participant"] and r["participant"]["year"] == YEAR][0]
    kept = service.keep_link(rv["id"], "test")
    with pytest.raises(service.PersonsError):
        service.undo(first["audit_id"], "test")
    service.undo(kept["audit_id"], "test")
    link = pdb.links_for_keys(conn, [(YEAR, "9101", "swim")])[(YEAR, "9101", "swim")]
    assert link["name_key"] == "тестреестрова анна"
    assert any(r["id"] == rv["id"] for r in service.reviews("open"))
```

- [ ] **Step 2: Тесты падают**

Run: `C:\Users\podbo\miniconda3\python.exe -m pytest tests/integration/test_siberman_persons.py -q -p no:cacheprovider`
Expected: 13 passed, 2 failed (`TypeError: merge() got an unexpected keyword argument 'review_id'`, `KeyError: 'audit_id'` или `TypeError`).

- [ ] **Step 3: `db.py`**

1. `delete_orphans` — не удалять людей, на которых ссылаются нерешённые записи. Запрос в ней заменить на:
```python
    cur.execute(f"SELECT s.id FROM siberman_persons s LEFT JOIN siberman_person_links l ON l.person_id=s.id "
                f"WHERE s.id IN ({marks}) AND l.person_id IS NULL AND NOT EXISTS (SELECT 1 FROM "
                "siberman_person_reviews r WHERE r.status <> 'resolved' AND "
                "(r.person_id = s.id OR FIND_IN_SET(s.id, r.other_person_ids)))", args)
```
2. В раздел «проверить» (после `reviews_for_person`) добавить:
```python
REVIEW_STATE = ("person_id", "other_person_ids", "status", "resolved_at", "resolved_by")


def reviews_state(conn, person_ids, review_ids=()) -> list:
    """Состояние записей «проверить», затронутых действием: где человек — основной или кандидат,
    плюс явно названные записи. Для снимка отмены."""
    ids = sorted({int(i) for i in person_ids if i is not None})
    rids = sorted({int(i) for i in review_ids if i is not None})
    conds, args = [], []
    for i in ids:
        conds.append("(person_id=%s OR FIND_IN_SET(%s, other_person_ids))")
        args += [i, str(i)]
    if rids:
        conds.append(f"id IN ({','.join(['%s'] * len(rids))})")
        args += rids
    if not conds:
        return []
    cur = _cur(conn)
    cur.execute(f"SELECT id, {', '.join(REVIEW_STATE)} FROM siberman_person_reviews WHERE {' OR '.join(conds)}", args)
    return cur.fetchall()


def restore_reviews(conn, rows: list) -> None:
    cur = conn.cursor()
    for r in rows:
        cur.execute(f"UPDATE siberman_person_reviews SET {', '.join(f'{k}=%s' for k in REVIEW_STATE)} WHERE id=%s",
                    [r[k] for k in REVIEW_STATE] + [int(r["id"])])


def move_reviews(conn, source_id: int, target_id: int) -> None:
    """Слияние: открытые и отложенные записи исходного человека — на целевого (FK обнулил бы их)."""
    conn.cursor().execute("UPDATE siberman_person_reviews SET person_id=%s WHERE person_id=%s AND status <> 'resolved'",
                          (int(target_id), int(source_id)))
```

- [ ] **Step 4: `service.py`**

1. `_snapshot` — с записями «проверить»:
```python
def _snapshot(conn, person_ids, keys: list, review_ids=()) -> dict:
    person_ids = sorted({int(i) for i in person_ids if i is not None})
    persons = pdb.get_persons(conn, person_ids)
    links = pdb.links_for_keys(conn, keys)
    return {"persons": {str(i): _plain(persons.get(i)) for i in person_ids},
            "links": [[k[0], k[1], k[2], links.get(tuple(k))] for k in keys],
            "reviews": [_plain(r) for r in pdb.reviews_state(conn, person_ids, review_ids)]}
```
2. `_record` — scope с записями:
```python
def _record(conn, action: str, summary: str, snap: dict, user: str) -> int:
    scope = ({f"p:{i}" for i in snap["persons"]} | {f"k:{y}/{b}/{s}" for y, b, s, _ in snap["links"]}
             | {f"r:{r['id']}" for r in snap.get("reviews", [])})
    return pdb.add_audit(conn, action, summary, snap, scope, user)
```
3. В `_restore` после цикла, восстанавливающего привязки (`for y, b, s, link in snap["links"]: … set_links …`), и ДО цикла, удаляющего созданных действием людей, добавить:
```python
    pdb.restore_reviews(conn, snap.get("reviews", []))
```
4. `merge` — сигнатура `def merge(source_id: int, target_id: int, user: str, review_id: Optional[int] = None) -> dict:`; снимок `_snapshot(conn, [source_id, target_id], pdb.links_of_person(conn, source_id), [review_id])`; сразу после `pdb.move_links(conn, source_id, target_id)` добавить `pdb.move_reviews(conn, source_id, target_id)`; перед `audit_id = _record(...)` добавить:
```python
        if review_id is not None:
            pdb.set_review_status(conn, review_id, "resolved", user)
```
5. `reassign` — сигнатура `def reassign(keys: list, target_id: Optional[int], user: str, review_id: Optional[int] = None) -> dict:`; снимок `_snapshot(conn, old_ids + [target_id] + ([holder["id"]] if holder else []), keys, [review_id])`; перед `audit_id = _record(...)` — тот же блок `if review_id is not None: pdb.set_review_status(...)`.
6. `set_birthdate` — сигнатура `def set_birthdate(person_id: int, value: Optional[datetime.date], user: str, review_id: Optional[int] = None) -> dict:`; снимок `_snapshot(conn, [person_id], [], [review_id])`; перед `audit_id = _record(...)` — тот же блок.
7. `keep_link` заменить:
```python
def keep_link(review_id: int, user: str) -> dict:
    """«Оставить привязку» по записи о выступлении: привязка становится ручной с текущим ФИ строки
    (подтверждённое написание попадает в ключи человека, следующая смена ФИ снова будет замечена).
    Пишется в журнал — отменяется, как остальные решения."""
    with _connection() as conn, _locked_tx(conn):
        r = pdb.get_review(conn, review_id)
        if not r or not r["race_year"]:
            raise PersonsError("Запись не найдена")
        k = (int(r["race_year"]), str(r["bib"]), r["relay_stage"])
        rows = pdb.participants_by_keys(conn, [k])
        link = pdb.links_for_keys(conn, [k]).get(k)
        if not rows or not link:
            raise PersonsError("Выступление не найдено — обновите страницу")
        snap = _snapshot(conn, [link["person_id"]], [k], [review_id])
        pdb.set_links(conn, [(k, link["person_id"], plain_key(rows[0]["surname"], rows[0]["name"]))], manual=True)
        pdb.set_review_status(conn, review_id, "resolved", user)
        audit_id = _record(conn, "keep_link", f"Привязка оставлена с новым ФИ: {_fio(rows[0])} ({k[0]}, №{k[1]})",
                           snap, user)
    return {"ok": True, "audit_id": audit_id}
```

- [ ] **Step 5: Тесты проходят**

Run: интеграционные — 15 passed; `tests/unit/` — 941 passed.

- [ ] **Step 6: Commit**

```bash
git add src/siberman/persons/db.py src/siberman/persons/service.py tests/integration/test_siberman_persons.py
git commit -m "fix(siberman/persons): отмена возвращает записи «проверить», «Оставить привязку» в журнале"
```

---

### Task 8: Счётчик финишей — по человеку

**Files:**
- Modify: `src/siberman/finish_counts.py`
- Modify: `src/siberman/db.py` (`get_results_for_year`, новые функции рядом с `get_finished_years_by_name`)
- Test: `tests/unit/test_siberman_finish_counts.py`, `tests/integration/test_siberman_persons.py`

- [ ] **Step 1: Unit-тесты**

Дописать в `tests/unit/test_siberman_finish_counts.py`:
```python
from src.siberman.finish_counts import finish_count_for


def test_finish_count_by_person_when_linked():
    by_person = {5: {2020, 2021, 2025}}
    assert finish_count_for(5, "Кто-то", "Другой", 2025, by_person, {}) == 2


def test_linked_person_without_finishes_is_zero_not_name_fallback():
    by_name = {"иванов иван": {2020}}
    assert finish_count_for(9, "Иванов", "Иван", 2025, {}, by_name) == 0


def test_unlinked_falls_back_to_name():
    by_name = {"иванов иван": {2020, 2021}}
    assert finish_count_for(None, "Иванов", "Иван", 2025, {}, by_name) == 2
```

- [ ] **Step 2: Тесты падают**

Run: `conda run -n base python -m pytest tests/unit/test_siberman_finish_counts.py -q`
Expected: FAIL — `ImportError: cannot import name 'finish_count_for'`.

- [ ] **Step 3: Реализация**

В конец `src/siberman/finish_counts.py`:
```python
def finish_count_for(
    person_id,
    surname: str,
    name: str,
    race_year: int,
    finished_years_by_person: dict,
    finished_years_by_name: dict,
) -> int:
    """Финиши ДО race_year: по человеку из реестра (тёзки не смешиваются), а если выступление
    ещё не привязано (до первой синхронизации или без миграции 014) — по ФИ, как раньше."""
    if person_id is not None:
        return sum(1 for y in finished_years_by_person.get(person_id, ()) if y < race_year)
    return get_finish_count(surname, name, race_year, finished_years_by_name)
```

В `src/siberman/db.py`:
1. Импорт: `from src.siberman.finish_counts import get_finish_count, person_key` → `from src.siberman.finish_counts import finish_count_for, get_finish_count, person_key`. `import mysql.connector` в файле уже есть.
2. После `get_finished_years_by_name` добавить:
```python
def get_finished_years_by_person(conn) -> dict[int, set[int]]:
    """person_id → годы, где личник финишировал (то же условие, что get_finished_years_by_name).
    Нет таблиц реестра (миграция 014 не применена) — пусто: счёт по ФИ."""
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("""
            SELECT DISTINCT p.race_year, l.person_id
            FROM participants p
            JOIN siberman_person_links l
              ON l.race_year=p.race_year AND l.bib=p.bib AND l.relay_stage=p.relay_stage
            JOIN checkpoint_times ct ON ct.participant_id = p.id
            JOIN checkpoints c ON c.id = ct.checkpoint_id
            WHERE p.format='individual' AND p.status='active'
              AND c.stage='run' AND c.seq=12 AND ct.cumulative_s IS NOT NULL
        """)
    except mysql.connector.Error:
        return {}
    result: dict[int, set[int]] = {}
    for row in cur.fetchall():
        result.setdefault(row["person_id"], set()).add(row["race_year"])
    return result


def get_person_ids_for_year(conn, race_year: int) -> dict[str, int]:
    """Личный номер года → человек реестра. Нет таблиц реестра — пусто."""
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT bib, person_id FROM siberman_person_links WHERE race_year=%s AND relay_stage='none'",
                    (race_year,))
    except mysql.connector.Error:
        return {}
    return {str(r["bib"]): r["person_id"] for r in cur.fetchall()}
```
3. В `get_results_for_year` после `finished_years_by_name = get_finished_years_by_name(conn)` добавить:
```python
    finished_years_by_person = get_finished_years_by_person(conn)
    person_ids = get_person_ids_for_year(conn, race_year)
```
и заменить строку
```python
        p["finish_count"] = get_finish_count(p["surname"], p["name"], race_year, finished_years_by_name)
```
на
```python
        p["finish_count"] = finish_count_for(person_ids.get(str(p["bib"])), p["surname"], p["name"],
                                             race_year, finished_years_by_person, finished_years_by_name)
```

- [ ] **Step 4: Интеграционный тест — на архиве числа не изменились**

Дописать в `tests/integration/test_siberman_persons.py`:
```python
def test_finish_counts_on_archive_match_name_based(conn):
    """После синхронизации реестра «N-й финиш» в архиве такой же, как при подсчёте по ФИ
    (в архиве нет тёзок-личников). Различия печатаются без ФИО — год и номер."""
    from src.siberman.db import get_finished_years_by_name, get_results_for_year
    from src.siberman.finish_counts import get_finish_count
    service.sync(conn)
    by_name = get_finished_years_by_name(conn)
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT race_year FROM participants WHERE race_year < 2090 ORDER BY race_year")
    diffs = []
    for (year,) in cur.fetchall():
        for p in get_results_for_year(conn, year)["individual"]:
            if p["finish_count"] != get_finish_count(p["surname"], p["name"], year, by_name):
                diffs.append((year, p["bib"]))
    assert diffs == []
```
(`get_results_for_year` возвращает личников под ключом `"individual"` — проверено при планировании.)

- [ ] **Step 5: Тесты проходят**

Run: `conda run -n base python -m pytest tests/unit/test_siberman_finish_counts.py tests/integration/test_siberman_persons.py -q`
Expected: все PASS. Если `test_finish_counts_on_archive_match_name_based` падает — НЕ подгонять тест: вывести только список (год, номер) и разобрать с пользователем (возможно, это Заволокина/Князева, у которой разные номера в разных годах).

- [ ] **Step 6: Commit**

```bash
git add src/siberman/finish_counts.py src/siberman/db.py tests/unit/test_siberman_finish_counts.py tests/integration/test_siberman_persons.py
git commit -m "feat(siberman/persons): «N-й финиш» по человеку из реестра, по ФИ — только для непривязанных"
```

---

### Task 9: API админки и страница «Люди»

**Files:**
- Create: `src/siberman/persons/router.py`
- Modify: `src/krasmarafon/router.py` (рядом с подключением `siberman_draw_router`)
- Create: `templates/siberman/people_admin.html`
- Create: `static/js/siberman-people-admin.js`
- Modify: `templates/siberman/admin.html:74-78`, `templates/siberman/draw_admin.html` (вкладки)
- Test: `tests/integration/test_siberman_persons.py`

- [ ] **Step 1: Тест API**

Дописать в `tests/integration/test_siberman_persons.py`:
```python
def test_admin_api_requires_auth_and_works(conn):
    from fastapi.testclient import TestClient
    from app import app
    from src.core.auth import api_require_auth
    client = TestClient(app)
    assert client.get("/api/siberman/admin/people/reviews").status_code == 401
    _ins(conn, YEAR, 9001, "Тестреестров", "Олег")
    service.sync(conn)
    app.dependency_overrides[api_require_auth] = lambda: "test"
    try:
        r = client.get("/api/siberman/admin/people/search", params={"q": "Тестреестров"})
        assert r.status_code == 200 and r.json()
        pid = _pid(conn, YEAR, 9001)
        assert client.get(f"/api/siberman/admin/people/{pid}").json()["person"]["id"] == pid
        r = client.post(f"/api/siberman/admin/people/{pid}/birthdate", json={"birthdate": "1980-01-01"})
        assert r.status_code == 200
        assert client.post("/api/siberman/admin/people/merge", json={"source_id": pid, "target_id": pid}).status_code == 409
        assert client.get("/api/siberman/admin/people/journal").status_code == 200
    finally:
        app.dependency_overrides.clear()
```

- [ ] **Step 2: Тест падает**

Run: `conda run -n base python -m pytest tests/integration/test_siberman_persons.py::test_admin_api_requires_auth_and_works -q`
Expected: FAIL — 404 вместо 401.

- [ ] **Step 3: Роутер**

`src/siberman/persons/router.py`:
```python
"""
Админка реестра людей Siberman: страница /admin/people и API /api/siberman/admin/people/*.
API — обычные def: блокирующий mysql-connector уходит в пул потоков. Статичные пути объявлены
раньше /{person_id}, иначе FastAPI сопоставит 'search' с параметром.
"""
import datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel

from src.core.auth import api_require_auth, require_auth_for
from src.siberman.persons import service
from src.siberman.persons.service import PersonsError, PersonsUnavailable
from src.siberman.router import templates

router = APIRouter(tags=["Siberman persons"])
_page_auth = require_auth_for("/login")
NO_STORE = {"Cache-Control": "no-store"}
MAX_CSV_BYTES = 10 * 1024 * 1024
API = "/api/siberman/admin/people"


class MergeIn(BaseModel):
    source_id: int
    target_id: int
    review_id: Optional[int] = None      # решение по записи «проверить» — в той же транзакции


class ReassignIn(BaseModel):
    keys: list[tuple[int, str, str]]
    target_id: Optional[int] = None
    review_id: Optional[int] = None


class BirthdateIn(BaseModel):
    birthdate: Optional[datetime.date] = None
    review_id: Optional[int] = None


class ReviewStatusIn(BaseModel):
    status: str


def _json(data, status: int = 200) -> JSONResponse:
    return JSONResponse(jsonable_encoder(data), status_code=status, headers=NO_STORE)


def _run(fn, *args, **kwargs) -> JSONResponse:
    try:
        return _json(fn(*args, **kwargs))
    except PersonsError as e:
        return _json({"detail": str(e)}, 503 if isinstance(e, PersonsUnavailable) else 409)


@router.get("/admin/people", response_class=HTMLResponse)
async def people_admin_page(request: Request, user=Depends(_page_auth)):
    if isinstance(user, RedirectResponse):
        return user
    if getattr(request.state, "domain", "") != "siberman":
        raise HTTPException(status_code=404)
    return templates.TemplateResponse("siberman/people_admin.html", {"request": request})


@router.get(f"{API}/reviews")
def api_reviews(status: str = "open", user: str = Depends(api_require_auth)):
    return _run(service.reviews, status)


@router.post(f"{API}/reviews/{{review_id}}")
def api_review_status(review_id: int, body: ReviewStatusIn, user: str = Depends(api_require_auth)):
    return _run(service.set_review_status, review_id, body.status, user)


@router.post(f"{API}/reviews/{{review_id}}/keep")
def api_keep_link(review_id: int, user: str = Depends(api_require_auth)):
    return _run(service.keep_link, review_id, user)


@router.get(f"{API}/search")
def api_search(q: str = "", user: str = Depends(api_require_auth)):
    return _run(service.search, q)


@router.get(f"{API}/journal")
def api_journal(user: str = Depends(api_require_auth)):
    return _run(service.journal)


@router.post(f"{API}/merge")
def api_merge(body: MergeIn, user: str = Depends(api_require_auth)):
    return _run(service.merge, body.source_id, body.target_id, user, body.review_id)


@router.post(f"{API}/reassign")
def api_reassign(body: ReassignIn, user: str = Depends(api_require_auth)):
    return _run(service.reassign, [list(k) for k in body.keys], body.target_id, user, body.review_id)


@router.post(f"{API}/undo/{{audit_id}}")
def api_undo(audit_id: int, user: str = Depends(api_require_auth)):
    return _run(service.undo, audit_id, user)


@router.post(f"{API}/sync")
def api_sync(user: str = Depends(api_require_auth)):
    return _run(service.sync_now)


@router.post(f"{API}/applicants")
def api_applicants(file: UploadFile = File(...), user: str = Depends(api_require_auth)):
    data = file.file.read(MAX_CSV_BYTES + 1)
    if len(data) > MAX_CSV_BYTES:
        return _json({"detail": "Файл больше 10 МБ"}, 413)
    return _run(service.import_applicants, data)


@router.get(f"{API}/{{person_id}}")
def api_person(person_id: int, user: str = Depends(api_require_auth)):
    return _run(service.person_card, person_id)


@router.post(f"{API}/{{person_id}}/birthdate")
def api_birthdate(person_id: int, body: BirthdateIn, user: str = Depends(api_require_auth)):
    return _run(service.set_birthdate, person_id, body.birthdate, user, body.review_id)
```

В `src/krasmarafon/router.py` после строк подключения `siberman_draw_router` добавить:
```python
from src.siberman.persons.router import router as siberman_persons_router
router.include_router(siberman_persons_router)
```

- [ ] **Step 4: Тест API проходит**

Run: `conda run -n base python -m pytest tests/integration/test_siberman_persons.py -q`
Expected: все PASS.

- [ ] **Step 5: Страница**

`templates/siberman/people_admin.html`:
```html
<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Siberman — Люди</title>
<link rel="icon" href="/static/images/siberman/favicon.ico" sizes="any">
<style>
* { box-sizing: border-box; }
body { margin: 0; background: #f7f7f7; color: #1a1a1a; font-family: system-ui, sans-serif; }
.header { background: #1a1a1a; color: #fff; padding: 14px 24px; display: flex; gap: 20px; align-items: center; }
.header h1 { font-size: 18px; margin: 0; flex: 1; color: #fff; }
.hlink { color: #ddd; text-decoration: none; font-size: 14px; }
.container { max-width: 1280px; margin: 20px auto; padding: 0 20px; }
.admin-tabs { display: flex; gap: 4px; margin-bottom: 16px; border-bottom: 1px solid #ddd; flex-wrap: wrap; }
.admin-tab { padding: 10px 18px; border: none; background: transparent; color: #555; font-size: 15px; font-weight: 600; cursor: pointer; border-bottom: 2px solid transparent; }
.admin-tab--active { color: #c0392b; border-bottom-color: #c0392b; }
.tab-content { display: none; } .tab-content.active { display: block; }
.msg { display: none; padding: 10px 14px; border-radius: 6px; margin-bottom: 12px; font-size: 15px; }
.msg-ok { background: #eafaf1; color: #1e8449; border: 1px solid #a9dfbf; }
.msg-error { background: #fdecea; color: #b71c1c; border: 1px solid #f5c6c2; }
.card { background: #fff; color: #1a1a1a; border-radius: 8px; padding: 16px 20px; margin-bottom: 12px; box-shadow: 0 1px 3px rgba(0,0,0,.08); }
.card h2 { font-size: 16px; margin: 0 0 10px; }
.rtitle { font-weight: 700; margin-bottom: 6px; }
.pboxes { display: flex; gap: 10px; flex-wrap: wrap; margin: 8px 0; }
.pbox { flex: 1 1 260px; border: 1px solid #e0e0e0; border-radius: 6px; padding: 8px 10px; font-size: 14px; background: #fafafa; }
.plabel { font-size: 11px; text-transform: uppercase; color: #777; letter-spacing: .5px; }
.muted { color: #666; font-size: 13px; }
.row { margin: 10px 0; display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.search { width: 100%; padding: 12px 14px; font-size: 18px; background: #fff; color: #1a1a1a; border: 2px solid #1a1a1a; border-radius: 6px; }
.res { padding: 10px 12px; background: #fff; color: #1a1a1a; border: 1px solid #e0e0e0; border-top: 0; cursor: pointer; font-size: 15px; }
.res:hover { background: #fff3c4; }
.tbl { width: 100%; border-collapse: collapse; font-size: 14px; margin: 8px 0; }
.tbl td, .tbl th { padding: 6px 8px; border-top: 1px solid #eee; text-align: left; color: #1a1a1a; }
.tbl th { color: #666; font-weight: 600; font-size: 12px; }
.tag { background: #fff8e1; color: #6b4e00; border-radius: 3px; padding: 0 4px; font-size: 11px; }
.journal { background: #fff; border: 1px solid #e0e0e0; border-radius: 6px; max-height: 600px; overflow: auto; }
.jrow { padding: 8px 10px; border-bottom: 1px solid #f0f0f0; font-size: 14px; color: #1a1a1a; }
.jrow.cancelled b { text-decoration: line-through; color: #888; }
input, select { font: inherit; padding: 6px 8px; border: 1px solid #bbb; border-radius: 6px; background: #fff; color: #1a1a1a; }
.btn { padding: 9px 18px; border-radius: 6px; border: 1px solid #888; background: #fff; color: #1a1a1a; font-weight: 600; cursor: pointer; }
.btn-primary { background: #c0392b; border-color: #c0392b; color: #fff; }
.btn-small { padding: 5px 10px; font-size: 13px; border: 1px solid #888; background: #fff; color: #1a1a1a; border-radius: 4px; cursor: pointer; }
.btn-small.danger { border-color: #c62828; color: #c62828; }
.btn-small.active { background: #1a1a1a; color: #fff; border-color: #1a1a1a; }
a[data-card] { color: #1565c0; }
.report { background: #fff; border: 1px solid #e0e0e0; border-radius: 6px; padding: 10px; white-space: pre-wrap; color: #1a1a1a; }
</style>
</head>
<body>
<div class="header">
  <h1>Siberman · Люди</h1>
  <a href="/admin" class="hlink">← Админка</a>
  <a href="/logout" class="hlink">Выйти</a>
</div>
<div class="container">
  <div class="admin-tabs">
    <button class="admin-tab admin-tab--active" data-tab="reviews">Проверить <span id="reviews-count"></span></button>
    <button class="admin-tab" data-tab="search">Люди</button>
    <button class="admin-tab" data-tab="journal">Журнал</button>
    <button class="admin-tab" data-tab="import">Заявки и пересборка</button>
  </div>
  <div id="msg" class="msg"></div>

  <section id="tab-reviews" class="tab-content active">
    <div class="row">
      <button class="btn-small active" data-status="open">Открытые</button>
      <button class="btn-small" data-status="deferred">Отложенные</button>
      <button class="btn-small" data-status="resolved">Решённые</button>
    </div>
    <div id="reviews"></div>
  </section>

  <section id="tab-search" class="tab-content">
    <input id="search" class="search" placeholder="Фамилия, имя, личный номер или id человека" autocomplete="off">
    <div id="results"></div>
    <div id="card" style="margin-top:12px"></div>
  </section>

  <section id="tab-journal" class="tab-content">
    <div id="journal" class="journal"></div>
  </section>

  <section id="tab-import" class="tab-content">
    <div class="card">
      <h2>Заявки Тильды → даты рождения</h2>
      <p class="muted">CSV-выгрузка заявок с Тильды (как есть). Сохраняются только ФИ, пол, дата рождения, город и номер заявки — телефоны, e-mail и тексты не сохраняются. После загрузки привязки пересобираются.</p>
      <div class="row"><input type="file" id="csv" accept=".csv,text/csv"> <button class="btn btn-primary" id="upload">Загрузить</button></div>
    </div>
    <div class="card">
      <h2>Пересобрать привязки</h2>
      <p class="muted">Привязать новые выступления к людям и дописать даты рождения. Ручные решения не меняются.</p>
      <button class="btn" id="sync">Пересобрать</button>
    </div>
    <div id="report" class="report" style="display:none"></div>
  </section>
</div>
<script src="/static/js/siberman-people-admin.js?v={{ v }}"></script>
</body>
</html>
```

- [ ] **Step 6: JS**

`static/js/siberman-people-admin.js`:
```js
'use strict';
// Админка реестра людей Siberman (/admin/people): «проверить», поиск и карточка человека,
// журнал с отменой, загрузка заявок Тильды. API: /api/siberman/admin/people/*.

const API = '/api/siberman/admin/people';
const STAGES = { none: 'личный', swim: 'плавание', bike: 'вело', run: 'бег' };
let reviewStatus = 'open';
let reviewsCache = [];
let card = null;
let searchTimer = null;

function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

async function api(path, opts = {}) {
  const headers = opts.body && !(opts.body instanceof FormData) ? { 'Content-Type': 'application/json' } : {};
  const r = await fetch(API + path, { credentials: 'same-origin', ...opts, headers });
  if (r.status === 401) { location.href = '/login?next=/admin/people'; throw new Error('auth'); }
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || ('Ошибка ' + r.status));
  return data;
}
const post = (path, body) => api(path, { method: 'POST', body: body instanceof FormData ? body : JSON.stringify(body || {}) });

function msg(text, kind = 'ok') {
  const el = document.getElementById('msg');
  el.className = 'msg msg-' + kind;
  el.textContent = text;
  el.style.display = 'block';
}

async function act(fn, okText) {
  try {
    await fn();
    if (okText) msg(okText);
    await refreshAll();
  } catch (e) {
    if (e.message !== 'auth') msg(e.message, 'error');
  }
}

function startText(s) {
  return s.format === 'individual'
    ? `${s.year} личный №${esc(s.bib)}`
    : `${s.year} эстафета №${esc(s.bib)}, ${esc(STAGES[s.stage])} «${esc(s.team)}»`;
}

function personBox(p, label) {
  if (!p) return `<div class="pbox muted">${esc(label)}: человека уже нет (слит с другим)</div>`;
  return `<div class="pbox"><div class="plabel">${esc(label)}</div>
    <b><a href="#" data-card="${p.id}">${esc(p.fio)}</a></b> · id ${p.id}${p.bib ? ' · личный №' + esc(p.bib) : ''}
    <div class="muted">ДР ${esc(p.birthdate || '—')} · ${esc(p.city || '')}</div>
    <div class="muted">${(p.starts || []).map(startText).join('; ')}</div></div>`;
}

function reviewButtons(r) {
  const B = (label, action, cls = '') => `<button class="btn-small ${cls}" data-act="${esc(action)}">${esc(label)}</button>`;
  const out = [];
  const bd = r.applicant ? r.applicant.birthdate : '';
  if (r.kind === 'namesake_candidate') {
    r.others.forEach(o => { if (o && r.person) out.push(B(`Это ${o.fio} (id ${o.id})`, `merge:${r.person.id}:${o.id}`)); });
    out.push(B('Это другой человек', 'resolve'));
  } else if (r.kind === 'relinked') {
    r.others.forEach(o => { if (o && r.person) out.push(B(`Тот же человек: слить с ${o.fio} (id ${o.id})`, `merge:${r.person.id}:${o.id}`)); });
    out.push(B('Разные люди', 'resolve'));
  } else if (r.kind === 'manual_name_changed') {
    out.push(B('Оставить привязку', 'keep'));
    if (r.participant) out.push(B('Отделить в нового человека', 'split'));
  } else if (r.kind === 'gender_mismatch') {
    r.others.forEach(o => { if (o && r.person) out.push(B(`Это ${o.fio} (id ${o.id})`, `merge:${r.person.id}:${o.id}`)); });
    out.push(B('Это другой человек', 'resolve'));
  } else if (r.kind === 'bib_name_change' || r.kind === 'format_switch' || r.kind === 'bib_gender_mismatch') {
    out.push(B('Тот же человек', 'resolve'));
    if (r.participant) out.push(B('Другой человек — отделить', 'split'));
  } else if (r.kind === 'bd_conflict' && r.person) {
    out.push(B(`Оставить ${r.person.birthdate || '—'}`, 'resolve'));
    if (bd) out.push(B(`Заменить на ${bd}`, `bd:${r.person.id}:${bd}`));
    out.push(B('Это заявка тёзки', 'resolve'));
  } else if (r.kind === 'applicant_ambiguous') {
    r.others.forEach(o => { if (o && bd) out.push(B(`ДР у ${o.fio} (id ${o.id})`, `bd:${o.id}:${bd}`)); });
    out.push(B('Ни у кого из них', 'resolve'));
  } else if ((r.kind === 'applicant_city_mismatch' || r.kind === 'applicant_unconfirmed') && r.person) {
    if (bd) out.push(B('Это он — записать ДР', `bd:${r.person.id}:${bd}`));
    out.push(B('Не он', 'resolve'));
  }
  out.push(r.status === 'open' ? B('Отложить', 'defer') : B('Вернуть в «проверить»', 'reopen'));
  return out.join(' ');
}

async function loadReviews() {
  reviewsCache = await api(`/reviews?status=${reviewStatus}`);
  document.getElementById('reviews-count').textContent = reviewStatus === 'open' ? `(${reviewsCache.length})` : '';
  const box = document.getElementById('reviews');
  if (!reviewsCache.length) { box.innerHTML = '<div class="muted">Пусто</div>'; return; }
  box.innerHTML = reviewsCache.map((r, i) => `<div class="card">
    <div class="rtitle">${esc(r.title)}</div>
    ${r.participant ? `<div>${startText(r.participant)} — ${esc(r.participant.fio)}, ${esc(r.participant.city)}</div>` : ''}
    ${r.applicant ? `<div>Заявка: ${esc(r.applicant.fio)}, ДР ${esc(r.applicant.birthdate)}, ${esc(r.applicant.city)}</div>` : ''}
    <div class="pboxes">${r.person ? personBox(r.person, ['namesake_candidate', 'gender_mismatch', 'relinked'].includes(r.kind) ? 'Сейчас — отдельный человек' : 'Человек') : ''}${r.others.map(o => personBox(o, 'Кандидат')).join('')}</div>
    <div data-i="${i}">${reviewButtons(r)}</div></div>`).join('');
}

async function onReviewAction(r, action) {
  const done = () => post(`/reviews/${r.id}`, { status: 'resolved' });
  if (action === 'resolve') return act(done, 'Отмечено как решённое');
  if (action === 'defer') return act(() => post(`/reviews/${r.id}`, { status: 'deferred' }), 'Отложено');
  if (action === 'keep') return act(() => post(`/reviews/${r.id}/keep`), 'Привязка подтверждена с новым ФИ');
  if (action === 'reopen') return act(() => post(`/reviews/${r.id}`, { status: 'open' }), 'Возвращено в «проверить»');
  // Действие и решение по записи — одним запросом (одна запись в журнале, одна отмена)
  if (action === 'split') {
    return act(() => post('/reassign', { keys: [r.participant.key], target_id: null, review_id: r.id }),
      'Выступление отделено в нового человека');
  }
  const [kind, a, b] = action.split(':');
  if (kind === 'merge') {
    return act(() => post('/merge', { source_id: +a, target_id: +b, review_id: r.id }), 'Слито');
  }
  if (kind === 'bd') {
    return act(() => post(`/${a}/birthdate`, { birthdate: b, review_id: r.id }), 'Дата рождения записана');
  }
}

async function openCard(id) {
  try {
    card = await api(`/${id}`);
    showTab('search');
    renderCard();
  } catch (e) {
    if (e.message !== 'auth') msg(e.message, 'error');
  }
}

function selectedKeys() {
  return [...document.querySelectorAll('#card input[data-k]:checked')].map(c => card.participations[+c.dataset.k].key);
}

function renderCard() {
  const el = document.getElementById('card');
  if (!card) { el.innerHTML = ''; return; }
  const p = card.person;
  el.innerHTML = `<div class="card">
    <h2>${esc(p.surname)} ${esc(p.name)} <span class="muted">id ${p.id}${p.bib_individual ? ' · личный №' + esc(p.bib_individual) : ''} · ${esc(p.city)}${p.country ? ', ' + esc(p.country) : ''}</span></h2>
    <div class="row">Дата рождения <input type="date" id="bd" value="${esc(p.birthdate || '')}">
      <button class="btn-small" id="bd-save">Сохранить</button>
      ${card.reviews.length ? `<span class="tag">в «проверить»: ${card.reviews.length}</span>` : ''}</div>
    <table class="tbl"><tr><th></th><th>Год</th><th>Формат</th><th>№</th><th>ФИ в протоколе</th><th>Статус</th><th>Город</th></tr>
    ${card.participations.map((x, i) => `<tr><td><input type="checkbox" data-k="${i}"></td><td>${x.year}</td>
      <td>${x.format === 'individual' ? 'личный' : 'эстафета, ' + esc(STAGES[x.stage]) + ' «' + esc(x.team) + '»'}</td>
      <td>${esc(x.bib)}</td><td>${esc(x.fio)}${x.manual ? ' <span class="tag">вручную</span>' : ''}</td>
      <td>${esc(x.status)}</td><td>${esc(x.city)}</td></tr>`).join('')}</table>
    <div class="row">Отмеченные выступления: <button class="btn-small" id="mv-new">в нового человека</button>
      или к человеку id <input id="mv-id" type="number" min="1" style="width:100px"> <button class="btn-small" id="mv-to">перенести</button></div>
    <div class="row">Слить этого человека с id <input id="mg-id" type="number" min="1" style="width:100px">
      <button class="btn-small danger" id="mg">слить</button>
      <span class="muted">выступления перейдут к указанному, этот человек исчезнет</span></div></div>`;
  document.getElementById('bd-save').onclick = () =>
    act(() => post(`/${p.id}/birthdate`, { birthdate: document.getElementById('bd').value || null }), 'Дата рождения сохранена');
  document.getElementById('mv-new').onclick = () => {
    const keys = selectedKeys();
    if (!keys.length) return msg('Отметьте выступления галочками', 'error');
    act(() => post('/reassign', { keys, target_id: null }), 'Перенесено в нового человека');
  };
  document.getElementById('mv-to').onclick = () => {
    const keys = selectedKeys(), id = +document.getElementById('mv-id').value;
    if (!keys.length || !id) return msg('Отметьте выступления и укажите id человека', 'error');
    act(() => post('/reassign', { keys, target_id: id }), `Перенесено к id ${id}`);
  };
  document.getElementById('mg').onclick = () => {
    const id = +document.getElementById('mg-id').value;
    if (!id) return msg('Укажите id человека', 'error');
    if (!confirm(`Слить «${p.surname} ${p.name}» (id ${p.id}) с id ${id}?`)) return;
    act(async () => { await post('/merge', { source_id: p.id, target_id: id }); card = await api(`/${id}`); }, 'Слито');
  };
}

async function doSearch() {
  const q = document.getElementById('search').value.trim();
  const box = document.getElementById('results');
  if (q.length < 2 && !/^\d+$/.test(q)) { box.innerHTML = ''; return; }
  const rows = await api(`/search?q=${encodeURIComponent(q)}`);
  box.innerHTML = rows.map(r => `<div class="res" data-card="${r.id}"><b>${esc(r.fio)}</b> · id ${r.id}${r.bib ? ' · №' + esc(r.bib) : ''}
    · ДР ${esc(r.birthdate || '—')} · ${esc(r.years)} · ${esc(r.city)}</div>`).join('') || '<div class="muted">Никого</div>';
}

async function loadJournal() {
  const rows = await api('/journal');
  document.getElementById('journal').innerHTML = rows.map(j => `<div class="jrow ${j.undone_at ? 'cancelled' : ''}">
    <span class="muted">${esc(String(j.created_at).replace('T', ' ').slice(0, 16))} · ${esc(j.created_by)}</span>
    <b>${esc(j.summary)}</b>
    ${j.undone_at ? '<span class="muted">отменено</span>' : `<button class="btn-small danger" data-undo="${j.id}">Отменить</button>`}</div>`).join('')
    || '<div class="jrow muted">Пока пусто</div>';
}

async function refreshAll() {
  await loadReviews();
  await loadJournal();
  if (card) {
    try { card = await api(`/${card.person.id}`); } catch (e) { card = null; }
    renderCard();
  }
}

function showTab(name) {
  document.querySelectorAll('.admin-tab').forEach(b => b.classList.toggle('admin-tab--active', b.dataset.tab === name));
  document.querySelectorAll('.tab-content').forEach(s => s.classList.toggle('active', s.id === 'tab-' + name));
}

function report(r) {
  const el = document.getElementById('report');
  const s = r.sync || r;
  const lines = [];
  if (r.rows !== undefined) {
    lines.push(`Строк в файле: ${r.rows}. Людей с датой рождения: ${r.people}. Без даты: ${r.no_birthday}. Неверных дат: ${r.bad_birthday}.`);
  }
  lines.push(`Привязано выступлений: ${s.linked}. Новых людей: ${s.new_persons}. Записано дат рождения: ${s.birthdates}. ` +
             `Новых «проверить»: ${s.reviews}. Снято привязок со стёртой фамилией: ${s.dropped}. ` +
             `Убрано устаревших привязок: ${s.stale_links}, людей без выступлений: ${s.orphans}.`);
  el.textContent = lines.join('\n');
  el.style.display = 'block';
}

document.addEventListener('click', e => {
  const t = e.target;
  const tab = t.closest('.admin-tab');
  if (tab) { showTab(tab.dataset.tab); return; }
  if (t.matches('[data-status]')) {
    reviewStatus = t.dataset.status;
    document.querySelectorAll('[data-status]').forEach(b => b.classList.toggle('active', b === t));
    loadReviews().catch(err => msg(err.message, 'error'));
    return;
  }
  const cardLink = t.closest('[data-card]');
  if (cardLink) { e.preventDefault(); openCard(+cardLink.dataset.card); return; }
  if (t.matches('[data-act]')) {
    const i = +t.closest('[data-i]').dataset.i;
    onReviewAction(reviewsCache[i], t.dataset.act);
    return;
  }
  if (t.matches('[data-undo]')) {
    act(() => post(`/undo/${t.dataset.undo}`), 'Действие отменено');
  }
});

document.getElementById('search').addEventListener('input', () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => doSearch().catch(err => msg(err.message, 'error')), 250);
});

document.getElementById('upload').onclick = async () => {
  const f = document.getElementById('csv').files[0];
  if (!f) return msg('Выберите CSV-файл', 'error');
  const fd = new FormData();
  fd.append('file', f);
  try { report(await post('/applicants', fd)); msg('Заявки загружены'); await refreshAll(); }
  catch (e) { if (e.message !== 'auth') msg(e.message, 'error'); }
};

document.getElementById('sync').onclick = async () => {
  try { report(await post('/sync')); msg('Привязки пересобраны'); await refreshAll(); }
  catch (e) { if (e.message !== 'auth') msg(e.message, 'error'); }
};

refreshAll().catch(e => { if (e.message !== 'auth') msg(e.message, 'error'); });
```

- [ ] **Step 7: Вкладка «Люди» в админке**

`templates/siberman/admin.html` — после строки
`<a class="admin-tab" href="/admin/draw" style="text-decoration:none">Жеребьёвка</a>` добавить:
```html
            <a class="admin-tab" href="/admin/people" style="text-decoration:none">Люди</a>
```
`templates/siberman/draw_admin.html` — в шапке рядом с `<a href="/admin" class="hlink">← Админка</a>` добавить:
```html
  <a href="/admin/people" class="hlink">Люди</a>
```

- [ ] **Step 8: Тесты**

Run: `conda run -n base python -m pytest tests/unit/ tests/integration/test_siberman_persons.py -q`
Expected: все PASS.

- [ ] **Step 9: Commit**

```bash
git add src/siberman/persons/router.py src/krasmarafon/router.py templates/siberman/people_admin.html static/js/siberman-people-admin.js templates/siberman/admin.html templates/siberman/draw_admin.html tests/integration/test_siberman_persons.py
git commit -m "feat(siberman/persons): вкладка «Люди» — проверить, поиск и карточка, журнал, загрузка заявок"
```

---

### Task 10: Первичное заполнение локально, проверка в браузере, документы

**Files:**
- Modify: `docs/superpowers/specs/2026-10-18-siberman-hall-ratings-records-design.md` §3.2
- Modify (основной репозиторий): `.taskmaster/tasks/todo.md`

- [ ] **Step 1: Заполнить реестр на локальном архиве и загрузить обе выгрузки заявок**

Run (из корня worktree):
```bash
conda run -n base python scripts/siberman_persons_init.py
conda run -n base python scripts/siberman_persons_init.py "C:/Users/podbo/Downloads/leads-3efa8a7f9b6289e92d18bfdb8fb0f10eb692eb50066aa4af07f7e6847e814154.csv" "C:/Users/podbo/Downloads/заявки 2028.csv"
```
Expected: печатаются только числа. Сверка с анализом брейншторма (архив 2016–2025): людей ≈ 337 (± тёзки), личников с номером 170, ДР у ≈ 79 человек.

- [ ] **Step 2: Сводка «проверить» по видам (только числа)**

В scratchpad сессии создать и запустить:
```python
import os, sys
sys.path.insert(0, os.getcwd())
from dotenv import load_dotenv
load_dotenv('.env.local', override=True)
from src.siberman.db import get_siberman_connection
c = get_siberman_connection(); cur = c.cursor()
for q in ("SELECT COUNT(*) FROM siberman_persons",
          "SELECT COUNT(*) FROM siberman_persons WHERE bib_individual IS NOT NULL",
          "SELECT COUNT(*) FROM siberman_persons WHERE birthdate IS NOT NULL",
          "SELECT kind, COUNT(*) FROM siberman_person_reviews WHERE status='open' GROUP BY kind"):
    cur.execute(q); print(q[:60], cur.fetchall())
```
Записать числа для отчёта пользователю.

- [ ] **Step 3: Проверка страницы в браузере**

Запустить локальный сервер из корня worktree (скрипт `serve.py` из scratchpad, порт 8011, `run_in_background`). Cookie сессии — через `src.core.auth.create_session_cookie` в файл scratchpad (не печатать). Playwright-скрипт в scratchpad (`channel="chrome"`), домен `siberman.localhost:8011`:
1. `/admin/people` без cookie → редирект на `/login?next=/admin/people`;
2. с cookie: вкладки на месте, «Проверить» показывает карточки (число = сумма открытых из Step 2), ошибок `pageerror` нет;
3. поиск «а» не ищет (меньше 2 символов), поиск по номеру личника из архива находит одного человека, клик открывает карточку;
4. в карточке отметить одно выступление → «в нового человека» → сообщение «Перенесено…», в журнале запись; «Отменить» → сообщение «Действие отменено», выступление снова в карточке;
5. скриншоты вкладок «Проверить» и карточки — в scratchpad, посмотреть глазами.

- [ ] **Step 4: Полный прогон тестов**

Run: `conda run -n base python -m pytest tests/unit/ tests/integration/test_siberman_persons.py -q`
Expected: все PASS; unit — 903 + 41 = 944.

- [ ] **Step 5: Уточнить спецификацию**

В `docs/superpowers/specs/2026-10-18-siberman-hall-ratings-records-design.md` §3.2 заменить пункт про `participants.person_id` / `person_locked` на:
```markdown
- `siberman_person_links (race_year, bib, relay_stage) → person_id, manual` — привязка выступления к человеку по естественному ключу (строки `participants` при загрузке Excel удаляются и вставляются заново — привязка по `participants.id` терялась бы). `manual=1` — ручное решение, синхронизация его не трогает.
```
и в §3.4 строку про `person_locked=1` — на «привязка помечается ручной (`manual=1`)». Добавить в §3.4 виды «проверить»: `format_switch` (эстафета ↔ личный зачёт по ФИ), `applicant_ambiguous`, `applicant_city_mismatch`.

- [ ] **Step 6: Commit**

```bash
git add docs/superpowers/specs/2026-10-18-siberman-hall-ratings-records-design.md
git commit -m "docs(siberman): реестр людей — привязки по (год, номер, этап), виды «проверить»"
```

- [ ] **Step 7: todo.md и отчёт**

В основном репозитории в `.taskmaster/tasks/todo.md` добавить секцию «Siberman: реестр людей (план 1 из 4)» с отмеченными пунктами и ревью (числа из Step 1–2, что проверено в браузере). Отчитаться пользователю: числа, сколько «проверить» по видам, что выкладка на прод — только с его разрешения и после merge жеребьёвки (миграция 014 идёт после 013; деплой кода — после применения миграции, иначе `get_finished_years_by_person` вернёт пусто и счёт останется по ФИ — безопасно, но реестр не заработает).
```

---

## Self-review (сделан при написании плана)

- Спецификация §3.1 — данные в Task 10 Step 1–2; §3.2 — Task 1 (с уточнением про links, Task 10 Step 5); §3.3 — Task 2 (`_resolve`, `attach_birthdates`) + Task 5 (`sync`) + Task 6 (хвост загрузки); §3.4 — Task 7 + Task 9 (поиск, карточка, правка ДР, «тот же/другой человек», отложить, отмена, загрузка заявок); §3.5 — Task 8. ДР наружу: только админские API (`api_require_auth`), публичных API в этом плане нет — проверка «публичные API не содержат birthdate» переходит в планы 2–4.
- Имена согласованы: `plain_key`, `natkey`, `Registry.attach/add/by_bib/by_key/new/bib_assigned`, `link_participants`, `attach_birthdates`, `pdb.*` из Task 4 используются в Task 5/7 с теми же сигнатурами; `finish_count_for(person_id, surname, name, race_year, by_person, by_name)`.
- Отмена «не только последнего действия» — по пересечению scope (как в жеребьёвке), с понятной ошибкой.
