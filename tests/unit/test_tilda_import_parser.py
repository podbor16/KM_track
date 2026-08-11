"""Тесты парсинга Tilda-экспорта (CSV/XLSX) для bulk-импорта заявок.

Первый блок тестов — синтетические заголовки (Фамилия/Событие/…),
проверяют структуру/поведение парсера в общем виде. Второй блок
(test_parse_real_tilda_export_headers*) — реальные заголовки колонок из
боевой выгрузки Tilda (surname/Name/sex/city/birthday/Phone/Email/product +
служебные utm_*/ma_*/Промокод и т.п., которые парсер игнорирует), с
анонимизированными данными, воспроизводящими найденные в реальном файле
паттерны (в т.ч. ~14% строк без года в тексте product — закрыто
slug-фоллбэком в parse_products(), см. tilda_webhook.py).
"""
import pytest

from src.krasmarafon.services.tilda_import_parser import parse_tilda_export, ImportResult, ImportRow


def _csv_bytes(rows: str) -> bytes:
    return rows.encode("utf-8-sig")


def test_parse_csv_with_separate_event_columns():
    csv_text = (
        "Фамилия,Имя,Дата рождения,Событие,Дистанция,Год\r\n"
        "Иванов,Иван,01.05.1990,Весна,5 км,2027\r\n"
    )
    result = parse_tilda_export(_csv_bytes(csv_text), filename="export.csv")

    assert isinstance(result, ImportResult)
    assert result.total_rows == 1
    assert result.errors == []
    assert len(result.rows) == 1
    row = result.rows[0]
    assert isinstance(row, ImportRow)
    assert row.surname == "Иванов"
    assert row.name == "Иван"
    assert row.birthday == "1990-05-01"
    assert row.event_name == "Весна"
    assert row.event_distance == "5 км"
    assert row.event_year == 2027


def test_parse_csv_with_products_blob():
    csv_text = (
        "Фамилия,Имя,Дата рождения,products\r\n"
        "Петров,Пётр,15.03.1985,\"7 км Женская семерка 2026 (id)=1000\"\r\n"
    )
    result = parse_tilda_export(_csv_bytes(csv_text), filename="export.csv")

    assert result.errors == []
    assert len(result.rows) == 1
    row = result.rows[0]
    assert row.event_distance == "7 км"
    assert row.event_year == 2026


def test_parse_normalizes_names_like_webhook():
    csv_text = (
        "Фамилия,Имя,Дата рождения,Событие,Дистанция,Год\r\n"
        "ИВАНОВ,иван,01.05.1990,Весна,5 км,2027\r\n"
    )
    result = parse_tilda_export(_csv_bytes(csv_text), filename="export.csv")
    assert result.rows[0].surname == "Иванов"
    assert result.rows[0].name == "Иван"


def test_parse_bad_birthday_collected_as_error_not_raised():
    csv_text = (
        "Фамилия,Имя,Дата рождения,Событие,Дистанция,Год\r\n"
        "Иванов,Иван,не дата,Весна,5 км,2027\r\n"
    )
    result = parse_tilda_export(_csv_bytes(csv_text), filename="export.csv")

    assert result.rows == []
    assert result.total_rows == 1
    assert len(result.errors) == 1
    assert "строка 2" in result.errors[0]


def test_parse_no_event_columns_at_all_collected_as_row_error():
    """Обязательны только surname/name/birthday (проверка Task B1) — если в
    файле вовсе нет колонок события/products, это не структурная ошибка
    файла (ValueError), а построчная: каждая строка не может определить
    событие и пропускается с записью в errors."""
    csv_text = (
        "Фамилия,Имя,Дата рождения\r\n"
        "Иванов,Иван,01.05.1990\r\n"
    )
    result = parse_tilda_export(_csv_bytes(csv_text), filename="export.csv")
    assert result.rows == []
    assert len(result.errors) == 1
    assert "строка 2" in result.errors[0]


def test_parse_empty_event_value_collected_as_row_error():
    csv_text = (
        "Фамилия,Имя,Дата рождения,Событие,Дистанция,Год\r\n"
        "Иванов,Иван,01.05.1990,,,2027\r\n"
    )
    result = parse_tilda_export(_csv_bytes(csv_text), filename="export.csv")
    assert result.rows == []
    assert len(result.errors) == 1
    assert "строка 2" in result.errors[0]


def test_parse_blank_row_skipped_silently():
    csv_text = (
        "Фамилия,Имя,Дата рождения,Событие,Дистанция,Год\r\n"
        "Иванов,Иван,01.05.1990,Весна,5 км,2027\r\n"
        ",,,,,\r\n"
    )
    result = parse_tilda_export(_csv_bytes(csv_text), filename="export.csv")
    assert len(result.rows) == 1
    assert result.errors == []
    assert result.total_rows == 2


def test_parse_missing_required_columns_raises():
    csv_text = "Событие,Дистанция\r\nВесна,5 км\r\n"
    with pytest.raises(ValueError, match="обязательные колонки"):
        parse_tilda_export(_csv_bytes(csv_text), filename="export.csv")


def test_parse_unsupported_extension_raises():
    with pytest.raises(ValueError, match="Неподдерживаемый формат"):
        parse_tilda_export(b"whatever", filename="export.txt")


