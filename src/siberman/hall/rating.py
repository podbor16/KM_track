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
