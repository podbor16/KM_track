#!/usr/bin/env python3
"""
Импорт заявок Весны 2023–2025 (2026-09-26, по аналогии с Ночным забегом —
import_tilda_google_registrations.py, но форматы листов Google другие).

Источники:
- Google xlsx, лист «2023»: Bib, surname, name, …, sent (UTC); продукта нет —
  по решению пользователя вся Весна 2023 — 5 км; часть строк со съехавшими
  колонками (дата — в соседней колонке).
- лист «2024»: фамилия — в колонке без заголовка, name, products
  («Весна 12.05.24, 5 км (Vesna5-2024, …)»), price, sent (UTC).
- лист «Стартовый 2025»: итоговый стартовый список организатора (Номер,
  Фамилия, Имя, products — дистанция, products — продукт), без дат.
- Tilda CSV 2025: «Дата оплаты» (Москва) и «Сумма заказа».

Решения пользователя:
- 2023 и 2024 — в БД заявок нет, вставляются все; дата — sent, у строк без
  неё — дата ближайшей строки выше; дубли человека на дистанции — самая ранняя;
- 2025 — в БД уже заявки вебхука (с датами), вставляются только участники
  стартового списка, которых нет в БД: дата — из Tilda CSV, иначе последний
  день регистрации (последняя «Дата оплаты» в CSV); «пачку» 21.01.2025 не трогаем;
- стартовые номера 2023 и 2025 записываются в заявки (и в новые, и в уже
  существующие).

Сессия БД — UTC.

  python scripts/import_vesna_2023_2025.py --google-xlsx … --tilda-csv …            # dry-run
  python scripts/import_vesna_2023_2025.py --google-xlsx … --tilda-csv … --apply --backup /root/backups/x.json
"""

import argparse
import datetime
import json
import re
import sys
import warnings
from collections import Counter
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import openpyxl

from scripts.import_boom_historical import _recompute_client_lead_dates, dedupe, get_connection, insert_leads
from scripts.import_tilda_google_registrations import (
    UTC, _contact_key, _fio_key, _key, _record, load_db_leads, parse_tilda_csv,
)
from scripts.import_zhara_2023_2024 import fill_missing_dates

warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl")

EVENT = "Весна"
_DT_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")
_DIST_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*км", re.IGNORECASE)
_PROMO_RE = re.compile(r"^[A-Z0-9]+$")


def _dt(v):
    if isinstance(v, datetime.datetime):
        return v
    s = str(v or "").strip()
    return datetime.datetime.strptime(s, "%Y-%m-%d %H:%M:%S") if _DT_RE.match(s) else None


def _sheet(ws):
    it = ws.iter_rows(values_only=True)
    headers = [str(h).strip() if h is not None else "" for h in next(it)]
    return headers, [r for r in it if any(v is not None and str(v).strip() != "" for v in r)]


def _sku(dist):
    """Синтетический код продукта для _record(): дистанцию он берёт из SKU
    в скобках ("(v5-2000" -> "5 км")."""
    return f"(v{dist.split()[0]}-2000)" if dist else None


def _distance(text, default=None):
    m = _DIST_RE.search(str(text or ""))
    return f"{m.group(1).replace(',', '.')} км" if m else default


def parse_2023(ws, stats):
    h, rows = _sheet(ws)
    i = {k.lower(): n for n, k in enumerate(h) if k}
    out = []
    for r in rows:
        get = lambda f: r[i[f]] if f in i and i[f] < len(r) else None
        # дата: sent, а у строк со съехавшими колонками — первая дата-время
        # правее колонки Checkbox
        date = _dt(get("sent")) or next((d for d in map(_dt, r[i["checkbox"]:]) if d), None)
        rec = _record(lambda f: {"product": _sku("5 км"), "total amount": get("price")}.get(f, get(f)),
                      EVENT, 2023, "product", date, "total amount")
        if rec:
            bib = get("bib")
            rec["start_number"] = int(bib) if str(bib or "").strip().isdigit() else None
            # в съехавших строках в колонку промокода попадают "Paid"/"RUB"
            if not _PROMO_RE.match(rec["promocode"]) or rec["promocode"] == "RUB":
                rec["promocode"] = ""
            out.append(rec)
        else:
            stats["2023: пропущено (нет ФИО)"] += 1
    return out


def parse_2024(ws, stats):
    h, rows = _sheet(ws)
    i = {k.lower(): n for n, k in enumerate(h) if k}
    i["surname"] = 0  # фамилия — в первой колонке без заголовка
    out = []
    for r in rows:
        get = lambda f: r[i[f]] if f in i and i[f] < len(r) else None
        dist = _distance(get("products"))
        rec = _record(lambda f: {"product": _sku(dist), "total amount": get("price")}.get(f, get(f)),
                      EVENT, 2024, "product", _dt(get("sent")), "total amount") if dist else None
        if rec:
            out.append(rec)
        else:
            stats["2024: пропущено (нет ФИО/дистанции)"] += 1
    return out


