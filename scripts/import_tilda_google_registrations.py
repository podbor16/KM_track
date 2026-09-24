#!/usr/bin/env python3
"""
Импорт заявок старта за 2024-2025 из пары источников: CSV-выгрузка Tilda CRM
+ xlsx из Google-таблиц (по листу на год). В 2025 заявки собирались в оба
места, часть из них уже лежит в БД — вебхуком и одной пачкой из Google
(у пачки одна и та же дата created_at и amount = 0).

Что делает:
- Google-лист года: дистанция из SKU продукта ("(night5y-2025" -> 5 км),
  дата — колонка sent; у строк без неё — дата из Tilda CSV (та же персона и
  дистанция), иначе — дата ближайшей строки выше;
- строки Tilda CSV, которых нет в Google, добавляются;
- дубли человека на одной дистанции -> одна (самая ранняя) заявка;
- в БД: новых заявок — INSERT (insert_leads()), строкам пачки
  (--batch-created-at) — UPDATE created_at и amount (если был 0). Прочие
  существующие заявки не трогаются.

Решения пользователя — .taskmaster/tasks/todo.md (Ночной забег 2024-2025).

Использование:
  python scripts/import_tilda_google_registrations.py --event-name "Ночной забег" \\
      --tilda-csv "...csv" --tilda-year 2025 --google-xlsx "...xlsx" --sheets 2025 2024 \\
      --batch-created-at "2025-01-21 04:50:00" [--apply --backup /root/backups/x.tsv]

Все даты — UTC (sent в Google, "Дата оплаты" в Tilda; сессия БД — +00:00),
поэтому и --batch-created-at задаётся в UTC.
"""

import argparse
import csv
import datetime
import io
import re
import sys
import warnings
from collections import Counter, defaultdict
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import openpyxl

from scripts.import_boom_historical import (
    _clean_email, _clean_phone, _clean_text, _recompute_client_lead_dates, _row_key,
    dedupe, get_connection, insert_leads,
)
from scripts.import_zhara_2023_2024 import _float, fill_missing_dates, parse_birthday, registered_at
from src.krasmarafon.services.tilda_webhook import is_name_suspicious, normalize_name

# Даты в источниках (sent в Google, "Дата оплаты" в Tilda) — UTC; сессия БД тоже в UTC
UTC = "+00:00"
warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl")

_SKU_RE = re.compile(r"\(([a-z]+?)(\d+)[a-z]*-(\d{4})")


def distance_from_sku(product):
    m = _SKU_RE.search(str(product or ""))
    if not m:
        return None
    n = m.group(2)
    return "21.1 км" if n == "21" else f"{n} км"


def normalize_sex(raw):
    """'жен'/'Ж'/'женский'/'Женщина' -> 'Женщина', аналогично для 'м'; иначе ''."""
    s = _clean_text(raw).lower()
    return "Женщина" if s.startswith("ж") else "Мужчина" if s.startswith("м") else ""


def _record(get, event_name, event_year, product_col, date, amount_col):
    distance = distance_from_sku(get(product_col))
    surname = normalize_name(_clean_text(get("surname")))
    name = normalize_name(_clean_text(get("name")))
    if distance is None or not surname or not name:
        return None
    return {
        "surname": surname,
        "name": name,
        "sex": normalize_sex(get("sex")),
        "city": _clean_text(get("city")),
        "club": _clean_text(get("club")) or None,
        "birthday": parse_birthday(get("birthday"), event_year),
        "phone": _clean_phone(get("phone")),
        "email": _clean_email(get("email")),
        "event_name": event_name,
        "event_distance": distance,
        "event_year": event_year,
        "amount": _float(get(amount_col)),
        "promocode": _clean_text(get("promocode")),
        "discount": _float(get("discount")),
        "registered_at": date,
        "is_name_suspicious": int(is_name_suspicious(surname, name)),
    }


def _key(r):
    return _row_key(r["surname"], r["name"], r["birthday"], r["event_name"], r["event_year"], r["event_distance"])


def parse_tilda_csv(path, event_name, event_year):
    text = Path(path).read_bytes().decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text), delimiter=";")
    rows = []
    for raw in reader:
        low = {str(k).strip().lower(): v for k, v in raw.items()}
        get = lambda f: low.get(f)
        low.setdefault("product", low.get("дистанция исходник"))
        # "Дата оплаты" — UTC, как sent в Google; "Date" выгрузки CRM сдвинута на -10 ч
        paid = (low.get("дата оплаты") or "").strip()
        date = datetime.datetime.strptime(paid[:19], "%Y-%m-%d %H:%M:%S") if paid else None
        rec = _record(get, event_name, event_year, "product", date, "сумма заказа")
        if rec:
            rows.append(rec)
    return rows


