import json
import logging
import math
import re

from src.common.names import normalize_event_name, normalize_person_name, normalize_sex

_log = logging.getLogger(__name__)

# Подозрительное имя: содержит не-кирилличные символы, пробелы, цифры, латиницу и т.п.
# Допустимо: кириллица и дефис (для составных имён типа Анна-Мария)
_CLEAN_NAME_RE = re.compile(r'^[а-яёА-ЯЁ\-]+$')


def is_name_suspicious(surname: str, name: str) -> bool:
    def _suspicious(val):
        return bool(val) and not _CLEAN_NAME_RE.match(val.strip())
    return _suspicious(surname) or _suspicious(name)


def decode_from_db_format(value):
    if value is None or value == "":
        return value
    try:
        num = float(value)
    except (TypeError, ValueError):
        return value
    if num > 1e9:
        without_offset = num - 1e9 - 1e6
        return without_offset / 1e7
    return num


def convert_birthday(birthday):
    """"ДД.ММ.ГГГГ" (и варианты с "-"/"/"/пробелом вместо точки — реальный
    случай из ручного Excel-стартового списка, 2026-08-19: организатор
    вписал дату как "27 08 1988") -> ISO "ГГГГ-ММ-ДД". Уже-ISO строка —
    без изменений. Всё остальное — без изменений (парсер выше по стеку
    решает, что делать с нераспознанным форматом, см. parse_tilda_export()
    в tilda_import_parser.py — не блокируем такой вариант тут молча)."""
    if not birthday or not isinstance(birthday, str):
        return birthday
    birthday = birthday.strip()
    match = re.match(r"^(\d{1,2})[.\-/\s](\d{1,2})[.\-/\s](\d{4})$", birthday)
    if match:
        day = match.group(1).zfill(2)
        month = match.group(2).zfill(2)
        year = match.group(3)
        return f"{year}-{month}-{day}"
    if re.match(r"^\d{4}-\d{2}-\d{2}$", birthday):
        return birthday
    return birthday


def normalize_name(s):
    """Единая нормализация ФИО заявок (вебхук, импорт /admin, скрипты) — см. normalize_person_name."""
    return normalize_person_name(s)


def _lookup_event_name_by_slug(slug_text: str) -> str:
    """Резолвит человекочитаемое имя события по префиксу slug-кода Tilda
    (например 'zhara2026-5' -> код 'zhara' -> name из config/events/zhara.yaml).
    Fallback для редких случаев, когда видимый текст названия в products
    пуст (Tilda пишет slug без названия для части заказов)."""
    m = re.match(r"^([a-zA-Zа-яА-ЯёЁ_]+)", slug_text.strip())
    if not m:
        return ""
    prefix = m.group(1).lower()
    try:
        from src.config.event_loader import load_events_cached
        events = load_events_cached()
    except Exception:
        return ""
    event = events.get(prefix)
    return event.name if event else ""


# Одно событие в БД под разными названиями продукта в Tilda (переименование
# «Х Трейл» → «Забег Икс» в 2026, латинское «X Trail» в старых продуктах).
# Ключ — название в нижнем регистре, значение — event_name в БД.
_EVENT_NAME_ALIASES = {
    "забег икс": "Х Трейл",
    "x trail": "Х Трейл",
    "xtrail": "Х Трейл",
}


def _canonical_event_name(name: str) -> str:
    name = normalize_event_name(name.strip())
    return _EVENT_NAME_ALIASES.get(name.lower(), name)


# kids2027, zhara2026-21, color5-2027, night2walkb-2025, Vesna5-2026y
_SLUG_YEAR_RE = re.compile(r"\(\s*[a-z]+(?:\d+[a-z]*-)?(20\d{2})", re.IGNORECASE)


_TITLE_YEAR_RE = re.compile(r"(?<!\d)(20\d{2})(?!\d)")


def year_candidates(products) -> list:
    """Годы продукта Tilda — из названия (до «(») и из slug товара в скобках.
    Ненадёжны оба: страницу копируют с прошлого года, не правя то название
    («…Детском забеге 2026 (kids2027…»), то slug («(zhara2024-5…» у слотов на
    2025). Выбор — resolve_event_year() по дате покупки."""
    raw = products[0] if isinstance(products, list) and products else str(products or "")
    title = _TITLE_YEAR_RE.search(raw.split("(")[0])
    slug = _SLUG_YEAR_RE.search(raw)
    return sorted({int(m.group(1)) for m in (title, slug) if m})


