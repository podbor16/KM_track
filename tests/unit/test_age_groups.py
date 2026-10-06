"""Тесты для настраиваемых возрастных групп (age_group_configs) —
get_age_group_label() и CRUD (list/create/update/delete_age_group)."""
import datetime
from unittest.mock import MagicMock, patch

import src.analytics.db_results as db_results
from src.analytics.db_results import (
    get_age_group_label,
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
def test_empty_string_without_config(mock_get_conn):
    """Для события/дистанции без настроенных границ — пустая строка, не
    развёрнутый текст (calculate_age_group() как фоллбэк убран по всему
    проекту, не только для Жары)."""
    conn, cur = _mock_conn()
    mock_get_conn.return_value = conn
    cur.fetchall.return_value = []  # в age_group_configs пусто

    label = get_age_group_label("Ночной забег", "5 км", "1990-01-01", "Мужчина")

    assert label == ''


@patch("src.analytics.db_results.get_pooled_connection")
def test_age_error_when_age_outside_all_configured_brackets(mock_get_conn):
    """Границы заданы, но возраст участника не попадает НИ В ОДИН из них
    (напр. несовершеннолетний на дистанции, где брекеты начинаются с 18) —
    явный маркер "Ошибка возраста" (сигнал непочищенной регистрации), не
    пустая строка и не развёрнутый текст."""
    conn, cur = _mock_conn()
    mock_get_conn.return_value = conn
    cur.fetchall.return_value = [
        {"event_name": "Жара", "event_distance": "21.1 км", "sex": "M", "min_age": 18, "max_age": 24, "label": "М18-24"},
    ]

    label = get_age_group_label("Жара", "21.1 км", 15, "Мужчина")

    assert label == 'Ошибка возраста'


@patch("src.analytics.db_results.get_pooled_connection")
def test_import_source_gets_minimum_bracket_instead_of_age_error(mock_get_conn):
    """source='import' (bulk-импорт из обработанного организатором файла,
    см. bulk_import_leads()) — для регистрации младше минимального возраста
    дистанции присваиваем минимальную возрастную категорию вместо "Ошибка
    возраста" (организатор уже разобрался с такими случаями руками при
    подготовке файла, 2026-08-19)."""
    conn, cur = _mock_conn()
    mock_get_conn.return_value = conn
    cur.fetchall.return_value = [
        {"event_name": "Жара", "event_distance": "21.1 км", "sex": "M", "min_age": 18, "max_age": 24, "label": "М18-24"},
        {"event_name": "Жара", "event_distance": "21.1 км", "sex": "M", "min_age": 25, "max_age": None, "label": "М25+"},
    ]

    label = get_age_group_label("Жара", "21.1 км", 15, "Мужчина", source="import")

    assert label == "М18-24"


@patch("src.analytics.db_results.get_pooled_connection")
def test_webhook_source_still_returns_age_error(mock_get_conn):
    """source='webhook' (или не передан вовсе) — поведение не меняется:
    "Ошибка возраста", регистрация требует ручной проверки организатором."""
    conn, cur = _mock_conn()
    mock_get_conn.return_value = conn
    cur.fetchall.return_value = [
        {"event_name": "Жара", "event_distance": "21.1 км", "sex": "M", "min_age": 18, "max_age": 24, "label": "М18-24"},
    ]

    label = get_age_group_label("Жара", "21.1 км", 15, "Мужчина", source="webhook")

    assert label == 'Ошибка возраста'


@patch("src.analytics.db_results.get_pooled_connection")
def test_falls_back_when_config_exists_for_other_event(mock_get_conn):
    """Границы заданы для Жары — для другого события они не применяются
    (используется общий фоллбэк "нет конфига", не чужие границы)."""
    conn, cur = _mock_conn()
    mock_get_conn.return_value = conn
    cur.fetchall.return_value = [
        {"event_name": "Жара", "event_distance": "5 км", "sex": "M", "min_age": 0, "max_age": 49, "label": "М49"},
    ]

    label = get_age_group_label("Ночной забег", "5 км", "1990-01-01", "Мужчина")

    assert label == ''


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


def test_sentinel_1900_birthday_returns_unknown_not_126_years_old():
    """leads.birthday NOT NULL DEFAULT '1900-01-01' — сентинел "дата не
    указана" (регистрация без даты рождения, необязательное поле с
    2026-08-18), не настоящий возраст. Раньше давало age=126, которое
    попадало в любой открытый верхний брекет (напр. "80+")."""
    assert get_age_group_label("Жара", "5 км", "1900-01-01", "Мужчина") == "Неизвестно"
    assert get_age_group_label("Жара", "5 км", datetime.date(1900, 1, 1), "Мужчина") == "Неизвестно"


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


# --- общая кнопка «Сохранить» (save_age_groups) ----------------------------

from src.analytics.db_results import save_age_groups, validate_age_groups  # noqa: E402
import pytest  # noqa: E402


def test_validate_age_groups_reports_problems():
    errors = validate_age_groups([
        {"sex": "M", "min_age": 0, "max_age": 49, "label": "М49"},
        {"sex": "M", "min_age": 0, "max_age": 59, "label": "М50"},
        {"sex": "F", "min_age": 50, "max_age": 40, "label": "Ж50"},
        {"sex": "F", "min_age": 60, "max_age": None, "label": " "},
    ])
    assert any("две границы начинаются с 0" in e for e in errors)
    assert any("«До» меньше «От»" in e for e in errors)
    assert any("не заполнена метка" in e for e in errors)


def test_validate_age_groups_same_min_for_different_sex_ok():
    assert validate_age_groups([
        {"sex": "M", "min_age": 0, "max_age": None, "label": "М"},
        {"sex": "F", "min_age": 0, "max_age": None, "label": "Ж"},
    ]) == []


@patch("src.analytics.db_results.get_pooled_connection")
def test_save_age_groups_invalid_writes_nothing(mock_get_conn):
    with pytest.raises(ValueError):
        save_age_groups("Жара", "5 км", [{"sex": "M", "min_age": 10, "max_age": 5, "label": "М"}])
    mock_get_conn.assert_not_called()


@patch("src.analytics.db_results.get_pooled_connection")
def test_save_age_groups_shifts_then_updates_then_inserts_in_one_transaction(mock_get_conn):
    conn, cur = _mock_conn()
    conn.in_transaction = False
    cur.rowcount = 1
    cur.fetchall.return_value = []
    mock_get_conn.return_value = conn
    save_age_groups("Жара", "5 км", [
        {"id": 1, "sex": "M", "min_age": 50, "max_age": None, "label": "М50+"},   # обмен «От» с id=2
        {"id": 2, "sex": "M", "min_age": 0, "max_age": 49, "label": "М49"},
        {"sex": "F", "min_age": 0, "max_age": None, "label": "Ж"},
    ])
    sqls = [c.args[0] for c in cur.execute.call_args_list]
    shift = [i for i, s in enumerate(sqls) if "min_age + %s" in s]
    final = [i for i, s in enumerate(sqls) if s.startswith("UPDATE age_group_configs SET sex")]
    insert = [i for i, s in enumerate(sqls) if s.startswith("INSERT")]
    assert len(shift) == 2 and len(final) == 2 and len(insert) == 1
    assert max(shift) < min(final) < max(final) < insert[0]
    # пустое «До» уходит в БД как NULL — раньше PATCH его отбрасывал
    assert cur.execute.call_args_list[final[0]].args[1][2] is None
    conn.start_transaction.assert_called_once()
    conn.rollback.assert_not_called()


@patch("src.analytics.db_results.get_pooled_connection")
def test_save_age_groups_missing_row_rolls_back(mock_get_conn):
    conn, cur = _mock_conn()
    conn.in_transaction = False
    cur.rowcount = 0
    mock_get_conn.return_value = conn
    with pytest.raises(ValueError, match="не найдена"):
        save_age_groups("Жара", "5 км", [{"id": 7, "sex": "M", "min_age": 0, "max_age": None, "label": "М"}])
    conn.rollback.assert_called_once()
    conn.commit.assert_not_called()
    conn.close.assert_called()


@patch("src.analytics.db_results.get_pooled_connection")
def test_no_connection_does_not_retry_per_lead(mock_get_conn):
    """Пул исчерпан — раньше каждая из 60 тыс. заявок стартового списка снова просила
    соединение (пустой кеш считался «нет кеша»), запрос висел десятки минут (2026-10-06)."""
    mock_get_conn.return_value = None
    for _ in range(100):
        get_age_group_label("Жара", "5 км", 30, "Мужчина")
    assert mock_get_conn.call_count == 1


@patch("src.analytics.db_results.get_pooled_connection")
def test_empty_config_table_cached_too(mock_get_conn):
    conn, cur = _mock_conn()
    mock_get_conn.return_value = conn
    cur.fetchall.return_value = []
    for _ in range(50):
        get_age_group_label("Жара", "5 км", 30, "Мужчина")
    assert mock_get_conn.call_count == 1
