"""
Таблица организаторов жеребьёвки (формат 2028: «Участник жеребьёвки», «Формат участия», «Пол», «Город»,
составы эстафет — «Плавание», «Велосипед», «Бег») → заявки draw_applicants.

Колонки ищутся по заголовку. Пул (цвет шарика): wild card (красные) → 'wildcard',
эстафета (синие) → 'relay', личник со стартами в личном зачёте → 'repeat',
иначе → 'novice' (чёрные, две ёмкости). Отметки «!» и «Участвует 2027» не
используются: решение организаторов — обычные участники (2026-10-14).
Эстафета — по капитану, названия команды в таблице нет. Тексты «Почему wild card» и «О результатах» —
не из таблицы, а из CSV заявок Тильды (вместе с контактами, parse_contacts).
"""
import csv
import io
from operator import itemgetter

import openpyxl

SHEET = "Спец вставка"
COL_FORMAT, COL_NAME, COL_SEX, COL_CITY = "Формат участия", "Участник жеребьёвки", "Пол", "Город"
COL_WILDCARD, COL_TOTAL, COL_EXTRA = "Wildcard", "Общая сумма шансов", "Сумма дополнительных шансов"
RELAY_COLS = {"swim": "Плавание", "bike": "Велосипед", "run": "Бег"}   # «Фамилия Имя» участника этапа
EXTRA_COLS = {
    "starts_individual": "Старты на гонке (индивидуально)",
    "starts_relay": "Старты на гонке (эстафета)",
    "draw_accumulated": "Накопленные шансы за участия в жеребьёвке",
    "is_local": "Карточка для местных атлетов",
    "duathlon_222": "Участие в 222 Дуатлоне",
    "race_24h": "Участие в суточной велогонке 24часа",
    "tattoo": "Тату Siberman",
}
REQUIRED = (COL_FORMAT, COL_NAME, COL_SEX, COL_CITY, COL_WILDCARD, COL_TOTAL, COL_EXTRA, *EXTRA_COLS.values(),
            *RELAY_COLS.values())
# Тексты заявки Тильды: поле заявки → поле draw_applicants
TILDA_TEXTS = {"wildcard_reason": "wildcard_reason", "results_text": "Расскажите_о_ваших_результатах"}
# Что сравнивать между версиями таблицы (тексты «причина wild card» и «о результатах» — нет)
DIFF_FIELDS = ("gender", "city", "pool", "is_wildcard", "chances", *EXTRA_COLS,
               "relay_swim", "relay_bike", "relay_run")


def _fold(t) -> str:
    return (t or "").lower().replace("ё", "е")


def _format_of(raw: str):
    """«Эстафетная команда» / «Индивидуальное участие» (таблица организаторов и заявки Тильды) → формат."""
    if raw.startswith("Эстафет"):
        return "relay"
    if raw.startswith("Индивид"):
        return "individual"
    return None


def _norm(v) -> str:
    return " ".join(str(v if v is not None else "").split())


def _int(v) -> int:
    if v is None or (isinstance(v, str) and not v.strip()):
        return 0
    if isinstance(v, (int, float)) and not isinstance(v, bool) and float(v).is_integer() and v >= 0:
        return int(v)
    if isinstance(v, str):
        t = v.strip()
        if t.isdigit():
            return int(t)
        if t.endswith(".0") and t[:-2].isdigit():
            return int(t[:-2])
    try:
        float(v)
    except (TypeError, ValueError):
        raise ValueError(f"не целое число: «{v}»") from None
    raise ValueError(f"не целое число ≥ 0: «{v}»")


def parse_applicants(file_bytes: bytes) -> tuple[list[dict], list[str]]:
    """(заявки, ошибки). Строка с ошибкой в заявки не попадает."""
    try:
        wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
    except Exception:
        return [], ["файл не похож на .xlsx — сохраните таблицу в формате Excel"]
    ws = wb[SHEET] if SHEET in wb.sheetnames else wb.worksheets[0]
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return [], ["пустой лист"]
    idx: dict[str, int] = {}
    for i, h in enumerate(rows[0]):
        if _norm(h) and _norm(h) not in idx:
            idx[_norm(h)] = i
    missing = [c for c in REQUIRED if c not in idx]
    if missing:
        return [], ["нет колонок: " + ", ".join(missing)]

    apps: list[dict] = []
    errors: list[str] = []
    seen: set[tuple] = set()
    for n, row in enumerate(rows[1:], start=2):
        def get(col, _row=row):
            i = idx.get(col)
            return _row[i] if i is not None and i < len(_row) else None

        full = _norm(get(COL_NAME))
        if not full:
            continue
        where = f"строка {n} «{full}»"
        fmt_raw = _norm(get(COL_FORMAT))
        fmt = _format_of(fmt_raw)
        if fmt is None:
            errors.append(f"{where}: формат «{fmt_raw}»")
            continue
        gender = {"Мужской": "M", "Женский": "F"}.get(_norm(get(COL_SEX)))
        if fmt == "individual" and gender is None:
            errors.append(f"{where}: пол «{_norm(get(COL_SEX))}»")
            continue
        wc_raw = _norm(get(COL_WILDCARD)).lower().replace(" ", "")
        if wc_raw not in ("", "!", "wildcard"):
            errors.append(f"{where}: «{COL_WILDCARD}» — непонятное значение «{_norm(get(COL_WILDCARD))}»")
            continue
        try:
            extra, col = {}, ""
            for k, col in EXTRA_COLS.items():
                extra[k] = _int(get(col))
            col = COL_TOTAL
            total = _int(get(col))
            col = COL_EXTRA
            extra_sum = _int(get(col))
        except ValueError as e:
            errors.append(f"{where}: «{col}» — {e}")
            continue
        if total < 1:
            errors.append(f"{where}: шансов меньше 1")
            continue
        if sum(extra.values()) != extra_sum or total != extra_sum + 1:
            errors.append(f"{where}: шансы не сходятся (доп. {sum(extra.values())}, "
                          f"«сумма доп.» {extra_sum}, итого {total})")
            continue
        surname, _, name = full.partition(" ")
        if not name:
            errors.append(f"{where}: нет имени")
            continue
        key = (fmt, _fold(surname), _fold(name))
        if key in seen:
            errors.append(f"{where}: повтор заявки")
            continue
        seen.add(key)
        is_wildcard = wc_raw == "wildcard"
        if is_wildcard:
            pool = "wildcard"
        elif fmt == "relay":
            pool = "relay"
        else:
            pool = "repeat" if extra["starts_individual"] > 0 else "novice"
        relay = {f"relay_{r}": _norm(get(col)) if fmt == "relay" else "" for r, col in RELAY_COLS.items()}
        apps.append({
            "format": fmt, "surname": surname, "name": name,
            "gender": gender if fmt == "individual" else None,
            "city": _norm(get(COL_CITY)), "pool": pool, "is_wildcard": is_wildcard,
            "chances": total, **extra, **relay,
            "wildcard_reason": "", "results_text": "",
        })
    return apps, errors


