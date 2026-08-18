"""Тесты для CRUD-функций participant_photos (ссылки на фото для
live-топ-10 трансляции Жары) и list_db_events() (числовой event_id для
селектора в /admin)."""
from unittest.mock import MagicMock, patch

from src.analytics.db_results import (
    list_db_events, list_participant_photos,
    upsert_participant_photo, delete_participant_photo,
)


def _mock_conn():
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value = cur
    return conn, cur


@patch("src.analytics.db_results.get_pooled_connection")
def test_list_db_events_returns_rows(mock_get_conn):
    conn, cur = _mock_conn()
    mock_get_conn.return_value = conn
    cur.fetchall.return_value = [
        {"id": 116, "event_name": "Жара", "event_distance": 21.1, "event_year": 2026},
    ]

    result = list_db_events()

    assert result == [{"id": 116, "event_name": "Жара", "event_distance": 21.1, "event_year": 2026}]


@patch("src.analytics.db_results.get_pooled_connection")
def test_list_participant_photos_filters_by_event(mock_get_conn):
    conn, cur = _mock_conn()
    mock_get_conn.return_value = conn
    cur.fetchall.return_value = [
        {"id": 1, "event_id": 116, "start_number": 245, "photo_url": "https://example.com/a.jpg"},
    ]

    result = list_participant_photos(116)

    assert len(result) == 1
    select_call = cur.execute.call_args_list[0]
    assert "event_id = %s" in select_call.args[0]
    assert select_call.args[1] == (116,)


@patch("src.analytics.db_results.get_pooled_connection")
def test_upsert_participant_photo_returns_saved_row(mock_get_conn):
    conn, cur = _mock_conn()
    mock_get_conn.return_value = conn
    cur.fetchone.return_value = {
        "id": 7, "event_id": 116, "start_number": 245, "photo_url": "https://example.com/a.jpg",
    }

    result = upsert_participant_photo(116, 245, "https://example.com/a.jpg")

    assert result["id"] == 7
    assert result["photo_url"] == "https://example.com/a.jpg"
    conn.commit.assert_called_once()
    insert_call = cur.execute.call_args_list[0]
    assert "ON DUPLICATE KEY UPDATE" in insert_call.args[0]


@patch("src.analytics.db_results.get_pooled_connection")
def test_delete_participant_photo_returns_true_on_success(mock_get_conn):
    conn, cur = _mock_conn()
    mock_get_conn.return_value = conn
    cur.rowcount = 1

    assert delete_participant_photo(7) is True
    conn.commit.assert_called_once()


@patch("src.analytics.db_results.get_pooled_connection")
def test_delete_participant_photo_returns_false_when_not_found(mock_get_conn):
    conn, cur = _mock_conn()
    mock_get_conn.return_value = conn
    cur.rowcount = 0

    assert delete_participant_photo(999) is False
