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
