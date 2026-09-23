#!/usr/bin/env python3
"""
Разовый импорт исторических регистраций 2013-2022 из "Бум.xlsx" (сборный
дамп нескольких экспортов Tilda прошлых лет, добыт организатором) — задача
"Импорт исторических данных 2013-2023" из бэклога.

Формат файла ОТЛИЧАЕТСЯ от боевой выгрузки Tilda (другие колонки: Sport,
surname, name, sex, city, club, birthday, phone, email, product, distance,
Total amount, Payment date, utm_*, Берег) — не подходит под
tilda_import_parser.py как есть, поэтому разбор написан отдельно.

НЕ переиспользует bulk_import_leads() — та функция дополнительно делает
hard-DELETE лидов, не попавших в файл, для каждой затронутой (event_name,
event_year) пары ("файл — источник истины"). Здесь это ОПАСНО: "Бум.xlsx"
не гарантированно полный список за эти годы, только чистый INSERT новых
исторических записей. Полностью безопасно, потому что импортируемые годы
(2013-2022) НЕ пересекаются с тем, что уже есть в БД (там данные с 2025) —
проверено отдельно перед началом работы.

Полный список решений по данным — .taskmaster/tasks/todo.md (история
переписки с пользователем) и .taskmaster/tasks/lessons.md.

Использование:
  # dry-run (по умолчанию) — только отчёт, БД не меняется
  python scripts/import_boom_historical.py

  # применить
  python scripts/import_boom_historical.py --apply

Требуется доступ к БД (те же DB_* из .env/.env.local) и оба файла:
  C:\\Users\\podbo\\Downloads\\Бум.xlsx
  C:\\Users\\podbo\\Downloads\\Бум_разбор_ФИО.xlsx
(пути можно переопределить --boom-file/--fixes-file).
"""

import argparse
import datetime
import re
import sys
from collections import Counter
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import openpyxl

from src.analytics.db_pool import get_pooled_connection
from src.krasmarafon.services.tilda_webhook import is_name_suspicious, normalize_name

DEFAULT_BOOM_FILE = r"C:\Users\podbo\Downloads\Бум.xlsx"
DEFAULT_FIXES_FILE = r"C:\Users\podbo\Downloads\Бум_разбор_ФИО.xlsx"

# --- Решения, зафиксированные с пользователем (todo.md) --------------------

EVENT_NAME_MAP = {
    "xtrail": "Х Трейл",           # уже есть история в БД под кириллическим именем
    "забег весна": "Весна",
}

# Событие -> дефолтная дистанция для лет, где отдельной колонки distance ещё
# не было, но событие однодистанционное (подтверждено пользователем).
SINGLE_DISTANCE_DEFAULTS = {
    "х трейл": "10 км",
    "женская семерка": "7 км",
    "снежная семерка": "7 км",
    "красочный забег": "5 км",
    "ночной забег": "5 км",
}

# "Детский забег" без отдельной колонки distance (2013, 2016-2019).
# Вариант "без разбивки" оказался технически невозможен — events.event_distance
# в БД DECIMAL NOT NULL, триггер обязан распарсить реальное число из текста,
# иначе не создаст строку events и весь INSERT в leads падает (проверено на
# локальной БД). Пользователь выбрал: эвристика по возрасту (тот же порог,
# что и в parse_products() для текущих загрузок) — <6 лет -> "500 м",
# >=6 -> "1 км". Точность ~90%+ по факту 2020-2021 (см. todo.md), не 100%.
KIDS_AGE_DISTANCE_THRESHOLD = 6
# 2013 год — дата рождения неизвестна вообще (заглушка 1905, см. todo.md),
# эвристика невозможна физически. Дефолт — более частая дистанция по факту
# 2020-2021 (1 км: ~73% детей).
KIDS_NO_BIRTHDAY_DEFAULT = "1 км"

DISTANCE_NUM_MAP = {
    1: "1 км",
    5: "5 км",
    7: "7 км",
    10: "10 км",
    21: "21.1 км",          # только "Жара" — historical "21 км" == текущие "21.1 км"
    "500 метров": "500 м",
}

