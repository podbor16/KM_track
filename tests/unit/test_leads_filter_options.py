"""Тесты для get_leads_filter_options() — каскадные фильтры события/года/
дистанции для вкладки «Стартовый список» в /admin (используется и как
фоллбэк event_name/event_year при импорте, см. upload_leads_import)."""
from unittest.mock import MagicMock, patch

from src.analytics.db_results import get_leads_filter_options


def _mock_conn():
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value = cur
    return conn, cur


@patch("src.analytics.db_results.get_pooled_connection")
def test_event_names_union_leads_and_events(mock_get_conn):
    """Реальный случай (Детский забег 2026, 2026-08-19): событие уже
    сконфигурировано и есть строка в events, но заявок в leads ещё 0 —
    раньше такое событие не появлялось в фильтре вообще (курица-яйцо: его
    нельзя выбрать для самого первого импорта). UNION с events закрывает
    этот пробел."""
    conn, cur = _mock_conn()
    mock_get_conn.return_value = conn
    cur.fetchall.return_value = [("Детский забег",), ("Жара",)]

    result = get_leads_filter_options()

    assert result["event_names"] == ["Детский забег", "Жара"]
    select_call = cur.execute.call_args_list[0]
    assert "UNION" in select_call.args[0]
    assert "FROM events" in select_call.args[0]


@patch("src.analytics.db_results.get_pooled_connection")
def test_years_union_leads_and_events(mock_get_conn):
    conn, cur = _mock_conn()
    mock_get_conn.return_value = conn
    cur.fetchall.return_value = [(2026,)]

    result = get_leads_filter_options(event_name="Детский забег")

    assert result["years"] == [2026]
    # [0] — всегда event_names, [1] — years (выполняется, раз передан event_name)
    years_call = cur.execute.call_args_list[1]
    assert "UNION" in years_call.args[0]
    assert "FROM events" in years_call.args[0]
    # event_name подставляется в оба SELECT UNION'а (leads и events)
    assert years_call.args[1] == ("Детский забег", "Детский забег")


@patch("src.analytics.db_results.get_pooled_connection")
def test_distances_not_unioned_with_events(mock_get_conn):
    """events.event_distance хранит число (км), leads.event_distance —
    отформатированную строку ("1 км") — форматы несовместимы, distances
    остаётся источником только leads (иначе фильтр показал бы "1.0"
    вместо "1 км")."""
    conn, cur = _mock_conn()
    mock_get_conn.return_value = conn
    cur.fetchall.return_value = [("1 км",)]

    get_leads_filter_options(event_name="Детский забег")

    # [0] — event_names, [1] — years, [2] — distances (все три выполняются,
    # раз передан event_name)
    distances_call = cur.execute.call_args_list[2]
    assert "UNION" not in distances_call.args[0]
    assert "FROM events" not in distances_call.args[0]
    assert "FROM leads" in distances_call.args[0]


@patch("src.analytics.db_results.get_pooled_connection")
def test_no_connection_returns_empty_lists(mock_get_conn):
    mock_get_conn.return_value = None
    result = get_leads_filter_options()
    assert result == {"event_names": [], "years": [], "distances": []}
