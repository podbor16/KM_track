"""recompute_duplicate_flag()/recompute_duplicates() — is_duplicate: одна основная заявка в группе
(client_id, event_id), остальные дубли (2026-10-06). На реальной БД — tests/integration/test_lead_flags.py."""
from unittest.mock import MagicMock, patch

from src.analytics.db_results import recompute_duplicate_flag, recompute_duplicates


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
    sql, params = cur.execute.call_args[0]
    assert "UPDATE leads" in sql and "ROW_NUMBER() OVER (PARTITION BY client_id, event_id" in sql
    assert "dup_main DESC" in sql and "created_at DESC" in sql      # ручной выбор, номер, самая поздняя
    assert "WHERE l.is_duplicate <> t.dup" in sql                   # пишутся только расхождения
    assert params == [42]
    conn.commit.assert_called_once()
    conn.close.assert_called_once()


@patch("src.analytics.db_results.get_pooled_connection")
def test_recompute_skips_when_client_id_missing(mock_get_conn):
    updated = recompute_duplicate_flag(client_id=0, event_id=7)
    assert updated == 0
    mock_get_conn.assert_not_called()


def test_recompute_all_without_client_filter():
    cur = MagicMock()
    recompute_duplicates(cur)
    sql, params = cur.execute.call_args[0]
    assert "client_id IN" not in sql and params == []


def test_recompute_empty_client_list_does_nothing():
    cur = MagicMock()
    assert recompute_duplicates(cur, [0, None]) == 0
    cur.execute.assert_not_called()


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
