#!/usr/bin/env python3
"""
Дистанция заявок Детского забега по возрасту (решение пользователя,
2026-09-26): год старта − год рождения ≤ 5 — 500 м, иначе 1 км. Правило для
всех лет; заявки без даты рождения (заглушка 1900/1905) не трогаются.

Меняются leads.event_distance и leads.event_id (событие года и дистанции;
если его нет — создаётся, как в trg_leads_before_insert).

  python scripts/fix_kids_distances.py                                        # dry-run
  python scripts/fix_kids_distances.py --apply --backup /root/backups/x.json
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.import_boom_historical import get_connection

EVENT = "Детский забег"
KM = {"500 м": 0.5, "1 км": 1.0}

_WRONG = """
SELECT id, event_year, event_distance, event_id, birthday,
       IF(event_year - YEAR(birthday) <= 5, '500 м', '1 км') AS want
FROM leads
WHERE event_name = %s AND YEAR(birthday) > 1905
HAVING event_distance <> want
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--backup")
    args = ap.parse_args()

    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(_WRONG, (EVENT,))
        wrong = cur.fetchall()
        print("Не по правилу:", dict(Counter((r["event_year"], r["event_distance"], r["want"]) for r in wrong)))
        if not args.apply or not wrong:
            print("\ndry-run. Повтори с --apply --backup <путь>." if wrong else "Исправлять нечего.")
            return 0
        if not args.backup:
            print("Нужен --backup.")
            return 1
        Path(args.backup).write_text(json.dumps(wrong, default=str), encoding="utf-8")
        events = {}
        for year, dist in sorted({(r["event_year"], r["want"]) for r in wrong}):
            cur.execute("SELECT id FROM events WHERE event_name = %s AND event_year = %s AND event_distance = %s "
                        "ORDER BY id LIMIT 1", (EVENT, year, KM[dist]))
            row = cur.fetchone()
            if not row:
                cur.execute("INSERT INTO events (event_name, event_distance, event_year, event_date) "
                            "VALUES (%s, %s, %s, NULL)", (EVENT, KM[dist], year))
                row = {"id": cur.lastrowid}
                print(f"  создано событие {year} {dist}: {row['id']}")
            events[(year, dist)] = row["id"]
        cur.executemany("UPDATE leads SET event_distance = %s, event_id = %s WHERE id = %s",
                        [(r["want"], events[(r["event_year"], r["want"])], r["id"]) for r in wrong])
        conn.commit()
        print(f"Исправлено: {len(wrong)}")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
