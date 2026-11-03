import datetime as dt

from src.krasmarafon.services.athlete_cabinet import group_by_person, protocol_url

TODAY = dt.date(2026, 11, 3)


def lead(id, surname="Иванов", name="Пётр", client_id=None, date=None, **kw):
    row = dict(id=id, surname=surname, name=name, client_id=client_id, event_id=100 + id,
               event_name="Жара", event_distance="21 км", event_year=2026, event_date=date,
               start_number=None, refund=0, race_status=None, time_clear_finish=None,
               time_gun_finish=None, rank_category=None, rank_category_clean=None)
    row.update(kw)
    return row


def test_groups_by_client_id_then_by_name():
    rows = [lead(1, client_id=7), lead(2, surname="ИВАНОВ", name="Петр", client_id=7),
            lead(3, surname="Иванова", name="Маша"), lead(4, surname="иванова", name="маша")]
    people = group_by_person(rows, TODAY)
    assert sorted(len(p["upcoming"]) + len(p["past"]) for p in people) == [2, 2]


def test_title_from_newest_lead():
    people = group_by_person([lead(1, surname="Иванов", name="Петя", client_id=7),
                              lead(5, surname="Иванов", name="Пётр", client_id=7)], TODAY)
    assert people[0]["title"] == "Иванов Пётр"


def test_upcoming_vs_past_and_sorting():
    rows = [lead(1, date=dt.date(2026, 12, 6)), lead(2, date=dt.date(2026, 11, 3)), lead(3, date=None),
            lead(4, date=dt.date(2026, 7, 12)), lead(5, date=dt.date(2026, 4, 26))]
    p = group_by_person(rows, TODAY)[0]
    assert [e["lead_id"] for e in p["upcoming"]] == [2, 1, 3]
    assert [e["lead_id"] for e in p["past"]] == [4, 5]


def test_result_time_place_and_no_result():
    rows = [lead(1, date=dt.date(2026, 7, 12), race_status="Finished",
                 time_clear_finish=dt.timedelta(hours=1, minutes=42, seconds=15),
                 time_gun_finish=dt.timedelta(hours=1, minutes=43), rank_category=20, rank_category_clean=18),
            lead(2, date=dt.date(2026, 4, 26), race_status="Finished",
                 time_gun_finish=dt.timedelta(minutes=25, seconds=3), rank_category=4),
            lead(3, date=dt.date(2026, 3, 1), race_status="DNF", time_gun_finish=dt.timedelta(minutes=50)),
            lead(4, date=dt.date(2026, 2, 1), refund=1)]
    past = {e["lead_id"]: e for e in group_by_person(rows, TODAY)[0]["past"]}
    assert (past[1]["time"], past[1]["place"]) == ("1:42:15", 18)
    assert (past[2]["time"], past[2]["place"]) == ("0:25:03", 4)
    assert past[3]["time"] is None
    assert past[4]["time"] is None and past[4]["refund"]


def test_people_order_nearest_upcoming_first():
    rows = [lead(1, surname="А", name="А", date=dt.date(2026, 12, 20)),
            lead(2, surname="Б", name="Б", date=dt.date(2026, 12, 6)),
            lead(3, surname="В", name="В", date=dt.date(2026, 7, 1)),
            lead(4, surname="Г", name="Г", date=dt.date(2026, 9, 1))]
    assert [p["title"] for p in group_by_person(rows, TODAY)] == ["Б Б", "А А", "Г Г", "В В"]


def test_protocol_url_known_and_unknown_event():
    url = protocol_url("Жара", 2026, "Иванов", {"Жара": "zhara"})
    assert url == "/results?event=zhara&year=2026&search=%D0%98%D0%B2%D0%B0%D0%BD%D0%BE%D0%B2"
    assert protocol_url("Неизвестный", 2026, "Иванов", {"Жара": "zhara"}) is None
