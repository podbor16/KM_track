"""Тесты для update_lead() — partial UPDATE одной строки leads из админки."""
from unittest.mock import MagicMock, patch

from src.analytics.db_results import update_lead


def _mock_conn():
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value = cur
    return conn, cur


@patch("src.analytics.db_results.get_pooled_connection")
def test_editing_name_leaves_suspicious_flag_to_db_trigger(mock_get_conn):
    """С 2026-10-06 флаг считает триггер trg_leads_name_flag_bu на любой записи заявки
    (раньше — только этот путь в коде, и флаг застревал после правок мимо него)."""
    conn, cur = _mock_conn()
    mock_get_conn.return_value = conn
    cur.fetchone.return_value = {"id": 1, "surname": "Казаков", "name": "Олег"}

    update_lead(1, {"surname": "Казаков", "name": "Олег"})

    update_call = next(c for c in cur.execute.call_args_list if c.args[0].startswith("UPDATE leads"))
    assert update_call.args == ("UPDATE leads SET surname = %s, name = %s WHERE id = %s", ["Казаков", "Олег", 1])


@patch("src.analytics.db_results.get_pooled_connection")
def test_duplicate_flag_not_editable_by_hand(mock_get_conn):
    """is_duplicate считает recompute_duplicates(); основная заявка — кнопкой «Сделать основной»."""
    assert update_lead(1, {"is_duplicate": 1}) is None
    mock_get_conn.assert_not_called()


@patch("src.analytics.db_results.get_pooled_connection")
def test_editing_unrelated_field_does_not_touch_is_name_suspicious(mock_get_conn):
    conn, cur = _mock_conn()
    mock_get_conn.return_value = conn
    cur.fetchone.return_value = {"id": 1, "status": 1}

    update_lead(1, {"status": 1})

    select_calls = [c for c in cur.execute.call_args_list if c.args[0].startswith("SELECT surname, name")]
    assert select_calls == []
    update_call = next(c for c in cur.execute.call_args_list if c.args[0].startswith("UPDATE leads"))
    sql, _ = update_call.args
    assert "is_name_suspicious" not in sql


@patch("src.analytics.db_results.get_pooled_connection")
def test_no_connection_returns_none(mock_get_conn):
    mock_get_conn.return_value = None
    assert update_lead(1, {"surname": "Иванов"}) is None


@patch("src.analytics.db_results.get_pooled_connection")
def test_no_allowed_fields_returns_none_without_query(mock_get_conn):
    conn, cur = _mock_conn()
    mock_get_conn.return_value = conn

    result = update_lead(1, {"email": "new@mail.ru"})  # не в ALLOWED

    assert result is None
    cur.execute.assert_not_called()