def import_report(apps: list[dict]) -> dict:
    """Люди и шарики по группам: repeat_M, novice_F, relay, wildcard_M, wildcard (эстафеты)…"""
    groups: dict[str, dict] = {}
    for a in apps:
        key = a["pool"] if a["format"] == "relay" else f"{a['pool']}_{a['gender']}"
        g = groups.setdefault(key, {"people": 0, "balls": 0})
        g["people"] += 1
        g["balls"] += a["chances"]
    return {"total": len(apps), "groups": groups}


def applicant_key(a: dict) -> tuple:
    """Одна и та же заявка в двух версиях таблицы: формат + фамилия + имя (без регистра и ё)."""
    return a["format"], _fold(a["surname"]), _fold(a["name"])


def _cmp(v):
    """Значение из БД (0/1, NULL) и из таблицы (bool, '') — к одному виду для сравнения."""
    return "" if v is None else int(v) if isinstance(v, bool) else v


def diff_applicants(old: list[dict], new: list[dict]) -> dict:
    """Что меняет новая таблица относительно загруженной: добавлены, убраны, изменены (поле: было → стало),
    шариков было → стало."""
    before = {applicant_key(a): a for a in old}
    after = {applicant_key(a): a for a in new}

    def brief(a: dict) -> dict:
        return {"fio": f"{a['surname']} {a['name']}", "format": a["format"], "chances": a["chances"]}

    changed = []
    for k, a in after.items():
        b = before.get(k)
        fields = [{"field": f, "old": b[f], "new": a[f]} for f in DIFF_FIELDS if b and _cmp(b[f]) != _cmp(a[f])]
        if fields:
            changed.append({**brief(a), "changes": fields})
    by_fio = itemgetter("fio")
    return {"added": sorted((brief(a) for k, a in after.items() if k not in before), key=by_fio),
            "removed": sorted((brief(b) for k, b in before.items() if k not in after), key=by_fio),
            "changed": sorted(changed, key=by_fio),
            "balls": {"old": sum(a["chances"] for a in old), "new": sum(a["chances"] for a in new)}}


# ── Контакты из выгрузки заявок Тильды (для счетов) ─────────────────────────

def fio_key(surname: str, name: str) -> str:
    return f"{_fold(_norm(surname))} {_fold(_norm(name))}"


def _decode_csv(data: bytes) -> str:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = data.decode("cp1251", errors="replace")
    return text.lstrip(chr(0xFEFF))


def parse_contacts(file_bytes: bytes) -> tuple[dict, dict]:
    """CSV заявок Тильды («;», UTF-8 или cp1251) → ({(формат, ФИ): {email, phone, wildcard_reason, results_text}},
    отчёт). Берём только ФИ, формат, Email, Phone, тексты TILDA_TEXTS и дату заявки; у эстафеты — заявителя
    (капитана, как в таблице организаторов).
    Повторная заявка — главнее последняя (правила жеребьёвки)."""
    rows = list(csv.DictReader(io.StringIO(_decode_csv(file_bytes)), delimiter=";"))
    report = {"rows": len(rows), "people": 0, "duplicates": 0, "bad_format": 0}
    if not rows or not {"surname", "Name", "Email", "Phone", "format"} <= set(rows[0]):
        return {}, report
    best: dict = {}
    for r in rows:
        fmt = _format_of(_norm(r.get("format")))
        if fmt is None or not _norm(r.get("surname")):
            report["bad_format"] += 1
            continue
        key = (fmt, fio_key(r["surname"], r["Name"]))
        when = _norm(r.get("Date"))
        if key in best:
            report["duplicates"] += 1
            if when < best[key][0]:
                continue
        best[key] = (when, {"email": _norm(r.get("Email")), "phone": _norm(r.get("Phone")),
                            **{k: (r.get(f) or "").strip() for k, f in TILDA_TEXTS.items()}})
    report["people"] = len(best)
    return {k: v for k, (_, v) in best.items()}, report


def contact_for(a: dict, contacts: dict):
    """Контакт заявки жеребьёвки: формат + ФИ (в любом порядке); нет — None."""
    for key in (fio_key(a["surname"], a["name"]), fio_key(a["name"], a["surname"])):
        if (a["format"], key) in contacts:
            return contacts[(a["format"], key)]
    return None
