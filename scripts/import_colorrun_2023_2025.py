#!/usr/bin/env python3
"""
Импорт заявок Красочного забега 2023–2025 из Google xlsx (2026-09-26, по
аналогии с Ночным забегом и Весной).

Листы:
- «2023», «2024» — регистрации (старая выгрузка Tilda: product, Total amount,
  sent в UTC); «LeadsFromTilda» — то же для 2025 (источник «пачки» в БД);
- «Стартовый 2023/2024/2025» — итоговые стартовые списки (номер, ФИО,
  дистанция).

Правила (решения пользователя по Ночному забегу и Весне):
- дата — sent; у строк без неё — дата ближайшей строки выше; дубли человека
  на дистанции — самая ранняя заявка;
- 2023, 2024 — в БД заявок нет, вставляются все регистрации + участники
  стартового листа, которых нет среди регистраций (дата — последняя
  регистрация года, сумма 0);
- 2025 — в БД заявки вебхука и «пачка» (--batch-from/--batch-to, UTC):
  строкам пачки — дата и сумма из LeadsFromTilda; участники стартового
  списка, которых нет в БД, — с датой последней регистрации года (максимум
  по файлу и по заявкам вебхука в БД);
- стартовые номера из стартовых листов пишутся во все заявки.

  python scripts/import_colorrun_2023_2025.py --google-xlsx …                      # dry-run
  python scripts/import_colorrun_2023_2025.py --google-xlsx … --apply --backup /root/backups/x.json
"""

import argparse
import datetime
import json
import sys
from collections import Counter
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import openpyxl

from scripts.import_boom_historical import _recompute_client_lead_dates, dedupe, get_connection, insert_leads
from scripts.import_tilda_google_registrations import (
    UTC, _contact_key, _fio_key, _key, apply_updates, load_db_leads, merge_year, parse_google_sheet,
    parse_start_list, plan,
)

EVENT = "Красочный забег"
REG_SHEETS = {2023: "2023", 2024: "2024", 2025: "LeadsFromTilda"}
START_SHEETS = {2023: "Стартовый 2023", 2024: "Стартовый 2024", 2025: "Стартовый 2025"}


def attach_bibs(rows, start_rows, stats, year):
    """Номер из стартового листа — в регистрации того же человека/дистанции;
    участники стартового листа без регистрации возвращаются отдельно."""
    idx = {}
    for r in rows:
        for k in (_key(r), _fio_key(r), _contact_key(r)):
            if k:
                idx.setdefault(k, []).append(r)
    extra = []
    for s in start_rows:
        match = next((idx[k] for k in (_key(s), _fio_key(s), _contact_key(s)) if k and k in idx), None)
        if match:
            for r in match:
                r["start_number"] = s["start_number"]
        else:
            extra.append(s)
    stats[f"{year}: в стартовом листе без регистрации"] = len(extra)
    return extra


