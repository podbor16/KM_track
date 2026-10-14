"""
Таблица организаторов жеребьёвки (лист «Спец вставка») → заявки draw_applicants.

Колонки ищутся по заголовку. Пул (цвет шарика): wild card (красные) → 'wildcard',
эстафета (синие) → 'relay', личник со стартами в личном зачёте → 'repeat',
иначе → 'novice' (чёрные, две ёмкости). Отметки «!» и «Участвует 2027» не
используются: решение организаторов — обычные участники (2026-10-14).
Эстафета — по капитану, названия команды в таблице нет.
"""
import io

import openpyxl

SHEET = "Спец вставка"
COL_FORMAT, COL_NAME, COL_SEX, COL_CITY = "format", "surname Name", "sex", "city (исправлено)"
COL_WILDCARD, COL_TOTAL, COL_EXTRA = "Wildcard", "Общая сумма шансов", "Сумма дополнительных шансов"
COL_WILDCARD_REASON, COL_RESULTS = "wildcard_reason", "Расскажите_о_ваших_результатах"
EXTRA_COLS = {
    "starts_individual": "Старты на гонке (индивидуально)",
    "starts_relay": "Старты на гонке (эстафета)",
    "draw_accumulated": "Накопленные шансы за участия в жеребьёвке",
    "is_local": "Карточка для местных атлетов",
    "duathlon_222": "Участие в 222 Дуатлоне",
    "race_24h": "Участие в суточной велогонке 24часа",
    "tattoo": "Тату Siberman",
}
REQUIRED = (COL_FORMAT, COL_NAME, COL_SEX, COL_CITY, COL_WILDCARD, COL_TOTAL, COL_EXTRA, *EXTRA_COLS.values())
RELAY_ROLES = ("swim", "bike", "run")


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
        if fmt_raw.startswith("Эстафет"):
            fmt = "relay"
        elif fmt_raw.startswith("Индивид"):
            fmt = "individual"
        else:
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
        def fold(t):
            return t.lower().replace("ё", "е")
        key = (fmt, fold(surname), fold(name))
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
        relay = {
            f"relay_{r}": _norm(f"{_norm(get('surname_' + r))} {_norm(get('name_' + r))}") if fmt == "relay" else ""
            for r in RELAY_ROLES
        }
        apps.append({
            "format": fmt, "surname": surname, "name": name,
            "gender": gender if fmt == "individual" else None,
            "city": _norm(get(COL_CITY)), "pool": pool, "is_wildcard": is_wildcard,
            "chances": total, **extra, **relay,
            "wildcard_reason": _norm(get(COL_WILDCARD_REASON)), "results_text": _norm(get(COL_RESULTS)),
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
