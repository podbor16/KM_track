"""Тесты для recompute_duplicate_flag() — пересчёт is_duplicate для группы (client_id, event_id)."""
from unittest.mock import MagicMock, patch

from src.analytics.db_results import recompute_duplicate_flag


def _mock_conn():
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value = cur
    return conn, cur


@patch("src.analytics.db_results.get_pooled_connection")
def test_recompute_marks_group_as_duplicate(mock_get_conn):
    conn, cur = _mock_conn()
    mock_get_conn.return_value = conn
    cur.rowcount = 3

    updated = recompute_duplicate_flag(client_id=42, event_id=7)

    assert updated == 3
    executed_sql = cur.execute.call_args[0][0]
    assert "UPDATE leads" in executed_sql
    assert "is_duplicate" in executed_sql
    assert cur.execute.call_args[0][1] == (42, 7, 42, 7)
    conn.commit.assert_called_once()
    conn.close.assert_called_once()


@patch("src.analytics.db_results.get_pooled_connection")
def test_recompute_skips_when_client_id_missing(mock_get_conn):
    updated = recompute_duplicate_flag(client_id=0, event_id=7)
    assert updated == 0
    mock_get_conn.assert_not_called()


@patch("src.analytics.db_results.get_pooled_connection")
def test_recompute_skips_when_event_id_missing(mock_get_conn):
    updated = recompute_duplicate_flag(client_id=1, event_id=None)
    assert updated == 0
    mock_get_conn.assert_not_called()


@patch("src.analytics.db_results.get_pooled_connection")
def test_recompute_no_connection_returns_zero(mock_get_conn):
    mock_get_conn.return_value = None
    assert recompute_duplicate_flag(client_id=1, event_id=1) == 0


@patch("src.analytics.db_results.get_pooled_connection")
def test_recompute_db_error_returns_zero_and_closes_connection(mock_get_conn):
    conn, cur = _mock_conn()
    mock_get_conn.return_value = conn
    cur.execute.side_effect = Exception("boom")

    updated = recompute_duplicate_flag(client_id=1, event_id=1)

    assert updated == 0
    conn.close.assert_called_once()
