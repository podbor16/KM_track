"""Сохраняет CSV штатного расширенного экспорта Tilda CRM вне репозитория."""

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit


REPO = Path(__file__).resolve().parents[1]
NAME = re.compile(r"[a-z][a-z0-9_-]{0,63}", re.ASCII)


class BackupError(Exception):
    pass


def outside_repo(value, field):
    if not isinstance(value, str) or not Path(value).is_absolute():
        raise BackupError(f"{field} должен быть абсолютным путём вне Git")
    path = Path(value).resolve()
    if path.is_relative_to(REPO):
        raise BackupError(f"{field} должен находиться вне Git")
    return path


def is_crm_url(value):
    if not isinstance(value, str):
        return False
    parsed = urlsplit(value)
    return (
        parsed.scheme == "https"
        and parsed.netloc.lower() in {"crm.tilda.cc", "crm.tilda.ru"}
    )


def normalized_headers(values):
    return [value.strip().casefold() for value in values]


def load_config(path):
    with path.open(encoding="utf-8-sig") as file:
        root = json.load(file)
    if not isinstance(root, dict) or not isinstance(root.get("tilda"), dict):
        raise BackupError("В JSON требуется раздел tilda")
    cfg = root["tilda"]
    storage = outside_repo(root.get("storage"), "storage")
    state = outside_repo(cfg.get("storage_state"), "tilda.storage_state")
    if not is_crm_url(cfg.get("login_url")):
        raise BackupError("tilda.login_url должен вести на HTTPS домен CRM Tilda")
    exports = cfg.get("exports")
    if not isinstance(exports, list) or not exports:
        raise BackupError("Укажите хотя бы один экспорт в tilda.exports")
    seen = set()
    for export in exports:
        if not isinstance(export, dict):
            raise BackupError("Элемент tilda.exports должен быть объектом")
        name = export.get("name")
        if not isinstance(name, str) or not NAME.fullmatch(name) or name in seen:
            raise BackupError("Недопустимое или повторяющееся имя экспорта CRM")
        seen.add(name)
        if not is_crm_url(export.get("url")):
            raise BackupError(f"{name}: url должен вести на HTTPS домен CRM Tilda")
        for field in ("ready_selector", "download_selector"):
            if not isinstance(export.get(field), str) or not export[field].strip():
                raise BackupError(f"{name}: отсутствует {field}")
        if export.get("delimiter", ";") not in (",", ";"):
            raise BackupError(f"{name}: delimiter должен быть запятой или точкой с запятой")
        if not isinstance(export.get("allow_empty", False), bool):
            raise BackupError(f"{name}: allow_empty должен быть логическим значением")
        if "expected_rows_selector" in export and (
            not isinstance(export["expected_rows_selector"], str)
            or not export["expected_rows_selector"].strip()
        ):
            raise BackupError(f"{name}: expected_rows_selector должен быть непустым")
        headers = export.get("required_headers")
        if not isinstance(headers, list) or not headers or not all(
            isinstance(header, str) and header.strip() and "\0" not in header for header in headers
        ):
            raise BackupError(f"{name}: укажите непустой список required_headers")
        steps = export.get("steps", [])
        if not isinstance(steps, list):
            raise BackupError(f"{name}: steps должен быть списком")
        for step in steps:
            if not isinstance(step, dict) or step.get("action") not in ("click", "check", "uncheck", "select"):
                raise BackupError(f"{name}: неизвестное действие")
            if not isinstance(step.get("selector"), str) or not step["selector"].strip():
                raise BackupError(f"{name}: отсутствует selector у действия")
            if step["action"] == "select" and (
                not isinstance(step.get("value"), str) or not step["value"]
            ):
                raise BackupError(f"{name}: select требует value")
    timeout = cfg.get("timeout_seconds", 60)
    if type(timeout) is not int or not 5 <= timeout <= 300:
        raise BackupError("tilda.timeout_seconds должен быть целым числом от 5 до 300")
    channel = cfg.get("browser_channel")
    if channel is not None and channel not in ("chrome", "msedge"):
        raise BackupError("tilda.browser_channel должен быть chrome или msedge")
    return cfg, storage, state


def validate_csv(path, export):
    delimiter = export.get("delimiter", ";")
    maximum_bytes = 100 * 1024**2
    if not 0 < path.stat().st_size <= maximum_bytes:
        raise BackupError("CSV имеет недопустимый размер")
    try:
        with path.open(encoding="utf-8-sig", newline="") as file:
            reader = csv.reader(file, delimiter=delimiter, strict=True)
            headers = normalized_headers(next(reader, []))
            if (
                not headers
                or any(not header or "\0" in header for header in headers)
                or len(set(headers)) != len(headers)
            ):
                raise BackupError("CSV содержит пустые или повторяющиеся заголовки")
            if not set(normalized_headers(export["required_headers"])).issubset(headers):
                raise BackupError("В CSV отсутствуют обязательные колонки")
            rows = 0
            for row in reader:
                if not row:
                    continue
                if len(row) != len(headers) or any("\0" in value for value in row):
                    raise BackupError("CSV содержит строку с неверной структурой")
                if any(value.strip() for value in row):
                    rows += 1
    except (UnicodeError, csv.Error):
        raise BackupError("CSV не читается как выгрузка UTF-8") from None
    if not rows and not export.get("allow_empty", False):
        raise BackupError("CRM вернула пустую выгрузку")
    with path.open("rb") as file:
        checksum = hashlib.file_digest(file, "sha256").hexdigest()
    return {"file": path.name, "name": export["name"], "sha256": checksum, "rows": rows, "delimiter": delimiter}


