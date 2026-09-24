#!/usr/bin/env python3
"""
Разовое исправление leads.created_at у импортированных заявок, записанных в
неверном часовом поясе (2026-09-24, переход проекта на красноярское время).

leads.created_at — TIMESTAMP (хранит момент в UTC). Импорты писали наивные
значения в сессии MSK, хотя источники были в других поясах:
- Жара 2023–2024 (sent — UTC)                         -> +3 ч
- «Бум» 2013–2022, Payment date (UTC)                  -> +3 ч
- «Бум», заглушка 01.01 00:00 MSK                      -> 01.01 00:00 по Красноярску (−4 ч)
- импорты 2026 через /admin: колонка "Date" CRM-выгрузки Tilda (UTC−7)
  записана как MSK. Исправляются только строки, у которых created_at точно
  равен такому значению для строки CSV с тем же человеком/дистанцией;
  новая дата — "Дата оплаты" (Москва), без неё — "Date" (UTC−7).

Ночной забег 2025 исправляется отдельно: import_tilda_google_registrations.py
--reapply-ids.

Все вычисления — в сессии UTC. Перед UPDATE — бэкап id/created_at в --backup.

  python scripts/fix_leads_timezones.py --csv-dir /tmp/tilda_csv            # dry-run
  python scripts/fix_leads_timezones.py --csv-dir /tmp/tilda_csv --apply --backup /root/backups/x.tsv
"""

import argparse
import csv
import datetime
import io
import sys
from collections import Counter
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from scripts.import_boom_historical import _row_key, get_connection
from src.krasmarafon.services.tilda_import_parser import parse_tilda_datetime, parse_tilda_export

H = datetime.timedelta(hours=1)


def tilda_date_fixes(csv_dir):
    """{(ключ заявки, старый created_at UTC): новый created_at UTC} по всем CSV."""
    fixes = {}
    for path in sorted(Path(csv_dir).glob("*.csv")):
        data = path.read_bytes()
        parsed = parse_tilda_export(data, filename=path.name)
        # тот же csv.reader, что в парсере: пустые строки не выкидываются,
        # номер строки r.row_number совпадает с индексом
        table = list(csv.reader(io.StringIO(data.decode("utf-8-sig")), delimiter=";"))
        header = [h.strip().lower() for h in table[0]]
        for r in parsed.rows:
            raw = dict(zip(header, table[r.row_number - 1]))
            date = parse_tilda_datetime(raw.get("date"))
            if not date or not r.event_year:
                continue
            paid = parse_tilda_datetime(raw.get("дата оплаты"))
            old = date - 3 * H                       # "Date", записанная как MSK
            new = paid - 3 * H if paid else date + 7 * H
            key = _row_key(r.surname, r.name, r.birthday or "1900-01-01", r.event_name, r.event_year, r.event_distance)
            fixes[(key, old)] = new
    return fixes


def plan(cur, csv_dir):
    cur.execute(
        "SELECT id, surname, name, birthday, event_name, event_year, event_distance, created_at "
        "FROM leads WHERE source = 'import'"
    )
    rows = cur.fetchall()
    fixes = tilda_date_fixes(csv_dir) if csv_dir else {}
    updates, stats = [], Counter()
    for r in rows:
        ca, year = r["created_at"], r["event_year"]
        if year <= 2022:
            if ca == datetime.datetime(year - 1, 12, 31, 21):      # 01.01 00:00 MSK
                updates.append((r["id"], ca, ca - 4 * H)); stats["boom_placeholder"] += 1
            else:
                updates.append((r["id"], ca, ca + 3 * H)); stats["boom_payment_date"] += 1
        elif r["event_name"] == "Жара" and year in (2023, 2024):
            updates.append((r["id"], ca, ca + 3 * H)); stats["zhara_2023_2024"] += 1
        elif year >= 2026:
            key = _row_key(r["surname"], r["name"], r["birthday"].isoformat(), r["event_name"], year, r["event_distance"])
            new = fixes.get((key, ca))
            if new:
                updates.append((r["id"], ca, new)); stats[f"tilda_date_{r['event_name']}_{year}"] += 1
            else:
                stats[f"untouched_{r['event_name']}_{year}"] += 1
        else:
            stats[f"untouched_{r['event_name']}_{year}"] += 1
    return updates, stats


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv-dir", help="папка с CSV-выгрузками Tilda CRM (для импортов 2026)")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--backup")
    args = ap.parse_args()

    conn = get_connection("+00:00")
    try:
        cur = conn.cursor(dictionary=True)
        updates, stats = plan(cur, args.csv_dir)
        for k in sorted(stats):
            print(f"  {k}: {stats[k]}")
        print(f"Всего к исправлению: {len(updates)}")
        if not args.apply:
            print("dry-run. Повтори с --apply --backup <путь>.")
            return 0
        if not args.backup:
            print("Нужен --backup.")
            return 1
        with open(args.backup, "w", encoding="utf-8") as f:
            f.write("id\tcreated_at_utc\n")
            for id_, old, _ in updates:
                f.write(f"{id_}\t{old}\n")
        cur.executemany("UPDATE leads SET created_at = %s WHERE id = %s", [(new, id_) for id_, _, new in updates])
        conn.commit()
        print(f"Исправлено: {len(updates)}, бэкап: {args.backup}")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