_BIRTHDAY_SENTINEL = "1900-01-01"
_YEAR_RE = re.compile(r"(19|20)\d{2}")

# Опечатка, подтверждена пользователем: 2991 -> 1991 (Колодезная Екатерина)
_TYPO_YEAR_FIX = {2991: 1991}

# Явные заглушки "дата неизвестна" — подтверждено находкой: 1905 использован
# как заглушка систематически (весь 2013 год) и точечно (2020/2022).
_PLACEHOLDER_BIRTH_YEARS = {1905, 1881}

# Найдено ПОСЛЕ разбора листов 1-3 (проверка на локальной БД): строка 43522
# — surname=1 (число), name='Денис', тот же паттерн порчи данных, что и 5
# строк "1/1" на листе 3 ("Бум_разбор_ФИО.xlsx"), не попала под фильтр
# "surname==name" при первом проходе. По тому же решению пользователя
# (удалить, не гадать фамилию) — тоже удаляем.
_EXTRA_DROP_ROWS = {43522}


def _row_key(surname, name, birthday, event_name, event_year, event_distance):
    return (surname.strip().lower(), name.strip().lower(), birthday, event_name, event_year, event_distance)


def _parse_birthday(raw):
    """-> 'YYYY-MM-DD' str, либо _BIRTHDAY_SENTINEL для заглушек/мусора."""
    if raw is None:
        return _BIRTHDAY_SENTINEL
    if isinstance(raw, (datetime.datetime, datetime.date)):
        year = raw.year
        if year in _TYPO_YEAR_FIX:
            year = _TYPO_YEAR_FIX[year]
        if year in _PLACEHOLDER_BIRTH_YEARS:
            return _BIRTHDAY_SENTINEL
        try:
            return datetime.date(year, raw.month, raw.day).isoformat()
        except ValueError:
            return _BIRTHDAY_SENTINEL
    if isinstance(raw, str):
        s = raw.strip()
        m = re.match(r"^(\d{1,2})[.\-/\s](\d{1,2})[.\-/\s](\d{4})$", s)
        if m:
            day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if year in _PLACEHOLDER_BIRTH_YEARS:
                return _BIRTHDAY_SENTINEL
            try:
                return datetime.date(year, month, day).isoformat()
            except ValueError:
                return _BIRTHDAY_SENTINEL
        return _BIRTHDAY_SENTINEL
    return _BIRTHDAY_SENTINEL


def _parse_payment_date(raw):
    """-> datetime, либо None если распознать не удалось (created_at тогда
    остаётся на усмотрение вызывающего — фоллбэк на "сейчас")."""
    if raw is None:
        return None
    if isinstance(raw, datetime.datetime):
        return raw
    if isinstance(raw, datetime.date):
        return datetime.datetime(raw.year, raw.month, raw.day)
    if isinstance(raw, str):
        s = raw.strip()
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                return datetime.datetime.strptime(s, fmt)
            except ValueError:
                continue
        return None
    if isinstance(raw, (int, float)):
        # Excel serial date (epoch 1899-12-30). Два реальных значения в файле
        # (790, 890) слишком малы, чтобы быть настоящей датой ~2020 года
        # (тогда serial ~44000) — явный мусор, а не сериализованная дата.
        try:
            dt = datetime.datetime(1899, 12, 30) + datetime.timedelta(days=float(raw))
        except (OverflowError, ValueError):
            return None
        if dt.year < 2013 or dt.year > 2023:
            return None
        return dt
    return None


def _normalize_sex(raw):
    s = (raw or "").strip()
    if s == "Женский":
        return "Женщина"
    return s


def _clean_text(raw):
    if raw is None:
        return ""
    return str(raw).strip()


def _clean_phone(raw):
    if raw is None or str(raw).strip() == "":
        return None
    if isinstance(raw, float):
        raw = int(raw)
    return str(raw).strip()


