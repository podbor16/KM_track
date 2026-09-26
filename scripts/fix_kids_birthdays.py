#!/usr/bin/env python3
"""
Дата рождения детям из Google xlsx Детского забега 2022–2025 (2026-09-26,
решение пользователя): у заявок с заглушкой (1900-01-01) дата берётся из
строки файла того же года с теми же фамилией и именем (регистрации и
стартовый лист), если дата в файле одна. Заявка перепривязывается к карточке
клиента с настоящей датой (recover_birthdays.set_birthdays). Дистанцию после
этого выравнивает scripts/fix_kids_distances.py.

  python scripts/fix_kids_birthdays.py --google-xlsx …                        # dry-run
  python scripts/fix_kids_birthdays.py --google-xlsx … --apply --backup /root/backups/x.json
"""

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent.parent))

import openpyxl

from scripts.import_boom_historical import _recompute_client_lead_dates, get_connection
from scripts.import_kids_2022_2025 import EVENT, REG_SHEETS, START_SHEETS, kids_distance
from scripts.import_tilda_google_registrations import parse_google_sheet, parse_start_list
from scripts.recover_birthdays import SENTINEL, set_birthdays


def file_birthdays(path):
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    rows = [r for y, s in REG_SHEETS.items() for r in parse_google_sheet(wb[s], EVENT, y, kids_distance)[0]]
    rows += [r for y, s in START_SHEETS.items() for r in parse_start_list(wb[s], EVENT, y, Counter(), kids_distance)]
    known = defaultdict(set)
    for r in rows:
        if r["birthday"] and r["birthday"] != SENTINEL:
            known[(r["surname"].lower(), r["name"].lower(), r["event_year"])].add(r["birthday"])
    return known


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--google-xlsx", required=True)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--backup")
    args = ap.parse_args()

    known = file_birthdays(args.google_xlsx)
    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(f"SELECT id, client_id, surname, name, event_year, event_distance FROM leads "
                    f"WHERE event_name = %s AND birthday = %s AND event_year IN ({','.join(['%s'] * len(REG_SHEETS))})",
                    (EVENT, SENTINEL, *REG_SHEETS))
        missing = cur.fetchall()
        plan, stats = [], Counter()
        for lead in missing:
            dates = known.get((lead["surname"].lower(), lead["name"].lower(), lead["event_year"]), set())
            if len(dates) == 1:
                plan.append((lead, next(iter(dates))))
            else:
                stats["нет в файле" if not dates else "в файле несколько дат"] += 1
                if dates:
                    print(f"  {lead['id']} | {lead['surname']} {lead['name']} | {lead['event_year']} | {sorted(dates)}")
        print(f"С заглушкой ДР: {len(missing)}, дата из файла: {len(plan)}, {dict(stats)}")
        if not args.apply:
            print("\ndry-run. Повтори с --apply --backup <путь>.")
            return 0
        if not args.backup:
            print("Нужен --backup.")
            return 1
        Path(args.backup).write_text(json.dumps(
            [{"id": l["id"], "client_id": l["client_id"], "birthday": SENTINEL} for l, _ in plan]), encoding="utf-8")
        relinked, kept, orphans = set_birthdays(conn, plan)
        print(f"Дата поставлена: {len(plan)} (перепривязано к карточке: {relinked}, дата карточке: {kept}), "
              f"удалено пустых карточек: {orphans}")
    finally:
        conn.close()
    _recompute_client_lead_dates()
    return 0


if __name__ == "__main__":
    sys.exit(main())
