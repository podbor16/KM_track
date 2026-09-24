#!/usr/bin/env python3
"""
Разовый импорт заявок Забега Икс 2026 (event_name в БД — «Х Трейл») из
CSV-выгрузки Tilda CRM. Вебхук на форме этого старта не подключён, в БД
заявок не было.

Разбор — тот же parse_tilda_export(), что в /admin (дата регистрации —
"Дата оплаты" -> Красноярск, «Забег Икс»/«X Trail» -> «Х Трейл»).
Решения пользователя (2026-09-24):
- 10 км -> 5 км (дистанцию сменили в сентябре 2026);
- заявки без продукта: Хохлов Степан — 2 км, Долгачёвы Мирон и Захар,
  Матвеев Федор — 5 км;
- склеенные ФИО разделены (FIO_FIXES ниже, таблица согласована);
  «Михалёва Маша» -> «Михалёва Мария», «Филин Варвара» — как есть;
- повтор человека на одной дистанции — остаётся последняя заявка.

  python scripts/import_xtrail_2026.py --file x.csv            # dry-run
  python scripts/import_xtrail_2026.py --file x.csv --apply
"""

import argparse
import csv
import io
import sys
from collections import Counter
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from scripts.import_boom_historical import _recompute_client_lead_dates, insert_leads
from src.config import settings
from src.krasmarafon.services.tilda_import_parser import ImportRow, parse_tilda_export, tilda_registered_at
from src.krasmarafon.services.tilda_webhook import convert_birthday, normalize_name

EVENT_NAME, EVENT_YEAR = "Х Трейл", 2026
DISTANCE_REMAP = {"10 км": "5 км"}
# (фамилия, имя) без продукта -> дистанция
EMPTY_PRODUCT_DISTANCE = {
    ("Хохлов", "Степан"): "2 км",
    ("Долгачёв", "Мирон"): "5 км",
    ("Долгачёв", "Захар"): "5 км",
    ("Матвеев", "Федор"): "5 км",
}
# (фамилия, имя) из файла -> (фамилия, имя)
FIO_FIXES = {
    ("Сергей Домборович", "Сергей Домборович"): ("Домборович", "Сергей"),
    ("Сокольников", "Роман С."): ("Сокольников", "Роман"),
    ("Королькова Наталья Сергеевна", "Королькова Наталья Сергеевна"): ("Королькова", "Наталья"),
    ("Жданов", "Жданов Олег Николаевич"): ("Жданов", "Олег"),
    ("Мусиенко", "Мусиенко Владимир"): ("Мусиенко", "Владимир"),
    ("Лексин", "Андрей Лексин"): ("Лексин", "Андрей"),
    ("Дарья Кобзаренко", "Дарья Кобзаренко"): ("Кобзаренко", "Дарья"),
    ("Ирина Ефимова", "Ирина Ефимова"): ("Ефимова", "Ирина"),
    ("Михалëва", "Маша"): ("Михалёва", "Мария"),
    ("Ирина Анисимова", "Ирина Анисимова"): ("Анисимова", "Ирина"),
    ("Федорова", "Светлана Алексеевна Федорова"): ("Федорова", "Светлана"),
    ("Рудницкий", "Эдвард Рудницкий"): ("Рудницкий", "Эдвард"),
    ("Лавренов Антон Иванович", "Лавренов Антон Иванович"): ("Лавренов", "Антон"),
    ("Филин", "Филин Варвара"): ("Филин", "Варвара"),
    ("Крысанов", "Алексей К."): ("Крысанов", "Алексей"),
    ("Моисеева", "Алëна"): ("Моисеева", "Алёна"),
    ("Прокопьева", "Ксения Прокопьева"): ("Прокопьева", "Ксения"),
    ("Анатолий Александрович Федоров", "Анатолий Александрович Федоров"): ("Федоров", "Анатолий"),
    ("Евгения Васильева", "Евгения"): ("Васильева", "Евгения"),
    ("Тилин", "Дмитрий Тилин"): ("Тилин", "Дмитрий"),
    ("Сергей Коваленко", "Сергей Коваленко"): ("Коваленко", "Сергей"),
    ("Золотарeв", "Павел"): ("Золотарев", "Павел"),
    ("Софья Дмитриевна Юрченко", "Софья Дмитриевна Юрченко"): ("Юрченко", "Софья"),
    ("Камиля Абдрахманова", "Камиля Абдрахманова"): ("Абдрахманова", "Камиля"),
    ("Рязанцев", "Ирина Рязанцева"): ("Рязанцева", "Ирина"),
    ("Артем Аничкин", "Артем Аничкин"): ("Аничкин", "Артем"),
}


