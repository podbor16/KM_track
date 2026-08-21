"""Тесты для RaceLoader.fetch_from_copernico() — поддержка списка Copernico
event-значений на одну дистанцию (нужно для Детского забега, где 6
возрастных групп по году рождения объединяются в один db_event_id),
параллельный fetch (ThreadPoolExecutor) и обработка HTTP 429."""
import sys
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from load_race_results import RaceLoader


def make_loader(copernico_event):
    """RaceLoader с замоканным логгером и заданными Copernico-параметрами —
    без реального __init__ (без БД/сети), по образцу make_loader() в
    tests/unit/test_bulk_upsert.py."""
    logger = MagicMock()
    loader = RaceLoader.__new__(RaceLoader)
    loader.logger = logger
    loader.copernico_race_id = "--2026-6118"
    loader.copernico_login = "podbor250718@gmail.com"
    loader.copernico_preset = "km_analytics"
    loader.copernico_event = copernico_event
    loader.gun_time_utc = None
    return loader


def _fake_response(runners, gun_time=None):
    resp = MagicMock()
    resp.status_code = 200
    resp.raise_for_status = MagicMock()
    payload = {"data": runners}
    if gun_time:
        payload["gunTime"] = gun_time
    resp.json.return_value = payload
    return resp


def _fake_429_response(retry_after=None):
    resp = MagicMock()
    resp.status_code = 429
    resp.headers = {"Retry-After": retry_after} if retry_after else {}
    return resp


class TestFetchFromCopernicoSingleEvent:
    """Регрессия — поведение с одной строкой event не должно измениться
    (все уже настроенные события Красмарафона используют одну строку)."""

    @patch("requests.get")
    def test_single_event_returns_runners_and_updates_gun_time(self, mock_get):
        loader = make_loader("5km")
        mock_get.return_value = _fake_response(
            [{"dorsal": 1, "surname": "Иванов"}], gun_time="2026-08-22T03:30:00.000Z"
        )

        runners = loader.fetch_from_copernico()

        assert runners == [{"dorsal": 1, "surname": "Иванов"}]
        assert loader.gun_time_utc == "2026-08-22T03:30:00.000Z"
        assert mock_get.call_count == 1
        url = mock_get.call_args.args[0]
        assert url.endswith("/5km")


class TestFetchFromCopernicoEventList:
    @patch("requests.get")
    def test_merges_runners_from_all_events(self, mock_get):
        loader = make_loader(["1km-2020", "1km-2019"])

        def side_effect(url, **kwargs):
            # Ключ по URL, а не позиционный список — запросы теперь идут
            # параллельно из разных потоков (ThreadPoolExecutor), порядок
            # вызовов mock_get не гарантирован.
            if "1km-2020" in url:
                return _fake_response([{"dorsal": 2118, "surname": None}], gun_time="2026-08-22T03:30:00.000Z")
            return _fake_response([{"dorsal": 9014, "surname": "Рековская"}], gun_time="2026-08-22T03:45:00.000Z")

        mock_get.side_effect = side_effect

        runners = loader.fetch_from_copernico()

        assert len(runners) == 2
        assert {r["dorsal"] for r in runners} == {2118, 9014}
        assert mock_get.call_count == 2

    @patch("requests.get")
    def test_gun_time_utc_not_updated_for_multiple_events(self, mock_get):
        """У каждой возрастной группы своё время старта — нет одного
        корректного значения для общего поля на весь db_event_id."""
        loader = make_loader(["1km-2020", "1km-2019"])

        def side_effect(url, **kwargs):
            if "1km-2020" in url:
                return _fake_response([{"dorsal": 2118}], gun_time="2026-08-22T03:30:00.000Z")
            return _fake_response([{"dorsal": 9014}], gun_time="2026-08-22T03:45:00.000Z")

        mock_get.side_effect = side_effect

        loader.fetch_from_copernico()

        assert loader.gun_time_utc is None

    @patch("requests.get")
    def test_one_failing_sub_event_does_not_break_the_rest(self, mock_get):
        loader = make_loader(["1km-2020", "1km-2019", "1km-2018"])

        def side_effect(url, **kwargs):
            if "1km-2019" in url:
                raise ConnectionError("timeout")
            if "1km-2020" in url:
                return _fake_response([{"dorsal": 2118}])
            return _fake_response([{"dorsal": 8008}])

        mock_get.side_effect = side_effect

        runners = loader.fetch_from_copernico()

        assert {r["dorsal"] for r in runners} == {2118, 8008}
        assert mock_get.call_count == 3

    @patch("requests.get")
    def test_all_sub_events_failing_returns_empty_list(self, mock_get):
        loader = make_loader(["1km-2020", "1km-2019"])
        mock_get.side_effect = ConnectionError("timeout")

        runners = loader.fetch_from_copernico()

        assert runners == []

    @patch("requests.get")
    def test_events_fetched_concurrently_not_sequentially(self, mock_get):
        """При списке событий запросы должны идти ПАРАЛЛЕЛЬНО — иначе цикл
        для Детского забега (6 event) занимал бы 6-12+ секунд вместо 1-2.
        threading.Barrier ловит регресс к последовательному fetch: если бы
        запросы шли по очереди, первый поток застрял бы на barrier.wait(),
        так и не дождавшись остальных (они стартуют только после него) —
        сработает BrokenBarrierError по таймауту, участники для этого
        события не попадут в результат."""
        events = ["1km-2020", "1km-2019", "1km-2018"]
        loader = make_loader(events)
        barrier = threading.Barrier(len(events), timeout=2)

        def side_effect(url, **kwargs):
            barrier.wait()
            return _fake_response([{"dorsal": 1}])

        mock_get.side_effect = side_effect

        runners = loader.fetch_from_copernico()

        assert len(runners) == len(events)


class TestFetchFromCopernicoRateLimit:
    @patch("requests.get")
    def test_429_sets_rate_limited_flag_and_returns_no_runners(self, mock_get):
        loader = make_loader("5km")
        mock_get.return_value = _fake_429_response(retry_after="10")

        runners = loader.fetch_from_copernico()

        assert runners == []
        assert loader.rate_limited is True

    @patch("requests.get")
    def test_429_on_one_sub_event_does_not_block_others(self, mock_get):
        loader = make_loader(["1km-2020", "1km-2019"])

        def side_effect(url, **kwargs):
            if "1km-2019" in url:
                return _fake_429_response()
            return _fake_response([{"dorsal": 2118}])

        mock_get.side_effect = side_effect

        runners = loader.fetch_from_copernico()

        assert {r["dorsal"] for r in runners} == {2118}
        assert loader.rate_limited is True

    @patch("requests.get")
    def test_rate_limited_flag_resets_on_next_successful_fetch(self, mock_get):
        """rate_limited не должен залипать навсегда — сбрасывается в начале
        каждого fetch_from_copernico()."""
        loader = make_loader("5km")
        mock_get.return_value = _fake_429_response()
        loader.fetch_from_copernico()
        assert loader.rate_limited is True

        mock_get.return_value = _fake_response([{"dorsal": 1}])
        loader.fetch_from_copernico()
        assert loader.rate_limited is False
