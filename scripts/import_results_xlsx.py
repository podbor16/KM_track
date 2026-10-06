#!/usr/bin/env python3
"""
Импорт результатов прошедшего старта из выгрузки Copernico в xlsx
(2026-09-26, первым — Х Трейл 2025, 10 км). Нужны трекеру следующего года:
личный темп и средний темп категорий (results_service — исторический кеш).

Колонки: Bib, Surname, Name, Date of Birth (дд/мм/гггг), Status, Start,
[Gender (Male/Female) — иначе пол из категории], [Category], время финиша. Колонок финиша в выгрузках бывает
несколько с одинаковым названием («Finish» — чистое / официальное / темп): время
определяется по содержимому (чч:мм:сс, темп «3'14"/km» отбрасывается), чистое —
колонка со словом «чист», иначе меньшая из двух; чистое > официального хоть у
одного — ошибка. Гандикап (Снежная семёрка): Start — задержка волны, официальное —
от первого выстрела (порядок прихода = места).
Промежуточные отметки не загружаются — дистанции КТ неизвестны.
Протоколы «по группам» (Жара 2025): строки-заголовки групп пропускаются, Start
необязателен, категории «Мужчины 1986−1990 г. р.» / «Мальчики 2014 г.р.» → краткий
вид как в 2026 («М35-39» — возраст в год старта). Элита (src/analytics/elite.py) —
в Bib «Элита» или фамилия (именной номер, Жара 2025): служебный номер как у замыкающих
в загрузчике (максимальный номер + 1000…), на сайте «Элита», диплом — по этому номеру.
Числовой номер вне основных диапазонов Жары 21,1 км («Присвоить номера») — тоже элита.
Места считаются заново: абсолютное/пол/категория по времени выстрела и по
чистому времени. client_id подставляет trg_results_before_insert.

  python scripts/import_results_xlsx.py --event-id 95 --xlsx …            # dry-run
  python scripts/import_results_xlsx.py --event-id 95 --xlsx … --apply
"""

import argparse
import collections
import datetime
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent.parent))

import openpyxl

from scripts.import_boom_historical import get_connection
from src.analytics.elite import distance_label, is_elite, main_ranges
from src.common.names import normalize_person_name

SENTINEL = "1900-01-01"
SEX = {"Male": "Мужчина", "Female": "Женщина"}
SERVICE_NUMBER_OFFSET = 1000                         # как SWEEPER_NUMBER_OFFSET в load_race_results.py
_GROUP = re.compile(r"^\s*(мужчины|юноши|мальчики|женщины|девушки|девочки)\W*(\d{4})(?:\s*[-−–]\s*(\d{4}))?", re.I)
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


def finish_columns(h, rows):
    """-> (чистое, официальное) — индексы колонок времени финиша (см. docstring модуля)."""
    low = [x.lower().replace('"', "").replace("«", "").replace("»", "") for x in h]
    cand = [k for k, x in enumerate(low) if x.startswith("finish") or "чист" in x]
    timed = [k for k in cand if (vals := [r[k] for r in rows if len(r) > k and r[k] not in (None, "")])
             and sum(_secs(v) is not None for v in vals) >= 0.9 * len(vals)]
    if not timed or len(timed) > 2:
        raise ValueError(f"не удалось определить колонки финиша: {[h[k] for k in cand]}")
    if len(timed) == 1:
        return timed[0], timed[0]
    a, b = timed
    named = [k for k in timed if "чист" in low[k]]
    if named:
        clean = named[0]
    else:
        pairs = [(_secs(r[a]), _secs(r[b])) for r in rows if _secs(r[a]) and _secs(r[b])]
        clean = a if sum(x for x, _ in pairs) <= sum(y for _, y in pairs) else b
    gun = b if clean == a else a
    bad = sum(1 for r in rows if _secs(r[clean]) and _secs(r[gun]) and _secs(r[clean]) > _secs(r[gun]))
    if bad:
        raise ValueError(f"чистое время больше официального у {bad} строк: «{h[clean]}» / «{h[gun]}»")
    return clean, gun


def short_category(category, year):
    """«Мужчины 1986−1990 г. р.» → «М35-39» (возраст в год старта); одиночный год —
    «Мальчики 2014 г.р.» → «М11». Остальное — как есть."""
    m = _GROUP.match(category or "")
    if not m:
        return category
    sex = "М" if m.group(1).lower() in ("мужчины", "юноши", "мальчики") else "Ж"
    y1, y2 = int(m.group(2)), int(m.group(3) or m.group(2))
    young, old = year - max(y1, y2), year - min(y1, y2)
    return f"{sex}{young}" if young == old else f"{sex}{young}-{old}"


