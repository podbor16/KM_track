"""Тесты для _insert_lead() — пересчёт is_duplicate после INSERT в leads."""
from unittest.mock import MagicMock, patch

from src.krasmarafon.routers.webhook import _insert_lead

_MINIMAL_DATA = {
    "surname": "Иванов", "name": "Иван", "sex": "", "city": "", "birthday": "1990-01-01",
    "email": "", "phone": "", "event_name": "Весна", "event_distance": "5 км",
    "event_year": 2027, "products": "", "payment_system": "", "transaction_id": "",
    "order_id": None, "promocode": "", "discount": 0.0, "amount": 0.0,
    "is_name_suspicious": 0, "client_id": 0, "event_id": 0,
    "is_duplicate": 0, "status": 0, "is_new": 0, "is_new_event": 0,
}


@patch("src.krasmarafon.routers.webhook.recompute_duplicate_flag")
@patch("src.krasmarafon.routers.webhook.get_pooled_connection")
def test_insert_lead_recomputes_duplicate_flag_for_resolved_group(mock_get_conn, mock_recompute):
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value = cur
    cur.lastrowid = 555
    cur.fetchone.return_value = (42, 7)
    mock_get_conn.return_value = conn

    _insert_lead(dict(_MINIMAL_DATA))

    mock_recompute.assert_called_once_with(client_id=42, event_id=7)
    conn.commit.assert_called_once()
    conn.close.assert_called_once()


@patch("src.krasmarafon.routers.webhook.recompute_duplicate_flag")
@patch("src.krasmarafon.routers.webhook.get_pooled_connection")
def test_insert_lead_skips_recompute_if_lookup_fails(mock_get_conn, mock_recompute):
    """Робастность: если SELECT после INSERT не находит строку (не должно
    случиться, но не должно и уронить обработку вебхука), recompute не
    вызывается и исключение не пробрасывается."""
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value = cur
    cur.lastrowid = 555
    cur.fetchone.return_value = None
    mock_get_conn.return_value = conn

    _insert_lead(dict(_MINIMAL_DATA))

    mock_recompute.assert_not_called()


@patch("src.krasmarafon.routers.webhook.get_pooled_connection")
def test_insert_lead_raises_without_connection(mock_get_conn):
    mock_get_conn.return_value = None
    try:
        _insert_lead(dict(_MINIMAL_DATA))
        assert False, "expected RuntimeError"
    except RuntimeError:
        pass
