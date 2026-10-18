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


def test_zero_segment_time_is_not_a_time():
    """IRONSTAR 2017: в протоколе нет времени велоэтапа, архив кладёт весь велоэтап на 2-й день,
    1-й день = 0 — это не время отрезка и не рекорд."""
    e = rel(2017, 13, "bike", "Велосипедов", times={"bike_day1": 0, "bike_day2": 73560})
    assert segment_time(e, ("bike_day1",)) is None
    assert segment_time(e, ("bike_day2",)) == 73560
    assert segment_time(e, ("bike_day1", "bike_day2")) is None


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
