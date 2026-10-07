"""Вытеснение устаревших записей кешей (src/common/cache.py) — RAM воркеров 2026-10-07."""
from unittest.mock import patch

from src.common.cache import prune


def test_prune_removes_stale_from_all_stores():
    ts = {"a": 100.0, "b": 195.0}
    values, json_ = {"a": 1, "b": 2}, {"a": "1", "b": "2"}
    assert prune(ts, 30, values, json_, now=200.0) == 1
    assert (ts, values, json_) == ({"b": 195.0}, {"b": 2}, {"b": "2"})


def test_prune_keeps_entry_within_read_window():
    ts, values = {"a": 170.0}, {"a": 1}
    assert prune(ts, 30, values, now=200.0) == 0 and values == {"a": 1}


def test_event_results_cache_does_not_keep_old_events():
    from src.krasmarafon.services import results_service as rs
    rs._response_cache.clear(); rs._response_cache_ts.clear(); rs._json_cache.clear()
    built = type("R", (), {"model_dump_json": lambda self: "{}"})()
    with patch.object(rs, "_do_build", return_value=built):
        rs.build_event_results(1, None, None, {})
        rs._response_cache_ts["1|None|None"] -= 1000      # запись забега 1 устарела
        rs.build_event_results(2, None, None, {})
    assert list(rs._response_cache) == ["2|None|None"] and list(rs._json_cache) == ["2|None|None"]