def _clean_email(raw):
    s = _clean_text(raw)
    if not s or "@" not in s:
        return "example@mail.ru"
    return s


def _kids_distance_by_age(event_year, birthday_raw):
    """Эвристика по возрасту для "Детский забег" без колонки distance.
    birthday_raw — сырое значение ячейки (datetime либо что угодно ещё)."""
    if isinstance(birthday_raw, (datetime.datetime, datetime.date)) and birthday_raw.year not in _PLACEHOLDER_BIRTH_YEARS:
        age = event_year - birthday_raw.year
        return "500 м" if age < KIDS_AGE_DISTANCE_THRESHOLD else "1 км"
    return KIDS_NO_BIRTHDAY_DEFAULT


def _resolve_event(product, distance_col, birthday_raw=None):
    """product (текст) + distance (число/строка из отдельной колонки) ->
    (event_name, event_distance, event_year) либо None, если строку нужно
    отбросить целиком (см. правила из todo.md)."""
    if not product:
        return None
    text = str(product).strip()
    if text == "Жара 2020":
        return None  # 75 строк без дистанции нигде — пользователь решил удалить

    ym = _YEAR_RE.search(text)
    if not ym:
        return None
    event_year = int(ym.group(0))
    base = _YEAR_RE.sub("", text).strip()

    # Дистанция, embedded в текст (сейчас — только "Жара", напр. "Жара 21 км")
    # ВАЖНО: вырезать распознанный кусок дистанции из base ДО того, как base
    # станет event_name — иначе event_name = "Жара 21 км" вместо "Жара" и не
    # смэтчится с уже существующими записями в БД.
    dist_match = re.search(r"\d+\s*км", base, re.IGNORECASE)
    base_no_dist = base[:dist_match.start()].strip() + " " + base[dist_match.end():].strip() if dist_match else base
    base_no_dist = base_no_dist.strip()

    key = base_no_dist.lower()
    if key.startswith("xtrail"):
        event_name = EVENT_NAME_MAP["xtrail"]
    elif key.startswith("забег весна"):
        event_name = EVENT_NAME_MAP["забег весна"]
    else:
        event_name = base_no_dist

    if dist_match:
        num = int(re.search(r"\d+", dist_match.group(0)).group(0))
        event_distance = DISTANCE_NUM_MAP.get(num, f"{num} км")
        return event_name, event_distance, event_year

    # Иначе — дистанция из отдельной колонки
    if distance_col is not None and distance_col != "":
        event_distance = DISTANCE_NUM_MAP.get(distance_col)
        if event_distance is None:
            event_distance = str(distance_col).strip()
        return event_name, event_distance, event_year

    # Ни в тексте, ни в колонке — однодистанционное событие без данных за
    # этот год (подтверждённые дефолты) либо "Детский забег" (эвристика по возрасту).
    ekey = event_name.lower()
    if ekey == "детский забег":
        return event_name, _kids_distance_by_age(event_year, birthday_raw), event_year
    if ekey in SINGLE_DISTANCE_DEFAULTS:
        return event_name, SINGLE_DISTANCE_DEFAULTS[ekey], event_year

    return None  # неизвестный случай — не гадаем, строка в failed


def load_fio_fixes(fixes_path):
    """Бум_разбор_ФИО.xlsx -> (fio_fix: {row_idx: (surname, name)}, drop_rows: set)."""
    wb = openpyxl.load_workbook(fixes_path, data_only=True)
    fio_fix = {}
    drop_rows = set()

    ws1 = wb["1. ФИО задвоено"]
    for row in ws1.iter_rows(min_row=2, values_only=True):
        if not row or row[1] is None:
            continue
        row_idx, surname, name = row[1], row[9], row[10]
        if surname and name:
            fio_fix[row_idx] = (str(surname).strip(), str(name).strip())

    ws2 = wb["2. Одно слово, второе неизвестн"]
    for row in ws2.iter_rows(min_row=2, values_only=True):
        if not row or row[1] is None:
            continue
        drop_rows.add(row[1])  # пользователь решил: удалить (surname/name NOT NULL в БД)

    ws3 = wb["3. Мусор-тест-плейсхолдер"]
    for row in ws3.iter_rows(min_row=2, values_only=True):
        if not row or row[1] is None:
            continue
        drop_rows.add(row[1])

    drop_rows |= _EXTRA_DROP_ROWS
    return fio_fix, drop_rows


