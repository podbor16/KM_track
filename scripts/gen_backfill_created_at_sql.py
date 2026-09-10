#!/usr/bin/env python3
"""
Генератор .sql-файла для бэкфилла leads.created_at из колонки "Date" выгрузок
Tilda — для случая, когда прямого доступа к БД из окружения нет, но есть
SQL-клиент.

Контекст: bulk_import_leads() до 2026-09 не заполнял created_at при INSERT →
DEFAULT CURRENT_TIMESTAMP = момент импорта, а не регистрации. Ломало чарты
динамики регистраций в DataLens. Парсер теперь читает "Date"; этот скрипт
чинит уже загруженные данные.

Что делает: разбирает файл(ы) выгрузки локально (только парсер, БД не нужна) и
пишет .sql, который:
  1. создаёт временную таблицу с (order_id, ФИО, ДР, событие, дата подачи)
  2. показывает распределение created_at по месяцам ДО
  3. UPDATE ... LEAST(created_at, дата_из_файла) — матчинг как в импорте:
     сначала по order_id, потом по surname+name+birthday+событие
  4. показывает распределение ПОСЛЕ
  5. удаляет временную таблицу
Всё в одной транзакции — в конце COMMIT (при желании замени на ROLLBACK и
прогони ещё раз, посмотрев цифры). LEAST только уменьшает дату; DELETE нет.

Использование:
  python scripts/gen_backfill_created_at_sql.py <файлы|папки> -o backfill_created_at.sql
"""

import argparse
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.krasmarafon.services.tilda_import_parser import (  # noqa: E402
    parse_tilda_export,
    parse_tilda_datetime,
)

_EXPORT_EXTS = (".csv", ".xlsx", ".xls")
_BIRTHDAY_SENTINEL = "1900-01-01"  # тот же, что в bulk_import_leads()/_find_lead_matches


def _collect_files(paths):
    out = []
    for p in paths:
        path = Path(p)
        if path.is_dir():
            out.extend(sorted(f for f in path.iterdir() if f.suffix.lower() in _EXPORT_EXTS))
        elif path.is_file():
            out.append(path)
        else:
            print(f"  ! не найден: {p}", file=sys.stderr)
    return out


def _sql_str(v: str) -> str:
    return "'" + str(v).replace("\\", "\\\\").replace("'", "''") + "'"


def _collect_rows(files, min_per_event: int):
    """[(order_id|None, surname, name, birthday, event_name, event_year,
    event_distance, 'YYYY-MM-DD HH:MM:SS')] — по всем файлам, только строки с
    распарсенной датой. Группы (event_name, event_year) с числом строк меньше
    min_per_event отбрасываются как вероятный шум разбора product-блоба
    (напр. 1 строка «Весна 2026» в выгрузке Жары)."""
    rows = []
    for f in files:
        result = parse_tilda_export(f.read_bytes(), filename=f.name)
        used = 0
        for r in result.rows:
            dt = parse_tilda_datetime(r.registered_at)
            if dt is None:
                continue
            oid = None
            oid_raw = (r.order_id or "").strip()
            if oid_raw.isdigit() and oid_raw != "0":
                oid = int(oid_raw)
            rows.append((
                oid, r.surname, r.name, r.birthday or _BIRTHDAY_SENTINEL,
                r.event_name, r.event_year, r.event_distance,
                dt.strftime("%Y-%m-%d %H:%M:%S"),
            ))
            used += 1
        print(f"  {f.name}: {used} строк с датой (из {len(result.rows)} разобранных, "
              f"{len(result.failed_rows)} не разобрано)", file=sys.stderr)

    from collections import Counter
    ev_counts = Counter((n, y) for _, _, _, _, n, y, _, _ in rows)
    dropped = {ev for ev, c in ev_counts.items() if c < min_per_event}
    if dropped:
        for ev in sorted(dropped, key=str):
            print(f"  ! отброшено: {ev[0]} {ev[1]} — {ev_counts[ev]} строк "
                  f"(< {min_per_event}, вероятно шум разбора)", file=sys.stderr)
        rows = [r for r in rows if (r[4], r[5]) not in dropped]
    return rows


