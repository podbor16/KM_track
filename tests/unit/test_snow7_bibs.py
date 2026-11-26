from unittest.mock import MagicMock

import pytest

from src.analytics import snow7_bibs


def entry(lead_id, number=None, distance="7 км"):
    return {
        "id": lead_id,
        "client_id": lead_id,
        "event_id": 1 if distance == "7 км" else 2,
        "event_distance": distance,
        "dup_main": 0,
        "created_at": None,
        "start_number": number,
    }


def test_manual_number_conflicts_with_another_distance():
    conn = MagicMock()
    cur = conn.cursor.return_value
    cur.fetchall.return_value = [entry(1), entry(2, number=24, distance="2 км")]

    with pytest.raises(snow7_bibs.AssignmentConflict, match="24"):
        snow7_bibs.assign(conn, 2026, 1, 24, "test")

    assert cur.execute.call_count == 1
    assert cur.execute.call_args.args[0].endswith("FOR UPDATE")
    conn.rollback.assert_called_once()
    conn.commit.assert_not_called()


def test_manual_assignment_updates_existing_bib_column(monkeypatch):
    conn = MagicMock()
    cur = conn.cursor.return_value
    cur.fetchall.return_value = [entry(1, number=24)]
    cur.fetchone.return_value = None
    invalidate_cache = MagicMock()
    monkeypatch.setattr(snow7_bibs, "invalidate_start_list_cache", invalidate_cache)

    result = snow7_bibs.assign(conn, 2027, 1, 25, "test")

    assert result == {"start_number": 25}
    assert cur.execute.call_args_list[0].args[1] == (snow7_bibs.SNOW7_EVENT, 2027)
    cur.execute.assert_any_call("UPDATE leads SET start_number = %s WHERE id = %s", (25, 1))
    assert cur.execute.call_args.args[1][0] == "assign_bib"
    conn.commit.assert_called_once()
    invalidate_cache.assert_called_once()
