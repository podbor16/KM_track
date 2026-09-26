#!/usr/bin/env python3
"""
Импорт заявок Снежной семерки 2022–2025 из Google xlsx (2026-09-26, тот же ход,
что у Красочного забега — import_colorrun_2023_2025.main()).

Листы:
- «2022», «2023», «2024» — регистрации (старая выгрузка Tilda, sent в UTC);
  «LeadsFromTilda» — то же для 2025 (источник «пачки» 24.02.2026 в БД);
- «Стартовый 2023» (без строки заголовков — колонки заданы здесь),
  «Стартовый 2025» — итоговые стартовые списки.

Продукты 2022 ("… на 7 км (Snowseven2022") и 2 км 2023 ("(snow2,") — без SKU
с годом, дистанция из текста. «2 км Северная ходьба» — дистанция 2 км.
Строка листа «2022» от 13.01.2023 (продукт сезона 2023, после старта) не
вставляется — как первая продажа следующего сезона у Женской семерки.

  python scripts/import_snow7_2022_2025.py --google-xlsx …                      # dry-run
  python scripts/import_snow7_2022_2025.py --google-xlsx … --apply --backup /root/backups/x.json
"""

import datetime
import itertools
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.import_colorrun_2023_2025 import main

# «Стартовый 2023»: данные с первой строки
_START_2023_HEADERS = {0: "номер", 3: "фамилия", 4: "имя", 5: "sex", 6: "city", 7: "club", 8: "birthday",
                       10: "phone", 11: "email", 14: "дистанция"}


class _Headed:
    """Лист без строки заголовков -> лист с заголовками для parse_start_list."""

    def __init__(self, ws, headers):
        self.ws, self.headers = ws, headers

    def iter_rows(self, values_only=True):
        head = tuple(self.headers.get(i) for i in range(max(self.headers) + 1))
        return itertools.chain([head], self.ws.iter_rows(values_only=values_only))


if __name__ == "__main__":
    sys.exit(main(
        event="Снежная семерка",
        reg_sheets={2022: "2022", 2023: "2023", 2024: "2024", 2025: "LeadsFromTilda"},
        start_sheets={2023: lambda wb: _Headed(wb["Стартовый 2023"], _START_2023_HEADERS), 2025: "Стартовый 2025"},
        batch=("2026-02-24 11:02:00", "2026-02-24 11:03:00"),
        doc=__doc__,
        drop=lambda r: r["event_year"] == 2022 and (r["registered_at"] or datetime.datetime.min) >= datetime.datetime(2023, 1, 1),
    ))
