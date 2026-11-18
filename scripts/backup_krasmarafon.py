"""Run the Krasmarafon backup jobs on the independent Windows backup host."""

import argparse
import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from urllib.request import Request, urlopen


SCRIPT_DIR = Path(__file__).resolve().parent
REPO = SCRIPT_DIR.parent
LOG = logging.getLogger("km-backup")
UTC = timezone.utc
SOURCES = ("mysql", "tilda", "pickup")
BUNDLE_NAME = re.compile(r"^\d{8}T\d{6}(?:\d{6})?Z(?:-[a-f0-9]{8})?$")


def external_path(value):
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise ValueError("Нужен абсолютный путь")
    path = path.resolve()
    if path == Path(path.anchor) or path == REPO or REPO in path.parents:
        raise ValueError("Данные резервирования должны находиться вне репозитория")
    return path


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def stamp(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Дата должна включать часовой пояс")
    return result.astimezone(UTC)


def current_bundles(parent):
    items = []
    if parent.is_dir():
        for path in parent.iterdir():
            if not path.is_dir() or path.is_symlink() or not BUNDLE_NAME.fullmatch(path.name):
                continue
            try:
                info = read_json(path / "manifest.json")
                captured = stamp(info["captured_at"])
                if parent.name == "pickup":
                    captured = min(captured, stamp(info["mysql_captured_at"]),
                                   stamp(info["crm_captured_at"]))
            except (OSError, ValueError, TypeError, AttributeError, KeyError):
                continue
            if captured <= datetime.now(UTC) + timedelta(minutes=5):
                items.append((captured, path, info))
    return sorted(items, key=lambda item: (item[0], item[1].name))


@contextmanager
def job_lock(storage):
    with (storage / ".runner.lock").open("a+b") as handle:
        if os.name == "nt":
            import msvcrt

            handle.seek(0)
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                yield False
                return
        else:
            import fcntl

            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                yield False
                return
        # Closing the handle releases the OS lock even after an interrupted run.
        yield True


def run_step(script, command, config_path, *args):
    try:
        result = subprocess.run(
            [sys.executable, str(SCRIPT_DIR / script), command,
             "--config", str(config_path), *map(str, args)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3600,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        LOG.error("%s %s: запуск не завершился", script, command)
        return False
    if result.returncode:
        LOG.error("%s %s: код %s", script, command, result.returncode)
        return False
    LOG.info("%s %s: завершено", script, command)
    return True


def file_hash(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def verify_artifacts(path, manifest):
    files = manifest.get("artifacts")
    if files is None and path.parent.name == "mysql":
        files = [{"file": "dump.sql.gz", "sha256": manifest["sha256"]}]
    if not files:
        raise ValueError("Архив без файлов")
    for entry in files:
        name = entry["file"]
        if not re.fullmatch(r"[a-zA-Z0-9_-]+\.(?:csv|xlsx|sql\.gz)", name):
            raise ValueError("Недопустимое имя файла архива")
        artifact = path / name
        if artifact.is_symlink() or file_hash(artifact) != entry["sha256"]:
            raise ValueError("Ошибка проверки целостности")


def copy_verified(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as handle:
        pending = Path(handle.name)
    try:
        shutil.copyfile(source, pending)
        if file_hash(source) != file_hash(pending):
            raise ValueError("Ошибка проверки копии")
        os.replace(pending, destination)
    finally:
        pending.unlink(missing_ok=True)


def mirror_bundles(storage, mirror):
    success = True
    for name in SOURCES:
        parent = mirror / name
        parent.mkdir(parents=True, exist_ok=True)
        for _, source, manifest in current_bundles(storage / name):
            destination = parent / source.name
            if destination.exists():
                continue
            try:
                with tempfile.TemporaryDirectory(prefix=".mirror-", dir=parent) as temp:
                    stage = Path(temp) / "bundle"
                    stage.mkdir()
                    for item in source.iterdir():
                        if item.is_symlink() or not item.is_file():
                            raise ValueError("Неожиданный объект в архиве")
                        copy_verified(item, stage / item.name)
                    verify_artifacts(source, manifest)
                    stage.rename(destination)
            except (OSError, ValueError):
                LOG.error("Не удалось скопировать архив %s на второй носитель", name)
                success = False
    return success


def prune(parent, days):
    cutoff = datetime.now(UTC) - timedelta(days=days)
    for captured, path, _ in current_bundles(parent)[:-1]:
        if captured < cutoff:
            if path.resolve().parent != parent.resolve():
                raise ValueError("Неожиданный путь при очистке")
            shutil.rmtree(path)


def send_alert(message):
    url = os.environ.get("KM_BACKUP_ALERT_URL")
    token = os.environ.get("KM_BACKUP_ALERT_TOKEN")
    if not url or not url.startswith("https://") or not token:
        LOG.error("Канал уведомлений KM_BACKUP_ALERT_URL/TOKEN не настроен")
        return False
    try:
        request = Request(url, data=message.encode("utf-8"), method="POST",
                          headers={"Authorization": f"Bearer {token}"})
        with urlopen(request, timeout=10):
            return True
    except (OSError, ValueError):
        LOG.error("Не удалось отправить уведомление")
        return False


def delivery_times(paths):
    times = []
    for value in paths:
        try:
            info = read_json(external_path(value) / ".pickup-version.json")
            times.append(stamp(info["captured_at"]))
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            return []
    return times


def latest_verified_time(parent):
    for captured, path, manifest in reversed(current_bundles(parent)):
        try:
            verify_artifacts(path, manifest)
        except (OSError, ValueError, KeyError, TypeError):
            LOG.error("Повреждена копия %s от %s", parent.name, captured.isoformat())
            continue
        return captured
    return None


def check_age(storage, destinations, mirror=None):
    now = datetime.now(UTC)
    healthy = True
    timestamps = {}
    for name in SOURCES:
        timestamps[name] = latest_verified_time(storage / name)
        if mirror is not None:
            timestamps[f"mirror-{name}"] = latest_verified_time(mirror / name)
    if destinations:
        times = delivery_times(destinations)
        timestamps["pickup-delivery"] = min(times) if times else None
    for name, captured in timestamps.items():
        if captured is not None:
            hours = (now - captured).total_seconds() / 3600
            if hours < 16:
                (storage / f".alert-{name}").unlink(missing_ok=True)
                continue
            level = "24" if hours >= 24 else "16"
            message = f"Красмарафон: резерв {name}, возраст {hours:.0f} ч."
        else:
            level = "missing"
            message = f"Красмарафон: отсутствует завершённая копия {name}."
        LOG.error("%s", message)
        healthy = False
        marker = storage / f".alert-{name}"
        if (not marker.exists() or marker.read_text(encoding="utf-8") != level) and send_alert(message):
            marker.write_text(level, encoding="utf-8")
    return healthy


def cycle(config_path, storage):
    started = datetime.now(UTC)
    mysql_ok = run_step("backup_mysql.py", "capture", config_path)
    tilda_ok = run_step("backup_tilda.py", "capture", config_path)
    if not (mysql_ok and tilda_ok):
        return False
    tilda = current_bundles(storage / "tilda")
    if not tilda or tilda[-1][0] < started:
        return False
    with tempfile.TemporaryDirectory(prefix=".pickup-", dir=storage) as temp:
        rows = Path(temp) / "mysql-rows.json"
        if not run_step("backup_mysql.py", "pickup-rows", config_path, "--output", rows):
            return False
        return run_step("backup_pickup.py", "build", config_path, "--mysql-json", rows,
                        "--crm-bundle", tilda[-1][1], "--output", storage / "pickup")


def publish(storage, destination):
    bundles = current_bundles(storage / "pickup")
    if not bundles:
        raise ValueError("Готовый список отсутствует")
    captured, source, manifest = bundles[-1]
    if datetime.now(UTC) - captured >= timedelta(hours=24):
        raise ValueError("Возраст списка превышает 24 часа")
    verify_artifacts(source, manifest)
    files = []
    for entry in manifest["artifacts"]:
        name = entry["file"]
        if not re.fullmatch(r"(STARTLIST|JOURNAL)-[a-z0-9_-]+\.xlsx", name):
            raise ValueError("Недопустимое имя списка")
        path = source / name
        files.append(path)
    if not any(path.name.startswith("STARTLIST-") for path in files):
        raise ValueError("В архиве нет списков XLSX")
    destination.mkdir(parents=True, exist_ok=True)
    for path in files:
        target = destination / path.name
        if path.name.startswith("STARTLIST-") or not target.exists():
            copy_verified(path, target)
    with tempfile.TemporaryDirectory(prefix=".delivery-", dir=destination) as temp:
        marker = Path(temp) / "version.json"
        marker.write_text(json.dumps({"captured_at": captured.isoformat()}), encoding="utf-8")
        os.replace(marker, destination / ".pickup-version.json")


def configured_path(storage, value):
    path = external_path(value)
    if storage == path or storage in path.parents or path in storage.parents:
        raise ValueError("Каталоги резервирования должны быть независимыми")
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("cycle", "monitor", "dev", "publish"))
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--restore", action="store_true")
    args = parser.parse_args()
    if args.restore and args.action != "dev":
        parser.error("--restore применим только к dev")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        config_path = external_path(args.config)
        config = read_json(config_path)
        storage = external_path(config["storage"])
        runner = config.get("runner", {})
        destinations = runner.get("pickup_destinations", [])
        if not isinstance(destinations, list):
            raise ValueError("pickup_destinations должен быть списком путей")
        storage.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            storage / f"{args.action}.log", maxBytes=1024 * 1024, backupCount=3,
            encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        LOG.addHandler(handler)
        if args.action == "monitor":
            mirror = configured_path(storage, runner["mirror"]) if runner.get("mirror") else None
            return 0 if check_age(storage, destinations, mirror) else 1
        with job_lock(storage) as acquired:
            if not acquired:
                LOG.error("Уже выполняется задача резервирования")
                return 1
            if args.action == "dev":
                flags = ("--restore",) if args.restore else ()
                return 0 if run_step("backup_mysql.py", "dev", config_path, *flags) else 1
            if args.action == "publish":
                if not destinations:
                    raise ValueError("Не заданы папки выдачи")
                for path in destinations:
                    publish(storage, configured_path(storage, path))
                return 0
            success = cycle(config_path, storage)
            if success:
                for path in destinations:
                    try:
                        publish(storage, configured_path(storage, path))
                    except (OSError, ValueError, KeyError):
                        LOG.error("Не удалось обновить одну из папок выдачи")
                        success = False
            mirror = None
            if runner.get("mirror"):
                mirror = configured_path(storage, runner["mirror"])
                if not mirror.is_dir():
                    LOG.error("Второй носитель недоступен")
                    success = False
                else:
                    success = mirror_bundles(storage, mirror) and success
            if success:
                for parent in (storage, mirror):
                    if parent is not None:
                        for name in SOURCES:
                            prune(parent / name, 30)
            return 0 if success else 1
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        LOG.error("Ошибка резервирования (%s). Проверьте конфигурацию и доступность дисков.",
                  type(error).__name__)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
