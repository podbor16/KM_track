"""Тесты для bulk_import_leads() / preview_leads_import_matches() —
сопоставление строк Tilda-импорта с leads по surname+name+birthday+событие."""
from unittest.mock import MagicMock, patch

from src.analytics.db_results import bulk_import_leads, preview_leads_import_matches
from src.krasmarafon.services.tilda_import_parser import ImportRow


def _row(**kw):
    base = dict(row_number=2, surname="Иванов", name="Иван", birthday="1990-01-01",
                event_name="Весна", event_year=2027, event_distance="5 км",
                sex="", city="", email="", phone="")
    base.update(kw)
    return ImportRow(**base)


def _mock_conn():
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value = cur
    return conn, cur


# --- bulk_import_leads ---------------------------------------------------

@patch("src.analytics.db_results.get_pooled_connection")
def test_updates_single_matched_row(mock_get_conn):
    conn, cur = _mock_conn()
    mock_get_conn.return_value = conn
    cur.fetchall.return_value = [{"id": 101}]

    summary = bulk_import_leads([_row(city="Красноярск")])

    assert summary["updated"] == 1
    assert summary["created"] == 0
    assert summary["errors"] == []
    conn.commit.assert_called_once()


@patch("src.analytics.db_results.get_pooled_connection")
def test_updates_all_rows_in_existing_duplicate_group(mock_get_conn):
    conn, cur = _mock_conn()
    mock_get_conn.return_value = conn
    cur.fetchall.return_value = [{"id": 101}, {"id": 102}]  # уже дубль-группа из 2 строк

    summary = bulk_import_leads([_row()])

    assert summary["updated"] == 2
    assert summary["created"] == 0


@patch("src.analytics.db_results.recompute_duplicate_flag")
@patch("src.analytics.db_results.get_pooled_connection")
def test_no_match_creates_new_lead_and_recomputes_duplicate_flag(mock_get_conn, mock_recompute):
    conn, cur = _mock_conn()
    mock_get_conn.return_value = conn
    # первый SELECT (поиск совпадений) — пусто; после INSERT — SELECT
    # client_id/event_id новой строки
    cur.fetchall.return_value = []
    cur.lastrowid = 999
    cur.fetchone.return_value = {"client_id": 55, "event_id": 3}

    summary = bulk_import_leads([_row()])

    assert summary["updated"] == 0
    assert summary["created"] == 1
    insert_calls = [c for c in cur.execute.call_args_list if "INSERT INTO leads" in c.args[0]]
    assert len(insert_calls) == 1
    mock_recompute.assert_called_once_with(client_id=55, event_id=3)


@patch("src.analytics.db_results.get_pooled_connection")
def test_no_connection_returns_zero_summary_with_error(mock_get_conn):
    mock_get_conn.return_value = None
    summary = bulk_import_leads([_row()])
    assert summary == {"updated": 0, "created": 0, "errors": ["Нет соединения с БД"]}


@patch("src.analytics.db_results.get_pooled_connection")
def test_db_error_rolls_back_and_reports_error(mock_get_conn):
    conn, cur = _mock_conn()
    mock_get_conn.return_value = conn
    cur.execute.side_effect = Exception("boom")

    summary = bulk_import_leads([_row()])

    assert summary["errors"] == ["boom"]
    conn.rollback.assert_called_once()


# --- preview_leads_import_matches -----------------------------------------

@patch("src.analytics.db_results.get_pooled_connection")
def test_preview_marks_matched_row_as_update(mock_get_conn):
    conn, cur = _mock_conn()
    mock_get_conn.return_value = conn
    cur.fetchone.return_value = (1,)

    preview = preview_leads_import_matches([_row()])

    assert preview[0]["will"] == "update"
    assert preview[0]["matched_count"] == 1


@patch("src.analytics.db_results.get_pooled_connection")
def test_preview_marks_unmatched_row_as_create(mock_get_conn):
    conn, cur = _mock_conn()
    mock_get_conn.return_value = conn
    cur.fetchone.return_value = (0,)

    preview = preview_leads_import_matches([_row()])

    assert preview[0]["will"] == "create"
    assert preview[0]["matched_count"] == 0


@patch("src.analytics.db_results.get_pooled_connection")
def test_preview_no_connection_returns_unknown(mock_get_conn):
    mock_get_conn.return_value = None
    preview = preview_leads_import_matches([_row()])
    assert preview[0]["will"] == "unknown"