def main(event=EVENT, reg_sheets=REG_SHEETS, start_sheets=START_SHEETS,
         batch=("2025-01-17 18:09:00", "2025-01-17 18:15:00"), doc=__doc__, drop=lambda r: False):
    """Общий ход для стартов «регистрации по годам + стартовые листы» (листа
    стартового списка у года может не быть)."""
    ap = argparse.ArgumentParser(description=doc, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--google-xlsx", required=True)
    ap.add_argument("--batch-from", default=batch[0], help="начало «пачки» 2025 в БД, UTC")
    ap.add_argument("--batch-to", default=batch[1], help="конец «пачки» 2025 в БД, UTC")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--backup")
    args = ap.parse_args()
    b_from, b_to = (datetime.datetime.strptime(v, "%Y-%m-%d %H:%M:%S") for v in (args.batch_from, args.batch_to))

    wb = openpyxl.load_workbook(args.google_xlsx, data_only=True, read_only=True)
    conn = get_connection(UTC)
    by_key, by_fio, by_contact = load_db_leads(conn, event, list(reg_sheets))
    db_last = {}
    for lst in by_key.values():
        for db in lst:
            db_last[db["event_year"]] = max(db_last.get(db["event_year"], db["created_at"]), db["created_at"])
    stats, rows_by_year, extras = Counter(), {}, []
    for year, sheet in reg_sheets.items():
        regs, skipped = parse_google_sheet(wb[sheet], event, year)
        stats[f"{year}: регистраций"] = len(regs)
        stats[f"{year}: пропущено строк регистраций"] = skipped
        stats[f"{year}: исключено вручную"] = sum(map(drop, regs))
        regs = [r for r in regs if not drop(r)]
        for r in regs:
            r["own_date"] = r["registered_at"] is not None
        regs = merge_year(regs, [], stats)                  # даты соседних строк
        regs, dup = dedupe(sorted(regs, key=lambda r: r["registered_at"] or datetime.datetime.min))
        stats[f"{year}: дублей убрано"] = dup
        # последний день регистрации года — по файлу и по заявкам вебхука в БД
        last_reg = max([r["registered_at"] for r in regs if r["registered_at"]] + ([db_last[year]] if year in db_last else []))
        start = parse_start_list(wb[start_sheets[year]], event, year, stats) if year in start_sheets else []
        for s in attach_bibs(regs, start, stats, year):
            s["registered_at"], s["amount"] = last_reg, 0.0
            extras.append(s)
        stats[f"{year}: последняя регистрация (UTC)"] = str(last_reg)
        rows_by_year[year] = regs

    try:
        in_batch = lambda db: db["event_year"] == 2025 and b_from <= db["created_at"] < b_to
        to_insert, to_update, suspicious = plan(
            [r for y in reg_sheets for r in rows_by_year[y]], by_key, by_fio, by_contact, in_batch)
        # участники стартовых листов без регистрации — только вставка, если их
        # нет в БД; даты существующих заявок они не меняют
        extra_insert, _, extra_known = plan(extras, by_key, by_fio, by_contact, lambda db: False)
        stats["стартовый лист: новых для вставки"] = len(extra_insert)
        stats["стартовый лист: тот же человек в БД под другими ДР/ФИО"] = len(extra_known)
        to_insert += extra_insert
        batch_total = sum(1 for lst in by_key.values() for db in lst if in_batch(db))
        # сколько строк пачки получат дату из самого файла, а не от соседней строки
        own = {db["id"] for r in rows_by_year.get(2025, []) if r["own_date"]
               for db in (by_key.get(_key(r)) or by_fio.get(_fio_key(r)) or by_contact.get(_contact_key(r)) or [])
               if in_batch(db)}
        bib_updates = []
        for r in rows_by_year.get(2025, []) + [e for e in extras if e["event_year"] == 2025]:
            if not r.get("start_number"):
                continue
            existing = by_key.get(_key(r)) or by_fio.get(_fio_key(r)) or by_contact.get(_contact_key(r)) or []
            bib_updates += [(db["id"], r["start_number"]) for db in existing]

        for k in sorted(stats):
            print(f"  {k}: {stats[k]}")
        print("К вставке:", dict(Counter((r["event_year"], r["event_distance"]) for r in to_insert)),
              "| со стартовым номером:", sum(1 for r in to_insert if r.get("start_number")))
        print(f"Пачка 2025: {batch_total}, исправить дату/сумму: {len(to_update)} (дата из файла: {len(own)}), "
              f"без пары в файле: {batch_total - len(to_update)}")
        print(f"Тот же человек в БД под другими ДР/ФИО (не вставлены): {len(suspicious)}")
        print(f"Номер в существующие заявки 2025: {len(bib_updates)}")
        if not args.apply:
            print("\ndry-run. Повтори с --apply --backup <путь>.")
            return 0
        if not args.backup:
            print("Нужен --backup.")
            return 1
        cur = conn.cursor(dictionary=True)
        ids = sorted({i for i, _ in bib_updates} | {db["id"] for db, _, _ in to_update})
        if ids:
            cur.execute(f"SELECT id, created_at, amount, start_number FROM leads WHERE id IN ({','.join(map(str, ids))})")
            Path(args.backup).write_text(json.dumps(cur.fetchall(), default=str), encoding="utf-8")
        cur.executemany("UPDATE leads SET start_number = %s WHERE id = %s", [(b, i) for i, b in bib_updates])
        conn.commit()
        if to_update:
            apply_updates(conn, to_update, args.backup + ".dates.tsv")
    finally:
        conn.close()
    inserted, skipped, errors = insert_leads(to_insert, UTC)
    if inserted is None:
        return 1
    print(f"Исправлено строк пачки: {len(to_update)}, номер записан: {len(bib_updates)}, вставлено: {inserted}, "
          f"пропущено: {skipped}, ошибок: {errors}")
    _recompute_client_lead_dates()
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
