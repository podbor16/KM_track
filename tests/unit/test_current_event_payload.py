from pathlib import Path

from src.config.event_loader import load_all_events
from src.krasmarafon.routers.api import build_current_event_response


def test_payload_for_zhara_has_both_distances():
    events = load_all_events(Path("config/events"))
    p = build_current_event_response(events["zhara"])
    assert p.event == "zhara"
    ids = {d.db_event_id for d in p.distances}
    assert ids == {115, 116}
    d21 = next(d for d in p.distances if d.db_event_id == 116)
    assert d21.gpx_file == "static/map/2026/zhara_21.gpx"
    assert len(d21.checkpoints) == 8
