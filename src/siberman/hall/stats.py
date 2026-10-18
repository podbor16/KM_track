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
