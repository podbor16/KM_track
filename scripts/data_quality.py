#!/usr/bin/env python3
"""
Проверка привязки заявок и результатов к карточкам клиентов (src/analytics/data_quality.py).

Показывает находки без запомненного решения (dq_decisions). С --apply-auto сначала
применяет очевидное: удаляет «Not started» со старым номером и склеивает двойники,
если не сработал ни один предохранитель (журнал и снимок «до» — в dq_actions).
Ночной прогон — deploy/km_data_quality.timer.

  python scripts/data_quality.py                         # вся база
  python scripts/data_quality.py --event-id 116          # результаты одного забега
  python scripts/data_quality.py --json findings.json
  python scripts/data_quality.py --apply-auto --notify   # ночью: очевидное + сводка в ntfy (NTFY_URL)
"""

import argparse
import collections
import dataclasses
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.analytics.data_quality import apply_auto, pending_findings  # noqa: E402
from src.common import ntfy  # noqa: E402

ORDER = {"high": 0, "medium": 1, "low": 2}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--event-id", type=int, action="append", help="только результаты этого события (можно несколько)")
    ap.add_argument("--json", help="сохранить находки в json")
    ap.add_argument("--apply-auto", action="store_true", help="применить очевидное до отчёта")
    ap.add_argument("--notify", action="store_true", help="сводка в ntfy, если что-то применено или ждёт решения")
    args = ap.parse_args()

    from scripts.import_boom_historical import get_connection
    conn = get_connection()
    try:
        done = apply_auto(conn, "nightly") if args.apply_auto else None
        findings, _ = pending_findings(conn, set(args.event_id or []))
    finally:
        conn.close()

    if done:
        print(f'Применено: удалено результатов {len(done["deleted"])}, склеено групп {len(done["merged"])}, '
              f'пропущено {len(done["skipped"])}')
        for line in done["deleted"] + done["merged"]:
            print("  +", line)
    findings.sort(key=lambda f: (f.code, ORDER[f.severity], f.message))
    stat = collections.Counter((f.code, f.severity) for f in findings)
    print("Находки:", ", ".join(f"{c} {s}: {k}" for (c, s), k in sorted(stat.items())) or "нет")
    for f in findings:
        print(f'  [{f.code} {f.severity}{" auto" if f.auto else ""}] {f.message}')
    if args.json:
        Path(args.json).write_text(json.dumps([{**dataclasses.asdict(f), "key": f.key} for f in findings],
                                              ensure_ascii=False, indent=1), encoding="utf-8")

    applied = done and (done["deleted"] or done["merged"])
    high = sum(f.severity == "high" for f in findings)
    if args.notify and (applied or high):
        lines = []
        if applied:
            lines.append(f'Исправлено автоматически: удалено «Not started» {len(done["deleted"])}, '
                         f'склеено карточек (групп) {len(done["merged"])}')
        lines.append(f"Ждут решения: {len(findings)} (важных {high}) — /admin → «Качество данных»")
        ntfy.send("KM_track — качество данных", lines, tags="card_index_dividers")
    return 0


if __name__ == "__main__":
    sys.exit(main())
