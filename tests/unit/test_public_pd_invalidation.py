"""Смена отказа обновляет публичные снимки и открытый трекер."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

from src.analytics import db_results
from src.krasmarafon.routers import api
from src.krasmarafon.services import results_service
from src.krasmarafon.services.public_pd import invalidate_local_public_pd_caches


def test_tracker_emits_delta_when_only_identity_becomes_hidden():
    before = {"id": 1, "surname": "Иванов", "full_name": "Иванов Иван",
              "birthday": "1990-01-01", "client_id": 42, "rank_absolute": 5}
    after = {**before, "surname": "Спортсмен", "full_name": "Спортсмен",
             "birthday": None, "client_id": None}
    assert api._tracker_runner_changed(before, after)
    assert api._resolve_result_id(123) == 123


def test_consent_change_clears_all_public_worker_caches():
    db_results._results_cache[1] = [{"surname": "old"}]
    db_results._results_cache_ts[1] = 1
    db_results._stats_cache["event"] = {"best": "old"}
    db_results._stats_cache_ts["event"] = 1
    results_service._response_cache["1|None|None"] = object()
    results_service._response_cache_ts["1|None|None"] = 1
    results_service._json_cache["1|None|None"] = '{"surname":"old"}'
    api._sse_initial_cache[1] = ('{"surname":"old"}', 1)

    invalidate_local_public_pd_caches()

    for cache in (db_results._results_cache, db_results._results_cache_ts,
                  db_results._stats_cache, db_results._stats_cache_ts,
                  results_service._response_cache, results_service._response_cache_ts,
                  results_service._json_cache, api._sse_initial_cache):
        assert not cache


def test_old_background_build_cannot_restore_public_name():
    def old_build(*args):
        results_service.invalidate_public_pd_results_cache()
        return object()

    with patch.object(results_service, "_do_build", side_effect=old_build):
        results_service._background_rebuild("1|None|None", 1, None, None, {})
    assert "1|None|None" not in results_service._response_cache


def test_admin_flag_change_notifies_other_workers():
    from src.krasmarafon.routers.admin import mark_lead_pd_refused

    redis = MagicMock()
    redis.publish = AsyncMock(return_value=3)
    redis.aclose = AsyncMock()
    with patch("src.analytics.db_results.set_lead_pd_refused", return_value={"event_id": 119}), \
         patch("src.krasmarafon.services.public_pd.invalidate_local_public_pd_caches"), \
         patch("redis.asyncio.Redis", return_value=redis):
        assert asyncio.run(mark_lead_pd_refused(1, True, "tester")) == {"status": "ok"}
    payload = json.loads(redis.publish.await_args.args[1])
    assert payload == {"type": "pd_refused_changed", "event_id": 119}


def test_warmed_public_json_is_not_reused_after_admin_refusal():
    from src.krasmarafon.routers.admin import mark_lead_pd_refused

    key = "119|None|None"
    results_service._json_cache[key] = '{"results":[{"surname":"OLD NAME"}]}'
    results_service._response_cache_ts[key] = 10**12
    redis = MagicMock()
    redis.publish = AsyncMock(return_value=3)
    redis.aclose = AsyncMock()
    fresh = MagicMock()
    fresh.model_dump_json.return_value = '{"results":[{"surname":"Спортсмен"}]}'
    with patch("src.analytics.db_results.set_lead_pd_refused", return_value={"event_id": 119}), \
         patch("redis.asyncio.Redis", return_value=redis), \
         patch("src.krasmarafon.routers.api.event_is_public", return_value=True), \
         patch("src.krasmarafon.services.results_service.build_event_results", return_value=fresh):
        asyncio.run(mark_lead_pd_refused(1, True, "tester"))
        response = asyncio.run(api.get_event_results(event_id=119, event_name=None, year=None))
    assert "OLD NAME" not in response.body.decode("utf-8")
    assert "Спортсмен" in response.body.decode("utf-8")