def parse_boom_file(boom_path, fio_fix, drop_rows):
    """-> (rows: list[dict], stats: dict). Каждый dict уже полностью
    нормализован и готов к INSERT (кроме дедупликации между строками файла
    — см. dedupe())."""
    wb = openpyxl.load_workbook(boom_path, data_only=True, read_only=True)
    ws = wb["Все участники"]
    headers = next(ws.iter_rows(min_row=1, max_row=1, values_only=True))
    COLS = {h: i for i, h in enumerate(headers) if h}

    def col(row, name):
        idx = COLS.get(name)
        return row[idx] if idx is not None and idx < len(row) else None

    rows_out = []
    stats = Counter()

    for r_idx, row in enumerate(ws.iter_rows(min_row=2, max_row=ws.max_row, values_only=True), start=2):
        if not any(v is not None and str(v).strip() != "" for v in row):
            continue
        stats["total_nonblank"] += 1

        if r_idx in drop_rows:
            stats["dropped_by_user_decision"] += 1
            continue

        surname_raw, name_raw = col(row, "surname"), col(row, "name")
        if r_idx in fio_fix:
            surname_raw, name_raw = fio_fix[r_idx]
            stats["fio_fixed"] += 1

        surname = normalize_name(_clean_text(surname_raw))
        name = normalize_name(_clean_text(name_raw))
        if not surname or not name:
            stats["missing_fio"] += 1
            continue

        event = _resolve_event(col(row, "product"), col(row, "distance"), col(row, "birthday"))
        if event is None:
            stats["event_unresolved"] += 1
            continue
        event_name, event_distance, event_year = event

        birthday = _parse_birthday(col(row, "birthday"))
        if birthday == _BIRTHDAY_SENTINEL:
            stats["birthday_unknown"] += 1

        pay_dt = _parse_payment_date(col(row, "Payment date"))
        if pay_dt is None:
            stats["payment_date_unparseable"] += 1

        amount_raw = col(row, "Total amount")
        try:
            amount = float(amount_raw) if amount_raw not in (None, "") else 0.0
        except (TypeError, ValueError):
            amount = 0.0

        rec = {
            "row_idx": r_idx,
            "surname": surname,
            "name": name,
            "sex": _normalize_sex(col(row, "sex")),
            "city": _clean_text(col(row, "city")),
            "club": _clean_text(col(row, "club")) or None,
            "birthday": birthday,
            "phone": _clean_phone(col(row, "phone")),
            "email": _clean_email(col(row, "email")),
            "event_name": event_name,
            "event_distance": event_distance,
            "event_year": event_year,
            "amount": amount,
            "registered_at": pay_dt,
            "is_name_suspicious": int(is_name_suspicious(surname, name)),
        }
        rows_out.append(rec)
        stats["parsed_ok"] += 1

    return rows_out, stats


