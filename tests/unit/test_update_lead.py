"""Тесты для update_lead() — partial UPDATE одной строки leads из админки."""
from unittest.mock import MagicMock, patch

from src.analytics.db_results import update_lead


def _mock_conn():
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value = cur
    return conn, cur


OLD = {"surname": "Казаков", "name": "Олег", "birthday": "1990-01-01", "event_distance": "5 км", "email": "a@b.ru"}


@patch("src.analytics.dq_actions.edit_record")
@patch("src.analytics.db_results.get_pooled_connection")
def test_editing_name_goes_through_journaled_edit_record(mock_get_conn, mock_edit):
    """ФИ/ДР/дистанция/почта правятся через dq_actions.edit_record (журнал «lead:<id>»), а не прямым UPDATE;
    флаг подозрительного ФИ по-прежнему считает триггер БД."""
    conn, cur = _mock_conn()
    mock_get_conn.return_value = conn
    cur.fetchone.return_value = OLD

    update_lead(1, {"surname": "Казаков", "name": "Олежек", "email": " A@B.ru "}, "tester")

    mock_edit.assert_called_once_with(conn, "leads", 1, {"name": "Олежек"}, "tester", "lead:1")
    assert not any(c.args[0].startswith("UPDATE leads") for c in cur.execute.call_args_list)


@patch("src.analytics.db_results.get_pooled_connection")
def test_duplicate_flag_not_editable_by_hand(mock_get_conn):
    """is_duplicate считает recompute_duplicates(); основная заявка — кнопкой «Сделать основной»."""
    assert update_lead(1, {"is_duplicate": 1}) is None
    mock_get_conn.assert_not_called()


@patch("src.analytics.dq_actions.edit_record")
@patch("src.analytics.db_results.get_pooled_connection")
def test_editing_status_is_plain_update_without_journal(mock_get_conn, mock_edit):
    conn, cur = _mock_conn()
    mock_get_conn.return_value = conn
    cur.fetchone.return_value = {**OLD, "status": 1}

    update_lead(1, {"status": 1})

    mock_edit.assert_not_called()
    update_call = next(c for c in cur.execute.call_args_list if c.args[0].startswith("UPDATE leads"))
    assert update_call.args == ("UPDATE leads SET status = %s WHERE id = %s", (1, 1))


@patch("src.analytics.db_results.get_pooled_connection")
def test_no_connection_returns_none(mock_get_conn):
    mock_get_conn.return_value = None
    assert update_lead(1, {"surname": "Иванов"}) is None


@patch("src.analytics.db_results.get_pooled_connection")
def test_no_allowed_fields_returns_none_without_query(mock_get_conn):
    conn, cur = _mock_conn()
    mock_get_conn.return_value = conn

    result = update_lead(1, {"ma_email": "new@mail.ru"})  # почта кабинета Tilda не в ALLOWED

    assert result is None
    cur.execute.assert_not_called()
