"""
Архив Siberman для рейтинга и рекордов (спецификация hall §4–§5): одна запись на строку
participants за все годы — официальный итог, времена этапов, какие этапы пройдены до последней КТ
своего года, человек из реестра. Эстафеты собираются в команды (год, номер).
"""
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

import mysql.connector

from src.siberman.persons import db as pdb
from src.siberman.persons.linking import plain_key

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
    has_time: bool = False                       # есть хоть одна отметка КТ

    @property
    def fio(self) -> str:
        return f"{self.surname} {self.name}".strip()


BIKE_DAYS = ("bike_day1", "bike_day2")


def race_time(e: Entry) -> Optional[int]:
    """Итог личника, финишировавшего всю гонку: статус active, есть официальный итог и последняя КТ
    каждого этапа (в живом году overall_results пишется и для идущих по дистанции)."""
    if e.format != "individual" or e.status != "active" or not e.overall_s or not set(STAGES) <= e.finished:
        return None
    return e.overall_s


def is_start(e: Entry) -> bool:
    """Вышел на старт: сошёл / снят или есть хоть одна отметка КТ. Статус dns ставят не всегда: в живом
    году Copernico переводит неявившихся в active, а стартовый протокол загружен до гонки."""
    return e.status in ("dnf", "dsq") or (e.status == "active" and e.has_time)


def segment_time(e: Entry, stages: tuple) -> Optional[int]:
    """Время отрезка из этапов stages: участник не сошёл и дошёл до последней КТ каждого этапа.
    Время этапа 0 — не время (архив кладёт весь велоэтап IRONSTAR 2017 на 2-й день); у такого
    участника и «2-й день» — весь велоэтап, поэтому отрезки отдельных дней не считаются."""
    if e.status != "active" or any(s not in e.finished or (e.times.get(s) or 0) <= 0 for s in stages):
        return None
    if len(stages) == 1 and stages[0] in BIKE_DAYS and any((e.times.get(d) or 0) <= 0 for d in BIKE_DAYS):
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
        """Итог команды — сумма этапов: все три этапа на месте, никто не сошёл, каждый дошёл до последней КТ
        своих этапов (в живом году итоги этапов пишутся и у идущих)."""
        if self.status != "active":
            return None
        total = 0
        for role in ROLES:
            m = self.member(role)
            if m is None:
                return None
            for s in ROLE_STAGES[role]:
                if m.times.get(s) is None or s not in m.finished:
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

STARTED_SQL = "SELECT DISTINCT participant_id FROM checkpoint_times WHERE cumulative_s IS NOT NULL"

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
    cur.execute(STARTED_SQL)
    started = {r["participant_id"] for r in cur.fetchall()}
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
            times={s: r[s] for s in STAGES}, finished=frozenset(finished.get(r["id"], ())),
            has_time=r["id"] in started))
    return out


def person_of(e: Entry):
    """Человек выступления: id реестра; без привязки — 'фамилия имя' (как рейтинг и трекер)."""
    return e.person_id or plain_key(e.surname, e.name)


def load_people(conn) -> tuple:
    """Люди реестра и заявки Тильды — для города человека; без таблиц реестра (миграция 014) — пусто."""
    try:
        return pdb.load_persons(conn), pdb.load_applicants(conn)
    except mysql.connector.Error:
        return [], []