def _kids_distance(event_year, birthday):
    try:
        return "500 м" if int(event_year) - int(birthday[:4]) < 6 else "1 км"
    except (TypeError, ValueError, IndexError):
        return ""


def parse_products(products, birthday=None):
    info = _parse_products(products, birthday)
    if info["event_name"]:
        info["event_name"] = _canonical_event_name(info["event_name"])
        cands = year_candidates(products)
        info["year_candidates"] = cands
        # без даты покупки — больший год (новые продажи идут на следующий старт)
        if cands and str(max(cands)) != str(info["event_year"]):
            info["event_year"] = str(max(cands))
            if info["event_name"] == "Детский забег" and birthday:
                info["event_distance"] = _kids_distance(info["event_year"], birthday) or info["event_distance"]
    return info


def resolve_event_year(event_name, candidates, purchased_on, first_race_date):
    """Год заявки по дате покупки: ближайший из candidates, старт которого
    ещё не наступил (день старта — уже прошедший: онлайн-регистрация к нему
    закрыта, в этот день покупают только следующий сезон — все ≈250 таких
    покупок с 2024 года). Все прошли — следующий за последним. Года без
    события в БД (опечатка «night2-2076») не выбираются, пока есть другой.
    first_race_date(event_name, year) -> date | None."""
    cands = sorted(int(y) for y in candidates)
    if not cands:
        return None
    for year in cands:
        race = first_race_date(event_name, year)
        if race is not None and purchased_on < race:
            return year
    known = [y for y in cands if first_race_date(event_name, y) is not None]
    return (max(known) + 1) if known else max(cands)


def _parse_products(products, birthday=None):
    empty = {"event_distance": "", "event_name": "", "event_year": ""}
    if not products:
        _log.warning(f"parse_products: пустой products={products!r}")
        return empty

    products_str = products[0] if isinstance(products, list) else str(products)

    # "(" после года — служебный хвост Tilda ("(slug, опции)"); в
    # обработанных организатором файлах его бывает нет вовсе ("5 км Забег
    # Икс 2026") — год тогда в конце строки.
    match = re.match(
        r"^(\d+(?:\.\d+)?)\s+(км|km)\s+([^(]+?)\s+(20\d{2})\s*(?:\(|$)",
        products_str.strip(),
        re.IGNORECASE,
    )
    if match:
        distance_num = match.group(1)
        unit = "км"
        event_name = match.group(3).strip()
        event_name = re.sub(r"\s+северная\s+ходьба\s*", " ", event_name, flags=re.IGNORECASE).strip()
        event_year = match.group(4)
        return {
            "event_distance": f"{distance_num} {unit}",
            "event_name": event_name,
            "event_year": event_year,
        }

    # Fallback: Tilda не всегда пишет год рядом с названием (зависит от того,
    # редактировал ли организатор название продукта в конструкторе после
    # старта продаж) — но год всегда есть в служебном slug-коде в скобках
    # (напр. "zhara2026-5"), иногда там же и единственное упоминание
    # названия события (slug без человекочитаемого текста вообще).
    fallback = re.match(
        r"^(\d+(?:\.\d+)?)\s+(км|km)\s*(.*?)\(([^)]*)",
        products_str,
        re.IGNORECASE,
    )
    if fallback:
        distance_num = fallback.group(1)
        unit = "км"
        visible_name = fallback.group(3).strip()
        slug = fallback.group(4)
        # Детский забег обрабатывается отдельной веткой ниже (возраст->дистанция) —
        # не перехватываем его здесь, даже если в тексте уже есть название.
        if not re.search(r"детск.*забег", visible_name, re.IGNORECASE):
            # НЕ \b(20\d{2})\b — буквы и цифры оба относятся к \w, поэтому
            # между "zhara" и "2026" в "zhara2026-5" нет границы слова;
            # изолируем год явными проверками соседних символов вместо \b.
            year_match = re.search(r"(?<!\d)(20\d{2})(?!\d)", slug)
            event_year = year_match.group(1) if year_match else ""
            event_name = visible_name or _lookup_event_name_by_slug(slug)
            if event_name and event_year:
                event_name = re.sub(r"\s+северная\s+ходьба\s*", " ", event_name, flags=re.IGNORECASE).strip()
                return {
                    "event_distance": f"{distance_num} {unit}",
                    "event_name": event_name,
                    "event_year": event_year,
                }

    if re.search(r"детск.*забег", products_str, re.IGNORECASE):
        year_match = re.search(r"\b(20\d{2})\b", products_str)
        event_year = year_match.group(1) if year_match else ""
        event_distance = ""
        if birthday and event_year:
            try:
                birth_year = int(birthday[:4])
                race_year = int(event_year)
                age = race_year - birth_year
                event_distance = "500 м" if age < 6 else "1 км"
            except (ValueError, IndexError):
                pass
        return {"event_distance": event_distance, "event_name": "Детский забег", "event_year": event_year}

    return empty