def parse_google_sheet(ws, event_name, event_year):
    it = ws.iter_rows(values_only=True)
    cols = {str(h).strip(): i for i, h in enumerate(next(it)) if h}
    low = {k.lower(): i for k, i in cols.items()}
    rows, skipped = [], 0
    for row in it:
        if not any(v is not None and str(v).strip() != "" for v in row):
            continue
        get = lambda f: row[low[f]] if f in low and low[f] < len(row) else None
        rec = _record(get, event_name, event_year, "product", registered_at(row, cols), "total amount")
        if rec is None:
            skipped += 1
        else:
            rows.append(rec)
    return rows, skipped


def merge_year(google_rows, tilda_rows, stats):
    """Даты строк Google без sent — из Tilda; остальное — соседняя строка
    выше. Строки Tilda, которых нет в Google, добавляются в конец."""
    by_key = defaultdict(list)
    for t in tilda_rows:
        by_key[_key(t)].append(t)
    used = set()
    for g in google_rows:
        match = by_key.get(_key(g))
        if not match:
            continue
        used.add(_key(g))
        if g["registered_at"] is None:
            g["registered_at"] = match[0]["registered_at"]
            stats["date_from_tilda"] += 1
        if not g["amount"] and match[0]["amount"]:
            g["amount"] = match[0]["amount"]
    fill_missing_dates(google_rows, stats)
    extra = [t for t in tilda_rows if _key(t) not in used]
    stats["tilda_only"] += len(extra)
    return google_rows + extra


def load_db_leads(conn, event_name, years):
    cur = conn.cursor(dictionary=True)
    cur.execute(
        "SELECT id, client_id, surname, name, birthday, email, event_year, event_distance, created_at, amount "
        f"FROM leads WHERE event_name = %s AND event_year IN ({','.join(['%s'] * len(years))})",
        (event_name, *years),
    )
    by_key, by_fio, by_contact = defaultdict(list), defaultdict(list), defaultdict(list)
    for r in cur.fetchall():
        r["birthday"] = r["birthday"].isoformat()
        by_key[_row_key(r["surname"], r["name"], r["birthday"], event_name, r["event_year"], r["event_distance"])].append(r)
        by_fio[_fio_key(r)].append(r)
        if _contact_key(r):
            by_contact[_contact_key(r)].append(r)
    cur.close()
    return by_key, by_fio, by_contact


def _fio_key(r):
    return (r["surname"].lower(), r["name"].lower(), r["event_year"], r["event_distance"])


def _contact_key(r):
    email = (r["email"] or "").strip().lower()
    return None if email in ("", "example@mail.ru") else (email, r["birthday"], r["event_year"], r["event_distance"])


def is_fio_glued(r):
    """Форма заполнена полным ФИО в обоих полях: surname == name, несколько слов."""
    return r["surname"].lower() == r["name"].lower() and " " in r["surname"].strip()


def plan(rows, by_key, by_fio, by_contact, batch_ts):
    """Строки пачки обновляются все (дубли одного человека в БД получают одну
    дату). Нет совпадения по ФИО+ДР — ищем того же человека по ФИО+дистанции
    (другая дата рождения) или по email+ДР+дистанции (ФИО в файле склеено):
    такие не вставляем, строки пачки исправляем."""
    to_insert, to_update, suspicious = [], [], []
    for r in rows:
        existing = by_key.get(_key(r))
        if not existing:
            existing = by_fio.get(_fio_key(r)) or by_contact.get(_contact_key(r))
            if not existing:
                to_insert.append(r)
                continue
            suspicious.append(r)
        for db in existing:
            if batch_ts and db["created_at"] == batch_ts and db["id"] not in {u[0]["id"] for u in to_update}:
                new_amount = r["amount"] if not float(db["amount"] or 0) and r["amount"] else float(db["amount"] or 0)
                to_update.append((db, r["registered_at"], new_amount))
    return to_insert, to_update, suspicious


