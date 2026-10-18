"""
Выгрузка заявок Тильды (CSV: «;», UTF-8 с BOM) → даты рождения для реестра людей.

Берём только ФИ, пол, ДР, город, номер заявки (tranid) и дату подачи — телефоны, e-mail и
тексты заявок не читаем. ДР в форме есть с 15.10.2024 (форма 807405240 и следующие); у
эстафеты — у каждого этапника (surname_swim/name_swim/birthday_swim и т.д.). Старые формы
без колонки surname (ФИ одной строкой в Name, ДР нет) пропускаются.
"""
import csv
import datetime
import io
from typing import Optional

from src.siberman.persons.linking import Applicant

STAGES = ("swim", "bike", "run")
MIN_YEAR = 1930
MIN_AGE = 14


def _clean(v) -> str:
    return " ".join(str(v or "").split())


def parse_birthdate(raw: str, today: datetime.date) -> Optional[datetime.date]:
    """'дд.мм.гггг' или 'дд-мм-гггг'; невозможная дата, раньше 1930 или моложе 14 лет → None."""
    parts = _clean(raw).replace("-", ".").replace("/", ".").split(".")
    if len(parts) != 3 or not all(p.isdigit() for p in parts) or len(parts[2]) != 4:
        return None
    try:
        d = datetime.date(int(parts[2]), int(parts[1]), int(parts[0]))
    except ValueError:
        return None
    if d.year < MIN_YEAR or d.year > today.year - MIN_AGE:
        return None
    return d


def _parse_dt(raw) -> Optional[datetime.datetime]:
    try:
        return datetime.datetime.strptime(_clean(raw), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def parse_applicants_csv(data: bytes, today: Optional[datetime.date] = None) -> tuple:
    """→ ([Applicant], {'rows', 'people', 'no_birthday', 'bad_birthday'}). ValueError — не выгрузка Тильды."""
    today = today or datetime.date.today()
    text = data.decode("utf-8", errors="replace").lstrip(chr(0xFEFF))
    reader = csv.DictReader(io.StringIO(text), delimiter=";")
    if not reader.fieldnames or "tranid" not in reader.fieldnames:
        raise ValueError("Это не выгрузка заявок Тильды: нет колонки tranid")
    found: dict = {}
    stats = {"rows": 0, "people": 0, "no_birthday": 0, "bad_birthday": 0}
    for row in reader:
        stats["rows"] += 1
        tranid = _clean(row.get("tranid"))
        if not tranid:
            continue
        submitted = _parse_dt(row.get("Date"))
        gender = {"Мужской": "M", "Женский": "F"}.get(_clean(row.get("sex")))
        city = _clean(row.get("city") or row.get("city_2"))
        people = [(tranid, row.get("surname"), row.get("Name"), row.get("birthday"), gender, city)]
        for st in STAGES:
            people.append((f"{tranid}:{st}", row.get(f"surname_{st}"), row.get(f"name_{st}"),
                           row.get(f"birthday_{st}"), None, ""))
        for tid, surname, name, bd_raw, g, c in people:
            surname, name = _clean(surname), _clean(name)
            if not surname:
                continue
            bd = parse_birthdate(bd_raw, today)
            if bd is None:
                stats["bad_birthday" if _clean(bd_raw) else "no_birthday"] += 1
                continue
            found[tid] = Applicant(tranid=tid, surname=surname, name=name, gender=g, birthdate=bd,
                                   city=c, submitted_at=submitted)
    stats["people"] = len(found)
    return list(found.values()), stats
