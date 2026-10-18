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
