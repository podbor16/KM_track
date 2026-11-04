import datetime as dt
from decimal import Decimal

from src.krasmarafon.services.athlete_history import build_history

TODAY = dt.date(2026, 11, 3)
CODES = {"Жара": "zhara"}


def td(h=0, m=0, s=0):
    return dt.timedelta(hours=h, minutes=m, seconds=s)


def res(id, year=2025, dist="21.1", status="Finished", time=None, gun=None, date=None, event_id=None,
        start_number=None, name="Жара", rank=None, rank_clean=None, **kw):
    row = dict(id=id, client_id=1, event_id=event_id if event_id is not None else 1000 + id,
               start_number=start_number if start_number is not None else id, event_name=name,
               event_year=year, event_date=date if date is not None else dt.date(year, 7, 12),
               event_distance=Decimal(dist) if dist is not None else None, race_status=status,
               time_clear_finish=time, time_gun_finish=gun, rank_category=rank, rank_category_clean=rank_clean,
               category=None, rank_absolute=None, rank_absolute_clean=None,
               finishers_total=None, finishers_category=None)
    row.update(kw)
    return row


def lead(id, year=2026, dist="21.1", date=None, event_id=None, start_number=None, refund=0, name="Жара",
         first="Иван", **kw):
    """name — название события, first — имя участника."""
    row = dict(id=id, client_id=1, event_id=event_id if event_id is not None else 2000 + id,
               start_number=start_number, event_name=name, event_year=year, event_date=date,
               event_distance=Decimal(dist) if dist is not None else None, refund=refund,
               surname="Иванов", name=first, birthday=dt.date(1986, 5, 1), created_at=None, order_id=None,
               amount=None, promocode=None, discount=None, products=None, email=None, ma_email=None)
    row.update(kw)
    return row


def build(results=(), leads=(), diplomas=(), account_email=None):
    return build_history(list(results), list(leads), TODAY, CODES, set(diplomas), account_email)


def test_empty_inputs():
    h = build()
    assert h["since"] is None
    assert h["tiles"] == {"starts": 0, "finishes": 0, "km": 0, "pace": None}
    assert h["records"] == [] and h["dynamics"] == {}
    assert h["results_years"] == [] and h["leads_years"] == []


def test_tiles_starts_finishes_km_pace():
    rows = [res(1, dist="21.1", time=td(1, 45)),
            res(2, dist="10", time=td(0, 50), year=2024),
            res(3, dist="5", status="Not started"),
            res(4, dist="42.2", status="DNF", gun=td(2, 10))]
    t = build(rows)["tiles"]
    assert t["starts"] == 3          # без Not started, DNF — это старт
    assert t["finishes"] == 2
    assert t["km"] == 31             # 21.1 + 10 = 31.1
    # 155 мин / 31.1 км = 4:59 /км (299 с)
    assert t["pace"] == "4:59"


def test_pace_ignores_distances_below_1km():
    rows = [res(1, dist="10", time=td(0, 50)), res(2, dist="0.5", time=td(0, 0, 10), year=2024)]
    t = build(rows)["tiles"]
    assert t["finishes"] == 2
    assert t["pace"] == "5:00"
    assert t["km"] == 11             # 10.5 -> 11 (округление половин вверх)


def test_pace_none_without_finishes():
    assert build([res(1, status="DNF", gun=td(1))])["tiles"]["pace"] is None


def test_finished_without_time_is_not_finish():
    h = build([res(1, status="Finished")])
    assert h["tiles"]["finishes"] == 0 and h["tiles"]["starts"] == 1
    assert h["results_years"][0]["items"][0]["status"] == "нет результата"


def test_time_clear_preferred_over_gun_and_place():
    rows = [res(1, time=td(1, 42, 15), gun=td(1, 43), rank=20, rank_clean=18),
            res(2, year=2024, gun=td(1, 50), rank=7, rank_clean=5)]
    items = {i["year"]: i for y in build(rows)["results_years"] for i in y["items"]}
    assert (items[2025]["time"], items[2025]["place"]) == ("1:42:15", 18)
    assert (items[2024]["time"], items[2024]["place"]) == ("1:50:00", 7)


def test_records_best_per_distance_sorted_desc():
    rows = [res(1, dist="21.1", time=td(1, 50), year=2023),
            res(2, dist="21.1", time=td(1, 45), year=2025),
            res(3, dist="5", time=td(0, 25), year=2024, name="Другой")]
    rec = build(rows)["records"]
    assert [r["distance"] for r in rec] == ["21,1 км", "5 км"]
    assert rec[0] == {"distance": "21,1 км", "time": "1:45:00", "pace": "4:59",
                      "event_name": "Жара", "year": 2025}
    assert (rec[1]["time"], rec[1]["pace"], rec[1]["event_name"]) == ("0:25:00", "5:00", "Другой")


