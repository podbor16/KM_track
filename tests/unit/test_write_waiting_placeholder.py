"""Тесты для RaceLoader.write_waiting_placeholder() — плейсхолдер "ждём
старта" в broadcast JSON для режиссёра трансляции, пишется ТОЛЬКО пока
файла ещё нет (не должен затирать реальные данные при рестарте
загрузчика посреди гонки)."""
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from load_race_results import RaceLoader


def make_loader(broadcast_json_path=None, gun_time_utc=None):
    logger = MagicMock()
    loader = RaceLoader.__new__(RaceLoader)
    loader.logger = logger
    loader.broadcast_json_path = broadcast_json_path
    loader.gun_time_utc = gun_time_utc
    return loader


class TestWriteWaitingPlaceholder:
    def test_noop_when_broadcast_json_path_not_set(self, tmp_path):
        loader = make_loader(broadcast_json_path=None)
        loader.write_waiting_placeholder("5 км", "2026-08-22")
        assert list(tmp_path.iterdir()) == []

    def test_noop_when_file_already_exists(self, tmp_path):
        """Защита от затирания реальных данных при рестарте загрузчика
        посреди уже идущей гонки."""
        target = tmp_path / "zhara_top10.json"
        target.write_text('{"real": "data"}', encoding="utf-8")
        loader = make_loader(broadcast_json_path=str(target))

        loader.write_waiting_placeholder("5 км", "2026-08-22")

        assert json.loads(target.read_text(encoding="utf-8")) == {"real": "data"}

    def test_writes_message_with_gun_time_converted_to_krasnoyarsk(self, tmp_path):
        """gunTime от Copernico — UTC, отображаемое время — Красноярск
        (UTC+7): 2026-08-22T03:30:00Z → 10:30 по Красноярску."""
        target = tmp_path / "zhara_top10.json"
        loader = make_loader(
            broadcast_json_path=str(target),
            gun_time_utc="2026-08-22T03:30:00.000Z",
        )

        loader.write_waiting_placeholder("5 км", "2026-08-22")

        data = json.loads(target.read_text(encoding="utf-8"))
        assert data["status"] == "waiting"
        assert "22.08" in data["message"]
        assert "10:30" in data["message"]
        assert "5 км" in data["message"]
        assert data["gun_time_utc"] == "2026-08-22T03:30:00.000Z"

    def test_falls_back_to_event_date_when_gun_time_unknown(self, tmp_path):
        target = tmp_path / "zhara_top10.json"
        loader = make_loader(broadcast_json_path=str(target), gun_time_utc=None)

        loader.write_waiting_placeholder("21.1 км", "2026-08-23")

        data = json.loads(target.read_text(encoding="utf-8"))
        assert "23.08" in data["message"]
        assert "21.1 км" in data["message"]

    def test_falls_back_to_generic_message_when_nothing_known(self, tmp_path):
        target = tmp_path / "zhara_top10.json"
        loader = make_loader(broadcast_json_path=str(target), gun_time_utc=None)

        loader.write_waiting_placeholder("5 км", None)

        data = json.loads(target.read_text(encoding="utf-8"))
        assert "скоро" in data["message"]

    def test_atomic_write_no_leftover_tmp_file(self, tmp_path):
        target = tmp_path / "zhara_top10.json"
        loader = make_loader(
            broadcast_json_path=str(target),
            gun_time_utc="2026-08-22T03:30:00.000Z",
        )

        loader.write_waiting_placeholder("5 км", "2026-08-22")

        assert target.exists()
        assert not (tmp_path / "zhara_top10.json.tmp").exists()
