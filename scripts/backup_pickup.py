"""Generate offline pickup lists from an independently saved MySQL and CRM pair."""

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
from pathlib import Path
import re
import sys
from tempfile import TemporaryDirectory
from uuid import uuid4

from openpyxl import Workbook
from openpyxl.styles import Font


IDENTIFIERS = ("transaction_id", "order_id")
MYSQL_FIELDS = {
    "id", "event_name", "event_year", "event_distance", "surname", "name",
    "start_number", "status", "refund", "is_duplicate", *IDENTIFIERS,
}
CRM_REQUIRED = {"surname", "name", "stage", "payment"}
KEY_RE = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}\Z")
UNSAFE_XLSX_CHARS = re.compile(r"[\x00-\x08\x0b-\x0c\x0e-\x1f]")


def value(item):
    return str(item).strip() if item is not None else ""


def normalized(item):
    return " ".join(value(item).casefold().replace("ё", "е").split())


def normalized_distance(item):
    text = normalized(item)
    match = re.fullmatch(r"(\d+(?:[.,]\d+)?)\s*(км|м|km|m)", text)
    if not match:
        return text
    unit = {"km": "км", "m": "м"}.get(match[2], match[2])
    return match[1].replace(",", ".") + " " + unit


def identifier(item):
    result = value(item)
    return "" if result in {"", "0", "NULL"} else result


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def checked_time(raw, now):
    stamped = datetime.fromisoformat(raw)
    if stamped.tzinfo is None or not timedelta(0) <= now - stamped <= timedelta(hours=24):
        raise ValueError("Время источника должно содержать часовой пояс, а копия быть не старше 24 часов")
    return stamped.isoformat()


def load_crm_artifact(bundle, artifact, columns):
    name = artifact["file"]
    if not isinstance(name, str) or Path(name).name != name or not name.endswith(".csv"):
        raise ValueError("Некорректное имя CSV в манифесте CRM")
    path = bundle / name
    if path.resolve().parent != bundle.resolve():
        raise ValueError("Файл CRM находится вне архива")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != artifact["sha256"]:
        raise ValueError("Контрольная сумма CRM не совпадает")
    delimiter = artifact.get("delimiter", ";")
    if delimiter not in {";", ","}:
        raise ValueError("Некорректный разделитель CSV в манифесте CRM")
    csv_rows = csv.DictReader(io.StringIO(raw.decode("utf-8-sig"), newline=""), delimiter=delimiter, strict=True)
    headers = csv_rows.fieldnames or []
    if len(set(headers)) != len(headers) or not set(columns.values()).issubset(headers):
        raise ValueError("Колонки CRM не совпадают с настроенным сопоставлением")
    rows = []
    for row in csv_rows:
        if None in row or None in row.values():
            raise ValueError("Выгрузка CRM содержит строку с неверным числом полей")
        if any(value(cell) for cell in row.values()):
            rows.append({field: value(row[header]) for field, header in columns.items()})
    if len(rows) != artifact["rows"]:
        raise ValueError("Число строк CRM не совпадает с манифестом")
    return rows


def crm_for_event(bundle, artifacts, event, columns):
    from src.krasmarafon.services.tilda_webhook import convert_birthday, parse_products

    rows = []
    for export_name in event["crm_exports"]:
        for row in load_crm_artifact(bundle, artifacts[export_name], columns):
            scope, year = row.get("event_name"), row.get("event_year")
            if row.get("products") and ("event_name" not in columns or "distance" not in columns):
                info = parse_products([row["products"]], birthday=convert_birthday(row.get("birthday", "")))
                if "event_name" not in columns and len(info.get("year_candidates", [])) <= 1:
                    scope, year = info["event_name"], info["event_year"]
                if "distance" not in columns:
                    row["distance"] = info["event_distance"]
            if scope and year:
                if (normalized(scope), year) != (normalized(event["name"]), str(event["year"])):
                    continue
            elif "event_name" in columns or "products" in columns:
                row["_scope_issue"] = True
            rows.append(row)
    return rows


