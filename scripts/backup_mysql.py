"""Read-only MySQL capture and explicitly authorised recovery to a dev slot."""

import argparse
import gzip
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID


DATABASE = "krasmarafon"
DATE_KEY = "%Y%m%dT%H%M%S%fZ"
TIMEOUT = 1800
ROOT = Path(__file__).resolve().parents[1]
PICKUP_COLUMNS = (
    "id", "order_id", "transaction_id", "surname", "name",
    "event_name", "event_year", "event_distance", "start_number",
    "status", "refund", "is_duplicate", "source", "products",
)
INVENTORY = f"""
SELECT CONCAT('table:', HEX(TABLE_NAME), ':', TABLE_TYPE)
  FROM information_schema.TABLES WHERE TABLE_SCHEMA = '{DATABASE}'
UNION ALL SELECT CONCAT('trigger:', HEX(TRIGGER_NAME))
  FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA = '{DATABASE}'
UNION ALL SELECT CONCAT('routine:', HEX(ROUTINE_NAME), ':', ROUTINE_TYPE)
  FROM information_schema.ROUTINES WHERE ROUTINE_SCHEMA = '{DATABASE}'
UNION ALL SELECT CONCAT('event:', HEX(EVENT_NAME))
  FROM information_schema.EVENTS WHERE EVENT_SCHEMA = '{DATABASE}';
"""


class BackupError(Exception):
    pass


def utc_now():
    return datetime.now(timezone.utc)


def absolute_path(value):
    original = Path(value)
    if not original.is_absolute():
        raise BackupError("Укажите абсолютные пути в конфигурации.")
    return original.resolve()


def read_config(path):
    config = json.loads(path.read_text(encoding="utf-8-sig"))
    storage = absolute_path(config["storage"])
    if storage.is_relative_to(ROOT):
        raise BackupError("Каталог копий должен быть вне репозитория.")
    return storage, config["mysql"]


def connection(settings, *, local=False):
    host = "127.0.0.1" if local else settings["host"]
    if local and settings.get("host", host) != host:
        raise BackupError("Восстановление возможно только на 127.0.0.1.")
    port = settings["port"]
    if type(port) is not int or not 1 <= port <= 65535:
        raise BackupError("Некорректный порт MySQL.")
    expected_uuid = str(UUID(settings["server_uuid"]))
    defaults_path = absolute_path(settings["defaults_file"])
    # Accept only a dedicated password file. Option files can otherwise inject
    # client commands or silently change the connection target.
    defaults = defaults_path.read_text(encoding="utf-8").splitlines()
    lines = [line.strip() for line in defaults if line.strip() and not line.lstrip().startswith(("#", ";"))]
    if (
        len(lines) != 2
        or lines[0] != "[client]"
        or not re.fullmatch(r"password\s*=\s*[^\r\n]+", lines[1])
    ):
        raise BackupError("Файл MySQL должен содержать только секцию [client] и строку password.")
    mode = settings.get("tls_mode", "DISABLED" if host == "127.0.0.1" else "VERIFY_IDENTITY")
    if mode not in {"DISABLED", "VERIFY_IDENTITY"} or mode == "DISABLED" and host != "127.0.0.1":
        raise BackupError("Для прямого подключения к MySQL требуется TLS VERIFY_IDENTITY.")
    options = [
        f"--defaults-file={defaults_path}", "--protocol=TCP", f"--host={host}",
        f"--port={port}", f"--user={settings['user']}", f"--ssl-mode={mode}",
        "--default-character-set=utf8mb4",
    ]
    if settings.get("tls_ca"):
        options.append(f"--ssl-ca={absolute_path(settings['tls_ca'])}")
    return options, expected_uuid


def run_mysql(binary, options, *, raw_input=None, stdin=None, stdout=subprocess.PIPE):
    # Never forward SQL, client diagnostics or connection credentials to logs.
    # Ignore inherited client controls including alternate login paths.
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.upper().startswith(("MYSQL_", "MARIADB_"))
    }
    with tempfile.TemporaryDirectory(prefix="km-mysql-client-") as temp:
        env["MYSQL_TEST_LOGIN_FILE"] = str(Path(temp) / "unused-login-path.cnf")
        try:
            completed = subprocess.run(
                [str(absolute_path(binary)), *options], input=raw_input, stdin=stdin,
                stdout=stdout, stderr=subprocess.DEVNULL, timeout=TIMEOUT, env=env,
                check=False, shell=False,
            )
        except subprocess.TimeoutExpired:
            raise BackupError("Истекло время ожидания клиента MySQL.") from None
    if completed.returncode:
        raise BackupError(f"Клиент MySQL завершился с кодом {completed.returncode}.")
    return completed.stdout


def read_sql(config, options, sql):
    return run_mysql(
        config["client"], [*options, "--batch", "--skip-column-names", "--raw", "--local-infile=0", "--connect-timeout=10",
                           "--execute", sql],
    ).decode("utf-8").split("\n")


