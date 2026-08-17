"""Тесты для настраиваемых возрастных групп (age_group_configs) —
get_age_group_label() и CRUD (list/create/update/delete_age_group)."""
from unittest.mock import MagicMock, patch

import src.analytics.db_results as db_results
from src.analytics.db_results import (
    get_age_group_label, calculate_age_group,
    create_age_group, update_age_group, delete_age_group, list_age_groups,
)


def _mock_conn():
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value = cur
    return conn, cur


def setup_function():
    # Кэш _get_age_group_configs() общий на модуль — сбрасываем перед каждым
    # тестом, иначе результат одного теста протекает в следующий.
    db_results._age_group_cache = {}
    db_results._age_group_cache_ts = 0.0


# --- get_age_group_label ---------------------------------------------------

@patch("src.analytics.db_results.get_pooled_connection")
def test_uses_configured_bracket_when_present(mock_get_conn):
    conn, cur = _mock_conn()
    mock_get_conn.return_value = conn
    cur.fetchall.return_value = [
        {"event_name": "Жара", "event_distance": "5 км", "sex": "M", "min_age": 0, "max_age": 49, "label": "М49"},
        {"event_name": "Жара", "event_distance": "5 км", "sex": "M", "min_age": 50, "max_age": 59, "label": "М50-59"},
    ]

    label = get_age_group_label("Жара", "5 км", "1990-01-01", "Мужчина")

    assert label == "М49"


@patch("src.analytics.db_results.get_pooled_connection")
def test_picks_correct_bracket_at_boundary(mock_get_conn):
    """Ровно 50 лет должно попасть в "50-59", не в "49" (min_age=50 —
    граница включительно)."""
    conn, cur = _mock_conn()
    mock_get_conn.return_value = conn
    cur.fetchall.return_value = [
        {"event_name": "Жара", "event_distance": "5 км", "sex": "M", "min_age": 0, "max_age": 49, "label": "М49"},
        {"event_name": "Жара", "event_distance": "5 км", "sex": "M", "min_age": 50, "max_age": 59, "label": "М50-59"},
    ]

    label = get_age_group_label("Жара", "5 км", 50, "Мужчина")

    assert label == "М50-59"


@patch("src.analytics.db_results.get_pooled_connection")
def test_open_ended_top_bracket(mock_get_conn):
    conn, cur = _mock_conn()
    mock_get_conn.return_value = conn
    cur.fetchall.return_value = [
        {"event_name": "Жара", "event_distance": "5 км", "sex": "M", "min_age": 75, "max_age": None, "label": "М75+"},
    ]

    label = get_age_group_label("Жара", "5 км", 90, "Мужчина")

    assert label == "М75+"


@patch("src.analytics.db_results.get_pooled_connection")
def test_falls_back_to_calculate_age_group_without_config(mock_get_conn):
    """Для события/дистанции без настроенных границ — старый развёрнутый
    формат, как раньше."""
    conn, cur = _mock_conn()
    mock_get_conn.return_value = conn
    cur.fetchall.return_value = []  # в age_group_configs пусто

    label = get_age_group_label("Ночной забег", "5 км", "1990-01-01", "Мужчина")

    assert label == calculate_age_group("1990-01-01", "Мужчина")
    assert "до 49" in label  # развёрнутый формат, не компактный


@patch("src.analytics.db_results.get_pooled_connection")
def test_falls_back_when_config_exists_for_other_event(mock_get_conn):
    """Границы заданы для Жары — для другого события используется
    дефолт, а не чужие границы."""
    conn, cur = _mock_conn()
    mock_get_conn.return_value = conn
    cur.fetchall.return_value = [
        {"event_name": "Жара", "event_distance": "5 км", "sex": "M", "min_age": 0, "max_age": 49, "label": "М49"},
    ]

    label = get_age_group_label("Ночной забег", "5 км", "1990-01-01", "Мужчина")

    assert label != "М49"


