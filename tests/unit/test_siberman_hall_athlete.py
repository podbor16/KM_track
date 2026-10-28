from dataclasses import replace
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
    assert "next_medal" not in p                                   # только полученные медали


def test_participations_places_and_stage_times():
    rows = pages()[1]["participations"]
    assert [r["year"] for r in rows] == [2022, 2021, 2020, 2019]
    dnf, fin, relay, first = rows
    assert (dnf["status"], dnf["dnf_stage"], dnf["finish_no"], dnf["place"]) == ("dnf", "run", None, None)
    assert dnf["times"] == {"swim": 27, "bike": 98, "run": None}             # сошёл на беге: этапы до него есть
    assert (fin["time_s"], fin["finish_no"], fin["place"], fin["record"]) == (180, 2, {"abs": 2, "gender": 2}, False)
    assert relay["stages"] == ["run"] and (relay["team"], relay["time_s"], relay["place"]) == ("Столбы", 165, {"relay": 1})
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


def test_two_stages_of_one_team_is_one_row_and_live_year_racing():
    entries = [rel(2020, 101, "swim", 1, (25,)), rel(2020, 101, "bike", 6, (40, 50)), rel(2020, 101, "run", 1, (50,)),
               ind(2021, 7, 1, None, (28, 45, 55, 0), finished=frozenset({"swim", "bike_day1", "bike_day2"}))]
    teams = build_teams(entries)
    p = build_athletes(entries, teams, build_records(entries, teams), {}, [])[1]
    rows = p["participations"]
    assert [(r["year"], r["format"]) for r in rows] == [(2021, "individual"), (2020, "relay")]
    assert (rows[0]["status"], rows[0]["place"]) == ("racing", None)          # последний год, ещё на дистанции
    assert (rows[1]["stages"], rows[1]["times"]) == (["swim", "run"], {"swim": 25, "run": 50})
    assert p["summary"]["starts"] == 2 and len(p["relay_medals"]) == 1


def test_relay_dnf_stage_is_where_team_dropped():
    entries = [rel(2020, 101, "swim", 1, (25,)),
               replace(rel(2020, 101, "bike", 6, (40, 50)), status="dnf", dnf_stage="bike_day2",
                       finished=frozenset({"bike_day1"})),
               rel(2020, 101, "run", 7, (0,))]
    teams = build_teams(entries)
    row = build_athletes(entries, teams, build_records(entries, teams), {}, [])[1]["participations"][0]
    assert (row["status"], row["dnf_stage"], row["time_s"]) == ("dnf", "bike_day2", None)