def source_inventory(config, options, expected_uuid):
    engines_query = (
        f"SELECT DISTINCT COALESCE(ENGINE, '') FROM information_schema.TABLES "
        f"WHERE TABLE_SCHEMA='{DATABASE}' AND TABLE_TYPE='BASE TABLE';"
    )
    rows = read_sql(config, options, "SELECT @@server_uuid;" + engines_query + INVENTORY)
    if rows[0].strip().lower() != expected_uuid:
        raise BackupError("UUID исходного сервера MySQL не совпадает.")
    engines = {row.strip().lower() for row in rows[1:] if row.strip() and ":" not in row}
    if engines != {"innodb"}:
        raise BackupError("Дамп требует видимых базовых таблиц только с движком InnoDB.")
    return sorted(row.strip() for row in rows[1:] if ":" in row)


def digest(path):
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def write_json(path, value):
    with path.open("w", encoding="utf-8", newline="\n") as file:
        json.dump(value, file, ensure_ascii=False)
        file.write("\n")
        file.flush()
        os.fsync(file.fileno())


def verify_dump(bundle):
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    path = bundle / "dump.sql.gz"
    if (
        not isinstance(manifest, dict)
        or manifest.get("format_version") != 1
        or manifest.get("database") != DATABASE
        or not isinstance(manifest.get("inventory"), list)
        or not manifest["inventory"]
        or path.stat().st_size != manifest.get("size_bytes")
        or digest(path) != manifest.get("sha256")
    ):
        raise BackupError("Проверка манифеста дампа не пройдена.")
    captured = datetime.fromisoformat(manifest["captured_at"])
    if captured.tzinfo is None or captured > utc_now():
        raise BackupError("Некорректное время в манифесте дампа.")
    UUID(manifest["source_uuid"])
    with gzip.open(path, "rb") as zipped:
        header = zipped.read(128)
        if not header.startswith(b"-- MySQL dump"):
            raise BackupError("Файл не содержит ожидаемый заголовок mysqldump.")
        while zipped.read(1024 * 1024):
            pass
    return manifest


def capture(storage, config):
    options, expected_uuid = connection(config["source"])
    target = storage / "mysql"
    target.mkdir(parents=True, exist_ok=True)
    inventory = source_inventory(config, options, expected_uuid)
    started = utc_now()
    with tempfile.TemporaryDirectory(prefix=".pending-", dir=target) as temp:
        staging = Path(temp)
        raw_path = staging / "dump.sql"
        with raw_path.open("wb") as raw:
            run_mysql(
                config["dump"], [
                    *options, "--single-transaction", "--quick", "--routines", "--triggers", "--events",
                    "--no-tablespaces", "--set-gtid-purged=OFF", "--skip-lock-tables", "--hex-blob",
                    "--databases", DATABASE,
                ],
                stdout=raw,
            )
        if source_inventory(config, options, expected_uuid) != inventory:
            raise BackupError("Состав объектов схемы изменился во время создания копии.")
        dump = staging / "dump.sql.gz"
        with raw_path.open("rb") as raw, gzip.open(dump, "wb", compresslevel=6) as zipped:
            shutil.copyfileobj(raw, zipped)
        raw_path.unlink()
        manifest = {
            "format_version": 1,
            "captured_at": started.isoformat(),
            "database": DATABASE,
            "sha256": digest(dump),
            "size_bytes": dump.stat().st_size,
            "table_count": sum(item.endswith(":BASE TABLE") for item in inventory),
            "inventory": inventory,
            "source_uuid": expected_uuid,
        }
        write_json(staging / "manifest.json", manifest)
        verify_dump(staging)
        staging.rename(target / started.strftime(DATE_KEY))


def pickup_rows(storage, config, output):
    output = output.resolve()
    if not output.is_relative_to(storage) or output == storage:
        raise BackupError("Вывод списка должен находиться внутри каталога копий.")
    options, expected_uuid = connection(config["source"])
    columns = ", ".join(f"'{name}', `{name}`" for name in PICKUP_COLUMNS)
    started = utc_now()
    sql = (
        "SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;"
        "START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY;"
        "SELECT @@server_uuid;"
        f"SELECT JSON_OBJECT({columns}) FROM `{DATABASE}`.`leads` "
        f"WHERE @@server_uuid = '{expected_uuid}' ORDER BY id; COMMIT;"
    )
    raw_rows = read_sql(config, options, sql)
    if raw_rows[0].strip().lower() != expected_uuid:
        raise BackupError("UUID исходного сервера MySQL не совпадает.")
    rows = [json.loads(row) for row in raw_rows[1:] if row]
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".pickup-", dir=output.parent) as temp:
        path = Path(temp) / "pickup.json"
        write_json(path, {"captured_at": started.isoformat(), "rows": rows})
        path.replace(output)


def newest_dump(storage):
    source = storage / "mysql"
    invalid = False
    if source.is_dir():
        for candidate in sorted(source.iterdir(), reverse=True):
            if not candidate.is_dir() or not re.fullmatch(r"\d{8}T\d{12}Z", candidate.name):
                continue
            try:
                manifest = verify_dump(candidate)
            except (BackupError, OSError, ValueError, KeyError, EOFError, zlib.error):
                invalid = True
            else:
                if invalid:
                    print("MySQL: более свежая копия повреждена. Используется предыдущая проверенная версия.",
                          file=sys.stderr)
                return candidate, manifest
    raise BackupError("Ни одной проверенной копии MySQL не найдено.")


