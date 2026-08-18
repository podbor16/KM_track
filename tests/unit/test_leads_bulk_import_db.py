"""Тесты для bulk_import_leads() / preview_leads_import_matches() —
сопоставление строк Tilda-импорта с leads по surname+name+birthday+событие."""
from unittest.mock import MagicMock, patch

from src.analytics.db_results import bulk_import_leads, preview_leads_import_matches
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


# --- bulk_import_leads ---------------------------------------------------

@patch("src.analytics.db_results.get_pooled_connection")
def test_updates_single_matched_row(mock_get_conn):
    conn, cur = _mock_conn()
    mock_get_conn.return_value = conn
    # 1-й fetchall — _find_lead_matches; 2-й — реконсиляция "пропавших" для
    # этого события/года (пусто, вне фокуса этого теста)
    cur.fetchall.side_effect = [[{"id": 101}], []]

    summary = bulk_import_leads([_row(city="Красноярск")])

    assert summary["updated"] == 1
    assert summary["created"] == 0
    assert summary["errors"] == []
    conn.commit.assert_called_once()


@patch("src.analytics.db_results.get_pooled_connection")
def test_matches_by_order_id_even_when_surname_name_changed(mock_get_conn):
    """Реальный инцидент (Жара 2026, 2026-08-17): организатор поправил
    фамилию/имя с английского на русское написание в Tilda и переимпортировал
    — заявка должна обновить СУЩЕСТВУЮЩУЮ строку (найденную по order_id),
    а не создать дубль, хотя surname/name в файле теперь другие."""
    conn, cur = _mock_conn()
    mock_get_conn.return_value = conn
    # найдено по order_id с первого запроса; 2-й fetchall — реконсиляция "пропавших"
    cur.fetchall.side_effect = [[{"id": 34901}], []]

    summary = bulk_import_leads([_row(surname="Казаков", name="Олег", order_id="1644133682")])

    assert summary["updated"] == 1
    assert summary["created"] == 0
    select_calls = [c for c in cur.execute.call_args_list if "SELECT id FROM leads" in c.args[0]]
    assert len(select_calls) == 1  # совпало по order_id — фоллбэк на surname+name не понадобился
    assert "order_id" in select_calls[0].args[0]
    assert 1644133682 in select_calls[0].args[1]


@patch("src.analytics.db_results.get_pooled_connection")
def test_falls_back_to_name_match_when_order_id_not_found(mock_get_conn):
    conn, cur = _mock_conn()
    mock_get_conn.return_value = conn
    # order_id: пусто, потом surname+name: совпало; 3-й — реконсиляция "пропавших"
    cur.fetchall.side_effect = [[], [{"id": 555}], []]

    summary = bulk_import_leads([_row(order_id="999999")])

    assert summary["updated"] == 1
    select_calls = [c for c in cur.execute.call_args_list if "SELECT id FROM leads" in c.args[0]]
    assert len(select_calls) == 2
    assert "surname" in select_calls[1].args[0]


@patch("src.analytics.db_results.recompute_duplicate_flag")
@patch("src.analytics.db_results.get_pooled_connection")
def test_order_id_zero_treated_as_no_order_id(mock_get_conn, mock_recompute):
    """order_id=0 — заглушка Tilda для бесплатных/незавершённых заявок (199
    строк 184 разных людей делили это значение на реальных данных), не
    настоящий номер заказа — не должен участвовать в поиске совпадений."""
    conn, cur = _mock_conn()
    mock_get_conn.return_value = conn
    cur.fetchall.return_value = []  # ни по order_id (пропущен), ни по surname+name
    cur.lastrowid = 999
    cur.fetchone.return_value = {"client_id": 1, "event_id": 1}

    bulk_import_leads([_row(order_id="0")])

    select_calls = [c for c in cur.execute.call_args_list if "SELECT id FROM leads" in c.args[0]]
    assert len(select_calls) == 1  # order_id=0 пропущен — сразу фоллбэк на surname+name
    assert "surname" in select_calls[0].args[0]


@patch("src.analytics.db_results.get_pooled_connection")
def test_updates_all_rows_in_existing_duplicate_group(mock_get_conn):
    conn, cur = _mock_conn()
    mock_get_conn.return_value = conn
    # уже дубль-группа из 2 строк; 2-й fetchall — реконсиляция "пропавших"
    cur.fetchall.side_effect = [[{"id": 101}, {"id": 102}], []]

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


