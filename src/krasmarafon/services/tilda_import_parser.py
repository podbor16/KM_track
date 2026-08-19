"""
Парсер CSV/XLSX-экспорта из Tilda (админка Tilda → организатор правит
заявки → выгружает файл) для bulk-импорта в leads. Не пишет в БД — см.
src/analytics/db_results.py: bulk_import_leads()/preview_leads_import_matches().

_HEADER_ALIASES сверен с реальной выгрузкой Tilda (leads-экспорт, изначально
32 колонки, позже добавилась 33-я — "Способ оплаты", поймана как раз через
ImportResult.unknown_headers на реальном импорте 2026-08-17):
surname/Name/sex/city/birthday/Phone/Email/product — совпадает по
смыслу с полями вебхука (src/krasmarafon/services/tilda_webhook.py), колонка
"product" (не "products") содержит тот же текстовый блоб, что и
payment.products в вебхуке — переиспользуем parse_products() как есть, чтобы
результат совпадал с уже занесёнными через вебхук заявками (иначе повторный
импорт создаст дубли вместо апдейта). Платёжные колонки (Промокод/Сумма
заказа/Сумма скидки/order_id/tranid/Способ оплаты) читаются в ImportRow —
используются ТОЛЬКО при создании новой заявки (bulk_import_leads()), не при
апдейте совпавшей: правки платёжных данных задним числом через CSV — не
задача этого импорта, см. docstring bulk_import_leads(). Остальные колонки
экспорта (Date, phone_2, ma_email, Checkbox, utm_*, ma_id/ma_name/
ma_phone, formid/formname, file_discount*, field13/field14, Stage) — в
leads нет соответствующей колонки, см. _KNOWN_IGNORED_HEADERS. Заголовок
файла, которого нет ни в алиасах, ни в _KNOWN_IGNORED_HEADERS, попадает в
ImportResult.unknown_headers — сигнал, что Tilda добавила/переименовала
колонку и это стоит проверить вручную, а не тихо потерять данные.
"""
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional
import csv
import io
import re

import openpyxl

from src.krasmarafon.services.tilda_webhook import convert_birthday, normalize_name, parse_products, is_name_suspicious


@dataclass
class ImportRow:
    row_number: int          # 1-based, для сообщений об ошибках/превью
    surname: str
    name: str
    birthday: str             # YYYY-MM-DD
    event_name: str
    event_year: Optional[int]
    event_distance: str
    sex: str = ""
    city: str = ""
    club: str = ""
    email: str = ""
    phone: str = ""
    amount: str = ""            # "Сумма заказа" — сырое значение, конвертация в float в bulk_import_leads()
    promocode: str = ""         # "Промокод"
    discount: str = ""          # "Сумма скидки" — сырое значение
    order_id: str = ""          # order_id — сырое значение (может быть числом или строкой)
    transaction_id: str = ""    # tranid
    payment_system: str = ""    # "Способ оплаты" — в вебхуке это короткий код
                                 # платёжной системы (parse_payment()'s "sys",
                                 # напр. "sbrf"), в выгрузке Tilda — человекочитаемая
                                 # строка ("Банковская карта" и т.п.); формат
                                 # разный, но колонка та же (leads.payment_system)
    is_name_suspicious: bool = False  # см. tilda_webhook.is_name_suspicious()
    start_number: str = ""      # "Номер" — стартовый номер (bib), присвоенный
                                 # организатором заранее (не результат гонки,
                                 # см. migrations/add_leads_start_number.sql).
                                 # Сырая строка, int-конвертация в bulk_import_leads()


@dataclass
class ImportResult:
    rows: list = field(default_factory=list)      # list[ImportRow]
    errors: list = field(default_factory=list)     # list[str]
    total_rows: int = 0        # включая пропущенные из-за ошибок
    unknown_headers: list = field(default_factory=list)  # заголовки файла вне алиасов И вне _KNOWN_IGNORED_HEADERS
    # Те же ошибки, что в errors, но структурированно — для подсветки
    # конкретной строки в таблице превью /admin (не только текстом списком):
    # list[{"row_number": int, "surname": str, "name": str, "birthday": str, "reason": str}]
    failed_rows: list = field(default_factory=list)