def test_parse_xlsx_smoke():
    import io
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Фамилия", "Имя", "Дата рождения", "Событие", "Дистанция", "Год"])
    ws.append(["Сидоров", "Семён", "01.05.1990", "Весна", "5 км", 2027])
    buf = io.BytesIO()
    wb.save(buf)

    result = parse_tilda_export(buf.getvalue(), filename="export.xlsx")
    assert len(result.rows) == 1
    assert result.rows[0].surname == "Сидоров"
    assert result.rows[0].event_year == 2027


# ---------------------------------------------------------------------------
# Реальные заголовки боевой выгрузки Tilda (данные ниже — фейковые)
# ---------------------------------------------------------------------------

_REAL_HEADERS = [
    "surname", "Name", "sex", "city", "Club", "birthday", "Phone", "Email",
    "product", "Date", "Сумма заказа", "Промокод", "Сумма скидки", "order_id",
    "phone_2", "ma_email", "Checkbox", "utm_source", "utm_medium",
    "utm_campaign", "tranid", "ma_id", "ma_name", "ma_phone", "formid",
    "formname", "file_discount", "file_discount_0", "file_discount_1",
    "field14", "field13", "Stage",
]


def _real_export_xlsx(data_rows: list) -> bytes:
    import io
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(_REAL_HEADERS)
    for row in data_rows:
        padded = row + [""] * (len(_REAL_HEADERS) - len(row))
        ws.append(padded)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _real_row(surname, name, sex, city, birthday, phone, email, product):
    row = [None] * len(_REAL_HEADERS)
    row[_REAL_HEADERS.index("surname")] = surname
    row[_REAL_HEADERS.index("Name")] = name
    row[_REAL_HEADERS.index("sex")] = sex
    row[_REAL_HEADERS.index("city")] = city
    row[_REAL_HEADERS.index("birthday")] = birthday
    row[_REAL_HEADERS.index("Phone")] = phone
    row[_REAL_HEADERS.index("Email")] = email
    row[_REAL_HEADERS.index("product")] = product
    return [v if v is not None else "" for v in row]


def test_parse_real_tilda_export_headers_with_year_in_product():
    xlsx = _real_export_xlsx([
        _real_row("Тестов", "Иван", "Мужчина", "Красноярск", "01.05.1990",
                  "+7 (900) 000-00-01", "test1@example.com",
                  "5 км Жара 2026 (zhara2026-5, Выберите категорию: Основная категория) x 1 ≡ 1790"),
    ])
    result = parse_tilda_export(xlsx, filename="export.xlsx")

    assert result.errors == []
    assert len(result.rows) == 1
    row = result.rows[0]
    assert row.surname == "Тестов"
    assert row.name == "Иван"
    assert row.birthday == "1990-05-01"
    assert row.sex == "Мужчина"
    assert row.city == "Красноярск"
    assert row.event_name == "Жара"
    assert row.event_distance == "5 км"
    assert row.event_year == 2026


def test_parse_real_tilda_export_product_without_year_uses_slug_fallback():
    """Реальная находка: ~14% строк боевой выгрузки не содержат год в
    видимом тексте product (Tilda пишет его не всегда) — но год всегда есть
    в служебном slug-коде в скобках. parse_products() (общая с вебхуком
    функция, см. tilda_webhook.py) резолвит его оттуда — импорт ведёт себя
    идентично вебхуку для одного и того же текста product."""
    xlsx = _real_export_xlsx([
        _real_row("Тестова", "Мария", "Женщина", "Красноярск", "11.06.1988",
                  "+7 (900) 000-00-02", "test2@example.com",
                  "5 км Жара (zhara2026-5, Выберите категорию: Основная категория) x 1 ≡ 1390"),
    ])
    result = parse_tilda_export(xlsx, filename="export.xlsx")

    assert result.errors == []
    assert len(result.rows) == 1
    assert result.rows[0].event_name == "Жара"
    assert result.rows[0].event_distance == "5 км"
    assert result.rows[0].event_year == 2026


def test_parse_real_tilda_export_garbage_product_value_collected_as_error():
    """Реальная находка: как минимум 1 строка боевой выгрузки содержала
    'yes' в колонке product вместо текста заказа (артефакт формы Tilda)."""
    xlsx = _real_export_xlsx([
        _real_row("Гарбаж", "Тест", "Мужчина", "Красноярск", "01.01.2000",
                  "+7 (900) 000-00-03", "test3@example.com", "yes"),
    ])
    result = parse_tilda_export(xlsx, filename="export.xlsx")

    assert result.rows == []
    assert len(result.errors) == 1


def test_parse_real_tilda_export_mixed_rows_with_service_columns_ignored():
    xlsx = _real_export_xlsx([
        _real_row("Тестов", "Пётр", "Мужчина", "Красноярск", "02.05.2001",
                  "+7 (900) 000-00-04", "test4@example.com",
                  "21.1 км Жара 2026 (zhara2026-21, Выберите категорию: Основная категория) x 1 ≡ 3090"),
        [""] * len(_REAL_HEADERS),  # полностью пустая строка — пропуск без ошибки
    ])
    result = parse_tilda_export(xlsx, filename="export.xlsx")

    assert result.total_rows == 2
    assert result.errors == []
    assert len(result.rows) == 1
    assert result.rows[0].event_distance == "21.1 км"
    assert result.rows[0].event_year == 2026
