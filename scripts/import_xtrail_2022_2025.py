#!/usr/bin/env python3
"""
Импорт заявок Забега Икс (в БД — «Х Трейл») 2022–2025 из Google xlsx
(2026-09-26, тот же ход, что у Красочного забега — import_colorrun_2023_2025.main()).

Листы:
- «2022», «2023», «2024» — регистрации (старая выгрузка Tilda, sent в UTC);
  «LeadsFromTilda» — то же для 2025;
- «Стартовый 2024», «Стартовый 2025» — итоговые стартовые списки.

2022 в БД уже есть из «Бума» — вставляются только недостающие. Продукт 2022
("… на 10 км (Xtrailtrun2022") — без SKU с годом, дистанция из текста.
«2 км Северная ходьба» — дистанция 2 км. Не вставляются: строка «test» (2024)
и заявки других стартов, попавшие в лист (Жара 21.1 км в «2022»).

  python scripts/import_xtrail_2022_2025.py --google-xlsx …                      # dry-run
  python scripts/import_xtrail_2022_2025.py --google-xlsx … --apply --backup /root/backups/x.json
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.import_colorrun_2023_2025 import main

if __name__ == "__main__":
    sys.exit(main(
        event="Х Трейл",
        reg_sheets={2022: "2022", 2023: "2023", 2024: "2024", 2025: "LeadsFromTilda"},
        start_sheets={2024: "Стартовый 2024", 2025: "Стартовый 2025"},
        batch=("2000-01-01 00:00:00", "2000-01-01 00:00:01"),
        doc=__doc__,
        drop=lambda r: r["surname"].lower() == "test" or r["event_distance"] not in ("10 км", "2 км"),
    ))