def _normalize_header(h) -> str:
    return str(h).strip().lower()


# ключ: нормализованное (lower+strip) имя колонки в файле Tilda,
# значение: наше поле ImportRow.
_HEADER_ALIASES = {
    "фамилия": "surname",
    "surname": "surname",
    "имя": "name",
    "name": "name",
    "дата рождения": "birthday",
    "birthday": "birthday",
    "пол": "sex",
    "sex": "sex",
    "город": "city",
    "city": "city",
    "клуб": "club",
    "club": "club",
    "email": "email",
    "e-mail": "email",
    "телефон": "phone",
    "phone": "phone",
    # событие/дистанция/год — либо отдельные колонки, либо единый
    # "products"-блоб (реальная выгрузка Tilda зовёт эту колонку "product",
    # в единственном числе — как в вебхуке), см. _extract_event_info()
    "products": "products",
    "product": "products",
    "событие": "event_name",
    "дистанция": "event_distance",
    "год": "event_year",
    # Платёжные поля — те же данные, что вебхук пишет в leads.amount/
    # .promocode/.discount/.order_id/.transaction_id (см. parse_payment()
    # в tilda_webhook.py), но выгрузка называет колонки по-другому.
    "сумма заказа": "amount",
    "промокод": "promocode",
    "сумма скидки": "discount",
    "order_id": "order_id",
    "tranid": "transaction_id",
    "способ оплаты": "payment_system",
    # Стартовый номер (bib) — не из штатной выгрузки Tilda, а из "обработанного"
    # организатором файла (номера расставлены вручную поверх экспорта), см.
    # migrations/add_leads_start_number.sql. Опциональная колонка.
    "номер": "start_number",
}

# Реальные заголовки боевой выгрузки Tilda (32 колонки, см. заголовок файла
# выше), для которых в leads НЕТ соответствующей колонки — Tilda-служебные
# (ma_* — интеграция с сервисом email-маркетинга, utm_* — метки кампаний,
# formid/formname/Stage — служебные поля CRM-воронки Tilda, file_discount* и
# field13/field14 — generic-поля конструктора форм без зафиксированного
# смысла) или дублирующие уже покрытое (Date/phone_2/ma_email/Checkbox
# — не нужны для сопоставления/создания лида). Перечислены явно, чтобы
# parse_tilda_export() мог отличить "мы осознанно не берём эту колонку" от
# "в файле появилась НОВАЯ колонка, которую мы никогда не видели" — второе
# репортится через ImportResult.unknown_headers.
_KNOWN_IGNORED_HEADERS = {
    "date", "phone_2", "ma_email", "checkbox",
    "utm_source", "utm_medium", "utm_campaign",
    "ma_id", "ma_name", "ma_phone", "formid", "formname",
    "file_discount", "file_discount_0", "file_discount_1",
    "field13", "field14", "stage",
}


def _read_csv_rows(file_bytes: bytes):
    text = file_bytes.decode("utf-8-sig")  # utf-8-sig — Excel/Tilda обычно пишут BOM
    # RU-локаль Excel/Tilda экспортирует CSV с ';' (запятая занята под
    # десятичный разделитель) — дефолтный csv.reader считал бы всю строку
    # заголовков одной колонкой. Sniffer определяет реальный разделитель по
    # первым строкам файла, ограничен только двумя реалистичными вариантами.
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;")
    except csv.Error:
        dialect = csv.excel  # непонятный сэмпл (например, файл из одной колонки) — дефолт ','
    rows = list(csv.reader(io.StringIO(text), dialect))
    return (rows[0], rows[1:]) if rows else ([], [])


