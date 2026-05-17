#!/usr/bin/env python3
"""
Локальный watchdog для load_race_results.py.
Запускает лоадер и перезапускает его при падении.

Использование:
  python run_loader.py vesna_5km          # читает config/loader/vesna_5km.env
  python run_loader.py vesna_5km --debug  # с отладочным выводом
  python run_loader.py --init vesna_5km   # запустить --init, затем continuous

Ctrl+C — остановить.
"""

import sys
import os
import re
import time
import subprocess
import signal
from pathlib import Path

RESTART_DELAY = 10   # секунд перед перезапуском после падения
MAX_RESTARTS = 999   # практически бесконечно

ROOT = Path(__file__).resolve().parent
LOADER_CONFIGS = ROOT / "config" / "loader"


def load_env(race: str) -> dict:
    env_file = LOADER_CONFIGS / f"{race}.env"
    if not env_file.exists():
        print(f"❌ Файл не найден: config/loader/{race}.env")
        print(f"   Создай файл по образцу config/loader/vesna_5km.env")
        sys.exit(1)
    result = {}
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r'^(\w+)\s*=\s*"?([^"]*)"?\s*$', line)
        if m:
            result[m.group(1)] = m.group(2)
    return result


def build_cmd(cfg: dict, extra_args: list) -> list:
    cmd = [sys.executable, str(ROOT / "load_race_results.py")]
    cmd += ["--config", cfg["LOADER_CONFIG"]]
    cmd += ["--distance", cfg["LOADER_DISTANCE"]]
    cmd += ["--interval", cfg.get("LOADER_INTERVAL", "5")]
    cmd += ["--reset-cache", cfg.get("LOADER_RESET_CACHE", "60")]
    cmd += extra_args
    return cmd


def run_once(cmd: list) -> int:
    """Запустить процесс и вернуть код выхода."""
    proc = subprocess.Popen(cmd)
    _current_proc[0] = proc
    try:
        return proc.wait()
    except KeyboardInterrupt:
        proc.send_signal(signal.SIGINT)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        return -1
    finally:
        _current_proc[0] = None


_current_proc = [None]


def handle_sigint(sig, frame):
    proc = _current_proc[0]
    if proc and proc.poll() is None:
        proc.send_signal(signal.SIGINT)
    sys.exit(0)


def main():
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0)

    # Разбор аргументов
    run_init = False
    extra_args = []
    race = None

    i = 0
    while i < len(args):
        if args[i] == "--init":
            run_init = True
        elif args[i] == "--debug":
            extra_args.append("--debug")
        elif args[i] == "--fix-routing":
            extra_args.append("--fix-routing")
        elif not args[i].startswith("--"):
            race = args[i]
        i += 1

    if not race:
        print("❌ Укажи имя гонки: python run_loader.py <race>")
        sys.exit(1)

    cfg = load_env(race)

    print(f"🏃 Загрузчик: {race}")
    print(f"   Конфиг:    {cfg['LOADER_CONFIG']}")
    print(f"   Дистанция: {cfg['LOADER_DISTANCE']}")
    print(f"   Интервал:  {cfg.get('LOADER_INTERVAL', '5')} сек")
    print()

    signal.signal(signal.SIGINT, handle_sigint)

    # Режим --init (однократно)
    if run_init:
        print("=== Режим INIT ===")
        init_cmd = build_cmd(cfg, extra_args + ["--init"])
        code = run_once(init_cmd)
        if code != 0:
            print(f"❌ Init завершился с кодом {code}")
            sys.exit(code)
        print("✅ Init завершён\n")

    # Continuous с watchdog
    print("=== Режим CONTINUOUS (watchdog активен) ===")
    print("   Ctrl+C — остановить\n")

    restarts = 0
    while restarts < MAX_RESTARTS:
        cmd = build_cmd(cfg, extra_args)
        code = run_once(cmd)

        if code == -1:
            # KeyboardInterrupt — штатная остановка
            print("\n⏹ Остановлено")
            break

        restarts += 1
        print(f"\n⚠️  Лоадер упал (код {code}). Перезапуск #{restarts} через {RESTART_DELAY} сек...")
        try:
            time.sleep(RESTART_DELAY)
        except KeyboardInterrupt:
            print("\n⏹ Остановлено")
            break

    print("Watchdog завершён.")


if __name__ == "__main__":
    main()