def parse_payment(payment_raw):
    result = {
        "payment_system": "",
        "transaction_id": "",
        "order_id": "",
        "products_raw": "",
        "promocode": "",
        "discount": 0.0,
        "amount": 0.0,
    }
    if not payment_raw:
        _log.warning("parse_payment: payment_raw пустой")
        return result
    try:
        parsed = json.loads(payment_raw) if isinstance(payment_raw, str) else payment_raw
    except (json.JSONDecodeError, TypeError) as e:
        _log.warning(f"parse_payment: json.loads ошибка: {e}, raw={payment_raw!r:.200}")
        return result
    result["payment_system"] = parsed.get("sys", "")
    result["transaction_id"] = parsed.get("systranid", "")
    result["order_id"] = parsed.get("orderid", "")
    result["products_raw"] = parsed.get("products", "")
    result["promocode"] = parsed.get("promocode", "")

    for field in ("discount", "amount"):
        raw = parsed.get(field)
        if raw is not None and raw != "":
            result[field] = decode_from_db_format(str(raw))

    return result


def transform_tilda_payload(body: dict, first_race_date=None, purchased_on=None) -> dict:
    """first_race_date/purchased_on — уточнение года по дате покупки
    (resolve_event_year); без них — год из parse_products()."""
    payment_raw = body.get("payment", "")
    payment = parse_payment(payment_raw)

    birthday = convert_birthday(body.get("birthday"))
    products_list = payment["products_raw"]
    event_info = parse_products(
        products_list if isinstance(products_list, list) else [products_list],
        birthday=birthday,
    )
    if first_race_date and purchased_on and event_info["event_name"] and event_info.get("year_candidates"):
        year = resolve_event_year(event_info["event_name"], event_info["year_candidates"], purchased_on, first_race_date)
        if year and str(year) != str(event_info["event_year"]):
            event_info["event_year"] = str(year)
            if event_info["event_name"] == "Детский забег" and birthday:
                event_info["event_distance"] = _kids_distance(year, birthday) or event_info["event_distance"]

    surname = normalize_name(body.get("surname", ""))
    name = normalize_name(body.get("name", ""))

    name_suspicious = int(is_name_suspicious(surname, name))

    products_str = (
        ", ".join(products_list)
        if isinstance(products_list, list)
        else str(products_list or "")
    )

    return {
        "surname": surname,
        "name": name,
        "sex": normalize_sex(body.get("sex", "")),
        "city": body.get("city", ""),
        "club": body.get("club", ""),
        "birthday": birthday,
        "email": body.get("email", ""),
        "phone": body.get("phone", ""),
        "event_name": event_info["event_name"],
        "event_distance": event_info["event_distance"],
        "event_year": int(event_info["event_year"]) if event_info["event_year"] else None,
        "products": products_str,
        "payment_system": payment["payment_system"],
        "transaction_id": payment["transaction_id"],
        "order_id": int(payment["order_id"]) if str(payment["order_id"]).isdigit() else None,
        "promocode": payment["promocode"],
        "discount": payment["discount"],
        "amount": payment["amount"],
        "is_name_suspicious": name_suspicious,
        "client_id": 0,
        "event_id": 0,
        "is_duplicate": 0,
        "status": 0,
        "is_new": 0,
        "is_new_event": 0,
    }