def status_rules(settings):
    rules = {}
    for key in ("mysql_allow", "crm_stage_allow", "crm_stage_block", "crm_payment_allow", "crm_payment_block"):
        configured = settings[key]
        if not isinstance(configured, list):
            raise ValueError("Правила статусов должны быть списками")
        rules[key] = {normalized(item) for item in configured}
        if "" in rules[key] or (key.endswith("_allow") and not rules[key]):
            raise ValueError("Разрешённые значения должны быть заданы явно")
    for prefix in ("crm_stage", "crm_payment"):
        if rules[prefix + "_allow"] & rules[prefix + "_block"]:
            raise ValueError("Статус CRM присутствует одновременно в разрешённых и запрещённых")
    return rules


def candidates_for(row, index):
    matches = {field: index[field].get(identifier(row[field]), set()) for field in IDENTIFIERS}
    tx, order = matches["transaction_id"], matches["order_id"]
    if tx and order:
        return tx & order or tx | order
    return tx or order


def decision_reasons(local, remote, rules, no_bib, repeated_bibs):
    reasons = []
    if local["refund"] not in (0, "0"):
        reasons.append("Возврат или неизвестный признак возврата в KM_track")
    if local["is_duplicate"] not in (0, "0"):
        reasons.append("Дубль или неизвестный признак дубля в KM_track")
    if normalized(local["status"]) not in rules["mysql_allow"]:
        reasons.append("Статус KM_track не подтверждает допуск")
    if not all(value(local[field]) for field in ("surname", "name", "event_distance")):
        reasons.append("Отсутствуют имя, фамилия или дистанция в KM_track")
    bib = value(local["start_number"])
    if bib in repeated_bibs:
        reasons.append("Один номер у нескольких заявок")
    if not re.fullmatch(r"[1-9][0-9]*", bib) and normalized_distance(local["event_distance"]) not in no_bib:
        reasons.append("Стартовый номер не назначен")
    if remote is None:
        return reasons
    for field in IDENTIFIERS:
        if identifier(local[field]) and identifier(remote.get(field)) and identifier(local[field]) != identifier(remote[field]):
            reasons.append("Идентификаторы заявки различаются")
            break
    if any(normalized(local[field]) != normalized(remote[field]) for field in ("surname", "name")):
        reasons.append("Фамилия или имя различаются")
    if remote.get("_scope_issue"):
        reasons.append("Нет события или года в CRM")
    if "distance" in remote and normalized_distance(local["event_distance"]) != normalized_distance(remote["distance"]):
        reasons.append("Дистанция в CRM не совпадает с KM_track")
    for field, label in (("stage", "Этап"), ("payment", "Оплата")):
        current = normalized(remote[field])
        if current in rules[f"crm_{field}_block"]:
            reasons.append(f"{label} CRM запрещает выдачу")
        elif current not in rules[f"crm_{field}_allow"]:
            reasons.append(f"{label} CRM не подтверждает допуск")
    return reasons


