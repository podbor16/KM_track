#!/usr/bin/env python3
"""
Разовый бэкфилл leads.created_at из колонки "Date" выгрузок Tilda.

Зачем: bulk_import_leads() до 2026-09 не заполнял created_at при INSERT новых
заявок → срабатывал DEFAULT CURRENT_TIMESTAMP → у всех импортных строк дата =
момент импорта, а не регистрации. Это ломало чарты динамики регистраций в
DataLens (у Жары-2026 все ~3500 заявок «зарегистрированы» в августе).

Что делает: для каждой строки файла находит совпавшие leads тем же матчингом,
что и импорт (order_id → surname+name+birthday+событие), и двигает created_at
НАЗАД к дате подачи из файла:

    UPDATE leads SET created_at = LEAST(created_at, <дата из файла>) WHERE id = ?

LEAST — реальную раннюю дату вебхук-заявки не трогает, поздний импорт-штамп
чинит. Скрипт НИКОГДА ничего не удаляет и не меняет других полей (в отличие
от переимпорта через /admin, который сделал бы hard-DELETE строк, которых нет
в свежем экспорте).

Использование:
  # dry-run (по умолчанию) — только отчёт, БД не меняется
  python scripts/backfill_created_at_from_tilda.py path/to/leads-*.csv
  python scripts/backfill_created_at_from_tilda.py path/to/exports_dir/

  # применить
  python scripts/backfill_created_at_from_tilda.py path/to/exports_dir/ --apply

Требуется доступ к БД (те же DB_* из .env, что и у приложения) — запускать
локально при активном SSH-туннеле/VPN либо прямо на VPS.
"""

import argparse
import sys
from collections import Counter
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv

load_dotenv(project_root / ".env")

from src.analytics.db_results import _find_lead_matches
from src.analytics.db_pool import get_pooled_connection
from src.krasmarafon.services.tilda_import_parser import (
    parse_tilda_export,
    parse_tilda_datetime,
)

_EXPORT_EXTS = (".csv", ".xlsx", ".xls")


def _collect_files(paths):
    files = []
    for p in paths:
        path = Path(p)
        if path.is_dir():
            files.extend(sorted(f for f in path.iterdir()
                                if f.suffix.lower() in _EXPORT_EXTS))
        elif path.is_file():
            files.append(path)
        else:
            print(f"  ! пропущен (не найден): {p}")
    return files


def _histogram(counter, indent="    "):
    if not counter:
        print(f"{indent}(пусто)")
    for key in sorted(counter):
        print(f"{indent}{key}: {counter[key]}")


def _event_month_histogram(cur, events):
    """leads.created_at по месяцам для затронутых (event_name, event_year)."""
    names = sorted({n for n, _ in events})
    years = sorted({y for _, y in events if y is not None})
    if not names or not years:
        return
    ph_n = ",".join(["%s"] * len(names))
    ph_y = ",".join(["%s"] * len(years))
    # формат-строку передаём ПАРАМЕТРОМ — иначе '%Y-%m' в тексте запроса
    # конфликтует с paramstyle mysql-connector и уходит в MySQL как литерал
    cur.execute(
        f"SELECT DATE_FORMAT(created_at, %s) m, COUNT(*) c "
        f"FROM leads WHERE event_name IN ({ph_n}) AND event_year IN ({ph_y}) "
        f"GROUP BY m ORDER BY m",
        ["%Y-%m"] + names + years,
    )
    hist = Counter({r["m"]: r["c"] for r in cur.fetchall()})
    print(f"  ({', '.join(names)} / {', '.join(map(str, years))}):")
    _histogram(hist, indent="    ")


