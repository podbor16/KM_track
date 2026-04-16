"""
Интеграционные тесты для событийных эндпоинтов.
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


class TestCurrentEvent:
    def test_current_event_200(self, client):
        response = client.get("/api/current-event")
        assert response.status_code == 200

    def test_current_event_has_event_field(self, client):
        data = client.get("/api/current-event").json()
        assert "event" in data

    def test_current_event_has_name(self, client):
        data = client.get("/api/current-event").json()
        assert "name" in data


class TestEventsList:
    def test_events_list_200(self, client):
        response = client.get("/api/events")
        assert response.status_code == 200

    def test_events_list_not_empty(self, client):
        data = client.get("/api/events").json()
        assert "events" in data
        assert isinstance(data["events"], list)
        assert len(data["events"]) > 0

    def test_each_event_has_required_fields(self, client):
        data = client.get("/api/events").json()
        for ev in data["events"]:
            for field in ("id", "name"):
                assert field in ev, f"Поле '{field}' отсутствует в событии {ev}"