def _normalize_xlsx_cell(value):
    """Ячейки с датой (напр. "Дата рождения", если колонка отформатирована
    в Excel как дата) openpyxl отдаёт как datetime.datetime/date, не строку
    — str(datetime(1985,3,11)) даёт "1985-03-11 00:00:00" (19 символов), что
    convert_birthday()/проверка len(birthday)==10 не распознаёт (ожидается
    голая "1985-03-11" или "11.03.1985"), и строка целиком браковалась как
    "не распознано ФИО/дата рождения" — найдено на реальном импорте
    2026-08-18 (3611 из 3627 строк). CSV этой проблемы не имеет — там ячейки
    всегда текст."""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    return value


def _read_xlsx_rows(file_bytes: bytes):
    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
    all_rows = list(wb.active.iter_rows(values_only=True))
    if not all_rows:
        return [], []
    headers = [str(h).strip() if h is not None else "" for h in all_rows[0]]
    data_rows = [[_normalize_xlsx_cell(c) for c in r] for r in all_rows[1:]]
    return headers, data_rows


def _extract_event_info(get, col_map: dict, birthday: str,
                         fallback_event_name: Optional[str] = None,
                         fallback_event_year: Optional[int] = None):
    """Если есть отдельные колонки event_name/event_distance — берём их
    напрямую; иначе, если есть 'products'-блоб (формат как в вебхуке) —
    переиспользуем parse_products().

    Реальный случай (обработанный организатором в Excel файл, 2026-08-18):
    строку продукта вручную укоротили до голой дистанции ("21.1 км" без
    названия события/года/slug) при переносе участника на другую дистанцию
    — parse_products() такое не разбирает. Если в файле при этом есть
    отдельная колонка "Дистанция" (event_distance, но БЕЗ event_name рядом,
    иначе сработала бы первая ветка) — используем её вместе с событием/годом,
    которые организатор уже выбрал в /admin перед загрузкой файла (тот же
    принцип, что явные колонки, просто источник события — контекст
    загрузки, а не сам файл). Без выбранного события/года — как раньше,
    строка идёт в ошибки, не гадаем."""
    if "event_name" in col_map and "event_distance" in col_map:
        yr = str(get("event_year") or "").strip()
        event_year = int(yr) if yr.isdigit() else None
        return str(get("event_name") or "").strip(), event_year, str(get("event_distance") or "").strip()

    if "products" in col_map:
        info = parse_products([str(get("products") or "")], birthday=birthday)
        if info["event_name"] and info["event_distance"]:
            event_year = int(info["event_year"]) if info["event_year"] else None
            return info["event_name"], event_year, info["event_distance"]

    if "event_distance" in col_map and fallback_event_name and fallback_event_year:
        distance = str(get("event_distance") or "").strip().replace(",", ".")
        if distance:
            return fallback_event_name, fallback_event_year, distance

    return "", None, ""