@patch("src.analytics.db_results.recompute_duplicate_flag")
@patch("src.analytics.db_results.get_pooled_connection")
def test_new_lead_insert_includes_payment_fields_from_import_row(mock_get_conn, mock_recompute):
    conn, cur = _mock_conn()
    mock_get_conn.return_value = conn
    cur.fetchall.return_value = []
    cur.lastrowid = 999
    cur.fetchone.return_value = {"client_id": 55, "event_id": 3}

    bulk_import_leads([_row(
        amount="4.9", promocode="99TEST", discount="485.1",
        order_id="1486212513", transaction_id="144860:7719674713",
        club="ILSS", payment_system="Банковская карта",
    )])

    insert_call = next(c for c in cur.execute.call_args_list if "INSERT INTO leads" in c.args[0])
    params = insert_call.args[1]
    assert params["amount"] == 4.9
    assert params["promocode"] == "99TEST"
    assert params["discount"] == 485.1
    assert params["order_id"] == 1486212513
    assert params["transaction_id"] == "144860:7719674713"
    assert params["club"] == "ILSS"
    assert params["payment_system"] == "Банковская карта"


@patch("src.analytics.db_results.recompute_duplicate_flag")
@patch("src.analytics.db_results.get_pooled_connection")
def test_new_lead_insert_includes_start_number(mock_get_conn, mock_recompute):
    conn, cur = _mock_conn()
    mock_get_conn.return_value = conn
    cur.fetchall.return_value = []
    cur.lastrowid = 999
    cur.fetchone.return_value = {"client_id": 55, "event_id": 3}

    bulk_import_leads([_row(start_number="42")])

    insert_call = next(c for c in cur.execute.call_args_list if "INSERT INTO leads" in c.args[0])
    assert insert_call.args[1]["start_number"] == 42


@patch("src.analytics.db_results.recompute_duplicate_flag")
@patch("src.analytics.db_results.get_pooled_connection")
def test_new_lead_insert_start_number_null_when_absent(mock_get_conn, mock_recompute):
    conn, cur = _mock_conn()
    mock_get_conn.return_value = conn
    cur.fetchall.return_value = []
    cur.lastrowid = 999
    cur.fetchone.return_value = {"client_id": 55, "event_id": 3}

    bulk_import_leads([_row()])  # start_number по умолчанию "" в _row()

    insert_call = next(c for c in cur.execute.call_args_list if "INSERT INTO leads" in c.args[0])
    assert insert_call.args[1]["start_number"] is None


@patch("src.analytics.db_results.get_pooled_connection")
def test_matched_row_update_applies_start_number_when_present(mock_get_conn):
    conn, cur = _mock_conn()
    mock_get_conn.return_value = conn
    cur.fetchall.side_effect = [[{"id": 101}], []]

    bulk_import_leads([_row(start_number="7")])

    start_number_calls = [
        c for c in cur.execute.call_args_list
        if "UPDATE leads SET start_number" in c.args[0]
    ]
    assert len(start_number_calls) == 1
    assert start_number_calls[0].args[1] == [7, 101]


@patch("src.analytics.db_results.get_pooled_connection")
def test_matched_row_update_preserves_start_number_when_absent(mock_get_conn):
    """Номер не в каждом импорте — повторный импорт файла БЕЗ колонки
    "Номер" не должен затирать уже проставленный номер у существующей
    заявки (в отличие от club/phone и т.п., где "пусто в файле" = "стереть",
    номер — намеренное исключение из этого правила)."""
    conn, cur = _mock_conn()
    mock_get_conn.return_value = conn
    cur.fetchall.side_effect = [[{"id": 101}], []]

    bulk_import_leads([_row()])  # start_number по умолчанию "" в _row()

    start_number_calls = [
        c for c in cur.execute.call_args_list
        if "UPDATE leads SET start_number" in c.args[0]
    ]
    assert start_number_calls == []


