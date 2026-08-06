from unittest.mock import patch, MagicMock

from src.siberman.google_sheet_sync import extract_sheet_id, fetch_sheet_xlsx, sync_google_sheet
from src.siberman.parser import ParseResult


def test_extract_sheet_id_from_full_edit_url():
    url = "https://docs.google.com/spreadsheets/d/18zFxQro0xtJJyjEaO5mwHGIKtGJ8uGM4uNjhWRtxUlM/edit?usp=sharing"
    assert extract_sheet_id(url) == "18zFxQro0xtJJyjEaO5mwHGIKtGJ8uGM4uNjhWRtxUlM"


def test_extract_sheet_id_passthrough_for_bare_id():
    assert extract_sheet_id("18zFxQro0xtJJyjEaO5mwHGIKtGJ8uGM4uNjhWRtxUlM") == "18zFxQro0xtJJyjEaO5mwHGIKtGJ8uGM4uNjhWRtxUlM"


@patch("src.siberman.google_sheet_sync.requests.get")
def test_fetch_sheet_xlsx_returns_bytes_on_success(mock_get):
    mock_resp = MagicMock()
    mock_resp.headers = {"Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}
    mock_resp.content = b"PK\x03\x04fake-xlsx-bytes"
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    result = fetch_sheet_xlsx("SHEET_ID")

    assert result == b"PK\x03\x04fake-xlsx-bytes"
    called_url = mock_get.call_args[0][0]
    assert called_url == "https://docs.google.com/spreadsheets/d/SHEET_ID/export?format=xlsx"


@patch("src.siberman.google_sheet_sync.requests.get")
def test_fetch_sheet_xlsx_raises_readable_error_when_not_publicly_shared(mock_get):
    mock_resp = MagicMock()
    mock_resp.headers = {"Content-Type": "text/html; charset=utf-8"}
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    try:
        fetch_sheet_xlsx("SHEET_ID")
        assert False, "должно было бросить ValueError"
    except ValueError as e:
        assert "ссылке" in str(e)


def _mk_conn():
    return MagicMock()


@patch("src.siberman.google_sheet_sync.get_google_sheet_config")
def test_sync_disabled_skips_fetch_entirely(mock_cfg):
    mock_cfg.return_value = {"sheet_id": "SHEET_ID", "enabled": False, "last_hash": None}

    result = sync_google_sheet(_mk_conn(), 2026)

    assert result == {"ok": True, "enabled": False, "changed": False}


@patch("src.siberman.google_sheet_sync.get_google_sheet_config")
def test_sync_enabled_without_sheet_id_returns_error(mock_cfg):
    mock_cfg.return_value = {"sheet_id": None, "enabled": True, "last_hash": None}

    result = sync_google_sheet(_mk_conn(), 2026)

    assert result["ok"] is False


@patch("src.siberman.google_sheet_sync.apply_parse_result_upsert")
@patch("src.siberman.google_sheet_sync.parse_excel")
@patch("src.siberman.google_sheet_sync.set_google_sheet_last_hash")
@patch("src.siberman.google_sheet_sync.fetch_sheet_xlsx")
@patch("src.siberman.google_sheet_sync.get_google_sheet_config")
def test_sync_unchanged_content_skips_parse_and_apply(mock_cfg, mock_fetch, mock_set_hash, mock_parse, mock_apply):
    content = b"same-bytes"
    import hashlib
    same_hash = hashlib.sha256(content).hexdigest()
    mock_cfg.return_value = {"sheet_id": "SHEET_ID", "enabled": True, "last_hash": same_hash}
    mock_fetch.return_value = content

    result = sync_google_sheet(_mk_conn(), 2026)

    assert result == {"ok": True, "enabled": True, "changed": False}
    mock_parse.assert_not_called()
    mock_apply.assert_not_called()
    mock_set_hash.assert_not_called()


@patch("src.siberman.google_sheet_sync.convert_bike_times_to_elapsed")
@patch("src.siberman.google_sheet_sync.get_race_start")
@patch("src.siberman.google_sheet_sync.apply_parse_result_upsert")
@patch("src.siberman.google_sheet_sync.parse_excel")
@patch("src.siberman.google_sheet_sync.set_google_sheet_last_hash")
@patch("src.siberman.google_sheet_sync.fetch_sheet_xlsx")
@patch("src.siberman.google_sheet_sync.get_google_sheet_config")
def test_sync_changed_content_parses_and_applies_then_updates_hash(
    mock_cfg, mock_fetch, mock_set_hash, mock_parse, mock_apply, mock_race_start, mock_convert,
):
    import datetime
    mock_cfg.return_value = {"sheet_id": "SHEET_ID", "enabled": True, "last_hash": "old-hash"}
    mock_fetch.return_value = b"new-bytes"
    mock_race_start.return_value = datetime.datetime(2026, 8, 8, 8, 0, 0)
    parsed = ParseResult(race_year=2026, participants=[{"bib": "1"}], errors=[])
    mock_parse.return_value = parsed
    mock_convert.return_value = {"1": 3600}
    mock_apply.return_value = {"ok": True, "participants": 1, "checkpoint_times": 0}

    conn = _mk_conn()
    result = sync_google_sheet(conn, 2026)

    mock_parse.assert_called_once_with(b"new-bytes", 2026)
    # race_start=08:00:00 -> 28800с — astronomical bike-время конвертируется
    # в elapsed ДО записи в БД (2026-08-06: без этого шага cumulative_s
    # писался как "секунды от полуночи", давая огромные "часы этапа").
    mock_convert.assert_called_once_with(parsed, 28800)
    assert parsed.handicaps == {"1": 3600}
    mock_apply.assert_called_once_with(conn, parsed)
    import hashlib
    expected_hash = hashlib.sha256(b"new-bytes").hexdigest()
    mock_set_hash.assert_called_once_with(conn, 2026, expected_hash)
    assert result["changed"] is True
    assert result["participants"] == 1


@patch("src.siberman.google_sheet_sync.get_race_start")
@patch("src.siberman.google_sheet_sync.apply_parse_result_upsert")
@patch("src.siberman.google_sheet_sync.parse_excel")
@patch("src.siberman.google_sheet_sync.fetch_sheet_xlsx")
@patch("src.siberman.google_sheet_sync.get_google_sheet_config")
def test_sync_changed_content_without_race_start_returns_error_without_applying(
    mock_cfg, mock_fetch, mock_parse, mock_apply, mock_race_start,
):
    mock_cfg.return_value = {"sheet_id": "SHEET_ID", "enabled": True, "last_hash": "old-hash"}
    mock_fetch.return_value = b"new-bytes"
    mock_race_start.return_value = None

    result = sync_google_sheet(_mk_conn(), 2026)

    assert result["ok"] is False
    mock_parse.assert_not_called()
    mock_apply.assert_not_called()
