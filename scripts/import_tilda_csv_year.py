#!/usr/bin/env python3
"""
Импорт заявок одного года из CRM-выгрузок Tilda (CSV, «;») — по файлу на старт
(2026-09-26: Весна, Красочный забег, Женская семерка 2026).

Дата — «Дата оплаты» (Москва -> UTC), сумма — «Сумма заказа», дистанция — из
SKU продукта (parse_tilda_csv). Дубли человека на дистанции — самая ранняя
заявка. Вставляются только те, кого нет в БД (ФИО+ДР+дистанция, а также ФИО
или email+ДР — «тот же человек», не вставляется).

  python scripts/import_tilda_csv_year.py --year 2026 --csv "Весна=…csv" --csv "…"             # dry-run
  python scripts/import_tilda_csv_year.py --year 2026 --csv … --apply
"""

import argparse
import sys
from collections import Counter
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.import_boom_historical import _recompute_client_lead_dates, dedupe, get_connection, insert_leads
from scripts.import_tilda_google_registrations import UTC, load_db_leads, parse_tilda_csv, plan


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--year", type=int, required=True)
    ap.add_argument("--csv", action="append", required=True, help="«Название старта в БД=путь к CSV»")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    to_insert = []
    conn = get_connection(UTC)
    try:
        for spec in args.csv:
            event, path = spec.split("=", 1)
            rows = parse_tilda_csv(path, event, args.year)
            rows, dup = dedupe(sorted(rows, key=lambda r: r["registered_at"]))
            by_key, by_fio, by_contact = load_db_leads(conn, event, [args.year])
            new, _, same = plan(rows, by_key, by_fio, by_contact, lambda db: False)
            d = [r["registered_at"] for r in new]
            print(f"{event} {args.year}: в файле {len(rows) + dup}, дублей {dup}, в БД уже {len(rows) - len(new) - len(same)}, "
                  f"тот же человек под другими ДР/ФИО {len(same)}, к вставке {len(new)} "
                  f"{dict(Counter(r['event_distance'] for r in new))}, даты (UTC) {min(d, default=None)} .. {max(d, default=None)}")
            to_insert += new
    finally:
        conn.close()
    if not args.apply:
        print("\ndry-run. Повтори с --apply.")
        return 0
    inserted, skipped, errors = insert_leads(to_insert, UTC)
    if inserted is None:
        return 1
    print(f"Вставлено: {inserted}, пропущено: {skipped}, ошибок: {errors}")
    _recompute_client_lead_dates()
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
