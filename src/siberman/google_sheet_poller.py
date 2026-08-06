"""
Standalone-скрипт непрерывной синхронизации Siberman с Google-таблицей —
по образцу copernico_run_poller.py (тот же паттерн, интервал вместо
backoff — ошибки скачивания/парсинга не считаются "неудачным циклом",
sync_google_sheet() сама возвращает {"ok": False, ...} и цикл просто ждёт
следующего интервала). Отдельный процесс, запускается вручную на время
гонки:

    python -m src.siberman.google_sheet_poller --race-year 2026 --interval 20

Останов — Ctrl+C.

⚠ Пока этот процесс активен — НЕ запускать обычную Excel-загрузку в
админке для этого года (apply_to_db() делает clear_race_year() и сотрёт
результат последнего цикла синхронизации).
"""
import argparse
import logging
import time

from src.siberman.db import get_siberman_connection
from src.siberman.google_sheet_sync import sync_google_sheet

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def run_poller(race_year: int, interval: int) -> None:
    log.info(f"Live-синхронизация Google-таблицы Siberman запущена: race_year={race_year}, interval={interval}с")
    try:
        while True:
            cycle_start = time.time()

            conn = get_siberman_connection()
            if conn is None:
                log.error("Нет соединения с БД, пропуск цикла")
                time.sleep(interval)
                continue
            try:
                result = sync_google_sheet(conn, race_year)
                if result.get("changed"):
                    log.info(f"Применены изменения: {result}")
                elif not result.get("ok"):
                    log.warning(f"Цикл не удался: {result}")
            except Exception as e:
                log.error(f"Ошибка синхронизации: {e}")
            finally:
                conn.close()

            elapsed = time.time() - cycle_start
            time.sleep(max(0.0, interval - elapsed))
    except KeyboardInterrupt:
        log.info("Остановлено пользователем (Ctrl+C)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Live-синхронизация Siberman с Google-таблицей")
    parser.add_argument("--race-year", type=int, required=True)
    parser.add_argument("--interval", type=int, default=20, help="секунд между опросами (по умолчанию 20)")
    args = parser.parse_args()
    run_poller(args.race_year, args.interval)


if __name__ == "__main__":
    main()
