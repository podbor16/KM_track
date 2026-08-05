"""
Standalone-скрипт непрерывного опроса Copernico для бегового этапа
Siberman — по образцу load_race_results.py::continuous_mode (тот же
backoff-паттерн). Отдельный процесс, запускается вручную на время гонки:

    python -m src.siberman.copernico_run_poller --race-year 2026 --interval 20

Останов — Ctrl+C. Никакой новой in-process фоновой инфраструктуры в
FastAPI-приложении не добавляется (в проекте её сейчас нет вообще).

⚠ Пока этот процесс активен для бегового этапа — НЕ запускать обычный
Excel apply в админке (для любого этапа): apply_to_db() делает
clear_race_year() и сотрёт всё, что этот поллер уже собрал по бегу.
"""
import argparse
import logging
import time
from pathlib import Path

from src.siberman.copernico_run import (
    apply_copernico_snapshot, fetch_run_snapshot, load_preset_config,
)
from src.siberman.db import get_siberman_connection

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

DEFAULT_PRESET_PATH = Path(__file__).resolve().parents[2] / "config" / "copernico" / "siberman2026.yaml"


def run_poller(race_year: int, interval: int, preset_path: Path) -> None:
    cfg = load_preset_config(str(preset_path))
    log.info(f"Copernico live-опрос бега Siberman запущен: race_year={race_year}, interval={interval}с, "
              f"preset={cfg.get('preset')}, event={cfg.get('event')!r}")

    consecutive_failures = 0
    try:
        while True:
            cycle_start = time.time()

            runners = fetch_run_snapshot(cfg)
            if not runners:
                consecutive_failures += 1
                backoff = min(interval + 10 * consecutive_failures, 30)
                log.warning(f"Пустой/неуспешный ответ Copernico (подряд: {consecutive_failures}), "
                             f"повтор через {backoff}с...")
                time.sleep(backoff)
                continue
            consecutive_failures = 0

            conn = get_siberman_connection()
            if conn is None:
                log.error("Нет соединения с БД, пропуск цикла")
                time.sleep(interval)
                continue
            try:
                result = apply_copernico_snapshot(conn, race_year, runners, cfg)
                log.info(f"Цикл применён: {result}")
            except Exception as e:
                log.error(f"Ошибка применения снапшота: {e}")
            finally:
                conn.close()

            elapsed = time.time() - cycle_start
            time.sleep(max(0.0, interval - elapsed))
    except KeyboardInterrupt:
        log.info("Остановлено пользователем (Ctrl+C)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Live-опрос Copernico для бегового этапа Siberman")
    parser.add_argument("--race-year", type=int, required=True)
    parser.add_argument("--interval", type=int, default=20, help="секунд между опросами (по умолчанию 20)")
    parser.add_argument("--preset-config", type=str, default=str(DEFAULT_PRESET_PATH))
    args = parser.parse_args()
    run_poller(args.race_year, args.interval, Path(args.preset_config))


if __name__ == "__main__":
    main()
