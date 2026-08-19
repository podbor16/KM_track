"""
Переключить раздел «История участия» (/history, /athlete-profile) на VPS
напрямую через SSH — тот же файл, что пишет POST /api/admin/history-toggle
из /admin (config/history_enabled.local, вне git, переживает деплой,
см. src/config/event_loader.py::set_history_enabled()). Нужен для
переключения без входа в браузерную админку.

Usage (из корня проекта, deploy/ — не пакет, нужен -m): python -m deploy.ssh_history_toggle on|off
"""
import subprocess
import sys
from deploy._vps_config import VPS_HOST, VPS_USER, VPS_PASSWORD

REMOTE_FILE = "/opt/km_track/config/history_enabled.local"

arg = sys.argv[1].lower() if len(sys.argv) > 1 else None
if arg not in ("on", "off"):
    print("Usage: python deploy/ssh_history_toggle.py on|off")
    sys.exit(1)
value = "true" if arg == "on" else "false"


def plink_run(cmd: str, timeout: int = 30) -> str:
    args = ["plink.exe", "-ssh", "-batch", "-pw", VPS_PASSWORD, f"{VPS_USER}@{VPS_HOST}", cmd]
    r = subprocess.run(args, capture_output=True, timeout=timeout)
    out = r.stdout.decode(errors="replace").strip()
    err = r.stderr.decode(errors="replace").strip()
    if out:
        print(out)
    if r.returncode != 0:
        raise RuntimeError(f"plink command failed (exit {r.returncode}): {cmd[:120]}\n{err}")
    return out


def main():
    print(f"=== Переключаю историю в '{arg}' на {VPS_HOST} ===")
    plink_run(f"echo {value} > {REMOTE_FILE}")
    result = plink_run(f"cat {REMOTE_FILE}")
    status = "включена" if result.strip().lower() != "false" else "выключена"
    print(f"=== Готово: история {status} ===")


if __name__ == "__main__":
    main()