def reconcile(local_rows, crm_rows, rules, no_bib):
    index = {field: defaultdict(set) for field in IDENTIFIERS}
    for number, remote in enumerate(crm_rows):
        for field in IDENTIFIERS:
            if key := identifier(remote.get(field)):
                index[field][key].add(number)

    picks = [candidates_for(row, index) for row in local_rows]
    claimed = Counter(number for candidate in picks for number in candidate)
    unambiguous = {next(iter(pick)) for pick in picks if len(pick) == 1}
    bibs = Counter(value(row["start_number"]) for row in local_rows if value(row["start_number"]))
    repeated_bibs = {bib for bib, count in bibs.items() if count > 1}
    ready, review = [], []
    for local, candidates in zip(local_rows, picks):
        matched = len(candidates) == 1 and claimed[next(iter(candidates))] == 1
        remote = crm_rows[next(iter(candidates))] if matched else None
        reasons = decision_reasons(local, remote, rules, no_bib, repeated_bibs)
        if remote is None:
            reasons.append("Неоднозначное сопоставление с CRM" if candidates else "Нет совпадения по идентификатору в CRM")
        entry = (
            f'km:{local["id"]}', value(local["surname"]), value(local["name"]),
            value(local["event_distance"]), value(local["start_number"]),
            remote.get("kit", "") if remote else "",
        )
        if reasons:
            review.append((*entry, "; ".join(reasons)))
        else:
            ready.append((*entry, "Допущен"))

    for number, remote in enumerate(crm_rows):
        if claimed[number] == 1 and number in unambiguous:
            continue
        ref = identifier(remote.get("transaction_id")) or identifier(remote.get("order_id")) or f"строка-{number + 1}"
        reason = "Неоднозначное сопоставление с KM_track" if claimed[number] else "Заявка CRM отсутствует в KM_track"
        review.append((f"crm:{ref}", remote["surname"], remote["name"], remote.get("distance", ""),
                       "", remote.get("kit", ""), reason))
    ready.sort(key=lambda row: (row[4] == "", len(row[4]), row[4], normalized(row[1]), normalized(row[2])))
    return ready, review


def append_text(sheet, values):
    # Store external values as strings, including any leading Excel formula prefix.
    sheet.append([UNSAFE_XLSX_CHARS.sub("", value(item)) for item in values])
    for cell in sheet[sheet.max_row]:
        cell.data_type = "s"


def add_table(book, title, headers, rows, widths):
    sheet = book.create_sheet(title)
    append_text(sheet, headers)
    for cell, width in zip(sheet[1], widths):
        sheet.column_dimensions[cell.column_letter].width = width
        cell.font = Font(bold=True)
    for row in rows:
        append_text(sheet, row)
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    return sheet


def write_workbooks(folder, event, ready, review, mysql_time, crm_time):
    key = event["key"]
    headers = ("Заявка", "Фамилия", "Имя", "Дистанция", "Номер", "Комплект")
    book = Workbook()
    book.remove(book.active)
    info = book.create_sheet("О списке")
    info.column_dimensions["A"].width = 105
    for line in (
        f'{event["name"]} {event["year"]}', f"MySQL: {mysql_time}", f"Tilda CRM: {crm_time}",
        f"Допущено: {len(ready)}. На проверку: {len(review)}.",
        "Отмечайте выдачу в отдельном журнале. Участников с листа «Проверить» направляйте старшему.",
    ):
        append_text(info, (line,))
    add_table(book, "Выдача", (*headers, "Статус"), ready, (22, 25, 25, 18, 12, 26, 20))
    add_table(book, "Проверить", (*headers, "Причина"), review, (22, 25, 25, 18, 12, 26, 90))
    book.save(folder / f"STARTLIST-{key}.xlsx")

    journal = Workbook()
    journal.remove(journal.active)
    add_table(journal, "Журнал выдачи", ("Заявка", "Время выдачи", "Оператор", "Примечание"),
              [], (22, 24, 25, 60))
    journal.save(folder / f"JOURNAL-{key}.xlsx")


