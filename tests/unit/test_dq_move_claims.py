"""Перенос привязок кабинета при склейке: до миграции athlete_claims (ошибка 1146) склейка работает как раньше."""
from unittest.mock import MagicMock

from mysql.connector.errors import ProgrammingError

from src.analytics import dq_actions


def test_move_claims_without_table_is_noop():
    cur = MagicMock()
    cur.execute.side_effect = ProgrammingError(msg="Table 'athlete_claims' doesn't exist", errno=1146)
    assert dq_actions._move_athlete_claims(cur, {2: 1}, "tester") == []


def test_move_claims_other_db_error_propagates():
    cur = MagicMock()
    cur.execute.side_effect = ProgrammingError(msg="syntax", errno=1064)
    try:
        dq_actions._move_athlete_claims(cur, {2: 1}, "tester")
    except ProgrammingError as e:
        assert e.errno == 1064
    else:
        raise AssertionError("ожидалась ошибка")