def dedupe(rows):
    seen = {}
    dup_count = 0
    for rec in rows:
        key = _row_key(rec["surname"], rec["name"], rec["birthday"],
                        rec["event_name"], rec["event_year"], rec["event_distance"])
        if key in seen:
            dup_count += 1
            continue
        seen[key] = rec
    return list(seen.values()), dup_count


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--boom-file", default=DEFAULT_BOOM_FILE)
    ap.add_argument("--fixes-file", default=DEFAULT_FIXES_FILE)
    ap.add_argument("--apply", action="store_true", help="применить изменения (без флага — только отчёт)")
    args = ap.parse_args()

    print(f"Файл: {args.boom_file}")
    print(f"Разбор ФИО: {args.fixes_file}")
    print(f"Режим: {'ПРИМЕНЕНИЕ' if args.apply else 'DRY-RUN (БД не меняется)'}")

    fio_fix, drop_rows = load_fio_fixes(args.fixes_file)
    print(f"\nЗагружено исправлений ФИО: {len(fio_fix)}, строк на удаление: {len(drop_rows)}")

    rows, stats = parse_boom_file(args.boom_file, fio_fix, drop_rows)
    print("\n--- Разбор файла ---")
    for k in ("total_nonblank", "dropped_by_user_decision", "fio_fixed", "missing_fio",
              "event_unresolved", "birthday_unknown", "payment_date_unparseable", "parsed_ok"):
        print(f"  {k}: {stats.get(k, 0)}")

    rows, dup_count = dedupe(rows)
    print(f"\nДублей внутри файла удалено: {dup_count}")
    print(f"К импорту после дедупликации: {len(rows)}")

    ev_counter = Counter((r["event_name"], r["event_year"], r["event_distance"]) for r in rows)
    print(f"\n--- События/годы/дистанции ({len(ev_counter)} комбинаций) ---")
    for k in sorted(ev_counter):
        print(f"  {k}: {ev_counter[k]}")

    no_created_at = sum(1 for r in rows if r["registered_at"] is None)
    print(f"\nСтрок без даты регистрации в источнике (created_at = 01.01 года события, "
          f"решение пользователя): {no_created_at}")

    print("\n--- Примеры (первые 5) ---")
    for r in rows[:5]:
        print(f"  {r['surname']} {r['name']} | {r['event_name']} {r['event_distance']} {r['event_year']} "
              f"| ДР={r['birthday']} | создано={r['registered_at']}")

    if not args.apply:
        print("\nЭто был dry-run. Повтори с --apply, чтобы применить.")
        return 0

    conn = get_pooled_connection()
    if not conn:
        print("Нет соединения с БД (проверь DB_* в .env/.env.local).")
        return 1

    inserted = skipped_existing = errors = 0
    try:
        cur = conn.cursor(dictionary=True, buffered=True)
        for r in rows:
            cur.execute(
                "SELECT id FROM leads WHERE surname=%s AND name=%s AND birthday=%s "
                "AND event_name=%s AND event_year=%s AND event_distance=%s",
                (r["surname"], r["name"], r["birthday"], r["event_name"], r["event_year"], r["event_distance"]),
            )
            if cur.fetchall():
                skipped_existing += 1
                continue
            # Решение пользователя: если в источнике нет даты регистрации
            # (100% случаев за 2013-2019, см. todo.md) — 1 января года
            # события, а не момент импорта (иначе на карточке участника
            # "Жара 2013" соседствовало бы с "зарегистрирован в 2026").
            created_at = r["registered_at"] or datetime.datetime(r["event_year"], 1, 1)
            try:
                cur.execute(
                    """
                    INSERT INTO leads (
                        surname, name, sex, city, club, birthday, email, phone,
                        event_name, event_distance, event_year, products,
                        amount, promocode, discount, order_id, transaction_id, payment_system,
                        is_name_suspicious, start_number, client_id, event_id, is_duplicate,
                        status, is_new, is_new_event, source, created_at
                    ) VALUES (
                        %(surname)s, %(name)s, %(sex)s, %(city)s, %(club)s, %(birthday)s,
                        %(email)s, %(phone)s, %(event_name)s, %(event_distance)s,
                        %(event_year)s, '', %(amount)s, '', 0, NULL, '', '',
                        %(is_name_suspicious)s, NULL, 0, 0, 0, 0, 0, 0, 'import', %(created_at)s
                    )
                    """,
                    {**r, "created_at": created_at},
                )
                inserted += 1
            except Exception as e:
                errors += 1
                print(f"  ! ошибка на строке {r['row_idx']} ({r['surname']} {r['name']}): {e}")
        conn.commit()
    finally:
        try:
            conn.close()
        except Exception:
            pass

    print(f"\nВставлено: {inserted}, пропущено (уже есть): {skipped_existing}, ошибок: {errors}")
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
