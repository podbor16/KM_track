#!/usr/bin/env python3
"""
Разовый импорт заявок Жары 2023 и 2024 из "Жара_2024-2023.xlsx" (два листа
"2024"/"2023", старый формат выгрузки Tilda: product, Total amount, Payment
status, sent, Promocode, Discount). Закрывает пропуск 2023-2024 в карте
заявок (Obsidian: knowledge/business/karta-propuskov-zayavok.md).

Вставка — та же, что у импорта «Бума» (insert_leads(): INSERT-only с
проверкой «уже есть», без reconciliation-DELETE bulk_import_leads()).

Решения пользователя (2026-09-24):
- дистанция — из SKU продукта (zhara2024-21 -> 21.1 км, суффиксы b/y —
  ценовые категории, на дистанцию не влияют); год — лист файла (SKU
  "zhara2022-21" на листе 2023 — слот, проданный после Жары 2022);
- заявки без оплаты импортируем все; дата регистрации у них — дата ближайшей
  датированной строки выше (строки выгрузки идут по времени);
- дубли человека на одной дистанции — одна (самая ранняя) заявка;
- дата рождения: 991 -> 1991, "M/D/YY" разбираем, невозможные годы -> 1900-01-01.

Использование:
  python scripts/import_zhara_2023_2024.py            # dry-run
  python scripts/import_zhara_2023_2024.py --apply
"""

import argparse
import datetime
import re
import sys
from collections import Counter
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import openpyxl

from scripts.import_boom_historical import (
    _BIRTHDAY_SENTINEL, _clean_email, _clean_phone, _clean_text, _parse_birthday,
    _recompute_client_lead_dates, dedupe, insert_leads,
)
from src.krasmarafon.services.tilda_webhook import is_name_suspicious, normalize_name

DEFAULT_FILE = r"C:\Users\podbo\Downloads\Жара_2024-2023.xlsx"
SHEETS = (2024, 2023)
EVENT_NAME = "Жара"

_SKU_RE = re.compile(r"\(zhara\d{4}-(\d+)[a-z]*\b")
_DISTANCE_BY_SKU = {"21": "21.1 км", "10": "10 км", "5": "5 км", "2": "2 км"}
_DT_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")
_MDY_RE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{2})$")
_TYPO_YEAR_FIX = {991: 1991}
_TYPO_YEAR_RE = re.compile(r"^(.*\D)(\d{3})$")
_MIN_BIRTH_YEAR = 1920
_MIN_AGE = 3

_SEX = {"Мужчина": "Мужчина", "Мужской": "Мужчина", "М": "Мужчина",
        "Женщина": "Женщина", "Женский": "Женщина", "Ж": "Женщина"}


def parse_birthday(raw, event_year, min_age=_MIN_AGE):
    if isinstance(raw, str):
        raw = raw.strip()
        m = _MDY_RE.match(raw)
        if m:
            month, day, yy = int(m.group(1)), int(m.group(2)), int(m.group(3))
            year = 1900 + yy if yy > event_year % 100 else 2000 + yy
            try:
                raw = datetime.date(year, month, day)
            except ValueError:
                return _BIRTHDAY_SENTINEL
        else:
            m = _TYPO_YEAR_RE.match(raw)
            if m and int(m.group(2)) in _TYPO_YEAR_FIX:
                raw = f"{m.group(1)}{_TYPO_YEAR_FIX[int(m.group(2))]}"
    birthday = _parse_birthday(raw)
    if birthday != _BIRTHDAY_SENTINEL and not _MIN_BIRTH_YEAR <= int(birthday[:4]) <= event_year - min_age:
        return _BIRTHDAY_SENTINEL
    return birthday


def distance_from_product(product):
    m = _SKU_RE.search(str(product or ""))
    return _DISTANCE_BY_SKU.get(m.group(1)) if m else None


def registered_at(row, cols):
    """'sent' — момент отправки формы; у строк со съехавшими колонками
    datetime оказывается в одной из соседних колонок — берём первую такую."""
    for v in (row[cols["sent"]], *row[cols["product"] + 1:]):
        if isinstance(v, datetime.datetime):
            return v
        if isinstance(v, str) and _DT_RE.match(v.strip()):
            return datetime.datetime.strptime(v.strip(), "%Y-%m-%d %H:%M:%S")
    return None


