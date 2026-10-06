#!/usr/bin/env python3
"""
Категории результатов → единый краткий вид (src/common/categories.py, решение 2026-10-06).

  python scripts/normalize_result_categories.py                                 # dry-run: что на что
  python scripts/normalize_result_categories.py --apply --backup /root/backups/x.tsv
  python scripts/normalize_result_categories.py --from-birthday 79 --apply ...   # + категории по ДР

--from-birthday EVENT_ID — протокол без категорий (Женская семёрка 2025): категория по
возрасту в год старта (группы как у Copernico 2026), места в категориях пересчитываются
(официальное и чистое время, как scripts/import_results_xlsx.py). Повторный запуск ничего не меняет.
"""

import argparse
import collections
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.import_boom_historical import get_connection  # noqa: E402
from src.common.categories import age_category, canonical_category  # noqa: E402

SENTINEL_YEAR = 1900


def categories_from_birthday(cur, event_id):
    """[(id, новая категория)] по возрасту в год старта; ДР-заглушка — без категории."""
    cur.execute("SELECT event_year FROM events WHERE id = %s", (event_id,))
    year = int(cur.fetchone()[0])
    cur.execute("SELECT id, birthday, sex, category FROM results WHERE event_id = %s", (event_id,))
    out = []
    for rid, bd, sex, cat in cur.fetchall():
        if not bd or bd.year <= SENTINEL_YEAR or not sex:
            continue
        new = age_category(sex[:1].upper(), year - bd.year)
        if new != cat:
            out.append((rid, new))
    return out


def recompute_category_ranks(cur, event_id):
    """Места в категории по официальному и по чистому времени (финишировавшие)."""
    for time_col, rank_col in (("time_gun_finish", "rank_category"), ("time_clear_finish", "rank_category_clean")):
        cur.execute(f"""SELECT id, category FROM results
                        WHERE event_id = %s AND race_status = 'Finished' AND {time_col} IS NOT NULL
                        ORDER BY {time_col}, start_number""", (event_id,))
        counter = collections.Counter()
        for rid, cat in cur.fetchall():
            counter[cat] += 1
            cur.execute(f"UPDATE results SET {rank_col} = %s WHERE id = %s", (counter[cat], rid))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--backup", help="TSV: id, категория и места в категории до правки")
    ap.add_argument("--from-birthday", type=int, action="append", default=[], help="событие без категорий")
    args = ap.parse_args()
    if args.apply and not args.backup:
        ap.error("--apply требует --backup")

    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT category, COUNT(*) FROM results GROUP BY category")
        mapping = {cat: canonical_category(cat) for cat, _ in cur.fetchall()}
        cur.execute("SELECT category, COUNT(*) FROM results GROUP BY category")
        counts = dict(cur.fetchall())
        changes = {old: new for old, new in mapping.items() if new != (old or "")}
        print(f"Категорий: {len(mapping)} → {len(set(mapping.values()))}; меняются {len(changes)} написаний, "
              f"{sum(counts[o] for o in changes)} результатов")
        for old, new in sorted(changes.items(), key=lambda kv: kv[1]):
            print(f"   {counts[old]:5}  «{old}» → «{new}»")
        birthday = {e: categories_from_birthday(cur, e) for e in args.from_birthday}
        for e, rows in birthday.items():
            print(f"Событие {e}: категории по ДР — {len(rows)} результатов: "
                  f"{dict(collections.Counter(new for _, new in rows))}")
        if not args.apply:
            print("\ndry-run. Повтори с --apply --backup …")
            return 0

        cur.execute("SELECT id, event_id, category, rank_category, rank_category_clean FROM results")
        with open(args.backup, "w", encoding="utf-8") as f:
            for row in cur.fetchall():
                f.write("\t".join("" if v is None else str(v) for v in row) + "\n")
        if conn.in_transaction:
            conn.commit()
        conn.start_transaction()
        for old, new in changes.items():
            cur.execute("UPDATE results SET category = %s WHERE category = %s", (new, old))
        for e, rows in birthday.items():
            cur.executemany("UPDATE results SET category = %s WHERE id = %s", [(new, rid) for rid, new in rows])
            recompute_category_ranks(cur, e)
        conn.commit()
        cur.execute("SELECT COUNT(DISTINCT category) FROM results")
        print("Готово. Категорий теперь:", cur.fetchone()[0])
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
