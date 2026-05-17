"""
Управление загрузчиком результатов (load_race_results.py) на VPS через SSH.

Использование:
  python deploy/ssh_loader.py setup              # установить service + run_loader.sh (один раз)
  python deploy/ssh_loader.py init vesna_5km    # синк конфигов + --init + старт continuous
  python deploy/ssh_loader.py start vesna_5km   # только systemctl start
  python deploy/ssh_loader.py stop vesna_5km    # systemctl stop
  python deploy/ssh_loader.py status            # все активные лоадеры + последние строки лога
  python deploy/ssh_loader.py logs vesna_5km    # journalctl последние 50 строк
"""

import os
import sys
import glob
import paramiko
from pathlib import Path

HOST = "89.108.88.104"
USER = "root"
PASSWORD = "shsfzw5fHiQY8v6g"

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOADER_CONFIGS_LOCAL = PROJECT_ROOT / "config" / "loader"
SERVICE_FILE_LOCAL = PROJECT_ROOT / "deploy" / "km_race_loader@.service"
RUN_LOADER_LOCAL = PROJECT_ROOT / "deploy" / "run_loader.sh"

REMOTE_APP_DIR = "/opt/km_track"
REMOTE_LOADER_CONFIGS = f"{REMOTE_APP_DIR}/config/loader"
REMOTE_SERVICE = "/etc/systemd/system/km_race_loader@.service"
REMOTE_RUN_LOADER = f"{REMOTE_APP_DIR}/run_loader.sh"


def connect() -> paramiko.SSHClient:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, password=PASSWORD, timeout=30)
    return client


def run(client: paramiko.SSHClient, cmd: str, timeout: int = 60, show: bool = True) -> str:
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    combined = (out + err).strip()
    if show and combined:
        print(combined)
    return combined


def upload_file(client: paramiko.SSHClient, local: Path, remote: str) -> None:
    sftp = client.open_sftp()
    sftp.put(str(local), remote)
    sftp.close()
    print(f"  ✓ {local.name} → {remote}")


def cmd_setup(client: paramiko.SSHClient) -> None:
    """Установить systemd-сервис и run_loader.sh на VPS (один раз)."""
    print("=== Установка loader на VPS ===")

    # Создать директорию для конфигов
    run(client, f"mkdir -p {REMOTE_LOADER_CONFIGS}")

    # Скопировать файлы
    upload_file(client, SERVICE_FILE_LOCAL, REMOTE_SERVICE)
    upload_file(client, RUN_LOADER_LOCAL, REMOTE_RUN_LOADER)

    # Сделать run_loader.sh исполняемым
    run(client, f"chmod +x {REMOTE_RUN_LOADER}")

    # Синхронизировать все env-файлы конфигов
    _sync_configs(client)

    # Перечитать systemd
    run(client, "systemctl daemon-reload")
    print("✅ Setup завершён. Теперь можно запускать: python deploy/ssh_loader.py init <race>")


def _sync_configs(client: paramiko.SSHClient) -> None:
    """Скопировать все config/loader/*.env на VPS."""
    env_files = list(LOADER_CONFIGS_LOCAL.glob("*.env"))
    if not env_files:
        print("  ⚠️  Нет файлов в config/loader/")
        return
    run(client, f"mkdir -p {REMOTE_LOADER_CONFIGS}", show=False)
    for f in env_files:
        upload_file(client, f, f"{REMOTE_LOADER_CONFIGS}/{f.name}")


def cmd_init(client: paramiko.SSHClient, race: str) -> None:
    """Синк конфигов + --init + старт continuous."""
    print(f"=== Инициализация гонки: {race} ===")

    env_file = LOADER_CONFIGS_LOCAL / f"{race}.env"
    if not env_file.exists():
        print(f"❌ Файл не найден: config/loader/{race}.env")
        sys.exit(1)

    # Синк всех конфигов
    _sync_configs(client)
    run(client, "systemctl daemon-reload", show=False)

    # Запустить --init (одноразово, блокирующий вызов)
    print(f"\n--- Запуск --init для {race} ---")
    init_cmd = (
        f"source /opt/km_track/config/loader/{race}.env && "
        f"/opt/km_track/venv/bin/python /opt/km_track/load_race_results.py "
        f'--config "$LOADER_CONFIG" --distance "$LOADER_DISTANCE" --init'
    )
    run(client, f'bash -c \'{init_cmd}\'', timeout=300)

    # Запустить continuous-сервис
    print(f"\n--- Запуск continuous-сервиса km_race_loader@{race} ---")
    run(client, f"systemctl start km_race_loader@{race}")
    import time; time.sleep(3)
    run(client, f"systemctl status km_race_loader@{race} --no-pager -l | head -8")
    print(f"\n✅ Лоадер запущен. Для проверки логов: python deploy/ssh_loader.py logs {race}")


def cmd_start(client: paramiko.SSHClient, race: str) -> None:
    run(client, f"systemctl start km_race_loader@{race}")
    import time; time.sleep(2)
    run(client, f"systemctl status km_race_loader@{race} --no-pager | head -6")


def cmd_stop(client: paramiko.SSHClient, race: str) -> None:
    run(client, f"systemctl stop km_race_loader@{race}")
    print(f"✅ Лоадер {race} остановлен")


def cmd_status(client: paramiko.SSHClient) -> None:
    print("=== Активные лоадеры ===")
    result = run(client, "systemctl list-units 'km_race_loader@*' --no-pager", show=False)
    if "km_race_loader@" not in result:
        print("  Нет запущенных лоадеров.")
    else:
        print(result)

    print("\n=== Последние логи (все лоадеры) ===")
    run(client, "journalctl -u 'km_race_loader@*' --no-pager -n 20 --no-hostname 2>&1 | tail -20")


def cmd_logs(client: paramiko.SSHClient, race: str) -> None:
    run(client, f"journalctl -u km_race_loader@{race} --no-pager -n 50 --no-hostname 2>&1")


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(0)

    command = args[0]
    client = connect()

    try:
        if command == "setup":
            cmd_setup(client)

        elif command == "init":
            if len(args) < 2:
                print("Укажи имя гонки: python deploy/ssh_loader.py init <race>")
                sys.exit(1)
            cmd_init(client, args[1])

        elif command == "start":
            if len(args) < 2:
                print("Укажи имя гонки: python deploy/ssh_loader.py start <race>")
                sys.exit(1)
            cmd_start(client, args[1])

        elif command == "stop":
            if len(args) < 2:
                print("Укажи имя гонки: python deploy/ssh_loader.py stop <race>")
                sys.exit(1)
            cmd_stop(client, args[1])

        elif command == "status":
            cmd_status(client)

        elif command == "logs":
            if len(args) < 2:
                print("Укажи имя гонки: python deploy/ssh_loader.py logs <race>")
                sys.exit(1)
            cmd_logs(client, args[1])

        else:
            print(f"Неизвестная команда: {command}")
            print(__doc__)
            sys.exit(1)
    finally:
        client.close()


if __name__ == "__main__":
    main()
