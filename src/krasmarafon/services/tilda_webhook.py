import json
import logging
import math
import re

_log = logging.getLogger(__name__)


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
    if not birthday or not isinstance(birthday, str):
        return birthday
    birthday = birthday.strip()
    match = re.match(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})$", birthday)
    if match:
        day = match.group(1).zfill(2)
        month = match.group(2).zfill(2)
        year = match.group(3)
        return f"{year}-{month}-{day}"
    if re.match(r"^\d{4}-\d{2}-\d{2}$", birthday):
        return birthday
    return birthday


def normalize_name(s):
    if not s or not isinstance(s, str):
        return s
    return " ".join(w.capitalize() for w in s.strip().split())


def parse_products(products, birthday=None):
    empty = {"event_distance": "", "event_name": "", "event_year": ""}
    if not products:
        _log.warning(f"parse_products: пустой products={products!r}")
        return empty

    products_str = products[0] if isinstance(products, list) else str(products)

    match = re.match(
        r"^(\d+(?:\.\d+)?)\s+(км|km)\s+(.+?)\s+(\d{4})\s*\(",
        products_str,
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


def transform_tilda_payload(body: dict) -> dict:
    payment_raw = body.get("payment", "")
    payment = parse_payment(payment_raw)

    birthday = convert_birthday(body.get("birthday"))
    products_list = payment["products_raw"]
    event_info = parse_products(
        products_list if isinstance(products_list, list) else [products_list],
        birthday=birthday,
    )

    surname = normalize_name(body.get("surname", ""))
    name = normalize_name(body.get("name", ""))

    # Подозрительное имя: содержит не-кирилличные символы, пробелы, цифры, латиницу и т.п.
    # Допустимо: кириллица и дефис (для составных имён типа Анна-Мария)
    _CLEAN_NAME = re.compile(r'^[а-яёА-ЯЁ\-]+$')
    def _suspicious(val):
        return bool(val) and not _CLEAN_NAME.match(val.strip())
    is_name_suspicious = int(_suspicious(surname) or _suspicious(name))

    products_str = (
        ", ".join(products_list)
        if isinstance(products_list, list)
        else str(products_list or "")
    )

    return {
        "surname": surname,
        "name": name,
        "sex": body.get("sex", ""),
        "city": body.get("city", ""),
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
        "is_name_suspicious": is_name_suspicious,
        "client_id": 0,
        "event_id": 0,
        "is_duplicate": 0,
        "status": 0,
        "is_new": 0,
        "is_new_event": 0,
    }