def parse_tilda_export(file_bytes: bytes, filename: str,
                        fallback_event_name: Optional[str] = None,
                        fallback_event_year: Optional[int] = None) -> ImportResult:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext == "csv":
        headers, data_rows = _read_csv_rows(file_bytes)
    elif ext in ("xlsx", "xls"):
        headers, data_rows = _read_xlsx_rows(file_bytes)
    else:
        raise ValueError(f"Неподдерживаемый формат файла: .{ext} (ожидается .csv или .xlsx)")

    col_map: dict = {}
    unknown_headers: list = []
    for i, h in enumerate(headers):
        normalized = _normalize_header(h)
        field_name = _HEADER_ALIASES.get(normalized)
        if field_name:
            col_map[field_name] = i
        elif normalized and normalized not in _KNOWN_IGNORED_HEADERS:
            unknown_headers.append(str(h).strip())

    missing = {"surname", "name", "birthday"} - col_map.keys()
    if missing:
        raise ValueError(f"В файле не найдены обязательные колонки: {missing} (заголовки: {headers})")

    result = ImportResult(unknown_headers=unknown_headers)
    for idx, raw_row in enumerate(data_rows, start=2):  # 2 = 1-based + строка заголовка
        result.total_rows += 1
        if not any(c not in (None, "") for c in raw_row):
            continue  # пустая строка — пропустить молча, не ошибка

        def get(field_name, default=""):
            ci = col_map.get(field_name)
            return raw_row[ci] if ci is not None and ci < len(raw_row) else default

        try:
            surname = normalize_name(str(get("surname") or "").strip())
            name = normalize_name(str(get("name") or "").strip())
            birthday_raw = str(get("birthday") or "").strip()
            birthday = convert_birthday(birthday_raw)
            if not re.match(r"^\d{4}-\d{2}-\d{2}$", birthday):
                # Дата рождения не указана/не распознана convert_birthday()
                # — не блокируем импорт целиком из-за одного поля: просто
                # нет данных для возраста/категории (get_age_group_label()
                # уже отдаёт "Неизвестно" при отсутствующей дате), колонка
                # "Год" на /start_list для такой строки будет пустой.
                # ВАЖНО: проверяем именно формат ГГГГ-ММ-ДД, а не длину —
                # нераспознанное значение вроде "27 08 1988" (тоже 10
                # символов) раньше проходило эту проверку "как есть" и
                # ломало SQL-сравнение с DATE-колонкой (MySQL 1525
                # "Incorrect DATE value", реальный инцидент 2026-08-19).
                birthday = ""
            if not surname or not name:
                reason = f"не распознано ФИО (surname={surname!r}, name={name!r})"
                result.errors.append(f"строка {idx}: {reason} — строка пропущена")
                result.failed_rows.append({
                    "row_number": idx, "surname": surname, "name": name,
                    "birthday": birthday_raw, "reason": reason,
                })
                continue

            event_name, event_year, event_distance = _extract_event_info(
                get, col_map, birthday, fallback_event_name, fallback_event_year
            )
            if not event_name or not event_distance:
                if "products" in col_map:
                    detail = f"product={str(get('products') or '')!r}"
                elif "event_name" in col_map and "event_distance" in col_map:
                    detail = (
                        f"событие={str(get('event_name') or '')!r}, "
                        f"дистанция={str(get('event_distance') or '')!r}"
                    )
                else:
                    detail = "в файле нет ни products, ни отдельных колонок событие/дистанция"
                reason = f"не удалось определить событие/дистанцию ({detail})"
                result.errors.append(f"строка {idx}: {reason} — строка пропущена")
                result.failed_rows.append({
                    "row_number": idx, "surname": surname, "name": name,
                    "birthday": birthday, "reason": reason,
                })
                continue

            result.rows.append(ImportRow(
                row_number=idx, surname=surname, name=name, birthday=birthday,
                event_name=event_name, event_year=event_year, event_distance=event_distance,
                sex=str(get("sex") or "").strip(), city=str(get("city") or "").strip(),
                club=str(get("club") or "").strip(),
                email=str(get("email") or "").strip(), phone=str(get("phone") or "").strip(),
                amount=str(get("amount") or "").strip(), promocode=str(get("promocode") or "").strip(),
                discount=str(get("discount") or "").strip(), order_id=str(get("order_id") or "").strip(),
                transaction_id=str(get("transaction_id") or "").strip(),
                payment_system=str(get("payment_system") or "").strip(),
                is_name_suspicious=is_name_suspicious(surname, name),
                start_number=str(get("start_number") or "").strip(),
            ))
        except Exception as e:
            reason = f"непредвиденная ошибка парсинга — {e}"
            result.errors.append(f"строка {idx}: {reason}")
            result.failed_rows.append({
                "row_number": idx, "surname": locals().get("surname", ""),
                "name": locals().get("name", ""), "birthday": locals().get("birthday_raw", ""),
                "reason": reason,
            })

    return result
