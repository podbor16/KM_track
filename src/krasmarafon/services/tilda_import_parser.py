"""
Парсер CSV/XLSX-экспорта из Tilda (админка Tilda → организатор правит
заявки → выгружает файл) для bulk-импорта в leads. Не пишет в БД — см.
src/analytics/db_results.py: bulk_import_leads()/preview_leads_import_matches().

_HEADER_ALIASES сверен с реальной выгрузкой Tilda (leads-экспорт, 32
колонки): surname/Name/sex/city/birthday/Phone/Email/product — совпадает по
смыслу с полями вебхука (src/krasmarafon/services/tilda_webhook.py), колонка
"product" (не "products") содержит тот же текстовый блоб, что и
payment.products в вебхуке — переиспользуем parse_products() как есть, чтобы
результат совпадал с уже занесёнными через вебхук заявками (иначе повторный
импорт создаст дубли вместо апдейта). Остальные колонки экспорта (Club,
Date, Промокод, utm_*, ma_*, formid и т.п.) не используются.
"""
from dataclasses import dataclass, field
from typing import Optional
import csv
import io

import openpyxl

from src.krasmarafon.services.tilda_webhook import convert_birthday, normalize_name, parse_products


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
    email: str = ""
    phone: str = ""


@dataclass
class ImportResult:
    rows: list = field(default_factory=list)      # list[ImportRow]
    errors: list = field(default_factory=list)     # list[str]
    total_rows: int = 0        # включая пропущенные из-за ошибок


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
}


def _read_csv_rows(file_bytes: bytes):
    text = file_bytes.decode("utf-8-sig")  # utf-8-sig — Excel/Tilda обычно пишут BOM
    rows = list(csv.reader(io.StringIO(text)))
    return (rows[0], rows[1:]) if rows else ([], [])


def _read_xlsx_rows(file_bytes: bytes):
    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
    all_rows = list(wb.active.iter_rows(values_only=True))
    if not all_rows:
        return [], []
    headers = [str(h).strip() if h is not None else "" for h in all_rows[0]]
    return headers, [list(r) for r in all_rows[1:]]


def _extract_event_info(get, col_map: dict, birthday: str):
    """Если есть отдельные колонки event_name/event_distance — берём их
    напрямую; иначе, если есть 'products'-блоб (формат как в вебхуке) —
    переиспользуем parse_products(). Точная ветка зависит от реального
    формата (план, Часть B, задача B0)."""
    if "event_name" in col_map and "event_distance" in col_map:
        yr = str(get("event_year") or "").strip()
        event_year = int(yr) if yr.isdigit() else None
        return str(get("event_name") or "").strip(), event_year, str(get("event_distance") or "").strip()
    if "products" in col_map:
        info = parse_products([str(get("products") or "")], birthday=birthday)
        event_year = int(info["event_year"]) if info["event_year"] else None
        return info["event_name"], event_year, info["event_distance"]
    return "", None, ""


def parse_tilda_export(file_bytes: bytes, filename: str) -> ImportResult:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext == "csv":
        headers, data_rows = _read_csv_rows(file_bytes)
    elif ext in ("xlsx", "xls"):
        headers, data_rows = _read_xlsx_rows(file_bytes)
    else:
        raise ValueError(f"Неподдерживаемый формат файла: .{ext} (ожидается .csv или .xlsx)")

    col_map: dict = {}
    for i, h in enumerate(headers):
        field_name = _HEADER_ALIASES.get(_normalize_header(h))
        if field_name:
            col_map[field_name] = i

    missing = {"surname", "name", "birthday"} - col_map.keys()
    if missing:
        raise ValueError(f"В файле не найдены обязательные колонки: {missing} (заголовки: {headers})")

    result = ImportResult()
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
            if not surname or not name or not birthday or len(birthday) != 10:
                result.errors.append(
                    f"строка {idx}: не удалось распознать ФИО/дату рождения "
                    f"(surname={surname!r}, name={name!r}, birthday={birthday_raw!r}) — строка пропущена"
                )
                continue

            event_name, event_year, event_distance = _extract_event_info(get, col_map, birthday)
            if not event_name or not event_distance:
                result.errors.append(f"строка {idx}: не удалось определить событие/дистанцию — строка пропущена")
                continue

            result.rows.append(ImportRow(
                row_number=idx, surname=surname, name=name, birthday=birthday,
                event_name=event_name, event_year=event_year, event_distance=event_distance,
                sex=str(get("sex") or "").strip(), city=str(get("city") or "").strip(),
                email=str(get("email") or "").strip(), phone=str(get("phone") or "").strip(),
            ))
        except Exception as e:
            result.errors.append(f"строка {idx}: непредвиденная ошибка парсинга — {e}")

    return result
