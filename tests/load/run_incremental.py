"""
Инкрементальный SSE-тест: запускает серию уровней с растущим числом SSE-клиентов,
мониторит VPS RAM/CPU, останавливается при первом провале.

Запуск:
    python tests/load/run_incremental.py
    python tests/load/run_incremental.py --sse-levels 1000,1500,2000,2500,3000
    python tests/load/run_incremental.py --realistic
"""
import argparse
import csv
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).parent.parent.parent
load_dotenv(REPO_ROOT / ".env")

HOST = os.environ.get("LOAD_TEST_HOST", "https://analytics.krasmarafon.ru")
LIVE_EVENT_ID = os.environ.get("LIVE_EVENT_ID", "104")
ADMIN_PASSWORD = os.environ.get("LOCUST_ADMIN_PASSWORD") or os.environ.get("ADMIN_PASSWORD", "")

DURATION = "5m"
HTTP_USERS = 200
HTTP_SPAWN_RATE = 20
PASS_THRESHOLD_PCT = 95
STOP_RAM_PCT = 90


def _duration_to_seconds(d: str) -> int:
    if d.endswith("m"): return int(d[:-1]) * 60
    if d.endswith("s"): return int(d[:-1])
    return int(d)


def _setup_race_data() -> bool:
    print("\n  [realistic] Генерация тест-данных (3000 бегунов)...")
    r = subprocess.run(
        [sys.executable, str(REPO_ROOT / "tests" / "load" / "setup_race_data.py"), "--setup"],
        cwd=REPO_ROOT, timeout=120,
    )
    return r.returncode == 0


def _teardown_race_data():
    print("\n  [realistic] Очистка тест-данных...")
    subprocess.run(
        [sys.executable, str(REPO_ROOT / "tests" / "load" / "setup_race_data.py"), "--teardown"],
        cwd=REPO_ROOT, timeout=60,
    )


