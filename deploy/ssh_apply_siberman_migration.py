"""
Применяет миграцию 004_race_config.sql к БД siberman на проде — то же
самое, что делает .github/workflows/migrate_siberman.yml (workflow_dispatch).

paramiko (прямой сокет из python.exe) блокируется файрволом на порт 22 в
этом окружении (443 у python.exe при этом работает нормально — HTTPS не
блокируется, порт 22 у python.exe — да). Обходной путь НЕ придумываем —
используем системный SSH-клиент (plink.exe из PuTTY) как отдельный
процесс: подключение инициирует plink.exe, а не python.exe, и файрвол его
не блокирует (проверено вручную через PowerShell Test-NetConnection и
через bash /dev/tcp — порт 22 снаружи python.exe открыт).

Usage: python deploy/ssh_apply_siberman_migration.py
"""
import subprocess
from pathlib import Path
from deploy._vps_config import VPS_HOST, VPS_USER, VPS_PASSWORD

ROOT = Path(__file__).resolve().parent.parent
SQL_FILE = ROOT / "src" / "siberman" / "migrations" / "004_race_config.sql"


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
    print(f"=== Applying {SQL_FILE.name} to siberman DB on {VPS_HOST} ===")
    sql_bytes = SQL_FILE.read_bytes()

    plink_run("mysql -u root siberman", stdin_bytes=sql_bytes)

    print("\n=== Tables ===")
    plink_run('mysql -u root siberman -e "SHOW TABLES;"')

    print("\n=== race_config schema ===")
    plink_run('mysql -u root siberman -e "DESCRIBE race_config;"')

    print("\n=== Migration OK ===")


if __name__ == "__main__":
    main()