@patch("src.analytics.db_results.recompute_duplicate_flag")
@patch("src.analytics.db_results.get_pooled_connection")
def test_new_lead_insert_maps_empty_birthday_to_sentinel(mock_get_conn, mock_recompute):
    """Дата рождения необязательна при импорте (2026-08-18) — ImportRow с
    birthday="" (parse_tilda_export больше не отбраковывает такие строки).
    leads.birthday NOT NULL — явно подставляем сентинел '1900-01-01', не
    полагаясь на DEFAULT колонки (сработал бы только без явного значения
    в INSERT)."""
    conn, cur = _mock_conn()
    mock_get_conn.return_value = conn
    cur.fetchall.return_value = []
    cur.lastrowid = 999
    cur.fetchone.return_value = {"client_id": 55, "event_id": 3}

    bulk_import_leads([_row(birthday="")])

    insert_call = next(c for c in cur.execute.call_args_list if "INSERT INTO leads" in c.args[0])
    assert insert_call.args[1]["birthday"] == "1900-01-01"


@patch("src.analytics.db_results.recompute_duplicate_flag")
@patch("src.analytics.db_results.get_pooled_connection")
def test_new_lead_insert_handles_missing_payment_fields(mock_get_conn, mock_recompute):
    conn, cur = _mock_conn()
    mock_get_conn.return_value = conn
    cur.fetchall.return_value = []
    cur.lastrowid = 999
    cur.fetchone.return_value = {"client_id": 55, "event_id": 3}

    bulk_import_leads([_row()])  # без платёжных полей — как раньше

    insert_call = next(c for c in cur.execute.call_args_list if "INSERT INTO leads" in c.args[0])
    params = insert_call.args[1]
    assert params["amount"] == 0.0
    assert params["promocode"] == ""
    assert params["discount"] == 0.0
    assert params["order_id"] is None
    assert params["transaction_id"] == ""


@patch("src.analytics.db_results.get_pooled_connection")
def test_matched_row_update_does_not_touch_payment_fields(mock_get_conn):
    """Платёжные поля — не в _IMPORT_UPDATABLE: повторный импорт CSV не
    должен затирать реальные данные о платеже, пришедшие через вебхук,
    правкой организатора контактных данных."""
    conn, cur = _mock_conn()
    mock_get_conn.return_value = conn
    cur.fetchall.side_effect = [[{"id": 101}], []]

    bulk_import_leads([_row(amount="999", promocode="SHOULD-NOT-APPLY")])

    update_call = next(c for c in cur.execute.call_args_list if "UPDATE leads" in c.args[0])
    sql = update_call.args[0]
    assert "amount" not in sql
    assert "promocode" not in sql
    assert "discount" not in sql


@patch("src.analytics.db_results.get_pooled_connection")
def test_matched_row_update_writes_empty_string_not_null_for_not_null_columns(mock_get_conn):
    """Реальный инцидент (Жара 2026, 2026-08-18): leads.sex/city/email —
    NOT NULL в схеме. Строка с пустыми sex/city/email в файле раньше писала
    None в UPDATE → MySQL 1048 "Column 'x' cannot be null" → исключение →
    ОТКАТ ВСЕГО импорта (один conn.commit() на весь файл), включая уже
    обработанные строки других дистанций — так стартовые номера для 5 км/
    2 км массово пропадали из-за одной строки без email/города где-то в
    файле. club/phone — NULLable, пустое значение там по-прежнему стирает
    старое (это осознанное поведение, не баг)."""
    conn, cur = _mock_conn()
    mock_get_conn.return_value = conn
    cur.fetchall.side_effect = [[{"id": 101}], []]

    bulk_import_leads([_row(sex="", city="", club="", email="", phone="")])

    update_call = next(c for c in cur.execute.call_args_list if "UPDATE leads SET" in c.args[0] and "start_number" not in c.args[0])
    sql, params = update_call.args
    columns = [c.strip().split(" = ")[0] for c in sql.split("SET", 1)[1].split("WHERE")[0].split(",")]
    values_by_col = dict(zip(columns, params))
    assert values_by_col["sex"] == ""
    assert values_by_col["city"] == ""
    assert values_by_col["email"] == ""
    assert values_by_col["club"] is None
    assert values_by_col["phone"] is None


@patch("src.analytics.db_results.get_pooled_connection")
def test_matched_row_update_applies_club(mock_get_conn):
    """club — контактные данные (как city/phone), не идентификационный
    признак: повторный импорт должен обновлять его при совпадении."""
    conn, cur = _mock_conn()
    mock_get_conn.return_value = conn
    cur.fetchall.side_effect = [[{"id": 101}], []]

    bulk_import_leads([_row(club="ILSS")])

    update_call = next(c for c in cur.execute.call_args_list if "UPDATE leads" in c.args[0])
    sql, params = update_call.args
    assert "club" in sql
    assert "ILSS" in params
    assert "order_id" not in sql
    assert "transaction_id" not in sql