def ms(y, m, d):
    return int(dt.datetime(y, m, d, tzinfo=dt.timezone.utc).timestamp() * 1000)


def test_dynamics_needs_two_finishes():
    assert build([res(1, dist="21.1", time=td(1, 50), year=2025)])["dynamics"] == {}
    same_year = [res(1, dist="21.1", time=td(1, 50), year=2025), res(2, dist="21.1", time=td(1, 45), year=2025,
                                                                      date=dt.date(2025, 9, 6))]
    assert list(build(same_year)["dynamics"]["series"]) == ["21.1"]      # два финиша в один год — уже динамика
    rows = same_year + [res(3, dist="21.1", time=td(1, 55), year=2024), res(4, dist="5", time=td(0, 25), year=2025)]
    d = build(rows)["dynamics"]
    assert d["default"] == "21.1"
    assert list(d["series"]) == ["21.1"]                                   # дистанция 5 км — один финиш
    assert d["series"]["21.1"] == [
        {"t": ms(2024, 7, 12), "s": 6900, "label": "Жара 2024", "date": "12.07.2024"},
        {"t": ms(2025, 7, 12), "s": 6600, "label": "Жара 2025", "date": "12.07.2025"},
        {"t": ms(2025, 9, 6), "s": 6300, "label": "Жара 2025", "date": "06.09.2025"},
    ]                                                                      # каждый финиш, по возрастанию даты


def test_dynamics_point_without_date_is_july_first():
    rows = [res(1, time=td(1, 50), year=2024, date=None), res(2, time=td(1, 45), year=2025)]
    rows[0]["event_date"] = None
    pts = build(rows)["dynamics"]["series"]["21.1"]
    assert pts[0] == {"t": ms(2024, 7, 1), "s": 6600, "label": "Жара 2024", "date": "2024"}


def test_dynamics_default_most_finishes_then_longer():
    rows = [res(1, dist="10", time=td(0, 50), year=2023), res(2, dist="10", time=td(0, 48), year=2024),
            res(3, dist="21.1", time=td(1, 50), year=2023), res(4, dist="21.1", time=td(1, 45), year=2024)]
    assert build(rows)["dynamics"]["default"] == "21.1"       # поровну — бо́льшая дистанция
    rows.append(res(5, dist="10", time=td(0, 47), year=2025))
    assert build(rows)["dynamics"]["default"] == "10"         # больше финишей


def test_distance_key_and_label_for_integer_decimals():
    h = build([res(1, dist="5.00", time=td(0, 25)), res(2, dist="10.0", time=td(0, 50), year=2024)])
    assert [r["distance"] for r in h["records"]] == ["10 км", "5 км"]


def test_lead_and_result_go_to_separate_feeds():
    rows = [res(1, event_id=77, start_number=5, time=td(1, 45))]
    leads = [lead(1, event_id=77, start_number=5, date=dt.date(2025, 7, 12), year=2025)]
    h = build(rows, leads)
    assert [i["time"] for y in h["results_years"] for i in y["items"]] == ["1:45:00"]
    items = [i for y in h["leads_years"] for i in y["items"]]
    assert len(items) == 1 and "time" not in items[0] and items[0]["result_time"] == "1:45:00"
    assert items[0]["status"] is None and items[0]["order"] is not None


def test_past_lead_takes_time_from_result_of_same_card_and_event_regardless_of_number():
    rows = [res(1, event_id=77, start_number=5, time=td(1, 45))]
    leads = [lead(1, event_id=77, start_number=None, date=dt.date(2025, 7, 12), year=2025),
             lead(2, event_id=78, start_number=None, date=dt.date(2025, 9, 1), year=2025)]
    items = {i["date"]: i for y in build(rows, leads)["leads_years"] for i in y["items"]}
    assert items[dt.date(2025, 7, 12)]["result_time"] == "1:45:00" and items[dt.date(2025, 7, 12)]["status"] is None
    assert items[dt.date(2025, 9, 1)]["result_time"] is None and items[dt.date(2025, 9, 1)]["status"] == "не стартовал"


