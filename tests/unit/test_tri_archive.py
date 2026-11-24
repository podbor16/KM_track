from datetime import datetime
from decimal import Decimal

import pytest
from fastapi import HTTPException, Request

from src.race_triatleta import router


@pytest.fixture
def races(monkeypatch):
    events = [
        {"id": 1, "code": "tri_24h_2026", "gun_datetime": datetime(2026, 6, 25, 13),
         "duration_hours": 24, "lap_distance_km": Decimal("4.040"), "race_year": 2026},
        {"id": 5, "code": "tri_6h_2024", "gun_datetime": None,
         "duration_hours": 6, "lap_distance_km": Decimal("4.040"), "race_year": 2024},
    ]
    monkeypatch.setattr(router, "get_result_events", lambda: events)


def test_archive_selects_same_event_for_results_and_laps(races, monkeypatch):
    monkeypatch.setattr(router, "get_standings", lambda event_id, category: [(event_id, category)])
    monkeypatch.setattr(router, "get_all_laps", lambda event_id: [event_id])
    assert router.tri_standings() == {"standings": [(1, None)]}
    assert router.tri_laps() == {"laps": [1]}
    assert router.tri_standings("Женщины", "tri_6h_2024") == {"standings": [(5, "Женщины")]}
    assert router.tri_laps("tri_6h_2024") == {"laps": [5]}
    with pytest.raises(HTTPException) as exc:
        router.tri_laps("missing")
    assert exc.value.status_code == 404


def test_archive_page_supports_a_year_without_calendar_date(races):
    request = Request({"type": "http", "method": "GET", "path": "/24h", "headers": []})
    default = router.tri_home(request).body.decode()
    assert "25–26 июня 2026" in default
    selected = router.tri_home(request, "tri_6h_2024").body.decode()
    assert '<option value="tri_6h_2024" selected>' in selected
    assert "Шестичасовая велогонка<br>2024" in selected
    assert 'id="to-slider" min="1" max="6" value="6"' in selected
    assert '"start": null' in selected