def _float(raw):
    try:
        return float(raw) if raw not in (None, "") else 0.0
    except (TypeError, ValueError):
        return 0.0


def parse_sheet(ws, event_year, stats):
    it = ws.iter_rows(values_only=True)
    cols = {str(h).strip(): i for i, h in enumerate(next(it)) if h}
    col = lambda row, name: row[cols[name]] if cols[name] < len(row) else None

    rows = []
    for r_idx, row in enumerate(it, start=2):
        if not any(v is not None and str(v).strip() != "" for v in row):
            continue
        stats["total_nonblank"] += 1
        distance = distance_from_product(col(row, "product"))
        if distance is None:
            stats["event_unresolved"] += 1
            continue
        surname = normalize_name(_clean_text(col(row, "surname")))
        name = normalize_name(_clean_text(col(row, "name")))
        if not surname or not name:
            stats["missing_fio"] += 1
            continue
        birthday = parse_birthday(col(row, "birthday"), event_year)
        if birthday == _BIRTHDAY_SENTINEL:
            stats["birthday_unknown"] += 1
        rows.append({
            "row_idx": f"{event_year}:{r_idx}",
            "surname": surname,
            "name": name,
            "sex": _SEX.get(_clean_text(col(row, "sex")), ""),
            "city": _clean_text(col(row, "city")),
            "club": _clean_text(col(row, "Club")) or None,
            "birthday": birthday,
            "phone": _clean_phone(col(row, "phone")),
            "email": _clean_email(col(row, "email")),
            "event_name": EVENT_NAME,
            "event_distance": distance,
            "event_year": event_year,
            "amount": _float(col(row, "Total amount")),
            "promocode": _clean_text(col(row, "Promocode")),
            "discount": _float(col(row, "Discount")),
            "registered_at": registered_at(row, cols),
            "is_name_suspicious": int(is_name_suspicious(surname, name)),
        })
    fill_missing_dates(rows, stats)
    return rows


def fill_missing_dates(rows, stats):
    """Нет даты -> дата ближайшей датированной строки выше (для самых первых
    строк листа — ближайшей ниже)."""
    prev = None
    for r in rows:
        if r["registered_at"] is None:
            stats["date_from_neighbor"] += 1
            r["registered_at"] = prev
        else:
            prev = r["registered_at"]
    nxt = None
    for r in reversed(rows):
        if r["registered_at"] is None:
            r["registered_at"] = nxt
        else:
            nxt = r["registered_at"]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--file", default=DEFAULT_FILE)
    ap.add_argument("--apply", action="store_true", help="применить изменения (без флага — только отчёт)")
    args = ap.parse_args()
    print(f"Файл: {args.file}\nРежим: {'ПРИМЕНЕНИЕ' if args.apply else 'DRY-RUN (БД не меняется)'}")

    wb = openpyxl.load_workbook(args.file, data_only=True, read_only=True)
    rows, stats = [], Counter()
    for year in SHEETS:
        rows += parse_sheet(wb[str(year)], year, stats)
    print("\n--- Разбор файла ---")
    for k in ("total_nonblank", "event_unresolved", "missing_fio", "birthday_unknown", "date_from_neighbor"):
        print(f"  {k}: {stats.get(k, 0)}")

    rows.sort(key=lambda r: (r["event_year"], r["registered_at"]))
    rows, dup_count = dedupe(rows)
    print(f"\nДублей на одной дистанции удалено: {dup_count}\nК импорту: {len(rows)}")

    print("\n--- Год / дистанция ---")
    for k, n in sorted(Counter((r["event_year"], r["event_distance"]) for r in rows).items()):
        print(f"  {k}: {n}")
    for year in SHEETS:
        dts = [r["registered_at"] for r in rows if r["event_year"] == year]
        print(f"  {year}: даты регистрации {min(dts)} .. {max(dts)}, без даты: {sum(d is None for d in dts)}")
    print(f"  сумма оплат: {sum(r['amount'] for r in rows):,.0f}")

    if not args.apply:
        print("\nЭто был dry-run. Повтори с --apply, чтобы применить.")
        return 0

    inserted, skipped, errors = insert_leads(rows, "+00:00")  # sent — UTC
    if inserted is None:
        return 1
    print(f"\nВставлено: {inserted}, пропущено (уже есть): {skipped}, ошибок: {errors}")
    if inserted:
        _recompute_client_lead_dates()
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