def test_result_of_one_card_does_not_apply_to_lead_of_another_card_in_same_event():
    rows = [res(1, event_id=77, start_number=5, time=td(1, 45))]
    leads = [lead(1, event_id=77, start_number=None, date=dt.date(2025, 7, 12), year=2025) | {"client_id": 2}]
    e = only_item(build(rows, leads), "leads_years")
    assert e["result_time"] is None and e["status"] == "не стартовал"


def test_past_lead_with_unfinished_result_shows_result_status():
    rows = [res(1, event_id=77, status="DNF", gun=td(1))]
    e = only_item(build(rows, [lead(1, event_id=77, date=dt.date(2025, 7, 12), year=2025)]), "leads_years")
    assert e["result_time"] is None and e["status"] == "сошёл"


def test_upcoming_lead_is_ticket():
    h = build(leads=[lead(1, date=dt.date(2026, 12, 6)), lead(2, date=None, year=2026)])
    items = h["leads_years"][0]["items"]
    assert [i["kind"] for i in items] == ["ticket", "ticket"]
    assert items[0]["distance"] == "21,1 км" and items[0]["status"] is None and items[0]["result_time"] is None
    assert h["since"] == 2026 and h["tiles"]["starts"] == 0 and h["results_years"] == []


def test_past_lead_without_result_and_refund():
    h = build(leads=[lead(1, year=2025, date=dt.date(2025, 7, 12)),
                     lead(2, year=2024, date=dt.date(2024, 7, 12), refund=1)])
    by_year = {y["year"]: y["items"][0] for y in h["leads_years"]}
    assert (by_year[2025]["kind"], by_year[2025]["status"]) == ("past", "не стартовал")
    assert (by_year[2024]["status"], by_year[2024]["refund"]) == ("возврат", True)
    assert h["since"] == 2024


def test_result_statuses():
    rows = [res(1, status="Not started", year=2020), res(2, status="DNF", year=2021, gun=td(1)),
            res(3, status="Withdrawn", year=2022), res(4, status="DSQ", year=2023),
            res(5, status="Weird", year=2024), res(6, status=None, year=2019)]
    st = {i["year"]: i["status"] for y in build(rows)["results_years"] for i in y["items"]}
    assert st == {2020: "не стартовал", 2021: "сошёл", 2022: "сошёл", 2023: "дисквалифицирован",
                  2024: "нет результата", 2019: "нет результата"}


def test_finish_entry_fields_pace_protocol_diploma():
    rows = [res(1, event_id=77, start_number=5, time=td(1, 45), rank=3, surname="Иванов")]
    e = build(rows, diplomas={77})["results_years"][0]["items"][0]
    assert e["distance"] == "21,1 км" and e["start_number"] == 5
    assert (e["time"], e["place"], e["pace"], e["status"]) == ("1:45:00", 3, "4:59", None)
    assert e["protocol_url"] == "/results?event=zhara&year=2025&search=%D0%98%D0%B2%D0%B0%D0%BD%D0%BE%D0%B2"
    assert e["diploma_url"] == "/diploma/77/5"
    e2 = build(rows)["results_years"][0]["items"][0]
    assert e2["diploma_url"] is None
    unfinished = build([res(2, status="DNF", gun=td(1), event_id=77, start_number=6)], diplomas={77})
    ne = unfinished["results_years"][0]["items"][0]
    assert ne["protocol_url"] is None and ne["diploma_url"] is None and ne["time"] is None


def test_results_year_and_item_sorting():
    rows = [res(1, year=2024, date=dt.date(2024, 4, 1), time=td(1)), res(2, year=2024, date=dt.date(2024, 9, 1), time=td(1)),
            res(3, year=2025, date=dt.date(2025, 7, 1), time=td(1))]
    years = build(rows)["results_years"]
    assert [y["year"] for y in years] == [2025, 2024]
    assert [i["date"] for i in years[1]["items"]] == [dt.date(2024, 9, 1), dt.date(2024, 4, 1)]


def test_leads_year_and_item_sorting():
    leads = [lead(1, year=2026, date=dt.date(2026, 12, 20)), lead(2, year=2026, date=dt.date(2026, 11, 10)),
             lead(3, year=2026, date=dt.date(2026, 3, 1)), lead(4, year=2024, date=dt.date(2024, 4, 1)),
             lead(5, year=2024, date=dt.date(2024, 9, 1))]
    years = build(leads=leads)["leads_years"]
    assert [y["year"] for y in years] == [2026, 2024]
    assert [i["date"] for i in years[0]["items"]] == [dt.date(2026, 11, 10), dt.date(2026, 12, 20), dt.date(2026, 3, 1)]
    assert [i["kind"] for i in years[0]["items"]] == ["ticket", "ticket", "past"]
    assert [i["date"] for i in years[1]["items"]] == [dt.date(2024, 9, 1), dt.date(2024, 4, 1)]


