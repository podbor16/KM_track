"""Строка бегуна на /results несёт client_id — кнопка «Профиль» ведёт на профиль по карточке."""
from datetime import date, timedelta
from unittest.mock import patch

DB = "src.analytics.db_connection_optimized"


def test_runner_row_has_client_id():
    from src.krasmarafon.services import results_service as rs
    runner = {"id": 7, "client_id": 40803, "surname": "Пцарев", "name": "Александр", "start_number": 1012,
              "race_status": "Finished", "time_gun_finish": timedelta(minutes=9), "sex": "Мужчина", "category": "М"}
    ev = {"event_name": "Детский забег", "event_distance": 1.0, "event_year": 2016, "event_date": date(2016, 8, 28)}
    with patch(f"{DB}.get_race_results_by_event_id", return_value=[runner]), \
            patch(f"{DB}.get_event_info_by_id", return_value=ev), \
            patch(f"{DB}.get_category_avg_paces", return_value={}), \
            patch(f"{DB}.get_prev_year_results", return_value=[]):
        resp = rs._do_build(150, None, None, {})
    row = resp.results[0]
    assert row["client_id"] == 40803 and row["id"] == 7