def apply_updates(conn, to_update, backup_path):
    with open(backup_path, "w", encoding="utf-8") as f:
        f.write("id\tcreated_at\tamount\n")
        for db, _, _ in to_update:
            f.write(f"{db['id']}\t{db['created_at']}\t{db['amount']}\n")
    cur = conn.cursor()
    for db, created_at, amount in to_update:
        cur.execute("UPDATE leads SET created_at = %s, amount = %s WHERE id = %s", (created_at, amount, db["id"]))
    # trg_leads_after_update при любом UPDATE переписывает клиенту phone/email
    # из этой (старой) заявки — возвращаем контакты из последней заявки клиента
    client_ids = sorted({db["client_id"] for db, _, _ in to_update if db["client_id"]})
    for cid in client_ids:
        cur.execute(
            """UPDATE clients c
               JOIN (SELECT phone, email FROM leads WHERE client_id = %s ORDER BY id DESC LIMIT 1) l
               SET c.phone = COALESCE(NULLIF(l.phone, ''), c.phone),
                   c.email = COALESCE(NULLIF(l.email, ''), c.email)
               WHERE c.id = %s""",
            (cid, cid),
        )
    conn.commit()
    cur.close()
    return len(client_ids)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--event-name", required=True)
    ap.add_argument("--tilda-csv")
    ap.add_argument("--tilda-year", type=int)
    ap.add_argument("--google-xlsx", required=True)
    ap.add_argument("--sheets", nargs="+", type=int, required=True)
    ap.add_argument("--batch-created-at", help="created_at строк, загруженных в БД пачкой, в UTC (их даты/суммы исправляются)")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--backup", help="куда сохранить id/created_at/amount исправляемых строк (обязательно с --apply)")
    args = ap.parse_args()
    batch_ts = datetime.datetime.strptime(args.batch_created_at, "%Y-%m-%d %H:%M:%S") if args.batch_created_at else None
    print(f"{args.event_name}: {args.sheets} | Режим: {'ПРИМЕНЕНИЕ' if args.apply else 'DRY-RUN'}")

    wb = openpyxl.load_workbook(args.google_xlsx, data_only=True, read_only=True)
    rows, stats = [], Counter()
    for year in args.sheets:
        g_rows, skipped = parse_google_sheet(wb[str(year)], args.event_name, year)
        t_rows = parse_tilda_csv(args.tilda_csv, args.event_name, year) if args.tilda_csv and year == args.tilda_year else []
        stats[f"{year}: google"] = len(g_rows)
        stats[f"{year}: google_skipped"] = skipped
        stats[f"{year}: tilda"] = len(t_rows)
        rows += merge_year(g_rows, t_rows, stats)
    rows.sort(key=lambda r: (r["event_year"], r["registered_at"] or datetime.datetime.min))
    rows, dup = dedupe(rows)
    stats["dedup_removed"] = dup
    for k in sorted(stats):
        print(f"  {k}: {stats[k]}")
    print(f"  без даты после заполнения: {sum(r['registered_at'] is None for r in rows)}")
    for k, n in sorted(Counter((r["event_year"], r["event_distance"]) for r in rows).items()):
        print(f"  {k}: {n}")

    conn = get_connection(UTC)
    try:
        by_key, by_fio, by_contact = load_db_leads(conn, args.event_name, args.sheets)
        to_insert, to_update, suspicious = plan(rows, by_key, by_fio, by_contact, batch_ts)
        remaining_batch = sum(1 for lst in by_key.values() for db in lst if batch_ts and db["created_at"] == batch_ts) - len(to_update)
        print(f"\nВ БД сейчас: {sum(map(len, by_key.values()))}")
        print(f"К вставке: {len(to_insert)} {dict(Counter((r['event_year'], r['event_distance']) for r in to_insert))}")
        print(f"Исправить дату/сумму у строк пачки: {len(to_update)} (из них сумма с 0: "
              f"{sum(1 for db, _, a in to_update if a and not float(db['amount'] or 0))})")
        print(f"Строк пачки, которым не нашлось пары в файлах: {remaining_batch}")
        print(f"Тот же человек в БД под другими ДР/ФИО (не вставлены): {len(suspicious)}")
        glued = [r for r in to_insert if is_fio_glued(r)]
        print(f"К вставке со склеенным ФИО (фамилия = имя = полное ФИО): {len(glued)}")
        if not args.apply:
            print("\nЭто был dry-run. Повтори с --apply --backup <путь>, чтобы применить.")
            return 0
        if to_update:
            if not args.backup:
                print("Нужен --backup для исправления существующих строк.")
                return 1
            fixed_clients = apply_updates(conn, to_update, args.backup)
            print(f"Исправлено строк: {len(to_update)}, контакты клиентов восстановлены: {fixed_clients}, бэкап: {args.backup}")
    finally:
        conn.close()

    inserted, skipped, errors = insert_leads(to_insert, UTC)
    if inserted is None:
        return 1
    print(f"Вставлено: {inserted}, пропущено (уже есть): {skipped}, ошибок: {errors}")
    _recompute_client_lead_dates()
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
