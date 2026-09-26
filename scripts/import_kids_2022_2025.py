#!/usr/bin/env python3
"""
Импорт заявок Детского забега 2022–2025 из Google xlsx (2026-09-26, тот же ход,
что у Красочного забега — import_colorrun_2023_2025.main()).

Листы:
- «2022», «2023», «2024» — регистрации (старая выгрузка Tilda, sent в UTC);
  «LeadsFromTilda» — то же для 2025 (источник «пачки» 24.02.2026 в БД);
- «Стартовый 2025» — итоговый стартовый список (номер — в первой колонке
  без заголовка, дистанции нет).

Дистанция — по возрасту (решение пользователя): ребёнку, которому в год
старта исполняется 5 лет или меньше (год старта − год рождения ≤ 5), —
500 м, остальным — 1 км. Без даты рождения — из SKU 2022 ("kids2022-500"),
в продуктах 2023–2025 дистанции нет — такие строки пропускаются.

  python scripts/import_kids_2022_2025.py --google-xlsx …                      # dry-run
  python scripts/import_kids_2022_2025.py --google-xlsx … --apply --backup /root/backups/x.json
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.import_boom_historical import _BIRTHDAY_SENTINEL
from scripts.import_colorrun_2023_2025 import main

_KIDS_SKU_RE = re.compile(r"\(kids\d{4}-(\d+)", re.IGNORECASE)


def kids_distance(birthday, event_year, get):
    if birthday and birthday != _BIRTHDAY_SENTINEL:
        return "500 м" if event_year - int(birthday[:4]) <= 5 else "1 км"
    m = _KIDS_SKU_RE.search(str(get("product") or ""))
    return {"1": "1 км", "500": "500 м"}.get(m.group(1)) if m else None


if __name__ == "__main__":
    sys.exit(main(
        event="Детский забег",
        reg_sheets={2022: "2022", 2023: "2023", 2024: "2024", 2025: "LeadsFromTilda"},
        start_sheets={2025: "Стартовый 2025"},
        batch=("2026-02-24 10:44:00", "2026-02-24 10:46:00"),
        doc=__doc__,
        distance_fn=kids_distance,
    ))
