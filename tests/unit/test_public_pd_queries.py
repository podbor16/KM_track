"""Публичные запросы db_results отдают флаг отказа и маскируют ФИ."""
from datetime import timedelta
from unittest.mock import MagicMock, patch

from src.analytics import db_results


def _conn(rows):
    cur = MagicMock()
    cur.fetchall.return_value = rows
    conn = MagicMock()
    conn.cursor.return_value = cur
    return conn, cur


def test_segment_rankings_mask_refused():
    rows = [{"result_id": 1, "segment_code": "kt1-kt2", "sg_time_clear": timedelta(minutes=5), "sg_time_gun": None,
             "sg_pace_avg": None, "sg_pace_avg_gun": None, "surname": "Иванов", "name": "Иван",
             "start_number": 7, "sex": "Мужчина", "category": "М", "pd_refused": 1}]
    conn, cur = _conn(rows)
    with patch.object(db_results, "get_pooled_connection", return_value=conn):
        out = db_results.get_event_segment_rankings(1, "kt1-kt2")
    assert "pd_refused" in cur.execute.call_args[0][0]
    assert (out[0]["surname"], out[0]["name"], out[0]["start_number"]) == ("Спортсмен", "", 7)
    assert "pd_refused" not in out[0]


def test_race_stats_best_result_masked():
    rows = [{"surname": "Иванов", "name": "Иван", "sex": "Мужчина", "time_clear_finish": timedelta(minutes=20),
             "time_gun_finish": None, "finish_pace_avg_clean": timedelta(minutes=4), "finish_pace_avg_gun": None,
             "race_status": "Finished", "event_distance": 5, "event_year": 2026, "pd_refused": 1}]
    conn, cur = _conn(rows)
    db_results._stats_cache.clear()
    with patch.object(db_results, "get_pooled_connection", return_value=conn):
        out = db_results.get_race_stats_from_db("Тест статистики")
    best = out["distances"][0]["best_result"]
    assert (best["surname"], best["name"]) == ("Спортсмен", "")
    assert "pd_refused" in cur.execute.call_args[0][0]
