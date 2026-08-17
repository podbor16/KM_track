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


def test_parse_computes_is_name_suspicious_clean_cyrillic_name():
    csv_text = (
        "Фамилия,Имя,Дата рождения,Событие,Дистанция,Год\r\n"
        "Иванов,Иван,01.05.1990,Весна,5 км,2027\r\n"
    )
    result = parse_tilda_export(_csv_bytes(csv_text), filename="export.csv")
    assert result.rows[0].is_name_suspicious is False


def test_parse_computes_is_name_suspicious_latin_name():
    """Раньше при bulk-импорте is_name_suspicious всегда оставался 0/False
    независимо от реального ФИО — теперь считается тем же критерием, что и
    у вебхука (см. tilda_webhook.is_name_suspicious)."""
    csv_text = (
        "Фамилия,Имя,Дата рождения,Событие,Дистанция,Год\r\n"
        "Ivanov,Ivan,01.05.1990,Весна,5 км,2027\r\n"
    )
    result = parse_tilda_export(_csv_bytes(csv_text), filename="export.csv")
    assert result.rows[0].is_name_suspicious is True


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


def test_parse_event_error_message_includes_raw_product_value():
    """Реальная находка (2026-08-14): сообщение об ошибке 'не удалось
    определить событие/дистанцию' не показывало САМ текст product, из-за
    которого не сработал разбор — организатору/админу нечего было
    диагностировать. Теперь сырое значение — в тексте ошибки."""
    csv_text = (
        "Фамилия,Имя,Дата рождения,products\r\n"
        "Иванов,Иван,01.05.1990,какая-то нераспознаваемая строка\r\n"
    )
    result = parse_tilda_export(_csv_bytes(csv_text), filename="export.csv")
    assert result.rows == []
    assert len(result.errors) == 1
    assert "какая-то нераспознаваемая строка" in result.errors[0]


def test_parse_event_error_message_includes_raw_columns_when_separate():
    csv_text = (
        "Фамилия,Имя,Дата рождения,Событие,Дистанция,Год\r\n"
        "Иванов,Иван,01.05.1990,,5 км,2027\r\n"
    )
    result = parse_tilda_export(_csv_bytes(csv_text), filename="export.csv")
    assert result.rows == []
    assert len(result.errors) == 1
    assert "5 км" in result.errors[0]


# ---------------------------------------------------------------------------
# failed_rows — структурированные данные о пропущенных строках (для
# подсветки прямо в таблице превью в /admin, а не только текстом списком)
# ---------------------------------------------------------------------------

def test_parse_event_error_populates_failed_rows_with_surname_and_reason():
    csv_text = (
        "Фамилия,Имя,Дата рождения,products\r\n"
        "Иванов,Иван,01.05.1990,какая-то нераспознаваемая строка\r\n"
    )
    result = parse_tilda_export(_csv_bytes(csv_text), filename="export.csv")
    assert len(result.failed_rows) == 1
    fr = result.failed_rows[0]
    assert fr["row_number"] == 2
    assert fr["surname"] == "Иванов"
    assert fr["name"] == "Иван"
    assert fr["birthday"] == "1990-05-01"
    assert "какая-то нераспознаваемая строка" in fr["reason"]


def test_parse_birthday_error_populates_failed_rows_with_whatever_was_parsed():
    csv_text = (
        "Фамилия,Имя,Дата рождения,Событие,Дистанция,Год\r\n"
        "Иванов,Иван,не дата,Весна,5 км,2027\r\n"
    )
    result = parse_tilda_export(_csv_bytes(csv_text), filename="export.csv")
    assert len(result.failed_rows) == 1
    fr = result.failed_rows[0]
    assert fr["row_number"] == 2
    assert fr["surname"] == "Иванов"
    assert fr["name"] == "Иван"
    assert "не дата" in fr["reason"]


def test_parse_successful_rows_do_not_appear_in_failed_rows():
    csv_text = (
        "Фамилия,Имя,Дата рождения,Событие,Дистанция,Год\r\n"
        "Иванов,Иван,01.05.1990,Весна,5 км,2027\r\n"
    )
    result = parse_tilda_export(_csv_bytes(csv_text), filename="export.csv")
    assert result.failed_rows == []


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


