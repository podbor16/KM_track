"""Хук live-JSON топ-10 (broadcast_json) в RaceLoader.continuous_mode() —
ошибка генерации не должна ронять весь live-цикл обновления результатов
(тот же принцип изоляции, что уже применён для avg_speed_kmh на Siberman —
см. спеку docs/superpowers/specs/2026-08-18-zhara-live-top10-broadcast-json-design.md)."""
import logging
from unittest.mock import patch

from load_race_results import RaceLoader


def _make_loader(broadcast_json_path="/tmp/x.json"):
    logger = logging.getLogger("test_broadcast_json_hook")
    loader = RaceLoader(event_id=999, logger=logger, broadcast_json_path=broadcast_json_path)
    loader.connection = object()
    return loader


@patch("src.krasmarafon.services.live_top10_export.generate_top10_json")
def test_maybe_write_broadcast_json_calls_generator_with_own_state(mock_gen):
    loader = _make_loader()
    loader._maybe_write_broadcast_json()
    mock_gen.assert_called_once_with(loader.connection, 999, "/tmp/x.json")


@patch("src.krasmarafon.services.live_top10_export.generate_top10_json", side_effect=RuntimeError("db down"))
def test_maybe_write_broadcast_json_swallows_errors(mock_gen):
    loader = _make_loader()
    loader._maybe_write_broadcast_json()  # не должно бросить исключение наружу


def test_broadcast_json_path_defaults_to_none():
    loader = RaceLoader(event_id=1, logger=logging.getLogger("t"))
    assert loader.broadcast_json_path is None
