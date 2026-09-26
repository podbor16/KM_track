#!/usr/bin/env python3
"""
Импорт заявок Женской семерки 2022–2025 из Google xlsx (2026-09-26, тот же ход,
что у Красочного забега — import_colorrun_2023_2025.main()).

Листы:
- «2022», «2023», «2024» — регистрации (старая выгрузка Tilda, sent в UTC);
  «LeadsFromTilda» — то же для 2025 (источник «пачки» 21.01.2025 в БД);
- «Стартовый» (2024) и «Стартовый 2025» — итоговые стартовые списки.

2022 в БД уже есть из «Бума» — вставляются только недостающие. Продукт 2022
("… на 7 км (Girlrun2022") — без SKU с годом, дистанция из текста.
«2 км Северная ходьба» — дистанция 2 км (как в заявках вебхука 2025).
Строка листа «2023» от 17.10.2023 (9,90 ₽) — тестовая продажа сезона 2024,
попавшая в выгрузку 2023 (решение пользователя): не вставляется.

  python scripts/import_womens7_2022_2025.py --google-xlsx …                      # dry-run
  python scripts/import_womens7_2022_2025.py --google-xlsx … --apply --backup /root/backups/x.json
"""

import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.import_colorrun_2023_2025 import main

if __name__ == "__main__":
    sys.exit(main(
        event="Женская семерка",
        reg_sheets={2022: "2022", 2023: "2023", 2024: "2024", 2025: "LeadsFromTilda"},
        start_sheets={2024: "Стартовый", 2025: "Стартовый 2025"},
        batch=("2025-01-21 10:16:00", "2025-01-21 10:18:00"),
        doc=__doc__,
        drop=lambda r: r["event_year"] == 2023 and (r["registered_at"] or datetime.datetime.min) >= datetime.datetime(2023, 10, 1),
    ))
