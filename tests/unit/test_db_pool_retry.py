"""Тесты для get_pooled_connection() — короткий повтор при временном
исчерпании пула соединений. Найдено на живых данных дня гонки Жары
21.1км 2026-08-23: get_race_results_by_event_id() (и ~18 других функций
в src/analytics/) молча трактует connection=None как "0 результатов" —
пиковая нагрузка (loader + тракер + результаты + стартовый список
одновременно) исчерпывала pool_size=5 на 3 gunicorn-воркерах, и
пользователи видели пустые фильтры/статистику вместо реальных данных."""
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from mysql.connector import Error as MySQLError

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import src.analytics.db_pool as db_pool


@pytest.fixture(autouse=True)
def reset_pool_state():
    """Изолируем тесты друг от друга — модуль хранит пул в глобальной переменной."""
    original = db_pool._connection_pool
    yield
    db_pool._connection_pool = original


def test_returns_connection_on_first_try(monkeypatch):
    mock_conn = MagicMock()
    mock_conn.is_connected.return_value = True
    mock_pool = MagicMock()
    mock_pool.get_connection.return_value = mock_conn
    db_pool._connection_pool = mock_pool

    result = db_pool.get_pooled_connection()

    assert result is mock_conn
    assert mock_pool.get_connection.call_count == 1


def test_retries_once_after_pool_exhausted_then_succeeds(monkeypatch):
    """Первая попытка — PoolError (пул исчерпан), вторая — успех.
    Не должно быть долгой задержки (sleep замокан)."""
    mock_conn = MagicMock()
    mock_conn.is_connected.return_value = True
    mock_pool = MagicMock()
    mock_pool.get_connection.side_effect = [MySQLError("pool exhausted"), mock_conn]
    db_pool._connection_pool = mock_pool

    slept = []
    monkeypatch.setattr(db_pool.time, "sleep", lambda s: slept.append(s))

    result = db_pool.get_pooled_connection()

    assert result is mock_conn
    assert mock_pool.get_connection.call_count == 2
    assert slept == [0.1], "должна быть ровно одна короткая пауза перед повтором"


def test_returns_none_if_both_attempts_fail(monkeypatch):
    mock_pool = MagicMock()
    mock_pool.get_connection.side_effect = MySQLError("pool exhausted")
    db_pool._connection_pool = mock_pool
    monkeypatch.setattr(db_pool.time, "sleep", lambda s: None)

    result = db_pool.get_pooled_connection()

    assert result is None
    assert mock_pool.get_connection.call_count == 2


def test_returns_none_immediately_if_pool_never_initialized(monkeypatch):
    db_pool._connection_pool = None
    monkeypatch.setattr(db_pool, "initialize_connection_pool", lambda: None)

    result = db_pool.get_pooled_connection()

    assert result is None
