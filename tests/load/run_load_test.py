"""
Оркестратор нагрузочного тестирования KM_track.
Запускает Locust (HTTP) + sse_load.py (SSE) одновременно для каждого уровня L1→L4.

SSE тест использует asyncio/aiohttp вместо k6: k6 http.get() не держит
chunked SSE-потоки и возвращается после первого чанка (известное ограничение).

Запуск:
    python tests/load/run_load_test.py
    python tests/load/run_load_test.py --level L1   # только один уровень
    python tests/load/run_load_test.py --smoke       # smoke (5 пользователей, 1 мин)

Переменные окружения:
    LOAD_TEST_HOST          — хост (по умолч. https://analytics.krasmarafon.ru)
    LIVE_EVENT_ID           — event_id live-гонки (по умолч. 104)
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
LIVE_EVENT_ID = os.environ.get("LIVE_EVENT_ID", "104")  # 104=Ночной забег, реальные данные
ADMIN_PASSWORD = os.environ.get("LOCUST_ADMIN_PASSWORD", "km2026admin")

LEVELS = [
    {"name": "L1", "locust_users": 165,  "sse_vus": 335,  "spawn_rate": 20},
    {"name": "L2", "locust_users": 665,  "sse_vus": 1335, "spawn_rate": 40},
    {"name": "L3", "locust_users": 1665, "sse_vus": 3335, "spawn_rate": 80},
    {"name": "L4", "locust_users": 3335, "sse_vus": 6665, "spawn_rate": 100},
]

SMOKE = {"name": "smoke", "locust_users": 5, "sse_vus": 10, "spawn_rate": 5}


def _duration_to_seconds(duration: str) -> int:
    """Конвертирует '8m', '1m', '30s' → секунды."""
    duration = duration.strip()
    if duration.endswith("m"):
        return int(duration[:-1]) * 60
    if duration.endswith("s"):
        return int(duration[:-1])
    return int(duration)

DURATION = "8m"
PAUSE_BETWEEN_S = 120  # 2 минуты

REPO_ROOT = Path(__file__).parent.parent.parent


def run_level(level: dict, report_dir: Path, duration: str = DURATION) -> bool:
    name = level["name"]
    total = level["locust_users"] + level["sse_vus"]

    print(f"\n{'=' * 60}")
    print(f"  Уровень {name}: {level['locust_users']} HTTP + {level['sse_vus']} SSE = {total} пользователей")
    print(f"  Хост: {HOST}  |  Live event_id: {LIVE_EVENT_ID}")
    print(f"{'=' * 60}")

    report_dir.mkdir(parents=True, exist_ok=True)
    locust_report = report_dir / f"locust_{name}.html"
    sse_stdout    = report_dir / f"sse_{name}_stdout.txt"

    # Длительность SSE: CONN_HOLD_S + буфер, чтобы уложиться в duration
    hold_s = _duration_to_seconds(duration) - 20
    hold_s = max(hold_s, 10)

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

    sse_cmd = [
        sys.executable,
        str(REPO_ROOT / "tests" / "load" / "sse_load_remote.py"),
        "--vus", str(level["sse_vus"]),
        "--hold", str(hold_s),
    ]

    env = {
        **os.environ,
        "LOCUST_LIVE_EVENT_ID": LIVE_EVENT_ID,
        "LOCUST_ADMIN_PASSWORD": ADMIN_PASSWORD,
        "PYTHONIOENCODING": "utf-8",
    }

    print(f"\n  Запуск Locust (HTTP) + sse_load.py (SSE) одновременно...")
    locust_proc = subprocess.Popen(locust_cmd, env=env, cwd=REPO_ROOT)
    with open(sse_stdout, "w", encoding="utf-8") as sse_log:
        sse_proc = subprocess.Popen(
            sse_cmd, env=env, cwd=REPO_ROOT,
            stdout=sse_log, stderr=subprocess.STDOUT,
        )

    locust_timeout = _duration_to_seconds(duration) + 60
    try:
        locust_proc.wait(timeout=locust_timeout)
        sse_proc.wait(timeout=120)
    except subprocess.TimeoutExpired:
        print(f"\n  WARN: процесс не завершился вовремя — принудительно останавливаем")
        for p in (locust_proc, sse_proc):
            p.terminate()
            p.wait()

    locust_ok = locust_proc.returncode == 0
    sse_ok = sse_proc.returncode == 0

    # Показываем финальную сводку SSE
    if sse_stdout.exists():
        lines = sse_stdout.read_text(encoding="utf-8", errors="replace").splitlines()
        tail = lines[-25:] if len(lines) > 25 else lines
        print(f"\n  SSE сводка:")
        for l in tail:
            print(f"    {l}")

    print(f"\n  Locust: {'OK' if locust_ok else 'FAIL'} (exit {locust_proc.returncode})")
    print(f"  SSE:    {'OK' if sse_ok else 'FAIL'} (exit {sse_proc.returncode})")
    print(f"  Отчёты: {locust_report.name}, {sse_stdout.name}")

    return locust_ok and sse_ok


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
