#!/usr/bin/env python3
"""Загрузка внешних регистраций («Бум.xlsx», лист «Все участники») в ext_registrations.

  python scripts/import_ext_registrations.py --file "<xlsx>" --source boom          # dry-run
  python scripts/import_ext_registrations.py --file "<xlsx>" --source boom --apply

Настройки БД (DB_*) — из окружения/.env через src.config (локально: load_dotenv('.env.local', override=True)
выставляется переменной окружения, на проде — .env сервера). Файл с ПДн в репозиторий не кладётся.
"""
import argparse
import datetime
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent.parent))

_YEAR_RE = re.compile(r"(19|20)\d{2}")
_DMY_RE = re.compile(r"^(\d{1,2})[.\-/\s](\d{1,2})[.\-/\s](\d{4})$")
_YMD_RE = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})(?:[ T].*)?$")
BATCH = 1000


def parse_birthday(raw):
    """-> datetime.date (1920–2025) либо None."""
    d = None
    if isinstance(raw, datetime.datetime):
        d = raw.date()
    elif isinstance(raw, datetime.date):
        d = raw
    elif isinstance(raw, str):
        s = raw.strip()
        m = _DMY_RE.match(s)
        parts = (m.group(3), m.group(2), m.group(1)) if m else None
        if parts is None:
            m = _YMD_RE.match(s)
            parts = m.groups() if m else None
        if parts:
            try:
                d = datetime.date(int(parts[0]), int(parts[1]), int(parts[2]))
            except ValueError:
                d = None
    if d is None or not 1920 <= d.year <= 2025:
        return None
    return d


def parse_phone(raw):
    """-> последние 10 цифр, иначе ''."""
    if raw is None:
        return ""
    if isinstance(raw, float):
        raw = int(raw)
    digits = re.sub(r"\D", "", str(raw))
    return digits[-10:] if len(digits) >= 10 else ""


def parse_email(raw):
    s = str(raw).strip().lower() if raw is not None else ""
    if "@" not in s or s.startswith("example@"):
        return ""
    return s


def parse_year(product):
    m = _YEAR_RE.search(str(product or ""))
    return int(m.group(0)) if m else None


def parse_sex(raw):
    s = str(raw or "").strip().upper()
    return s[0] if s[:1] in ("М", "Ж") else ""


def _text(raw):
    return "" if raw is None else str(raw).strip()


def parse_file(path):
    """-> список dict (source_row — номер строки Excel)."""
    import openpyxl
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    ws = wb["Все участники"]
    rows = ws.iter_rows(values_only=True)
    headers = next(rows)
    idx = {h: i for i, h in enumerate(headers) if h}

    def col(row, name):
        i = idx.get(name)
        return row[i] if i is not None and i < len(row) else None

    out = []
    for n, row in enumerate(rows, start=2):
        surname, name = _text(col(row, "surname")), _text(col(row, "name"))
        if not surname or not name:
            continue
        product = _text(col(row, "product"))
        out.append({
            "source_row": n, "surname": surname, "name": name,
            "birthday": parse_birthday(col(row, "birthday")),
            "sex": parse_sex(col(row, "sex")),
            "phone": parse_phone(col(row, "phone")),
            "email": parse_email(col(row, "email")),
            "product": product, "event_year": parse_year(product),
        })
    return out


SQL = ("INSERT INTO ext_registrations (source, source_row, surname, name, birthday, sex, "
       "phone, email, product, event_year) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)")


def apply(rows, source):
    import mysql.connector
    from src.config import settings
    # Одно прямое соединение, не пул: на проде пул (10 соединений) упирается в max_connections.
    conn = mysql.connector.connect(
        host=settings.DB_HOST, port=settings.DB_PORT, database=settings.DB_NAME,
        user=settings.DB_USER, password=settings.DB_PASSWORD,
        charset="utf8mb4", autocommit=False)
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM ext_registrations WHERE source = %s", (source,))
        data = [(source, r["source_row"], r["surname"], r["name"], r["birthday"], r["sex"],
                 r["phone"], r["email"], r["product"], r["event_year"]) for r in rows]
        for i in range(0, len(data), BATCH):
            cur.executemany(SQL, data[i:i + BATCH])
        conn.commit()
        cur.execute("SELECT COUNT(*) FROM ext_registrations WHERE source = %s", (source,))
        return cur.fetchone()[0]
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True)
    ap.add_argument("--source", required=True)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    rows = parse_file(a.file)
    print(f"строк: {len(rows)}; с ДР: {sum(1 for r in rows if r['birthday'])}; "
          f"с телефоном: {sum(1 for r in rows if r['phone'])}; "
          f"с почтой: {sum(1 for r in rows if r['email'])}; "
          f"с годом: {sum(1 for r in rows if r['event_year'])}")
    if a.apply:
        print(f"загружено в ext_registrations[{a.source}]: {apply(rows, a.source)}")
    else:
        print("dry-run (без --apply БД не меняется)")


if __name__ == "__main__":
    main()