def test_year_from_date_when_event_year_missing_and_since():
    rows = [res(1, year=None, date=dt.date(2022, 5, 1), time=td(1)), res(2, year=2023, time=td(1), dist="10")]
    h = build(rows)
    assert [y["year"] for y in h["results_years"]] == [2023, 2022]
    assert h["since"] == 2022


def test_since_ignores_not_started_when_starts_exist():
    rows = [res(1, year=2019, status="Not started"), res(2, year=2021, time=td(1))]
    assert build(rows, leads=[lead(1, year=2018, date=dt.date(2018, 7, 1))])["since"] == 2021


def test_missing_distance_does_not_break():
    h = build([res(1, dist=None, time=td(1))])
    assert h["tiles"]["finishes"] == 1 and h["tiles"]["km"] == 0 and h["tiles"]["pace"] is None
    assert h["records"] == [] and h["dynamics"] == {}
    item = h["results_years"][0]["items"][0]
    assert item["distance"] is None and item["pace"] is None


# ---------------------------------------------------------------- доработки: места, возврат, подробности заявки

def only_item(h, feed="results_years"):
    items = [i for y in h[feed] for i in y["items"]]
    assert len(items) == 1
    return items[0]


def test_places_absolute_and_category_out_of_finishers_clean_time():
    r = res(1, time=td(1, 45), gun=td(1, 46), rank=4, rank_clean=3, category="М40-49", rank_absolute=12,
            rank_absolute_clean=10, finishers_total=250, finishers_category=40)
    assert only_item(build([r]))["places"] == ["10/250 абс.", "3/40 М40-49"]


def test_places_use_gun_ranks_without_clear_time():
    r = res(1, gun=td(1, 46), rank=4, rank_clean=3, category="М40-49", rank_absolute=12, rank_absolute_clean=10,
            finishers_total=250, finishers_category=40)
    assert only_item(build([r]))["places"] == ["12/250 абс.", "4/40 М40-49"]


def test_places_without_finisher_counts_keep_plain_format():
    assert only_item(build([res(1, time=td(1), rank_absolute=7)]))["places"] == ["7 абс."]
    assert only_item(build([res(1, time=td(1), rank=2, category="Ж30")]))["places"] == ["2 в Ж30"]
    assert only_item(build([res(1, time=td(1), rank=2)]))["places"] == ["2 место в категории"]
    r = res(1, time=td(1), rank_absolute=7, rank=2, category="Ж30", finishers_total=90)
    assert only_item(build([r]))["places"] == ["7/90 абс.", "2 в Ж30"]          # нет M по категории — как раньше
    r = res(1, time=td(1), rank_absolute=7, rank=2, category="Ж30", finishers_category=15)
    assert only_item(build([r]))["places"] == ["7 абс.", "2/15 Ж30"]            # нет M по событию — только «N абс.»


def test_places_without_category_use_generic_label():
    r = res(1, time=td(1), rank=2, finishers_category=30)
    assert only_item(build([r]))["places"] == ["2/30 в категории"]


def test_places_skip_missing_rank_even_with_counts():
    r = res(1, time=td(1), finishers_total=90, finishers_category=15, category="Ж30")
    assert only_item(build([r]))["places"] == []
    r = res(1, time=td(1), rank=2, category="Ж30", finishers_total=90, finishers_category=15)
    assert only_item(build([r]))["places"] == ["2/15 Ж30"]
    unfinished = res(1, status="DNF", gun=td(1), rank=2, rank_absolute=3, finishers_total=90)
    assert only_item(build([unfinished]))["places"] == []


def test_refund_hidden_when_event_has_active_lead_or_result():
    ev = dict(event_id=77, year=2025, date=dt.date(2025, 7, 12))
    h = build(leads=[lead(1, refund=1, **ev), lead(2, start_number=5, **ev)])
    assert only_item(h, "leads_years")["refund"] is False
    h = build([res(1, event_id=77, start_number=5, time=td(1, 45))], [lead(1, refund=1, start_number=5, **ev)])
    assert h["leads_years"] == []


def test_refund_shown_when_alone_or_other_card_or_other_event():
    ev = dict(year=2025, date=dt.date(2025, 7, 12))
    h = build(leads=[lead(1, refund=1, event_id=77, **ev)])
    assert only_item(h, "leads_years")["status"] == "возврат"
    other_card = lead(2, event_id=77, **ev) | {"client_id": 2}
    other_event = lead(3, event_id=78, **ev)
    items = [i for y in build(leads=[lead(1, refund=1, event_id=77, **ev), other_card, other_event])["leads_years"]
             for i in y["items"]]
    assert sorted(i["refund"] for i in items) == [False, False, True]