def assert_crm(page):
    if not is_crm_url(page.url):
        raise BackupError("CRM переадресовала браузер. Проверьте вход и доступ к листу")


def open_export(page, export):
    page.goto(export["url"], wait_until="domcontentloaded")
    assert_crm(page)
    page.locator(export["ready_selector"]).wait_for(state="visible")
    assert_crm(page)


def download_export(page, export, path):
    open_export(page, export)
    for step in export.get("steps", []):
        assert_crm(page)
        locator = page.locator(step["selector"])
        action = step["action"]
        if action == "select":
            locator.select_option(value=step["value"])
        elif action == "check":
            locator.check()
        elif action == "uncheck":
            locator.uncheck()
        else:
            locator.click()
    assert_crm(page)
    expected_rows = None
    if selector := export.get("expected_rows_selector"):
        raw_count = page.locator(selector).inner_text()
        normalized_count = "".join(raw_count.split())
        if not re.fullmatch(r"[0-9]+", normalized_count):
            raise BackupError("Не удалось прочитать число заявок, выбранных для экспорта")
        expected_rows = int(normalized_count)
    with page.expect_download() as download_event:
        page.locator(export["download_selector"]).click()
    download_event.value.save_as(str(path))
    return expected_rows


def launch_browser(playwright, config, capture, downloads):
    kwargs = {"headless": capture, "downloads_path": str(downloads)}
    if config.get("browser_channel"):
        kwargs["channel"] = config["browser_channel"]
    return playwright.chromium.launch(**kwargs)


def configure_context(context, config):
    context.set_default_timeout(config.get("timeout_seconds", 60) * 1000)


def login(playwright, config, state, browser_error, scratch):
    with closing(launch_browser(playwright, config, capture=False, downloads=scratch)) as browser:
        context = browser.new_context()
        configure_context(context, config)
        page = context.new_page()
        page.goto(config["login_url"], wait_until="domcontentloaded")
        input("Войдите в выделенную учётную запись CRM в браузере и нажмите Enter. ")
        for export in config["exports"]:
            try:
                open_export(page, export)
            except browser_error:
                raise BackupError(f"{export['name']}: не удалось подтвердить вход и доступ к листу") from None
        state.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=state.parent, prefix=".tilda-state-", delete=False) as file:
            temporary = Path(file.name)
        try:
            context.storage_state(path=str(temporary))
            temporary.replace(state)
        finally:
            temporary.unlink(missing_ok=True)
    print("Сессия CRM сохранена")


def capture(playwright, config, storage, state, browser_error):
    if not state.is_file():
        raise BackupError("Файл сеанса CRM отсутствует. Выполните команду login")
    destination = storage / "tilda"
    if destination.resolve() != destination:
        raise BackupError("Каталог tilda должен находиться внутри storage без перенаправления")
    destination.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    version = now.strftime("%Y%m%dT%H%M%S%fZ")
    stage = Path(tempfile.mkdtemp(dir=destination, prefix=".pending-"))
    try:
        artifacts = []
        with closing(launch_browser(playwright, config, capture=True, downloads=stage)) as browser:
            context = browser.new_context(storage_state=str(state), accept_downloads=True)
            configure_context(context, config)
            page = context.new_page()
            for export in config["exports"]:
                name = export["name"]
                path = stage / f"{name}.csv"
                try:
                    expected_rows = download_export(page, export, path)
                    artifact = validate_csv(path, export)
                    if expected_rows is not None and artifact["rows"] != expected_rows:
                        raise BackupError("Число строк CSV не совпадает с числом выбранных заявок в CRM")
                    artifacts.append(artifact)
                except browser_error:
                    raise BackupError(
                        f"{name}: CRM не завершила экспорт. Проверьте вход, доступ и элементы интерфейса"
                    ) from None
                except BackupError as error:
                    raise BackupError(f"{name}: {error}") from None
        manifest = {"kind": "tilda", "captured_at": now.isoformat(), "artifacts": artifacts}
        (stage / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False) + "\n", encoding="utf-8")
        stage.rename(destination / version)
    finally:
        # Путь создаётся mkdtemp внутри каталога этого экспорта.
        if stage.exists() and stage.resolve().parent == destination.resolve():
            shutil.rmtree(stage)
    print(f"CRM: сохранена версия {version}, файлов: {len(artifacts)}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("login", "capture"))
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    try:
        from playwright.sync_api import Error as PlaywrightError, sync_playwright
    except ImportError:
        print("CRM: установите Playwright в окружение резервного копирования", file=sys.stderr)
        return 1
    try:
        config, storage, state = load_config(args.config)
        storage.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=storage, prefix=".tilda-browser-") as scratch:
            # Драйвер Playwright и Chromium создают профили/кэш во временной папке.
            for variable in ("TEMP", "TMP", "TMPDIR"):
                os.environ[variable] = scratch
            with sync_playwright() as playwright:
                if args.operation == "login":
                    login(playwright, config, state, PlaywrightError, scratch)
                else:
                    capture(playwright, config, storage, state, PlaywrightError)
    except BackupError as error:
        print(f"CRM: {error}", file=sys.stderr)
        return 1
    except (OSError, ValueError, EOFError, PlaywrightError):
        print("CRM: проверьте JSON, пути, установку браузера и доступ к файлам", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