def _analyze_file(cur, path: Path, min_per_event: int = 5):
    """Разбор одного файла + матчинг. Возвращает dict со сводкой и списком
    (lead_id, reg_dt) к обновлению. БД не меняет. Группы (event_name,
    event_year) с числом строк меньше min_per_event отбрасываются как шум
    разбора product-блоба (напр. 1 строка «Весна 2026» в выгрузке Жары)."""
    result = parse_tilda_export(path.read_bytes(), filename=path.name)

    grp = Counter((r.event_name, r.event_year) for r in result.rows)
    noise = {ev for ev, c in grp.items() if c < min_per_event}
    rows = [r for r in result.rows if (r.event_name, r.event_year) not in noise]
    dropped_noise = sorted(f"{n} {y} ({grp[(n, y)]})" for n, y in noise)

    with_date = 0
    matched_rows = 0
    unmatched_rows = 0
    updates = []
    file_month_hist = Counter()
    events = set()

    for row in rows:
        reg_dt = parse_tilda_datetime(row.registered_at)
        if reg_dt is None:
            continue
        with_date += 1
        file_month_hist[reg_dt.strftime("%Y-%m")] += 1
        events.add((row.event_name, row.event_year))

        matches = _find_lead_matches(cur, row)
        if not matches:
            unmatched_rows += 1
            continue
        matched_rows += 1
        for m in matches:
            updates.append((m["id"], reg_dt))

    would_move = already_ok = 0
    if updates:
        ids = list({u[0] for u in updates})
        cur.execute(
            f"SELECT id, created_at FROM leads WHERE id IN ({','.join(['%s'] * len(ids))})",
            ids,
        )
        current = {r["id"]: r["created_at"] for r in cur.fetchall()}
        for lead_id, reg_dt in updates:
            cur_val = current.get(lead_id)
            if cur_val is not None and reg_dt < cur_val:
                would_move += 1
            else:
                already_ok += 1

    return {
        "name": path.name,
        "parsed": len(result.rows),
        "kept": len(rows),
        "dropped_noise": dropped_noise,
        "with_date": with_date,
        "failed": len(result.failed_rows),
        "unknown_headers": result.unknown_headers,
        "events": events,
        "matched_rows": matched_rows,
        "unmatched_rows": unmatched_rows,
        "updates": updates,
        "would_move": would_move,
        "already_ok": already_ok,
        "file_month_hist": file_month_hist,
    }


def _print_summary(s):
    print(f"\n=== {s['name']} ===")
    print(f"  строк разобрано        : {s['parsed']}")
    if s["dropped_noise"]:
        print(f"  ! отброшено (шум)      : {', '.join(s['dropped_noise'])}")
    print(f"  из них с датой (Date)  : {s['with_date']}")
    print(f"  не разобрано (failed)  : {s['failed']}")
    if s["unknown_headers"]:
        print(f"  ! неизвестные колонки  : {s['unknown_headers']}")
    print(f"  события в файле         : "
          + ", ".join(f"{n} {y}" for n, y in sorted(s["events"], key=str)))
    print(f"  строк сматчено с БД     : {s['matched_rows']}")
    print(f"  строк НЕ сматчено       : {s['unmatched_rows']}  "
          f"(created_at не тронется — вероятно поздние/ручные регистрации)")
    print(f"  затронуто строк БД     : {len(s['updates'])}  "
          f"(сдвинется назад: {s['would_move']}, уже раньше даты файла: {s['already_ok']})")
    print(f"  даты файла по месяцам  :")
    _histogram(s["file_month_hist"])


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+", help="файлы выгрузок Tilda или папки с ними")
    ap.add_argument("--apply", action="store_true",
                    help="применить изменения (без флага — только отчёт)")
    ap.add_argument("--min-per-event", type=int, default=5,
                    help="отбросить группы (событие, год) с числом строк меньше "
                         "этого (шум разбора product); по умолчанию 5")
    args = ap.parse_args()

    files = _collect_files(args.paths)
    if not files:
        print("Файлы не найдены.")
        return 1
    print(f"Файлов к обработке: {len(files)}")
    print(f"Режим: {'ПРИМЕНЕНИЕ' if args.apply else 'DRY-RUN (БД не меняется)'}")

    conn = get_pooled_connection()
    if not conn:
        print("Нет соединения с БД (проверь DB_* в .env / туннель).")
        return 1

    try:
        cur = conn.cursor(dictionary=True, buffered=True)

        summaries = [_analyze_file(cur, f, args.min_per_event) for f in files]
        all_events = set()
        for s in summaries:
            all_events |= s["events"]

        print("\n########## СОСТОЯНИЕ ДО ##########")
        _event_month_histogram(cur, all_events)

        for s in summaries:
            _print_summary(s)

        total_updates = sum(len(s["updates"]) for s in summaries)
        total_move = sum(s["would_move"] for s in summaries)
        print(f"\nИТОГО: строк БД к обновлению {total_updates}, из них сдвинется назад {total_move}")

        if args.apply and total_updates:
            for s in summaries:
                for lead_id, reg_dt in s["updates"]:
                    cur.execute(
                        "UPDATE leads SET created_at = LEAST(created_at, %s) WHERE id = %s",
                        (reg_dt, lead_id),
                    )
            conn.commit()
            print("\nИзменения зафиксированы (commit).")
            print("\n########## СОСТОЯНИЕ ПОСЛЕ ##########")
            _event_month_histogram(cur, all_events)

        cur.close()
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        print(f"\nОШИБКА: {e}")
        return 1
    finally:
        try:
            conn.close()
        except Exception:
            pass

    if not args.apply:
        print("\nЭто был dry-run. Повтори с --apply, чтобы применить.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