def parse_2025_start_list(ws, stats):
    h, rows = _sheet(ws)
    low = [k.lower() for k in h]
    i = {"surname": low.index("фамилия"), "name": low.index("имя"), "bib": low.index("номер"),
         "distance": low.index("products"), "sex": low.index("sex"), "city": low.index("city"),
         "club": low.index("club"), "birthday": low.index("birthday"), "phone": low.index("phone"),
         "email": low.index("email")}
    out = []
    for r in rows:
        get = lambda f: r[i[f]] if f in i and i[f] < len(r) else None
        dist = _distance(get("distance"))
        rec = _record(lambda f: {"product": _sku(dist)}.get(f, get(f)),
                      EVENT, 2025, "product", None, "total amount") if dist else None
        if rec:
            bib = get("bib")
            rec["start_number"] = int(bib) if str(bib or "").strip().isdigit() else None
            out.append(rec)
        else:
            stats["2025: пропущено (номер без участника)"] += 1
    return out


def find_existing(r, by_key, by_fio, by_contact):
    return by_key.get(_key(r)) or by_fio.get(_fio_key(r)) or by_contact.get(_contact_key(r)) or []


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--google-xlsx", required=True)
    ap.add_argument("--tilda-csv", required=True)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--backup")
    args = ap.parse_args()

    wb = openpyxl.load_workbook(args.google_xlsx, data_only=True, read_only=True)
    stats = Counter()
    rows_2023, rows_2024 = parse_2023(wb["2023"], stats), parse_2024(wb["2024"], stats)
    for year, rows in ((2023, rows_2023), (2024, rows_2024)):
        stats[f"{year}: без даты -> соседняя строка"] = sum(r["registered_at"] is None for r in rows)
        fill_missing_dates(rows, Counter())
    hist, dup = dedupe(sorted(rows_2023 + rows_2024, key=lambda r: (r["event_year"], r["registered_at"])))
    stats["2023-2024: дублей убрано"] = dup

    start_2025 = parse_2025_start_list(wb["Стартовый 2025"], stats)
    tilda = {_key(t): t for t in parse_tilda_csv(args.tilda_csv, EVENT, 2025)}
    last_reg = max(t["registered_at"] for t in tilda.values())

    conn = get_connection(UTC)
    try:
        by_key, by_fio, by_contact = load_db_leads(conn, EVENT, [2023, 2024, 2025])
        to_insert = [r for r in hist if not find_existing(r, by_key, by_fio, by_contact)]
        bib_updates = []
        for r in start_2025:
            existing = find_existing(r, by_key, by_fio, by_contact)
            if existing:
                if r["start_number"]:
                    bib_updates += [(db["id"], r["start_number"]) for db in existing if db["event_distance"] == r["event_distance"]]
                continue
            t = tilda.get(_key(r))
            r["registered_at"] = t["registered_at"] if t else last_reg
            r["amount"] = t["amount"] if t else 0.0
            stats["2025: новых, дата из Tilda" if t else "2025: новых, дата — последний день регистрации"] += 1
            to_insert.append(r)

        for k in sorted(stats):
            print(f"  {k}: {stats[k]}")
        print(f"  последний день регистрации 2025 (UTC): {last_reg}")
        print("К вставке:", dict(Counter((r["event_year"], r["event_distance"]) for r in to_insert)))
        print("  со стартовым номером:", sum(1 for r in to_insert if r.get("start_number")))
        print("Номер в существующие заявки 2025:", len(bib_updates))
        for y in (2023, 2024):
            d = [r["registered_at"] for r in to_insert if r["event_year"] == y]
            if d:
                print(f"  {y}: даты {min(d)} .. {max(d)}")
        if not args.apply:
            print("\ndry-run. Повтори с --apply --backup <путь>.")
            return 0
        if not args.backup:
            print("Нужен --backup.")
            return 1
        cur = conn.cursor(dictionary=True)
        ids = [i for i, _ in bib_updates]
        if ids:
            cur.execute(f"SELECT id, start_number FROM leads WHERE id IN ({','.join(map(str, ids))})")
            Path(args.backup).write_text(json.dumps(cur.fetchall(), default=str), encoding="utf-8")
            cur.executemany("UPDATE leads SET start_number = %s WHERE id = %s", [(b, i) for i, b in bib_updates])
            conn.commit()
    finally:
        conn.close()
    inserted, skipped, errors = insert_leads(to_insert, UTC)
    if inserted is None:
        return 1
    print(f"Номер записан в существующие: {len(bib_updates)}; вставлено: {inserted}, пропущено: {skipped}, ошибок: {errors}")
    _recompute_client_lead_dates()
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
