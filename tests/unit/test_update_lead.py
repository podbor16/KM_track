"""Тесты для update_lead() — partial UPDATE одной строки leads из админки."""
from unittest.mock import MagicMock, patch

from src.analytics.db_results import update_lead


def _mock_conn():
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value = cur
    return conn, cur


@patch("src.analytics.db_results.get_pooled_connection")
def test_editing_name_recomputes_is_name_suspicious_to_clean(mock_get_conn):
    """Реальная находка: правка ФИО вручную в админке (напр. "Kazakov"->
    "Казаков") раньше не пересчитывала is_name_suspicious — флаг оставался
    застрявшим (1547 записей с чистым ФИО, но is_name_suspicious=1)."""
    conn, cur = _mock_conn()
    mock_get_conn.return_value = conn
    cur.fetchone.side_effect = [
        {"surname": "Kazakov", "name": "Oleg"},  # текущие значения до правки
        {"id": 1, "surname": "Казаков", "name": "Олег"},  # финальный SELECT *
    ]

    update_lead(1, {"surname": "Казаков", "name": "Олег"})

    update_call = next(c for c in cur.execute.call_args_list if c.args[0].startswith("UPDATE leads"))
    sql, params = update_call.args
    assert "is_name_suspicious" in sql
    assert 0 in params


@patch("src.analytics.db_results.get_pooled_connection")
def test_editing_name_recomputes_is_name_suspicious_to_suspicious(mock_get_conn):
    conn, cur = _mock_conn()
    mock_get_conn.return_value = conn
    cur.fetchone.side_effect = [
        {"surname": "Иванов", "name": "Иван"},
        {"id": 1, "surname": "Ivanov", "name": "Иван"},
    ]

    update_lead(1, {"surname": "Ivanov"})

    update_call = next(c for c in cur.execute.call_args_list if c.args[0].startswith("UPDATE leads"))
    sql, params = update_call.args
    assert "is_name_suspicious" in sql
    assert 1 in params


@patch("src.analytics.db_results.get_pooled_connection")
def test_editing_only_name_uses_existing_surname_for_check(mock_get_conn):
    """Правится только name — surname берётся из текущего значения в БД, не
    теряется при пересчёте."""
    conn, cur = _mock_conn()
    mock_get_conn.return_value = conn
    cur.fetchone.side_effect = [
        {"surname": "Иванов", "name": "Old"},
        {"id": 1, "surname": "Иванов", "name": "Иван"},
    ]

    update_lead(1, {"name": "Иван"})

    select_current = next(
        c for c in cur.execute.call_args_list
        if c.args[0].startswith("SELECT surname, name")
    )
    assert select_current.args[1] == (1,)
    update_call = next(c for c in cur.execute.call_args_list if c.args[0].startswith("UPDATE leads"))
    sql, params = update_call.args
    assert "is_name_suspicious" in sql
    assert 0 in params  # "Иванов"/"Иван" — оба чистые


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
