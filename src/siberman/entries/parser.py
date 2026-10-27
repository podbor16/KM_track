"""
Заявка на Siberman из формы Тильды: тело вебхука или строка CSV-выгрузки (имена полей одинаковые) → поля
siberman_entries. Не заявка (нет tranid / ФИ / непонятный формат) — BadEntry: повтор не поможет.
"""
import csv
import datetime
import io
from typing import Optional

from src.siberman.persons.applicants import parse_birthdate

STAGES = ("swim", "bike", "run")
RESULTS_FIELD = "Расскажите_о_ваших_результатах"


class BadEntry(ValueError):
    """Тело не превращается в заявку."""


def _clean(v) -> str:
    return " ".join(str(v if v is not None else "").split())


def _text(v) -> str:
    return str(v if v is not None else "").strip()


def format_of(raw: str) -> Optional[str]:
    if raw.startswith("Индивид"):
        return "individual"
    if raw.startswith("Эстафет"):
        return "relay"
    return None


def is_test_ping(body: dict) -> bool:
    """Тильда при подключении вебхука шлёт test=test."""
    return _clean(body.get("test")) == "test"


def parse_entry(body: dict, today: datetime.date) -> dict:
    tranid = _clean(body.get("tranid"))
    if not tranid:
        raise BadEntry("нет tranid")
    fmt = format_of(_clean(body.get("format")))
    if fmt is None:
        raise BadEntry(f"формат «{_clean(body.get('format'))}»")
    surname, name = _clean(body.get("surname")), _clean(body.get("Name") or body.get("name"))
    if not surname or not name:
        raise BadEntry("нет фамилии или имени")
    relay = {f"relay_{s}": _clean(f"{_clean(body.get('surname_' + s))} {_clean(body.get('name_' + s))}")
             if fmt == "relay" else "" for s in STAGES}
    return {
        "tranid": tranid[:64], "formid": _clean(body.get("formid"))[:64], "format": fmt,
        "surname": surname[:100], "name": name[:100],
        "gender": {"Мужской": "M", "Женский": "F"}.get(_clean(body.get("sex"))) if fmt == "individual" else None,
        "birthdate": parse_birthdate(_clean(body.get("birthday")), today),
        "city": _clean(body.get("city"))[:150],
        "email": _clean(body.get("Email") or body.get("email"))[:255],
        "phone": _clean(body.get("Phone") or body.get("phone"))[:64],
        "team_name": _clean(body.get("team_name"))[:150], **relay,
        "wildcard_reason": _text(body.get("wildcard_reason")), "results_text": _text(body.get(RESULTS_FIELD)),
        "result_url": _clean(body.get("result_url"))[:500],
        "raw": {k: v for k, v in body.items() if isinstance(v, (str, int, float, list))},
    }


def _decode(data: bytes) -> str:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = data.decode("cp1251", errors="replace")
    return text.lstrip(chr(0xFEFF))


def parse_csv(data: bytes, today: datetime.date) -> tuple[list[tuple[dict, Optional[datetime.datetime]]], list[str]]:
    """CSV-выгрузка заявок Тильды («;») → ([(заявка, время подачи из Date)], ошибки по строкам)."""
    reader = csv.DictReader(io.StringIO(_decode(data), newline=""), delimiter=";")
    if not reader.fieldnames or "tranid" not in reader.fieldnames:
        raise BadEntry("это не выгрузка заявок Тильды: нет колонки tranid")
    entries, errors = [], []
    for n, row in enumerate(reader, start=2):
        try:
            e = parse_entry(row, today)
        except BadEntry as err:
            errors.append(f"строка {n}: {err}")
            continue
        try:
            at = datetime.datetime.strptime(_clean(row.get("Date")), "%Y-%m-%d %H:%M:%S")
        except ValueError:
            at = None
        entries.append((e, at))
    return entries, errors
