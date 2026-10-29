#!/usr/bin/env python3
"""Разовое применение надёжных ДР из регистраций (ext_registrations): находки X-BD уровня high (одна ДР,
совпал телефон или почта из заявок) без решения — ответ «bd:<дата>» дела «Качества данных» (ДР карточки и её
строк с заглушкой; журнал dq_actions, отмена — на экране «Журнал»).

  python scripts/apply_ext_birthdays.py                                   # dry-run: что будет записано
  python scripts/apply_ext_birthdays.py --apply [--user "admin (Claude)"]

Настройки БД (DB_*) — из окружения/.env через src.config (локально — переменными окружения из .env.local,
на проде — .env сервера). Телефоны и почты не печатаются. Конфликт ФИ+ДР с другой карточкой не склеивается —
остаётся вопросом.
"""
import argparse
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.analytics import dq_actions, dq_cases, dq_checks  # noqa: E402

EVENTS_SHOWN = 3


def pick(findings, decided):
    """Находки для применения: X-BD high с одной ДР, без решения в dq_decisions (и без «отложено»)."""
    return [f for f in findings if f.code == "X-BD" and f.severity == "high" and len(f.fix) == 1
            and f.key not in decided]


def describe(data, f):
    """Строка таблицы: ФИО, было, станет, забеги карточки, совпало по (телефон/почта)."""
    cid, bd = f.client_ids[0], f.fix[0]
    c = data.clients[cid]
    rows = [x for x in dq_checks.ext_of(data, c) if x["birthday"] == bd]
    by = [w for w, ok in (("телефон", any(x["phone"] in data.card_phones.get(cid, ()) for x in rows)),
                          ("почта", any(x["email"] in data.card_emails.get(cid, ()) for x in rows))) if ok]
    events = sorted({data.event_label(r["event_id"]) for r in data.res_by_card[cid]})
    shown = ", ".join(events[:EVENTS_SHOWN]) + (f" и ещё {len(events) - EVENTS_SHOWN}" if len(events) > EVENTS_SHOWN else "")
    return {"fio": f'{c["surname"]} {c["name"]}', "was": c["birthday"], "will": bd, "events": shown,
            "by": " и ".join(by)}


def outcome(fio, bd, out):
    """Результат apply_answer -> (done | conflict | skipped, строка отчёта)."""
    ids = ", ".join(map(str, out.get("action_ids") or []))
    if out.get("conflict"):
        return "conflict", f'{fio} {bd}: {out["conflict"]["message"]}'
    if out.get("error"):
        return "skipped", f'{fio} {bd}: записано частично (действия журнала {ids or "—"}): {out["error"]}'
    return "done", f"{fio} → {bd}: действия журнала {ids}"


def connect():
    import mysql.connector
    from src.config import settings
    # Одно прямое соединение, не пул: на проде пул (10 соединений) упирается в max_connections.
    return mysql.connector.connect(host=settings.DB_HOST, port=settings.DB_PORT, database=settings.DB_NAME,
                                   user=settings.DB_USER, password=settings.DB_PASSWORD, charset="utf8mb4",
                                   autocommit=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--user", default="admin (Claude)")
    a = ap.parse_args()
    conn = connect()
    try:
        data = dq_checks.load(conn)
        findings = dq_checks.run_checks(data)
        decided = dq_actions.load_decisions(conn)
        chosen = pick(findings, decided)
        case_of = {i: c["key"] for c in dq_cases.group_cases(dq_cases._open(findings, decided), data) for i in c["cards"]}
        for f in chosen:
            d = describe(data, f)
            print(f'{d["fio"]} · {d["was"]} → {d["will"]} · {d["events"]} · совпало: {d["by"]}')
        print(f"надёжных ДР: {len(chosen)}")
        if not a.apply:
            print("dry-run (без --apply БД не меняется)")
            return
        res = {"done": [], "conflict": [], "skipped": []}
        for f in chosen:
            fio = describe(data, f)["fio"]
            try:
                out = dq_cases.apply_answer(conn, case_of[f.client_ids[0]], f.key, f"bd:{f.fix[0]}", {}, a.user)
            except (ValueError, dq_cases.StaleQuestion) as e:      # открыта ранняя ступень, дело изменилось
                res["skipped"].append(f"{fio} {f.fix[0]}: {e}")
                continue
            kind, line = outcome(fio, f.fix[0], out)
            res[kind].append(line)
            if kind == "done":
                print(line)
        done, conflicts, skipped = res["done"], res["conflict"], res["skipped"]
        for title, items in (("конфликты ФИ+ДР (остались вопросами)", conflicts), ("пропущены", skipped)):
            if items:
                print(f"{title}:\n  " + "\n  ".join(items))
        print(f"записано: {len(done)}; конфликтов: {len(conflicts)}; пропущено: {len(skipped)}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
