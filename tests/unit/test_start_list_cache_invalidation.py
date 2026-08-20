"""Тесты для invalidate_start_list_cache() — сброс in-memory кеша
get_test_table_data() (TTL 5 минут) сразу после прямой правки leads.

Реальная находка (2026-08-20): организатор переимпортировал файл Детского
забега с добавленными стартовыми номерами — номера записались в БД
корректно, но /start_list не показывал их до истечения 5-минутного TTL
кеша, независимо от того, сколько раз перезагружали страницу."""
from unittest.mock import MagicMock, patch

from src.analytics import db_results
from src.analytics.db_results import (
    invalidate_start_list_cache, bulk_import_leads, update_lead,
)
from src.krasmarafon.services.tilda_import_parser import ImportRow


def _row(**kw):
    base = dict(row_number=2, surname="Иванов", name="Иван", birthday="1990-01-01",
                event_name="Весна", event_year=2027, event_distance="5 км",
                sex="", city="", club="", email="", phone="")
    base.update(kw)
    return ImportRow(**base)


def _mock_conn():
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value = cur
    return conn, cur


def test_invalidate_start_list_cache_resets_module_globals():
    db_results._start_list_cache = [{"surname": "Иванов"}]
    db_results._start_list_cache_ts = 123456.0

    invalidate_start_list_cache()

    assert db_results._start_list_cache == []
    assert db_results._start_list_cache_ts == 0.0


@patch("src.analytics.db_results.invalidate_start_list_cache")
@patch("src.analytics.db_results.get_pooled_connection")
def test_bulk_import_leads_invalidates_cache_after_successful_commit(mock_get_conn, mock_invalidate):
    conn, cur = _mock_conn()
    mock_get_conn.return_value = conn
    cur.fetchall.side_effect = [[{"id": 101}], []]

    bulk_import_leads([_row()])

    mock_invalidate.assert_called_once()


@patch("src.analytics.db_results.invalidate_start_list_cache")
@patch("src.analytics.db_results.get_pooled_connection")
def test_bulk_import_leads_does_not_invalidate_cache_on_db_error(mock_get_conn, mock_invalidate):
    conn, cur = _mock_conn()
    mock_get_conn.return_value = conn
    cur.execute.side_effect = Exception("boom")

    bulk_import_leads([_row()])

    mock_invalidate.assert_not_called()


@patch("src.analytics.db_results.invalidate_start_list_cache")
@patch("src.analytics.db_results.get_pooled_connection")
def test_bulk_import_leads_does_not_invalidate_cache_without_connection(mock_get_conn, mock_invalidate):
    mock_get_conn.return_value = None

    bulk_import_leads([_row()])

    mock_invalidate.assert_not_called()


@patch("src.analytics.db_results.invalidate_start_list_cache")
@patch("src.analytics.db_results.get_pooled_connection")
def test_update_lead_invalidates_cache_after_successful_commit(mock_get_conn, mock_invalidate):
    conn, cur = _mock_conn()
    mock_get_conn.return_value = conn
    cur.fetchone.return_value = {"id": 1, "surname": "Иванов", "name": "Иван"}

    update_lead(1, {"status": 1})

    mock_invalidate.assert_called_once()