@patch("src.analytics.db_results.recompute_duplicate_flag")
@patch("src.analytics.db_results.get_pooled_connection")
def test_new_lead_insert_computes_is_name_suspicious(mock_get_conn, mock_recompute):
    """Раньше is_name_suspicious при bulk-импорте был всегда захардкожен в 0
    — теперь считается тем же критерием, что и у вебхука (только кириллица
    и дефис — иначе подозрительно)."""
    conn, cur = _mock_conn()
    mock_get_conn.return_value = conn
    cur.fetchall.return_value = []
    cur.lastrowid = 999
    cur.fetchone.return_value = {"client_id": 55, "event_id": 3}

    bulk_import_leads([_row(surname="Ivanov", is_name_suspicious=True)])

    insert_call = next(c for c in cur.execute.call_args_list if "INSERT INTO leads" in c.args[0])
    _, params = insert_call.args
    assert params["is_name_suspicious"] == 1


@patch("src.analytics.db_results.recompute_duplicate_flag")
@patch("src.analytics.db_results.get_pooled_connection")
def test_new_lead_insert_clean_name_is_not_suspicious(mock_get_conn, mock_recompute):
    conn, cur = _mock_conn()
    mock_get_conn.return_value = conn
    cur.fetchall.return_value = []
    cur.lastrowid = 999
    cur.fetchone.return_value = {"client_id": 55, "event_id": 3}

    bulk_import_leads([_row(is_name_suspicious=False)])

    insert_call = next(c for c in cur.execute.call_args_list if "INSERT INTO leads" in c.args[0])
    _, params = insert_call.args
    assert params["is_name_suspicious"] == 0


@patch("src.analytics.db_results.get_pooled_connection")
def test_matched_row_update_applies_is_name_suspicious(mock_get_conn):
    """Повторный импорт должен обновить флаг, если исправленное ФИО
    изменило его подозрительность — иначе после ручной правки в Tilda флаг
    остался бы устаревшим до следующей смены surname/name напрямую в БД."""
    conn, cur = _mock_conn()
    mock_get_conn.return_value = conn
    cur.fetchall.side_effect = [[{"id": 101}], []]

    bulk_import_leads([_row(is_name_suspicious=True)])

    update_call = next(c for c in cur.execute.call_args_list if "UPDATE leads" in c.args[0])
    sql, params = update_call.args
    assert "is_name_suspicious" in sql
    assert 1 in params


@patch("src.analytics.db_results.get_pooled_connection")
def test_no_connection_returns_zero_summary_with_error(mock_get_conn):
    mock_get_conn.return_value = None
    summary = bulk_import_leads([_row()])
    assert summary == {"updated": 0, "created": 0, "deleted": 0, "errors": ["Нет соединения с БД"]}


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
    # 1-й fetchall — _find_lead_matches (совпало); 2-й — _find_leads_to_delete
    # (проверка "пропавших" для этого события/года — пусто, не в фокусе теста)
    cur.fetchall.side_effect = [[{"id": 101}], []]

    preview = preview_leads_import_matches([_row()])

    assert preview["rows"][0]["will"] == "update"
    assert preview["rows"][0]["matched_count"] == 1


@patch("src.analytics.db_results.get_pooled_connection")
def test_preview_marks_unmatched_row_as_create(mock_get_conn):
    conn, cur = _mock_conn()
    mock_get_conn.return_value = conn
    cur.fetchall.side_effect = [[], []]

    preview = preview_leads_import_matches([_row()])

    assert preview["rows"][0]["will"] == "create"
    assert preview["rows"][0]["matched_count"] == 0


@patch("src.analytics.db_results.get_pooled_connection")
def test_preview_handles_row_with_empty_birthday(mock_get_conn):
    """Реальный инцидент (Жара 2026, 2026-08-18): дата рождения необязательна
    при импорте с этой же сессии — но _find_lead_matches() передавал
    row.birthday="" напрямую в SQL-сравнение с DATE-колонкой, что MySQL
    отвергает как невалидную дату (ошибка 1525 "Incorrect DATE value: ''"),
    роняя весь /api/admin/leads/import/upload с 500. Фикс — тот же сентинел
    '1900-01-01', что уже используется при INSERT."""
    conn, cur = _mock_conn()
    mock_get_conn.return_value = conn
    cur.fetchall.side_effect = [[], []]

    preview = preview_leads_import_matches([_row(birthday="")])

    assert preview["rows"][0]["will"] == "create"
    select_call = cur.execute.call_args_list[0]
    assert "1900-01-01" in select_call.args[1]


