"""
Оркестратор нагрузочного тестирования KM_track.
Запускает Locust + k6 одновременно для каждого уровня L1→L4.

Запуск:
    python tests/load/run_load_test.py
    python tests/load/run_load_test.py --level L1   # только один уровень
    python tests/load/run_load_test.py --smoke       # smoke (5 пользователей, 1 мин)

Переменные окружения:
    LOAD_TEST_HOST          — хост (по умолч. https://analytics.krasmarafon.ru)
    LIVE_EVENT_ID           — event_id live-гонки (по умолч. 106)
    LOCUST_ADMIN_PASSWORD   — пароль бизнес-аналитики (по умолч. km2026admin)
"""

import argparse
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

HOST = os.environ.get("LOAD_TEST_HOST", "https://analytics.krasmarafon.ru")
LIVE_EVENT_ID = os.environ.get("LIVE_EVENT_ID", "106")
ADMIN_PASSWORD = os.environ.get("LOCUST_ADMIN_PASSWORD", "km2026admin")

LEVELS = [
    {"name": "L1", "locust_users": 165,  "k6_vus": 335,  "spawn_rate": 20},
    {"name": "L2", "locust_users": 665,  "k6_vus": 1335, "spawn_rate": 40},
    {"name": "L3", "locust_users": 1665, "k6_vus": 3335, "spawn_rate": 80},
    {"name": "L4", "locust_users": 3335, "k6_vus": 6665, "spawn_rate": 100},
]

SMOKE = {"name": "smoke", "locust_users": 5, "k6_vus": 10, "spawn_rate": 5}

DURATION = "8m"
PAUSE_BETWEEN_S = 120  # 2 минуты

REPO_ROOT = Path(__file__).parent.parent.parent


def run_level(level: dict, report_dir: Path, duration: str = DURATION) -> bool:
    name = level["name"]
    total = level["locust_users"] + level["k6_vus"]

    print(f"\n{'=' * 60}")
    print(f"  Уровень {name}: {level['locust_users']} HTTP + {level['k6_vus']} SSE = {total} пользователей")
    print(f"  Хост: {HOST}  |  Live event_id: {LIVE_EVENT_ID}")
    print(f"{'=' * 60}")

    report_dir.mkdir(parents=True, exist_ok=True)
    locust_report = report_dir / f"locust_{name}.html"
    k6_report = report_dir / f"k6_{name}.json"

    locust_cmd = [
        sys.executable, "-m", "locust",
        "-f", str(REPO_ROOT / "locustfile.py"),
        "--host", HOST,
        "--users", str(level["locust_users"]),
        "--spawn-rate", str(level["spawn_rate"]),
        "--run-time", duration,
        "--html", str(locust_report),
        "--headless",
    ]

    k6_cmd = [
        "k6", "run",
        str(REPO_ROOT / "tests" / "load" / "sse_test.js"),
        "--vus", str(level["k6_vus"]),
        "--duration", duration,
        "--out", f"json={k6_report}",
        "--env", f"K6_HOST={HOST}",
        "--env", f"K6_EVENT_ID={LIVE_EVENT_ID}",
    ]

    env = {
        **os.environ,
        "LOCUST_LIVE_EVENT_ID": LIVE_EVENT_ID,
        "LOCUST_ADMIN_PASSWORD": ADMIN_PASSWORD,
    }

    print(f"\n  Запуск Locust + k6 одновременно...")
    locust_proc = subprocess.Popen(locust_cmd, env=env, cwd=REPO_ROOT)
    try:
        k6_proc = subprocess.Popen(k6_cmd, cwd=REPO_ROOT)
    except FileNotFoundError:
        locust_proc.terminate()
        locust_proc.wait()
        print(f"\n  ОШИБКА: k6 не найден. Установи: winget install k6 --id k6.k6")
        return False

    try:
        locust_proc.wait(timeout=600)
        k6_proc.wait(timeout=60)
    except subprocess.TimeoutExpired:
        print(f"\n  WARN: процесс не завершился вовремя — принудительно останавливаем")
        locust_proc.terminate()
        k6_proc.terminate()
        locust_proc.wait()
        k6_proc.wait()

    locust_ok = locust_proc.returncode == 0
    k6_ok = k6_proc.returncode == 0

    print(f"\n  Locust: {'OK' if locust_ok else 'FAIL'} (exit {locust_proc.returncode})")
    print(f"  k6:     {'OK' if k6_ok else 'FAIL'} (exit {k6_proc.returncode})")
    print(f"  Отчёты: {locust_report.name}, {k6_report.name}")

    return locust_ok and k6_ok


def main():
    parser = argparse.ArgumentParser(description="Оркестратор нагрузочного тестирования KM_track")
    parser.add_argument("--level", choices=["L1", "L2", "L3", "L4"], help="Запустить только один уровень")
    parser.add_argument("--smoke", action="store_true", help="Smoke-тест (5+10 users, 1 мин)")
    parser.add_argument("--yes", "-y", action="store_true", help="Не спрашивать подтверждение (для conda run / CI)")
    args = parser.parse_args()

    date_str = datetime.now().strftime("%Y-%m-%d")
    report_dir = REPO_ROOT / "reports" / "load" / date_str

    print(f"\nKM_track Load Test Orchestrator")
    print(f"Хост: {HOST}")
    print(f"Отчёты: {report_dir}")
    print(f"\nВАЖНО: Перед запуском войдите на VPS и запустите:")
    print(f"  ./monitor_vps.sh <LEVEL>")

    if args.smoke:
        levels = [SMOKE]
        duration = "1m"
        print(f"\nРежим: SMOKE (5+10 users, 1 мин)")
    elif args.level:
        levels = [next(l for l in LEVELS if l["name"] == args.level)]
        duration = DURATION
        print(f"\nРежим: одиночный уровень {args.level}")
    else:
        levels = LEVELS
        duration = DURATION
        print(f"\nРежим: ПОЛНЫЙ тест L1→L4 (~40 мин)")

    if not args.yes:
        try:
            input("\nНажмите Enter для начала или Ctrl+C для отмены...")
        except EOFError:
            pass  # conda run не пробрасывает stdin — продолжаем без паузы

    all_ok = True
    for i, level in enumerate(levels):
        ok = run_level(level, report_dir, duration)
        all_ok = all_ok and ok

        if i < len(levels) - 1:
            print(f"\n  Пауза {PAUSE_BETWEEN_S // 60} мин перед следующим уровнем...")
            time.sleep(PAUSE_BETWEEN_S)

    print(f"\n{'=' * 60}")
    status = "ВСЕ УРОВНИ ПРОЙДЕНЫ" if all_ok else "ЕСТЬ ОШИБКИ — проверь отчёты"
    print(f"  {status}")
    print(f"  Отчёты: {report_dir}")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