def test_parse_csv_with_semicolon_delimiter():
    """Реальная находка (2026-08-14): русская локаль Excel/Tilda экспортирует
    CSV с ';' вместо ',' (запятая — десятичный разделитель в RU-локали).
    csv.reader с дефолтным диалектом читал всю строку заголовков как ОДНУ
    колонку — обязательные surname/name/birthday не находились вовсе."""
    csv_text = (
        "Фамилия;Имя;Дата рождения;Событие;Дистанция;Год\r\n"
        "Иванов;Иван;01.05.1990;Весна;5 км;2027\r\n"
    )
    result = parse_tilda_export(_csv_bytes(csv_text), filename="export.csv")

    assert result.errors == []
    assert len(result.rows) == 1
    row = result.rows[0]
    assert row.surname == "Иванов"
    assert row.event_name == "Весна"
    assert row.event_year == 2027


def test_parse_csv_semicolon_with_quoted_field_containing_comma():
    """Значения с запятой внутри (например, город) должны остаться в
    кавычках корректно распознаны даже при ';'-разделителе — запятая
    внутри поля не должна ломать разбиение по колонкам."""
    csv_text = (
        'Фамилия;Имя;Дата рождения;Город;Событие;Дистанция;Год\r\n'
        '"Петров";"Пётр";15.03.1985;"Красноярск, Сибирь";Весна;5 км;2027\r\n'
    )
    result = parse_tilda_export(_csv_bytes(csv_text), filename="export.csv")

    assert result.errors == []
    assert len(result.rows) == 1
    row = result.rows[0]
    assert row.city == "Красноярск, Сибирь"
    assert row.event_name == "Весна"


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
    "field14", "field13", "Stage", "Способ оплаты",
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


def _real_row(surname, name, sex, city, birthday, phone, email, product,
              amount=None, promocode=None, discount=None, order_id=None, tranid=None,
              club=None, payment_system=None):
    row = [None] * len(_REAL_HEADERS)
    row[_REAL_HEADERS.index("surname")] = surname
    row[_REAL_HEADERS.index("Name")] = name
    row[_REAL_HEADERS.index("sex")] = sex
    row[_REAL_HEADERS.index("city")] = city
    row[_REAL_HEADERS.index("Club")] = club
    row[_REAL_HEADERS.index("birthday")] = birthday
    row[_REAL_HEADERS.index("Phone")] = phone
    row[_REAL_HEADERS.index("Email")] = email
    row[_REAL_HEADERS.index("product")] = product
    row[_REAL_HEADERS.index("Сумма заказа")] = amount
    row[_REAL_HEADERS.index("Промокод")] = promocode
    row[_REAL_HEADERS.index("Сумма скидки")] = discount
    row[_REAL_HEADERS.index("order_id")] = order_id
    row[_REAL_HEADERS.index("tranid")] = tranid
    row[_REAL_HEADERS.index("Способ оплаты")] = payment_system
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


# ---------------------------------------------------------------------------
# Платёжные поля (Промокод/Сумма заказа/Сумма скидки/order_id/tranid) —
# раньше молча отбрасывались, теперь читаются в ImportRow.
# ---------------------------------------------------------------------------

def test_parse_real_tilda_export_captures_payment_fields():
    xlsx = _real_export_xlsx([
        _real_row("Тестов", "Иван", "Мужчина", "Красноярск", "01.05.1990",
                  "+7 (900) 000-00-01", "test1@example.com",
                  "5 км Жара 2026 (zhara2026-5, Выберите категорию: Основная категория) x 1 ≡ 1790",
                  amount="4.9", promocode="99TEST", discount="485.1",
                  order_id=1486212513, tranid="144860:7719674713"),
    ])
    result = parse_tilda_export(xlsx, filename="export.xlsx")

    assert result.errors == []
    row = result.rows[0]
    assert row.amount == "4.9"
    assert row.promocode == "99TEST"
    assert row.discount == "485.1"
    assert row.order_id == "1486212513"
    assert row.transaction_id == "144860:7719674713"


def test_parse_real_tilda_export_missing_payment_fields_default_to_empty():
    xlsx = _real_export_xlsx([
        _real_row("Тестов", "Иван", "Мужчина", "Красноярск", "01.05.1990",
                  "+7 (900) 000-00-01", "test1@example.com",
                  "5 км Жара 2026 (zhara2026-5, Выберите категорию: Основная категория) x 1 ≡ 1790"),
    ])
    result = parse_tilda_export(xlsx, filename="export.xlsx")

    assert result.errors == []
    row = result.rows[0]
    assert row.amount == ""
    assert row.promocode == ""
    assert row.discount == ""
    assert row.order_id == ""
    assert row.transaction_id == ""


