"""
Применяет 001_init.sql — создаёт БД duathlon_222 и таблицы на проде.

paramiko (прямой сокет из python.exe) блокируется файрволом на порт 22 в
этом окружении — используем plink.exe (PuTTY) как отдельный процесс, см.
deploy/ssh_apply_siberman_migration.py (тот же паттерн).

Usage: python deploy/ssh_apply_duathlon222_migration.py
"""
import subprocess
from pathlib import Path
from deploy._vps_config import VPS_HOST, VPS_USER, VPS_PASSWORD

ROOT = Path(__file__).resolve().parent.parent
SQL_FILE = ROOT / "src" / "duathlon222" / "migrations" / "001_init.sql"


def plink_run(cmd: str, stdin_bytes: bytes = None, timeout: int = 60) -> str:
    args = ["plink.exe", "-ssh", "-batch", "-pw", VPS_PASSWORD, f"{VPS_USER}@{VPS_HOST}", cmd]
    r = subprocess.run(args, input=stdin_bytes, capture_output=True, timeout=timeout)
    out = r.stdout.decode(errors="replace").strip()
    err = r.stderr.decode(errors="replace").strip()
    if out:
        print(out)
    if r.returncode != 0:
        raise RuntimeError(f"plink command failed (exit {r.returncode}): {cmd[:120]}\n{err}")
    return out


def main():
    print(f"=== Applying {SQL_FILE.name} on {VPS_HOST} ===")
    sql_bytes = SQL_FILE.read_bytes()

    plink_run("mysql -u root", stdin_bytes=sql_bytes)

    print("\n=== Tables ===")
    plink_run('mysql -u root duathlon_222 -e "SHOW TABLES;"')

    print("\n=== participants schema ===")
    plink_run('mysql -u root duathlon_222 -e "DESCRIBE participants;"')

    print("\n=== Migration OK ===")


if __name__ == "__main__":
    main()