def run_level(sse_vus: int, report_dir: Path, duration: str, realistic: bool, http_users: int = HTTP_USERS) -> dict:
    """Возвращает dict с результатами: sse_pct, ram_max_pct, locust_ok."""
    name = f"T{sse_vus}"
    total = http_users + sse_vus
    print(f"\n{'=' * 60}")
    print(f"  {name}: {http_users} HTTP + {sse_vus} SSE = {total} users | {duration}")
    print(f"{'=' * 60}")
    report_dir.mkdir(parents=True, exist_ok=True)

    from tests.load.vps_monitor import VpsMonitor
    mon_path = report_dir / f"vps_{name}.csv"
    monitor = VpsMonitor(mon_path)
    monitor.start()

    env = {
        **os.environ,
        "LOCUST_LIVE_EVENT_ID": LIVE_EVENT_ID,
        "LOCUST_ADMIN_PASSWORD": ADMIN_PASSWORD,
        "PYTHONIOENCODING": "utf-8",
        "PYTHONPATH": str(REPO_ROOT),
    }

    sim_proc = sim_log = None
    if realistic:
        if not _setup_race_data():
            monitor.stop()
            return {"sse_pct": 0, "ram_max_pct": 0, "locust_ok": False, "error": "setup failed"}
        time.sleep(10)
        sim_dur = _duration_to_seconds(duration) + 30
        sim_log_path = report_dir / f"simulator_{name}.txt"
        sim_log = open(sim_log_path, "w", encoding="utf-8")
        sim_proc = subprocess.Popen(
            [sys.executable, str(REPO_ROOT / "tests" / "load" / "race_simulator.py"),
             "--duration", str(sim_dur)],
            stdout=sim_log, stderr=subprocess.STDOUT, cwd=REPO_ROOT,
        )

    locust_report = report_dir / f"locust_{name}.html"
    locust_cmd = [
        sys.executable, "-m", "locust",
        "-f", str(REPO_ROOT / "locustfile.py"),
        "--host", HOST,
        "--users", str(http_users),
        "--spawn-rate", str(HTTP_SPAWN_RATE),
        "--run-time", duration,
        "--html", str(locust_report),
        "--headless",
    ]

    hold_s = _duration_to_seconds(duration) - 20
    sse_stdout = report_dir / f"sse_{name}_stdout.txt"
    sse_cmd = [
        sys.executable,
        str(REPO_ROOT / "tests" / "load" / "sse_load_remote.py"),
        "--vus", str(sse_vus),
        "--hold", str(hold_s),
    ]

    locust_proc = subprocess.Popen(locust_cmd, env=env, cwd=REPO_ROOT)
    with open(sse_stdout, "w", encoding="utf-8") as sf:
        sse_proc = subprocess.Popen(sse_cmd, env=env, cwd=REPO_ROOT,
                                    stdout=sf, stderr=subprocess.STDOUT)

    timeout = _duration_to_seconds(duration) + 60
    try:
        locust_proc.wait(timeout=timeout)
        sse_proc.wait(timeout=120)
    except subprocess.TimeoutExpired:
        for p in (locust_proc, sse_proc):
            p.terminate(); p.wait()
    finally:
        monitor.stop()
        if sim_proc:
            sim_proc.terminate(); sim_proc.wait()
        if sim_log:
            sim_log.close()
        if realistic:
            _teardown_race_data()

    sse_pct = 0
    if sse_stdout.exists():
        for line in sse_stdout.read_text(encoding="utf-8", errors="replace").splitlines():
            print(f"    {line}")
            if "held (" in line:
                m = re.search(r"\((\d+)%\)", line)
                if m:
                    sse_pct = max(sse_pct, int(m.group(1)))

    ram_max = 0.0
    if mon_path.exists():
        with open(mon_path, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                ram_max = max(ram_max, float(row.get("ram_pct", 0)))

    locust_ok = locust_proc.returncode == 0
    result = {
        "sse_pct": sse_pct,
        "ram_max_pct": round(ram_max, 1),
        "locust_ok": locust_ok,
    }
    print(f"\n  Результат {name}: SSE {sse_pct}% | RAM max {ram_max:.1f}% | Locust {'OK' if locust_ok else 'FAIL'}")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sse-levels", default="1000,1500,2000,2500,3000",
                        help="Уровни SSE через запятую")
    parser.add_argument("--http-users", type=int, default=HTTP_USERS)
    parser.add_argument("--duration", default=DURATION)
    parser.add_argument("--realistic", action="store_true")
    parser.add_argument("--stop-on-fail", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--yes", "-y", action="store_true")
    args = parser.parse_args()

    levels = [int(x) for x in args.sse_levels.split(",")]
    date_str = datetime.now().strftime("%Y-%m-%d")
    report_dir = REPO_ROOT / "reports" / "load" / date_str

    print(f"\nKM_track Incremental SSE Test")
    print(f"Хост: {HOST} | Уровни SSE: {levels}")
    print(f"Режим: {'realistic' if args.realistic else 'synthetic'} | Длительность: {args.duration}")

    if not args.yes:
        try:
            input("\nНажмите Enter для начала или Ctrl+C для отмены...")
        except EOFError:
            pass

    results = []
    for sse_vus in levels:
        res = run_level(sse_vus, report_dir, args.duration, args.realistic, args.http_users)
        res["sse_vus"] = sse_vus
        results.append(res)

        if args.stop_on_fail and res["sse_pct"] < PASS_THRESHOLD_PCT:
            print(f"\n  СТОП: SSE {res['sse_pct']}% < {PASS_THRESHOLD_PCT}% на {sse_vus} VUs")
            break
        if res["ram_max_pct"] > STOP_RAM_PCT:
            print(f"\n  СТОП: RAM {res['ram_max_pct']}% > {STOP_RAM_PCT}%")
            break

        if sse_vus != levels[-1]:
            print(f"\n  Пауза 60с перед следующим уровнем...")
            time.sleep(60)

    print(f"\n{'=' * 60}")
    print("  ИТОГИ:")
    print(f"  {'SSE VUs':>8} | {'SSE%':>6} | {'RAM max':>8} | {'Locust':>7}")
    print(f"  {'-'*8}-+-{'-'*6}-+-{'-'*8}-+-{'-'*7}")
    for r in results:
        status = "PASS" if r["sse_pct"] >= PASS_THRESHOLD_PCT else "FAIL"
        print(f"  {r['sse_vus']:>8} | {r['sse_pct']:>5}% | {r['ram_max_pct']:>7}% | {status:>7}")
    ceiling = max((r["sse_vus"] for r in results if r["sse_pct"] >= PASS_THRESHOLD_PCT), default=0)
    print(f"\n  Потолок SSE на текущем железе: {ceiling} VUs")
    print(f"  Отчёты: {report_dir}")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