def archive_dev(storage, source, manifest):
    root = storage / "mysql-dev"
    root.mkdir(parents=True, exist_ok=True)
    target = root / source.name
    if target.exists():
        if verify_dump(target) != manifest:
            raise BackupError("Запись dev-архива с таким именем не совпадает с источником.")
        return
    with tempfile.TemporaryDirectory(prefix=".pending-", dir=root) as temp:
        staging = Path(temp)
        for name in ("dump.sql.gz", "manifest.json"):
            shutil.copyfile(source / name, staging / name)
        verify_dump(staging)
        staging.rename(target)


def prune_dev(storage, keep):
    root = storage / "mysql-dev"
    if root.resolve() != root or not root.is_dir():
        raise BackupError("Ротация возможна только внутри локального каталога dev-архива.")
    cutoff = utc_now() - timedelta(days=30)
    for candidate in root.iterdir():
        if candidate.name == keep or not re.fullmatch(r"\d{8}T\d{12}Z", candidate.name):
            continue
        if candidate.resolve() != candidate or not candidate.is_dir():
            continue
        try:
            captured = datetime.strptime(candidate.name, DATE_KEY).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if captured < cutoff:
            shutil.rmtree(candidate)


def restore(storage, config, source, manifest, slot):
    options, expected_uuid = connection(config[slot], local=True)
    if expected_uuid in {str(UUID(config["source"]["server_uuid"])), manifest["source_uuid"]}:
        raise BackupError("Исходный и локальный экземпляры должны иметь разные UUID.")
    check = (
        f"@@server_uuid = '{expected_uuid}' AND @@event_scheduler IN ('OFF', 'DISABLED') "
        f"AND NOT EXISTS (SELECT 1 FROM information_schema.SCHEMATA WHERE SCHEMA_NAME='{DATABASE}')"
    )
    if read_sql(config, options, f"SELECT IF({check}, 1, 0);")[0].strip() != "1":
        raise BackupError("Восстановление требует пустого локального слота и выключенного планировщика.")
    # Repeat the safety guard in the very same session that can write SQL.
    # The mysql client terminates on the deliberate error unless --force is used.
    guard = (
        f"SET @backup_lock = GET_LOCK('km_backup_restore_{DATABASE}', 0);\n"
        f"SET @backup_guard = IF(@backup_lock = 1 AND {check}, 'SELECT 1', 'INVALID BACKUP RESTORE TARGET');\n"
        "PREPARE backup_guard FROM @backup_guard;\n"
        "EXECUTE backup_guard;\nDEALLOCATE PREPARE backup_guard;\n"
    ).encode("ascii")
    storage.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryFile(dir=storage) as sql:
        sql.write(guard)
        with gzip.open(source / "dump.sql.gz", "rb") as zipped:
            shutil.copyfileobj(zipped, sql)
        sql.seek(0)
        run_mysql(
            config["client"], [*options, "--binary-mode", "--batch", "--local-infile=0", "--connect-timeout=10"],
            stdin=sql, stdout=subprocess.DEVNULL,
        )
    restored = read_sql(config, options, "SELECT @@server_uuid;" + INVENTORY)
    if restored[0].strip().lower() != expected_uuid or sorted(row.strip() for row in restored[1:] if row) != manifest["inventory"]:
        raise BackupError("Объекты восстановленной БД не совпадают с манифестом.")
    print(f"Изолированный снимок проверен на порту {config[slot]['port']}.")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("capture", "pickup-rows", "dev", "recover"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("--config", required=True, type=Path)
        if command == "pickup-rows":
            subparser.add_argument("--output", required=True, type=Path)
        if command == "recover":
            subparser.add_argument("--bundle", required=True, type=Path)
        if command in ("dev", "recover"):
            subparser.add_argument("--restore", action="store_true", required=(command == "recover"),
                                   help="Восстановить в заранее выделенный пустой локальный экземпляр.")
    args = parser.parse_args(argv)
    try:
        storage, config = read_config(args.config)
        if args.command == "capture":
            capture(storage, config)
        elif args.command == "pickup-rows":
            pickup_rows(storage, config, args.output)
        elif args.command == "dev":
            source, manifest = newest_dump(storage)
            archive_dev(storage, source, manifest)
            prune_dev(storage, source.name)
            if args.restore:
                restore(storage, config, source, manifest, "dev")
        else:
            source = args.bundle.resolve()
            restore(storage, config, source, verify_dump(source), "recovery")
    except BackupError as exc:
        print(f"MySQL: {exc}", file=sys.stderr)
        return 1
    except (KeyError, TypeError, ValueError, OSError, EOFError, zlib.error):
        print("MySQL: недоступный файл, некорректная конфигурация или формат данных.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