@patch("src.analytics.db_results.get_pooled_connection")
def test_preview_no_connection_returns_unknown(mock_get_conn):
    mock_get_conn.return_value = None
    preview = preview_leads_import_matches([_row()])
    assert preview["rows"][0]["will"] == "unknown"
    assert preview["to_delete"] == []


# --- реконсиляция "файл — источник истины" (удаление пропавших) ----------

@patch("src.analytics.db_results.get_pooled_connection")
def test_deletes_leads_missing_from_import_file(mock_get_conn):
    """Реальный сценарий (2026-08-18): организатор удалил заявку из файла и
    переимпортировал — старая запись должна пропасть из БД, а не остаться
    навсегда. row (id=101) совпадает и остаётся; id=202 отсутствует в файле
    и не защищён — должен быть удалён."""
    conn, cur = _mock_conn()
    mock_get_conn.return_value = conn
    cur.fetchall.side_effect = [
        [{"id": 101}],  # _find_lead_matches для единственной строки файла
        [{"id": 101, "surname": "Иванов", "name": "Иван", "event_distance": "5 км", "start_number": None},
         {"id": 202, "surname": "Петров", "name": "Пётр", "event_distance": "5 км", "start_number": None}],
    ]

    summary = bulk_import_leads([_row()])

    assert summary["deleted"] == 1
    delete_call = next(c for c in cur.execute.call_args_list if "DELETE FROM leads" in c.args[0])
    assert delete_call.args[1] == [202]


@patch("src.analytics.db_results.get_pooled_connection")
def test_protects_lead_matching_failed_row_from_deletion(mock_get_conn):
    """Заявка, чьё (surname, name) совпадает со строкой, не разобранной
    парсером (failed_rows), не удаляется — мы не знаем, что с ней на самом
    деле произошло в файле (баг парсинга ≠ "человека убрали")."""
    conn, cur = _mock_conn()
    mock_get_conn.return_value = conn
    cur.fetchall.side_effect = [
        [{"id": 101}],
        [{"id": 101, "surname": "Иванов", "name": "Иван", "event_distance": "5 км", "start_number": None},
         {"id": 303, "surname": "Сидоров", "name": "Семён", "event_distance": "5 км", "start_number": None}],
    ]

    summary = bulk_import_leads(
        [_row()],
        failed_rows=[{"surname": "Сидоров", "name": "Семён", "birthday": "", "reason": "не распознано"}],
    )

    assert summary["deleted"] == 0
    delete_calls = [c for c in cur.execute.call_args_list if "DELETE FROM leads" in c.args[0]]
    assert delete_calls == []


@patch("src.analytics.db_results.get_pooled_connection")
def test_preview_includes_to_delete(mock_get_conn):
    """preview_leads_import_matches() должен показать организатору
    удаления ДО подтверждения, тем же расчётом, что и apply."""
    conn, cur = _mock_conn()
    mock_get_conn.return_value = conn
    cur.fetchall.side_effect = [
        [{"id": 101}],
        [{"id": 101, "surname": "Иванов", "name": "Иван", "event_distance": "5 км", "start_number": None},
         {"id": 202, "surname": "Петров", "name": "Пётр", "event_distance": "5 км", "start_number": None}],
    ]

    preview = preview_leads_import_matches([_row()])

    assert len(preview["to_delete"]) == 1
    assert preview["to_delete"][0]["id"] == 202


@patch("src.analytics.db_results.get_pooled_connection")
def test_deletion_scoped_to_event_name_and_year_only(mock_get_conn):
    """Реконсиляция ищет "пропавших" только по (event_name, event_year) из
    файла — не по event_distance, т.к. один файл-импорт может не содержать
    все дистанции события (ответ пользователя: "Событие + год")."""
    conn, cur = _mock_conn()
    mock_get_conn.return_value = conn
    cur.fetchall.side_effect = [[{"id": 101}], []]

    bulk_import_leads([_row(event_name="Весна", event_year=2027)])

    select_calls = [c for c in cur.execute.call_args_list if "FROM leads" in c.args[0] and "WHERE event_name" in c.args[0]]
    assert len(select_calls) == 1
    assert select_calls[0].args[1] == ("Весна", 2027)