def empty_product_rows(data: bytes, failed_rows) -> list:
    """Строки без продукта (парсер их отбрасывает) — собираем из исходных
    колонок теми же функциями, что и parse_tilda_export(), с согласованной
    дистанцией."""
    table = list(csv.reader(io.StringIO(data.decode("utf-8-sig")), delimiter=";"))
    hdr = [h.strip().lower() for h in table[0]]
    out = []
    for f in failed_rows:
        raw = dict(zip(hdr, table[f["row_number"] - 1]))
        surname, name = normalize_name(raw["surname"].strip()), normalize_name(raw["name"].strip())
        dist = EMPTY_PRODUCT_DISTANCE.get((surname, name))
        if not dist:
            continue
        out.append(ImportRow(
            row_number=f["row_number"], surname=surname, name=name,
            birthday=convert_birthday(raw["birthday"].strip()),
            event_name=EVENT_NAME, event_year=EVENT_YEAR, event_distance=dist,
            sex=raw["sex"].strip(), city=raw["city"].strip(), club=raw["club"].strip(),
            email=raw["email"].strip(), phone=raw["phone"].strip(),
            amount=raw["сумма заказа"].strip(), promocode=raw["промокод"].strip(),
            discount=raw["сумма скидки"].strip(),
            registered_at=tilda_registered_at(raw.get("дата оплаты"), raw.get("date")),
        ))
    return out


def build_rows(path):
    data = Path(path).read_bytes()
    res = parse_tilda_export(data, filename="x.csv")
    extra = empty_product_rows(data, res.failed_rows)
    stats = Counter(total=res.total_rows, parse_errors=len(res.errors), empty_product_filled=len(extra))
    rows = []
    for r in res.rows + extra:
        fix = FIO_FIXES.get((r.surname, r.name))
        if fix:
            r.surname, r.name = fix
            r.is_name_suspicious = False
            stats["fio_fixed"] += 1
        if r.event_distance in DISTANCE_REMAP:
            r.event_distance = DISTANCE_REMAP[r.event_distance]
            stats["distance_10_to_5"] += 1
        stats[f"event:{r.event_name}"] += 1
        rows.append({
            "row_idx": r.row_number, "surname": r.surname, "name": r.name, "sex": r.sex,
            "city": r.city, "club": r.club or None, "birthday": r.birthday or "1900-01-01",
            "phone": r.phone or None, "email": r.email or "example@mail.ru",
            "event_name": r.event_name, "event_distance": r.event_distance, "event_year": r.event_year,
            "amount": float(r.amount or 0), "promocode": r.promocode,
            "discount": float(r.discount or 0), "registered_at": r.registered_at,
            "is_name_suspicious": int(r.is_name_suspicious),
        })
    # повтор человека на одной дистанции — остаётся последняя заявка
    latest = {}
    for r in sorted(rows, key=lambda r: r["registered_at"]):
        latest[(r["surname"].lower(), r["name"].lower(), r["birthday"], r["event_distance"])] = r
    stats["dedup_removed"] = len(rows) - len(latest)
    return list(latest.values()), res, stats


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--file", required=True)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    rows, res, stats = build_rows(args.file)
    for k in sorted(stats):
        print(f"  {k}: {stats[k]}")
    print(f"  ошибки разбора (строки без продукта восстановлены отдельно): {res.errors}")
    print(f"К импорту: {len(rows)}", dict(Counter((r["event_name"], r["event_year"], r["event_distance"]) for r in rows)))
    print(f"  подозрительных ФИО осталось: {sum(r['is_name_suspicious'] for r in rows)}")
    print(f"  даты регистрации (Красноярск): {min(r['registered_at'] for r in rows)} .. {max(r['registered_at'] for r in rows)}")
    bad = [r for r in rows if (r["event_name"], r["event_year"]) != (EVENT_NAME, EVENT_YEAR) or r["event_distance"] not in ("5 км", "2 км")]
    if bad:
        print(f"СТОП: {len(bad)} строк вне «{EVENT_NAME} {EVENT_YEAR}» 5/2 км")
        return 1
    if not args.apply:
        print("dry-run. Повтори с --apply.")
        return 0
    inserted, skipped, errors = insert_leads(rows, settings.DB_TIME_ZONE)
    if inserted is None:
        return 1
    print(f"Вставлено: {inserted}, пропущено (уже есть): {skipped}, ошибок: {errors}")
    _recompute_client_lead_dates()
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
