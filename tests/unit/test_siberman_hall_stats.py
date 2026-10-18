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