def parse(path, year):
    ws = openpyxl.load_workbook(path, read_only=True, data_only=True).active
    rows = list(ws.iter_rows(values_only=True))
    h = [str(x or "").strip() for x in rows[0]]
    i = {k: h.index(k) for k in ("Bib", "Surname", "Name", "Date of Birth", "Status")}
    start_i = h.index("Start") if "Start" in h else None
    sex_i = h.index("Gender") if "Gender" in h else None
    i["clean"], i["Finish"] = finish_columns(h, rows[1:])
    cat_i = h.index("Category") if "Category" in h else None
    out = []
    for r in rows[1:]:
        if not r or not r[i["Surname"]]:                               # пусто / заголовок группы
            continue
        bib = str(r[i["Bib"]] or "").strip()
        category = short_category(str(r[cat_i] or "").strip(), year) if cat_i is not None else ""
        sex = SEX.get(str(r[sex_i] or "").strip(), "") if sex_i is not None else ""
        if not sex and category[:1].upper() in "МЖ":                   # нет Gender — пол из категории
            sex = "Мужчина" if category[:1].upper() == "М" else "Женщина"
        status = STATUS.get(str(r[i["Status"]] or "").strip(), str(r[i["Status"]] or "").strip())
        clean, gun = _secs(r[i["clean"]]), _secs(r[i["Finish"]])
        finished = status == "Finished" and clean and gun
        out.append({
            "surname": normalize_person_name(str(r[i["Surname"]])), "name": normalize_person_name(str(r[i["Name"]] or "")),
            "birthday": _birthday(r[i["Date of Birth"]]), "sex": sex,
            "bib": bib, "start_number": int(bib) if bib.isdigit() else None,
            "category": category,
            "race_status": status, "start": _secs(r[start_i]) if start_i is not None else None,
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

    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT event_name, event_year, event_distance FROM events WHERE id = %s", (args.event_id,))
        ev = cur.fetchone()
        if not ev:
            print(f"Нет события {args.event_id}")
            return 1
        rows = parse(args.xlsx, int(ev[1]))
        ranges = main_ranges(cur, ev[0], distance_label(ev[2]))
        next_service = max([r["start_number"] for r in rows if r["start_number"]] or [0]) + SERVICE_NUMBER_OFFSET
        for r in rows:
            r["is_elite"] = int(is_elite(r["bib"], ranges, r["surname"]))
            if r["start_number"] is None:               # именной номер / «Элита» — служебный номер
                r["start_number"], next_service = next_service, next_service + 1
        rank(rows)
        bibs = collections.Counter(r["start_number"] for r in rows)
        dup = [b for b, k in bibs.items() if k > 1]
        print(f"Строк: {len(rows)}, по статусам: {dict(collections.Counter(r['race_status'] for r in rows))}, "
              f"без даты рождения: {sum(r['birthday'] == SENTINEL for r in rows)}, без пола: {sum(not r['sex'] for r in rows)}, "
              f"элита: {sum(r['is_elite'] for r in rows)} (основные диапазоны: {ranges or 'не заданы'}), "
              f"текст вместо номера не-элиты: {[r['bib'] for r in rows if not r['bib'].isdigit() and not r['is_elite']]}, "
              f"повторы номеров: {dup}")
        print("Категории:", dict(sorted(collections.Counter(r["category"] for r in rows).items())))
        if dup:
            return 1
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
                   finish_pace_avg_clean, time_gun_finish_ms, time_clear_finish_ms, is_elite)
               VALUES (%s, %s, %s, 0, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            [(r["surname"], r["name"], r["birthday"], args.event_id, r["sex"], r["start_number"], r["category"],
              r["race_status"], _hms(r["start"]), _hms(r["gun"]), _hms(r["clean"]), r.get("rank_absolute"),
              r.get("rank_sex"), r.get("rank_category"), r.get("rank_absolute_clean"), r.get("rank_sex_clean"),
              r.get("rank_category_clean"), pace(r["gun"]), pace(r["clean"]),
              r["gun"] * 1000 if r["gun"] else None, r["clean"] * 1000 if r["clean"] else None,
              r["is_elite"]) for r in rows])
        conn.commit()
        cur.execute("SELECT COUNT(*), SUM(client_id = 0), SUM(race_status = 'Finished') FROM results WHERE event_id = %s",
                    (args.event_id,))
        print("Загружено (всего, без клиента, финишировали):", cur.fetchone())
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
