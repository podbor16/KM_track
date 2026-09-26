#!/usr/bin/env python3
"""
Импорт результатов прошедшего старта из выгрузки Copernico в xlsx
(2026-09-26, первым — Х Трейл 2025, 10 км). Нужны трекеру следующего года:
личный темп и средний темп категорий (results_service — исторический кеш).

Колонки: #, Bib, Tag, Surname, Name, Club, Phone, Date of Birth (дд/мм/гггг),
Gender (Male/Female), Category, Status, Start, Finish, чистое время («Finish чистое» или
«чистое»). Гандикап (Снежная семёрка): Start — задержка волны, Finish — от первого
выстрела (порядок прихода = места), «чистое» — своё время бега.
Промежуточная отметка kt2 не загружается — дистанция КТ неизвестна.
Места считаются заново: абсолютное/пол/категория по времени выстрела и по
чистому времени. client_id подставляет trg_results_before_insert.

  python scripts/import_results_xlsx.py --event-id 95 --xlsx …            # dry-run
  python scripts/import_results_xlsx.py --event-id 95 --xlsx … --apply
"""

import argparse
import collections
import datetime
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent.parent))

import openpyxl

from scripts.import_boom_historical import get_connection

SENTINEL = "1900-01-01"
SEX = {"Male": "Мужчина", "Female": "Женщина"}
STATUS = {"Disqualified": "DSQ"}                     # как в остальных результатах БД


def _secs(v):
    if isinstance(v, datetime.time):
        return v.hour * 3600 + v.minute * 60 + v.second
    if isinstance(v, datetime.timedelta):
        return int(v.total_seconds())
    try:
        h, m, s = (int(x) for x in str(v).strip().split(":"))
        return h * 3600 + m * 60 + s
    except (TypeError, ValueError):
        return None


def _birthday(v):
    if isinstance(v, datetime.datetime):
        return v.date().isoformat()
    try:
        return datetime.datetime.strptime(str(v).strip(), "%d/%m/%Y").date().isoformat()
    except ValueError:
        return SENTINEL


def _hms(s):
    return None if s is None else f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def parse(path):
    ws = openpyxl.load_workbook(path, read_only=True, data_only=True).active
    rows = list(ws.iter_rows(values_only=True))
    h = [str(x or "").strip() for x in rows[0]]
    i = {k: h.index(k) for k in ("Bib", "Surname", "Name", "Date of Birth", "Gender", "Category", "Status",
                                 "Start", "Finish")}
    i["clean"] = next(h.index(k) for k in ("Finish чистое", "чистое") if k in h)
    out = []
    for r in rows[1:]:
        if not r or not r[i["Surname"]] or not str(r[i["Bib"]] or "").strip().isdigit():
            continue
        status = STATUS.get(str(r[i["Status"]] or "").strip(), str(r[i["Status"]] or "").strip())
        clean, gun = _secs(r[i["clean"]]), _secs(r[i["Finish"]])
        finished = status == "Finished" and clean and gun
        out.append({
            "surname": str(r[i["Surname"]]).strip(), "name": str(r[i["Name"]] or "").strip(),
            "birthday": _birthday(r[i["Date of Birth"]]), "sex": SEX.get(str(r[i["Gender"]] or "").strip(), ""),
            "start_number": int(r[i["Bib"]]), "category": str(r[i["Category"]] or "").strip(),
            "race_status": status, "start": _secs(r[i["Start"]]),
            "gun": gun if finished else None, "clean": clean if finished else None,
        })
    return out


def rank(rows):
    fin = [r for r in rows if r["gun"]]
    for field, suffix in (("gun", ""), ("clean", "_clean")):
        order = sorted(fin, key=lambda r: (r[field], r["start_number"]))
        by_sex, by_cat = collections.Counter(), collections.Counter()
        for n, r in enumerate(order, 1):
            by_sex[r["sex"]] += 1
            by_cat[r["category"]] += 1
            r["rank_absolute" + suffix], r["rank_sex" + suffix], r["rank_category" + suffix] = n, by_sex[r["sex"]], by_cat[r["category"]]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--xlsx", required=True)
    ap.add_argument("--event-id", type=int, required=True, help="событие в БД (дистанция берётся из events)")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    rows = parse(args.xlsx)
    rank(rows)
    bibs = collections.Counter(r["start_number"] for r in rows)
    dup = [b for b, k in bibs.items() if k > 1]
    print(f"Строк: {len(rows)}, по статусам: {dict(collections.Counter(r['race_status'] for r in rows))}, "
          f"без даты рождения: {sum(r['birthday'] == SENTINEL for r in rows)}, без пола: {sum(not r['sex'] for r in rows)}, "
          f"повторы номеров: {dup}")
    if dup:
        return 1
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT event_name, event_year, event_distance FROM events WHERE id = %s", (args.event_id,))
        ev = cur.fetchone()
        cur.execute("SELECT COUNT(*) FROM results WHERE event_id = %s", (args.event_id,))
        existing = cur.fetchone()[0]
        print(f"Событие {args.event_id}: {ev}, результатов в БД: {existing}")
        if not ev or not ev[2] or existing:
            print("Нет события, нет дистанции или результаты уже есть — не загружаю.")
            return 1
        distance_km = float(ev[2])
        if not args.apply:
            print("\ndry-run. Повтори с --apply.")
            return 0
        pace = lambda s: _hms(round(s / distance_km)) if s else None
        cur.executemany(
            """INSERT INTO results (surname, name, birthday, client_id, event_id, sex, start_number, category,
                   race_status, time_gun_start, time_gun_finish, time_clear_finish, rank_absolute, rank_sex,
                   rank_category, rank_absolute_clean, rank_sex_clean, rank_category_clean, finish_pace_avg_gun,
                   finish_pace_avg_clean, time_gun_finish_ms, time_clear_finish_ms)
               VALUES (%s, %s, %s, 0, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            [(r["surname"], r["name"], r["birthday"], args.event_id, r["sex"], r["start_number"], r["category"],
              r["race_status"], _hms(r["start"]), _hms(r["gun"]), _hms(r["clean"]), r.get("rank_absolute"),
              r.get("rank_sex"), r.get("rank_category"), r.get("rank_absolute_clean"), r.get("rank_sex_clean"),
              r.get("rank_category_clean"), pace(r["gun"]), pace(r["clean"]),
              r["gun"] * 1000 if r["gun"] else None, r["clean"] * 1000 if r["clean"] else None) for r in rows])
        conn.commit()
        cur.execute("SELECT COUNT(*), SUM(client_id = 0), SUM(race_status = 'Finished') FROM results WHERE event_id = %s",
                    (args.event_id,))
        print("Загружено (всего, без клиента, финишировали):", cur.fetchone())
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