@patch("src.analytics.db_results.get_pooled_connection")
def test_female_uses_female_brackets(mock_get_conn):
    conn, cur = _mock_conn()
    mock_get_conn.return_value = conn
    cur.fetchall.return_value = [
        {"event_name": "Жара", "event_distance": "5 км", "sex": "M", "min_age": 0, "max_age": 49, "label": "М49"},
        {"event_name": "Жара", "event_distance": "5 км", "sex": "F", "min_age": 0, "max_age": 49, "label": "Ж49"},
    ]

    label = get_age_group_label("Жара", "5 км", "1990-01-01", "Женщина")

    assert label == "Ж49"


def test_no_birthday_returns_unknown():
    assert get_age_group_label("Жара", "5 км", None, "Мужчина") == "Неизвестно"


# --- CRUD --------------------------------------------------------------

@patch("src.analytics.db_results.get_pooled_connection")
def test_create_age_group_returns_created_row(mock_get_conn):
    conn, cur = _mock_conn()
    mock_get_conn.return_value = conn
    cur.lastrowid = 7
    cur.fetchone.return_value = {
        "id": 7, "event_name": "Жара", "event_distance": "5 км",
        "sex": "M", "min_age": 0, "max_age": 49, "label": "М49",
    }

    result = create_age_group("Жара", "5 км", "M", 0, 49, "М49")

    assert result["id"] == 7
    assert result["label"] == "М49"
    conn.commit.assert_called_once()


@patch("src.analytics.db_results.get_pooled_connection")
def test_create_age_group_invalidates_cache(mock_get_conn):
    db_results._age_group_cache = {("x", "y", "M"): [(0, 49, "old")]}
    db_results._age_group_cache_ts = 999999999.0  # "свежий" кэш до вызова

    conn, cur = _mock_conn()
    mock_get_conn.return_value = conn
    cur.lastrowid = 1
    cur.fetchone.return_value = {"id": 1, "event_name": "x", "event_distance": "y",
                                  "sex": "M", "min_age": 0, "max_age": 49, "label": "new"}

    create_age_group("x", "y", "M", 0, 49, "new")

    assert db_results._age_group_cache_ts == 0.0


@patch("src.analytics.db_results.get_pooled_connection")
def test_update_age_group_applies_fields(mock_get_conn):
    conn, cur = _mock_conn()
    mock_get_conn.return_value = conn
    cur.fetchone.return_value = {
        "id": 7, "event_name": "Жара", "event_distance": "5 км",
        "sex": "M", "min_age": 0, "max_age": 44, "label": "М44",
    }

    result = update_age_group(7, {"max_age": 44, "label": "М44"})

    assert result["max_age"] == 44
    update_call = next(c for c in cur.execute.call_args_list if "UPDATE age_group_configs" in c.args[0])
    assert "max_age" in update_call.args[0]
    assert "label" in update_call.args[0]


@patch("src.analytics.db_results.get_pooled_connection")
def test_update_age_group_ignores_unknown_fields(mock_get_conn):
    conn, cur = _mock_conn()
    mock_get_conn.return_value = conn

    result = update_age_group(7, {"unknown_field": "x"})

    assert result is None
    cur.execute.assert_not_called()


@patch("src.analytics.db_results.get_pooled_connection")
def test_delete_age_group_returns_true_on_success(mock_get_conn):
    conn, cur = _mock_conn()
    mock_get_conn.return_value = conn
    cur.rowcount = 1

    assert delete_age_group(7) is True
    conn.commit.assert_called_once()


@patch("src.analytics.db_results.get_pooled_connection")
def test_delete_age_group_returns_false_when_not_found(mock_get_conn):
    conn, cur = _mock_conn()
    mock_get_conn.return_value = conn
    cur.rowcount = 0

    assert delete_age_group(999) is False


@patch("src.analytics.db_results.get_pooled_connection")
def test_list_age_groups_filters_by_event(mock_get_conn):
    conn, cur = _mock_conn()
    mock_get_conn.return_value = conn
    cur.fetchall.return_value = [
        {"id": 1, "event_name": "Жара", "event_distance": "5 км", "sex": "M", "min_age": 0, "max_age": 49, "label": "М49"},
    ]

    result = list_age_groups(event_name="Жара")

    assert len(result) == 1
    select_call = cur.execute.call_args_list[0]
    assert "event_name = %s" in select_call.args[0]
    assert "Жара" in select_call.args[1]
