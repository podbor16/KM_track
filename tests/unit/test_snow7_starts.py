from unittest.mock import MagicMock

import pytest

from src.analytics import snow7_starts


def entry(lead_id, number=None, wave=None, distance="7 км"):
    return {
        "id": lead_id,
        "client_id": lead_id,
        "event_id": 119 if distance == "7 км" else 120,
        "event_distance": distance,
        "dup_main": 0,
        "created_at": None,
        "start_number": number,
        "start_wave": wave,
    }


def test_manual_number_conflicts_with_another_distance():
    conn = MagicMock()
    cur = conn.cursor.return_value
    cur.fetchall.return_value = [entry(1), entry(2, number=24, distance="2 км")]

    with pytest.raises(snow7_starts.AssignmentConflict, match="24"):
        snow7_starts.assign(conn, 1, 24, 1, "test")

    assert cur.execute.call_count == 1
    assert cur.execute.call_args.args[0].endswith("FOR UPDATE")
    conn.rollback.assert_called_once()
    conn.commit.assert_not_called()


def test_manual_assignment_updates_number_and_wave_together(monkeypatch):
    conn = MagicMock()
    cur = conn.cursor.return_value
    cur.fetchall.return_value = [entry(1, number=24, wave=1)]
    cur.fetchone.return_value = None
    invalidate_cache = MagicMock()
    monkeypatch.setattr(snow7_starts, "invalidate_start_list_cache", invalidate_cache)

    result = snow7_starts.assign(conn, 1, 25, 13, "test")

    assert result == {"start_number": 25, "start_wave": 13}
    assert any(
        sql.startswith("UPDATE leads SET start_number = %s, start_wave = %s") and params == (25, 13, 1)
        for sql, params in (call.args for call in cur.execute.call_args_list)
    )
    assert cur.execute.call_args.args[1][0] == "snow7_start"
    conn.commit.assert_called_once()
    invalidate_cache.assert_called_once()
