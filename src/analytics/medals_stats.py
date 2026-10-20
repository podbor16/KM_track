"""
Статистика страницы сертификата «Забега Единства» (/medals/, static/medals/).

Страница шлёт событие POST /medals/stat?e=<событие>&f=<рамка> (sendBeacon, без фото и данных
участника). На проде запрос не доходит до Python: nginx отвечает 204 и пишет строку в лог
(log_format medals_stat в deploy/nginx.conf), локально — тот же формат пишет append().
Строка: «время ISO 8601 <TAB> событие <TAB> рамка <TAB> IP». В цифры попадают только известные
события и рамки из certificate.config.json — подделанный запрос не исказит статистику.
IP нужен только для числа уникальных посетителей и в выгрузку не попадает.
"""

import collections
import io
import json
import os
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
LOG_PATH = Path(os.getenv("MEDALS_STAT_LOG", BASE_DIR / "logs" / "medals_stat.log"))
CONFIG_PATH = BASE_DIR / "static" / "medals" / "certificate.config.json"

EVENTS = {"open": "Открыли страницу", "download": "Скачали сертификат", "share": "Поделились"}


def frames():
    """{id рамки: подпись} из конфига страницы."""
    try:
        config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        return {t["id"]: t.get("label") or t["id"] for t in config.get("templates", [])}
    except (OSError, ValueError, KeyError):
        return {}


def append(event, frame, ip, path=None, now=None):
    """Записать событие в формате nginx (для localhost: на проде пишет nginx)."""
    path = Path(path or LOG_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = (now or datetime.now().astimezone()).isoformat(timespec="seconds")
    clean = lambda v: str(v or "").replace("\t", " ").replace("\n", " ")[:64]
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(f"{stamp}\t{clean(event)}\t{clean(frame)}\t{clean(ip)}\n")


def read(path=None):
    """[(время, событие, рамка или '', ip)] — только известные события и рамки."""
    path = Path(path or LOG_PATH)
    known = frames()
    rows = []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except FileNotFoundError:
        return rows
    for line in lines:
        parts = line.split("\t")
        if len(parts) != 4 or parts[1] not in EVENTS:
            continue
        try:
            ts = datetime.fromisoformat(parts[0])
        except ValueError:
            continue
        frame = parts[2] if parts[2] in known else ""
        rows.append((ts, parts[1], frame, parts[3]))
    return rows


def summary(rows):
    """Итоги, по рамкам и по часам для /admin."""
    known = frames()
    totals = collections.Counter(e for _, e, _, _ in rows)
    visitors = {ip for _, e, _, ip in rows if e == "open"}
    downloaded = {ip for _, e, _, ip in rows if e == "download"} & visitors
    by_frame = collections.defaultdict(collections.Counter)
    by_hour = collections.defaultdict(collections.Counter)
    for ts, event, frame, _ in rows:
        if event != "open":
            by_frame[frame][event] += 1
        by_hour[ts.strftime("%Y-%m-%d %H:00")][event] += 1
    return {
        "events": EVENTS,
        "totals": {e: totals[e] for e in EVENTS},
        "visitors": len(visitors),
        # доля посетителей (по IP), скачавших хотя бы один сертификат; за общим IP мобильного
        # оператора — несколько человек, поэтому оценка приблизительная
        "conversion": round(100 * len(downloaded) / len(visitors), 1) if visitors else None,
        "by_frame": [{"frame": f, "label": known.get(f, "не указана"), **{e: by_frame[f][e] for e in ("download", "share")}}
                     for f in list(known) + ([""] if "" in by_frame else [])],
        "by_hour": [{"hour": h, **{e: by_hour[h][e] for e in EVENTS}} for h in sorted(by_hour, reverse=True)],
        "first": rows[0][0].isoformat(timespec="minutes") if rows else None,
        "last": rows[-1][0].isoformat(timespec="minutes") if rows else None,
    }


def to_xlsx(rows):
    """Excel: «Итоги», «По рамкам», «По часам», «События» (без IP)."""
    from openpyxl import Workbook
    from openpyxl.styles import Font

    s = summary(rows)
    known = frames()
    wb = Workbook()
    sheets = {
        "Итоги": [["Показатель", "Значение"]]
                 + [[EVENTS[e], s["totals"][e]] for e in EVENTS]
                 + [["Уникальных посетителей (по IP)", s["visitors"]],
                    ["Посетителей, скачавших сертификат, %", s["conversion"] if s["conversion"] is not None else "—"],
                    ["Первое событие", s["first"] or "—"], ["Последнее событие", s["last"] or "—"]],
        "По рамкам": [["Рамка", "Скачали", "Поделились"]]
                     + [[r["label"], r["download"], r["share"]] for r in s["by_frame"]],
        "По часам": [["Час", *EVENTS.values()]]
                    + [[r["hour"], *(r[e] for e in EVENTS)] for r in sorted(s["by_hour"], key=lambda r: r["hour"])],
        "События": [["Время", "Событие", "Рамка"]]
                   + [[ts.strftime("%Y-%m-%d %H:%M:%S"), EVENTS[e], known.get(f, "")] for ts, e, f, _ in rows],
    }
    wb.remove(wb.active)
    for title, data in sheets.items():
        ws = wb.create_sheet(title)
        for row in data:
            ws.append(row)
        for cell in ws[1]:
            cell.font = Font(bold=True)
        for col in ws.columns:
            ws.column_dimensions[col[0].column_letter].width = max(12, min(40, max(len(str(c.value or "")) for c in col) + 2))
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