def build(config, mysql_json, crm_bundle, output_root):
    """Write an immutable pickup bundle and return its directory."""
    settings = config["pickup"]
    now = datetime.now(timezone.utc)
    source = read_json(mysql_json)
    mysql_time = checked_time(source["captured_at"], now)
    if not isinstance(source["rows"], list) or any(not MYSQL_FIELDS <= row.keys() for row in source["rows"]):
        raise ValueError("Снимок MySQL не содержит обязательных полей")
    mysql_ids = [identifier(row["id"]) for row in source["rows"]]
    if "" in mysql_ids or len(set(mysql_ids)) != len(mysql_ids):
        raise ValueError("Идентификаторы строк MySQL должны быть заполнены и уникальны")
    crm_bundle = Path(crm_bundle)
    crm = read_json(crm_bundle / "manifest.json")
    if crm["kind"] != "tilda":
        raise ValueError("Ожидается архив Tilda")
    crm_time = checked_time(crm["captured_at"], now)
    artifacts = {item["name"]: item for item in crm["artifacts"]}
    if len(artifacts) != len(crm["artifacts"]):
        raise ValueError("Имена выгрузок CRM в архиве повторяются")
    columns = settings["crm_columns"]
    if (not CRM_REQUIRED <= columns.keys() or not columns.keys() & set(IDENTIFIERS)
            or ("event_name" in columns) != ("event_year" in columns)
            or len(set(columns.values())) != len(columns) or any(not value(header) for header in columns.values())):
        raise ValueError("Неверное сопоставление колонок CRM")
    rules = status_rules(settings["status_rules"])
    events = settings["events"]
    keys = [event["key"] for event in events]
    if not keys or len(keys) != len(set(keys)) or any(not KEY_RE.fullmatch(key) for key in keys):
        raise ValueError("Ключи стартов должны быть заполнены, уникальны и безопасны для имени файла")
    event_ids = [(normalized(event["name"]), str(event["year"])) for event in events]
    if len(set(event_ids)) != len(event_ids) or any(not name or not re.fullmatch(r"\d{4}", year) for name, year in event_ids):
        raise ValueError("Нужны уникальные пары названия старта и года")
    export_names = [name for event in events for name in event["crm_exports"]]
    has_scope = "event_name" in columns or "products" in columns
    if not has_scope and len(export_names) != len(set(export_names)):
        raise ValueError("Выгрузка для нескольких стартов должна содержать событие и год или продукт")
    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    target = output_root / f"{now:%Y%m%dT%H%M%SZ}-{uuid4().hex[:8]}"
    manifest_items = []
    with TemporaryDirectory(prefix=".pickup-", dir=output_root) as temporary:
        folder = Path(temporary) / "bundle"
        folder.mkdir()
        for event, (name, year) in zip(events, event_ids):
            exports = event["crm_exports"]
            if not exports or len(set(exports)) != len(exports):
                raise ValueError("Для старта нужны уникальные имена выгрузок CRM")
            local = [
                row for row in source["rows"]
                if (normalized(row["event_name"]), value(row["event_year"])) == (name, year)
            ]
            remote = crm_for_event(crm_bundle, artifacts, event, columns)
            no_bib = {normalized_distance(distance) for distance in event.get("no_bib_distances", [])}
            ready, review = reconcile(local, remote, rules, no_bib)
            write_workbooks(folder, event, ready, review, mysql_time, crm_time)
            for kind, prefix in (("startlist", "STARTLIST"), ("journal", "JOURNAL")):
                file = f'{prefix}-{event["key"]}.xlsx'
                manifest_items.append({"kind": kind, "event": event["key"], "file": file,
                                       "sha256": hashlib.sha256((folder / file).read_bytes()).hexdigest()})
        manifest = {"kind": "pickup", "captured_at": now.isoformat(), "mysql_captured_at": mysql_time,
                    "crm_captured_at": crm_time, "artifacts": manifest_items}
        (folder / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        folder.rename(target)
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["build"])
    for option in ("--config", "--mysql-json", "--crm-bundle", "--output"):
        parser.add_argument(option, type=Path, required=True)
    args = parser.parse_args()
    try:
        print(build(read_json(args.config), args.mysql_json, args.crm_bundle, args.output))
    except (ValueError, KeyError, TypeError, OSError, csv.Error):
        # Source values and raw exception details can contain personal data.
        print("Сборка списка для выдачи не удалась. Проверьте конфигурацию, источники и их свежесть.",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    if not __package__:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    raise SystemExit(main())
