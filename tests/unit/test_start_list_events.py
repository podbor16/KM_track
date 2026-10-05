"""Селектор события /start_list: события с заявками на текущий год и позже, по ближайшему старту."""
from datetime import date

from src.analytics.db_results import order_start_list_events

TODAY = date(2026, 10, 5)


def row(name, year, first, last=None):
    return {"event_name": name, "event_year": year, "first_date": first, "last_date": last or first}


def test_upcoming_by_date_then_past_newest_first_then_without_date():
    rows = [
        row("Жара", 2026, date(2026, 8, 22), date(2026, 8, 23)),
        row("Ночной забег", 2027, date(2027, 3, 27)),
        row("Снежная семерка", 2026, date(2026, 12, 6)),
        row("Весна", 2026, date(2026, 5, 17)),
        row("Новый забег", 2027, None, None),
    ]
    names = [e["event_name"] for e in order_start_list_events(rows, TODAY)]
    assert names == ["Снежная семерка", "Ночной забег", "Жара", "Весна", "Новый забег"]


def test_one_item_per_event_nearest_upcoming_year():
    rows = [
        row("Х Трейл", 2026, date(2026, 9, 27)),          # уже прошёл
        row("Х Трейл", 2027, date(2027, 10, 24)),
        row("Х Трейл", 2028, date(2028, 10, 22)),
    ]
    assert order_start_list_events(rows, TODAY) == [{"event_name": "Х Трейл", "year": 2027, "date": "2027-10-24"}]


def test_multi_day_event_still_upcoming_on_its_last_day():
    rows = [row("Жара", 2026, date(2026, 10, 4), date(2026, 10, 5)), row("Весна", 2027, date(2027, 5, 16))]
    assert [e["event_name"] for e in order_start_list_events(rows, TODAY)] == ["Жара", "Весна"]


def test_past_only_event_shows_latest_past_start():
    rows = [row("Весна", 2026, date(2026, 5, 17))]
    assert order_start_list_events(rows, TODAY)[0]["year"] == 2026