def _emit_sql(rows) -> str:
    events = sorted({(n, y) for _, _, _, _, n, y, _, _ in rows if y is not None})
    ev_names = sorted({n for n, _ in events})
    ev_years = sorted({y for _, y in events})
    names_in = ", ".join(_sql_str(n) for n in ev_names)
    years_in = ", ".join(str(y) for y in ev_years)

    L = []
    L.append("-- Бэкфилл leads.created_at из колонки \"Date\" выгрузок Tilda.")
    L.append("-- Сгенерировано scripts/gen_backfill_created_at_sql.py")
    L.append(f"-- События в наборе: {', '.join(f'{n} {y}' for n, y in events)}")
    L.append(f"-- Строк с датой: {len(rows)}")
    L.append("-- LEAST(created_at, дата_из_файла) — дату только уменьшает; строки не трогает.")
    L.append("")
    L.append("START TRANSACTION;")
    L.append("")
    L.append("DROP TEMPORARY TABLE IF EXISTS _tilda_reg;")
    L.append("CREATE TEMPORARY TABLE _tilda_reg (")
    L.append("  order_id       BIGINT NULL,")
    L.append("  surname        VARCHAR(255),")
    L.append("  name           VARCHAR(255),")
    L.append("  birthday       DATE,")
    L.append("  event_name     VARCHAR(255),")
    L.append("  event_year     INT,")
    L.append("  event_distance VARCHAR(255),")
    L.append("  registered_at  DATETIME,")
    # префиксные индексы — полный композит из 6 VARCHAR(255) превысил бы лимит
    # длины ключа MySQL; для таблицы в тысячи строк этого с запасом хватает
    L.append("  KEY k_oid (order_id),")
    L.append("  KEY k_name (birthday, surname(40), name(40))")
    L.append(");")
    L.append("")

    CHUNK = 500
    for i in range(0, len(rows), CHUNK):
        chunk = rows[i:i + CHUNK]
        L.append("INSERT INTO _tilda_reg (order_id, surname, name, birthday, "
                 "event_name, event_year, event_distance, registered_at) VALUES")
        vals = []
        for oid, sn, nm, bd, en, ey, ed, ra in chunk:
            vals.append(
                f"  ({'NULL' if oid is None else oid}, {_sql_str(sn)}, {_sql_str(nm)}, "
                f"{_sql_str(bd)}, {_sql_str(en)}, {ey if ey is not None else 'NULL'}, "
                f"{_sql_str(ed)}, {_sql_str(ra)})"
            )
        L.append(",\n".join(vals) + ";")
        L.append("")

    L.append("-- === РАСПРЕДЕЛЕНИЕ created_at ПО МЕСЯЦАМ — ДО ===")
    L.append(f"SELECT DATE_FORMAT(created_at, '%Y-%m') AS month, COUNT(*) AS cnt")
    L.append(f"FROM leads WHERE event_name IN ({names_in}) AND event_year IN ({years_in})")
    L.append("GROUP BY month ORDER BY month;")
    L.append("")

    L.append("-- === UPDATE 1: матч по order_id (переживает правку ФИО в Tilda) ===")
    L.append("UPDATE leads l")
    L.append("JOIN _tilda_reg t")
    L.append("  ON t.order_id IS NOT NULL AND l.order_id = t.order_id")
    L.append("  AND l.event_name = t.event_name AND l.event_year = t.event_year")
    L.append("  AND l.event_distance = t.event_distance")
    L.append("SET l.created_at = LEAST(l.created_at, t.registered_at)")
    L.append("WHERE t.registered_at < l.created_at;")
    L.append("")

    L.append("-- === UPDATE 2: фоллбэк по ФИО+ДР+событие (заявки без order_id) ===")
    L.append("UPDATE leads l")
    L.append("JOIN _tilda_reg t")
    L.append("  ON l.surname = t.surname AND l.name = t.name AND l.birthday = t.birthday")
    L.append("  AND l.event_name = t.event_name AND l.event_year = t.event_year")
    L.append("  AND l.event_distance = t.event_distance")
    L.append("SET l.created_at = LEAST(l.created_at, t.registered_at)")
    L.append("WHERE t.registered_at < l.created_at;")
    L.append("")

    L.append("-- === РАСПРЕДЕЛЕНИЕ created_at ПО МЕСЯЦАМ — ПОСЛЕ ===")
    L.append(f"SELECT DATE_FORMAT(created_at, '%Y-%m') AS month, COUNT(*) AS cnt")
    L.append(f"FROM leads WHERE event_name IN ({names_in}) AND event_year IN ({years_in})")
    L.append("GROUP BY month ORDER BY month;")
    L.append("")

    L.append("DROP TEMPORARY TABLE IF EXISTS _tilda_reg;")
    L.append("")
    L.append("-- Цифры ПОСЛЕ устраивают? -> COMMIT;  иначе -> ROLLBACK;")
    L.append("COMMIT;")
    L.append("")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+", help="файлы выгрузок Tilda или папки с ними")
    ap.add_argument("-o", "--out", default="backfill_created_at.sql",
                    help="куда писать .sql (по умолчанию ./backfill_created_at.sql)")
    ap.add_argument("--min-per-event", type=int, default=5,
                    help="отбросить группы (событие, год) с числом строк меньше "
                         "этого (шум разбора product); по умолчанию 5")
    args = ap.parse_args()

    files = _collect_files(args.paths)
    if not files:
        print("Файлы не найдены.", file=sys.stderr)
        return 1
    print(f"Файлов: {len(files)}", file=sys.stderr)

    rows = _collect_rows(files, args.min_per_event)
    if not rows:
        print("Ни одной строки с распарсенной датой — нечего генерировать.", file=sys.stderr)
        return 1

    sql = _emit_sql(rows)
    Path(args.out).write_text(sql, encoding="utf-8")
    print(f"\nГотово: {args.out}  ({len(rows)} строк, {len(sql)} байт)", file=sys.stderr)
    print("Открой в SQL-клиенте, посмотри цифры ДО/ПОСЛЕ, в конце COMMIT.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