def test_two_refunds_same_event_both_stay():
    ev = dict(event_id=77, year=2025, date=dt.date(2025, 7, 12))
    items = [i for y in build(leads=[lead(1, refund=1, **ev), lead(2, refund=1, **ev)])["leads_years"]
             for i in y["items"]]
    assert len(items) == 2


FULL = dict(surname="Иванов", first="Иван", birthday=dt.date(1986, 5, 1), created_at=dt.datetime(2026, 9, 20, 14, 5),
            order_id=2062310870, amount=1090.0, promocode="VIM99", discount=109.5,
            products="21.1 км Жара (zhara-2026) - 1x1090 = 1090", email="Me@Mail.ru", ma_email=None)
NBSP = "\u00a0"


def test_order_details_of_upcoming_lead():
    e = only_item(build(leads=[lead(1, date=dt.date(2026, 12, 6), **FULL)], account_email="me@mail.ru"), "leads_years")
    assert e["kind"] == "ticket"
    assert e["order"] == {
        "participant": "Иванов Иван", "birthday": dt.date(1986, 5, 1), "created": dt.datetime(2026, 9, 20, 14, 5),
        "order_id": 2062310870, "amount": f"1{NBSP}090 ₽", "promocode": "VIM99", "discount": "109,5 ₽",
        "products": "21.1 км Жара (zhara-2026) - 1x1090 = 1090", "email": "Me@Mail.ru"}


def test_order_email_masked_unless_account_email():
    other = dict(FULL, email="petr@mail.ru")
    assert only_item(build(leads=[lead(1, date=dt.date(2026, 12, 6), **other)], account_email="me@mail.ru"), "leads_years")[
        "order"]["email"] == "p***@mail.ru"
    assert only_item(build(leads=[lead(1, date=dt.date(2026, 12, 6), **other)]), "leads_years")["order"]["email"] == "p***@mail.ru"
    via_ma = dict(FULL, email="  ", ma_email="ME@mail.ru")
    assert only_item(build(leads=[lead(1, date=dt.date(2026, 12, 6), **via_ma)], account_email="me@mail.ru"), "leads_years")[
        "order"]["email"] == "ME@mail.ru"
    nobody = dict(FULL, email=None, ma_email=None)
    assert only_item(build(leads=[lead(1, date=dt.date(2026, 12, 6), **nobody)]), "leads_years")["order"]["email"] is None


def test_order_skips_empty_promocode_discount_and_formats_money():
    bare = dict(FULL, promocode="", discount=0, amount=0.0, products="", order_id=None, created_at=None)
    o = only_item(build(leads=[lead(1, date=dt.date(2026, 12, 6), **bare)]), "leads_years")["order"]
    assert (o["promocode"], o["discount"], o["products"], o["order_id"], o["created"]) == (None,) * 5
    assert o["amount"] == "0 ₽"
    odd = dict(FULL, amount=1234567.5, discount=None, promocode=None)
    o = only_item(build(leads=[lead(1, date=dt.date(2026, 12, 6), **odd)]), "leads_years")["order"]
    assert o["amount"] == f"1{NBSP}234{NBSP}567,5 ₽" and o["discount"] is None
    no_amount = dict(FULL, amount=None)
    assert only_item(build(leads=[lead(1, date=dt.date(2026, 12, 6), **no_amount)]), "leads_years")["order"]["amount"] is None


def test_order_details_of_past_lead_without_result():
    e = only_item(build(leads=[lead(1, year=2025, date=dt.date(2025, 7, 12), **FULL)]), "leads_years")
    assert e["status"] == "не стартовал" and e["order"]["order_id"] == 2062310870


def test_result_entry_has_no_order_or_refund_even_with_lead():
    """Подробности заказа — только у заявок; у результата — места, протокол, диплом (решение пользователя)."""
    ev = dict(event_id=77, year=2025, date=dt.date(2025, 7, 12))
    r = res(1, event_id=77, start_number=5, time=td(1, 45))
    leads = [lead(1, start_number=5, **dict(FULL, order_id=111), **ev)]
    e = only_item(build([r], leads))
    assert "order" not in e and "refund" not in e


def test_result_without_lead_has_no_order():
    assert "order" not in only_item(build([res(1, time=td(1))]))
