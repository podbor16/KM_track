#!/usr/bin/env python3
"""
Применение migrations/remove_yo_in_names.sql с проверкой (2026-09-28): триггеры
(DDL — без транзакции), затем замена «ё» в ФИО и возврат контактов карточек в
одной транзакции; если phone/email хоть одной карточки отличаются от исходных
побайтово — откат. Выполнять после scripts/clean_clients.py, лоадер остановлен.

  python scripts/apply_remove_yo.py            # dry-run: сколько строк с «ё»
  python scripts/apply_remove_yo.py --apply
"""

import argparse
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.import_boom_historical import get_connection

SQL = Path(__file__).parent.parent / "migrations" / "remove_yo_in_names.sql"
YO = "(" + " OR ".join(f"CONCAT(surname, ' ', name) LIKE BINARY '%{ch}%'" for ch in "ёЁëË") + ")"


def statements(sql):
    out, delim, buf = [], ";", []
    for line in sql.splitlines():
        s = line.strip()
        if s.startswith("DELIMITER "):
            delim = s.split()[1]
            continue
        if not buf and (not s or s.startswith("--")):
            continue
        buf.append(line)
        if s.endswith(delim):
            out.append("\n".join(buf).strip()[: -len(delim)].strip())
            buf = []
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    conn = get_connection()
    cur = conn.cursor()
    counts = {}
    for t in ("clients", "leads", "results"):
        cur.execute(f"SELECT COUNT(*) FROM {t} WHERE {YO}")
        counts[t] = cur.fetchone()[0]
    print("строк с «ё» в ФИО:", counts)
    if not args.apply:
        print("\ndry-run. Повтори с --apply.")
        return 0
    stmts = statements(SQL.read_text(encoding="utf-8"))
    ddl = [s for s in stmts if s.upper().startswith(("DROP TRIGGER", "CREATE TRIGGER"))]
    dml = [s for s in stmts if s not in ddl]
    for s in ddl:
        cur.execute(s)
    print(f"триггеров создано: {sum(s.upper().startswith('CREATE TRIGGER') for s in ddl)}")
    cur.execute("SELECT id, phone, email FROM clients")
    before = {r[0]: (r[1], r[2]) for r in cur.fetchall()}
    conn.commit()                                   # DDL выше — отдельно; дальше одна транзакция
    for s in dml:
        cur.execute(s)
        if cur.with_rows:
            print("  ", cur.fetchall())
    cur.execute("SELECT id, phone, email FROM clients")
    changed = [i for i, p, e in cur.fetchall() if i in before and before[i] != (p, e)]
    left = {}
    for t in ("clients", "leads", "results"):
        cur.execute(f"SELECT COUNT(*) FROM {t} WHERE {YO}")
        left[t] = cur.fetchone()[0]
    if changed or any(left.values()):
        conn.rollback()
        print(f"ОТКАТ: контакты изменились у {len(changed)} карточек {changed[:10]}, осталось «ё»: {left}")
        return 1
    conn.commit()
    print("Готово: «ё» в ФИО не осталось, контакты карточек не изменились.")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