def test_parse_real_tilda_export_captures_club():
    xlsx = _real_export_xlsx([
        _real_row("Экзархова", "Юлия", "Женщина", "Красноярск", "26.04.1979",
                  "+7 (913) 031-50-35", "u19792007@ya.ru",
                  "21.1 км Жара 2026 (zhara2026-21, Выберите категорию: Основная категория) x 1 ≡ 1790",
                  club="ILSS"),
    ])
    result = parse_tilda_export(xlsx, filename="export.xlsx")

    assert result.errors == []
    assert result.rows[0].club == "ILSS"


def test_parse_real_tilda_export_missing_club_defaults_to_empty():
    xlsx = _real_export_xlsx([
        _real_row("Тестов", "Иван", "Мужчина", "Красноярск", "01.05.1990",
                  "+7 (900) 000-00-01", "test1@example.com",
                  "5 км Жара 2026 (zhara2026-5, Выберите категорию: Основная категория) x 1 ≡ 1790"),
    ])
    result = parse_tilda_export(xlsx, filename="export.xlsx")

    assert result.errors == []
    assert result.rows[0].club == ""


def test_parse_real_tilda_export_captures_payment_system():
    """"Способ оплаты" — колонка, появившаяся в выгрузке Tilda позже
    остальных 32 (поймана через unknown_headers на реальном импорте
    2026-08-17, до этого теста была не сопоставлена ни с одним полем)."""
    xlsx = _real_export_xlsx([
        _real_row("Экзархова", "Юлия", "Женщина", "Красноярск", "26.04.1979",
                  "+7 (913) 031-50-35", "u19792007@ya.ru",
                  "21.1 км Жара 2026 (zhara2026-21, Выберите категорию: Основная категория) x 1 ≡ 1790",
                  payment_system="Банковская карта"),
    ])
    result = parse_tilda_export(xlsx, filename="export.xlsx")

    assert result.errors == []
    assert result.rows[0].payment_system == "Банковская карта"


def test_parse_real_tilda_export_missing_payment_system_defaults_to_empty():
    xlsx = _real_export_xlsx([
        _real_row("Тестов", "Иван", "Мужчина", "Красноярск", "01.05.1990",
                  "+7 (900) 000-00-01", "test1@example.com",
                  "5 км Жара 2026 (zhara2026-5, Выберите категорию: Основная категория) x 1 ≡ 1790"),
    ])
    result = parse_tilda_export(xlsx, filename="export.xlsx")

    assert result.errors == []
    assert result.rows[0].payment_system == ""


# ---------------------------------------------------------------------------
# unknown_headers — предупреждение о заголовках файла, которых нет ни среди
# используемых алиасов, ни среди явно задокументированных игнорируемых
# (защита от будущего дрейфа полей в Tilda, найденного вживую тихого
# игнора).
# ---------------------------------------------------------------------------

def test_parse_real_tilda_export_all_known_headers_produce_no_warning():
    """Полный реальный набор из 32 колонок — ни одна не должна попасть в
    unknown_headers (все либо используются, либо явно задокументированы как
    игнорируемые)."""
    xlsx = _real_export_xlsx([
        _real_row("Тестов", "Иван", "Мужчина", "Красноярск", "01.05.1990",
                  "+7 (900) 000-00-01", "test1@example.com",
                  "5 км Жара 2026 (zhara2026-5, Выберите категорию: Основная категория) x 1 ≡ 1790"),
    ])
    result = parse_tilda_export(xlsx, filename="export.xlsx")
    assert result.unknown_headers == []


def test_parse_detects_genuinely_unknown_header():
    csv_text = (
        "Фамилия,Имя,Дата рождения,Событие,Дистанция,Год,НоваяКолонкаТильды\r\n"
        "Иванов,Иван,01.05.1990,Весна,5 км,2027,что-то новое\r\n"
    )
    result = parse_tilda_export(_csv_bytes(csv_text), filename="export.csv")
    assert result.unknown_headers == ["НоваяКолонкаТильды"]
