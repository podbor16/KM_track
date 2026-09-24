#!/usr/bin/env python3
"""
Восстановление даты рождения у заявок, где она неизвестна (leads.birthday =
1900-01-01: весь 2013 год «Бума» и единичные заявки других лет), по более
поздним заявкам того же человека (2026-09-24, решение пользователя).

Уровни (совпадение по фамилии+имени с заявками, где дата известна):
  A  — совпал email или телефон, дата у человека одна     -> применяем
  B1 — совпал город, дата одна                            -> применяем
  X  — совпал email/телефон, но дат несколько              -> список пользователю
  B2/B3/C/D — только ФИ / другой город / несколько дат / нет совпадений — не трогаем

Заявке ставится дата и она перепривязывается к карточке клиента с такими
ФИО и датой (история участия объединяется); опустевшие карточки удаляются
migrations/cleanup_orphan_clients.sql, даты клиентов пересчитываются.

  python scripts/recover_birthdays.py            # dry-run + список X
  python scripts/recover_birthdays.py --apply --backup /root/backups/x.json
"""

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from scripts.import_boom_historical import _recompute_client_lead_dates, get_connection
from src.config import settings

SENTINEL = "1900-01-01"
APPLY_TIERS = ("A", "B1")


def _email(v):
    v = (v or "").strip().lower()
    return "" if v in ("", "example@mail.ru") else v


def _phone(v):
    d = re.sub(r"\D", "", v or "")
    return d[-10:] if len(d) >= 10 else ""


def classify(lead, known):
    """-> (tier, дата | None, {дата: число заявок} для X)."""
    same_fio = known.get((lead["surname"].lower(), lead["name"].lower()), [])
    em, ph, ci = _email(lead["email"]), _phone(lead["phone"]), (lead["city"] or "").strip().lower()
    by_contact = Counter(k["bd"] for k in same_fio
                         if (em and _email(k["email"]) == em) or (ph and _phone(k["phone"]) == ph))
    if len(by_contact) == 1:
        return "A", next(iter(by_contact)), None
    if len(by_contact) > 1:
        return "X", None, dict(by_contact)
    dates = {k["bd"] for k in same_fio}
    if len(dates) == 1:
        if ci and any((k["city"] or "").strip().lower() == ci for k in same_fio):
            return "B1", next(iter(dates)), None
        return ("B2" if not ci else "B3"), None, None
    return ("C" if dates else "D"), None, None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--backup")
    args = ap.parse_args()

    conn = get_connection(settings.DB_TIME_ZONE)
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT id, surname, name, email, phone, city, client_id, event_name, event_year, event_distance "
                "FROM leads WHERE birthday = %s", (SENTINEL,))
    missing = cur.fetchall()
    cur.execute("SELECT surname, name, birthday, email, phone, city FROM leads WHERE birthday <> %s", (SENTINEL,))
    known = defaultdict(list)
    for k in cur.fetchall():
        known[(k["surname"].lower(), k["name"].lower())].append({**k, "bd": k["birthday"].isoformat()})

    plan, tiers, x_list = [], Counter(), []
    for lead in missing:
        tier, bd, x = classify(lead, known)
        tiers[(tier, lead["event_year"] == 2013)] += 1
        if tier in APPLY_TIERS:
            plan.append((lead, bd))
        elif tier == "X":
            x_list.append((lead, x))
    for t in sorted({t for t, _ in tiers}):
        print(f"  {t}: всего {tiers[(t, False)] + tiers[(t, True)]}, из них 2013 — {tiers[(t, True)]}")
    print(f"К применению ({'+'.join(APPLY_TIERS)}): {len(plan)}")

    print("\nX — у человека в заявках разные даты рождения:")
    for lead, dates in sorted(x_list, key=lambda p: (p[0]["surname"], p[0]["name"])):
        opts = ", ".join(f"{d} ({n})" for d, n in sorted(dates.items(), key=lambda kv: -kv[1]))
        print(f"  {lead['id']} | {lead['surname']} {lead['name']} | {lead['event_name']} {lead['event_year']} {lead['event_distance']} | {opts}")

    if not args.apply:
        print("\ndry-run. Повтори с --apply --backup <путь>.")
        return 0
    if not args.backup:
        print("Нужен --backup.")
        return 1
    Path(args.backup).write_text(json.dumps(
        [{"id": l["id"], "client_id": l["client_id"], "birthday": SENTINEL} for l, _ in plan]), encoding="utf-8")
    relinked = kept = 0
    for lead, bd in plan:
        cur.execute("SELECT id FROM clients WHERE surname = %s AND name = %s AND birthday = %s LIMIT 1",
                    (lead["surname"], lead["name"], bd))
        target = cur.fetchone()
        if target:
            cur.execute("UPDATE leads SET birthday = %s, client_id = %s WHERE id = %s", (bd, target["id"], lead["id"]))
            relinked += 1
        else:
            cur.execute("UPDATE leads SET birthday = %s WHERE id = %s", (bd, lead["id"]))
            kept += 1
    conn.commit()
    # то же, что migrations/cleanup_orphan_clients.sql
    cur.execute(
        "DELETE c FROM clients c WHERE c.id <> 0 "
        "AND NOT EXISTS (SELECT 1 FROM leads l WHERE l.client_id = c.id) "
        "AND NOT EXISTS (SELECT 1 FROM results r WHERE r.client_id = c.id)"
    )
    orphans = cur.rowcount
    conn.commit()
    conn.close()
    print(f"Дата восстановлена: {len(plan)} (перепривязано к карточке: {relinked}, без перепривязки: {kept}), "
          f"удалено пустых карточек: {orphans}, бэкап: {args.backup}")
    _recompute_client_lead_dates()
    return 0


if __name__ == "__main__":
    sys.exit(main())
