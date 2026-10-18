from src.siberman.medals import medal_for


def test_medals_by_finish_number():
    assert [medal_for(n)["key"] for n in range(1, 8)] == [
        "silver", "black", "gold", "copper", "chameleon", "hex_black", "hex_silver_red"]
    assert medal_for(12)["key"] == "hex_silver_red"
    assert medal_for(0) is None and medal_for(None) is None
    assert medal_for(None, relay=True)["key"] == "relay_silver"
    assert set(medal_for(3)) == {"key", "name", "color"}
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
