import pytest
from src.tracker.services.tilda_webhook import (
    decode_from_db_format,
    convert_birthday,
    normalize_name,
    parse_products,
    parse_payment,
    transform_tilda_payload,
)


def test_decode_from_db_format_simple():
    assert decode_from_db_format("4.9") == 4.9


def test_decode_from_db_format_encoded():
    encoded = 1000000000 + 1e6 + 490 * 1e7
    assert decode_from_db_format(str(int(encoded))) == pytest.approx(490.0, rel=1e-3)


def test_decode_from_db_format_string_passthrough():
    assert decode_from_db_format("не число") == "не число"


def test_convert_birthday_ru_format():
    assert convert_birthday("01.05.1990") == "1990-05-01"


def test_convert_birthday_iso_passthrough():
    assert convert_birthday("1990-05-01") == "1990-05-01"


def test_convert_birthday_none():
    assert convert_birthday(None) is None


def test_normalize_name():
    assert normalize_name("ИВАНОВ") == "Иванов"
    assert normalize_name("иван петров") == "Иван Петров"


def test_parse_products_standard():
    products = ["5 км Весна 2027 (Vesna5b-2027, Выберите категорию: Пенсионеры)=490"]
    result = parse_products(products)
    assert result["event_distance"] == "5 км"
    assert result["event_name"] == "Весна"
    assert result["event_year"] == "2027"


def test_parse_products_km_latin():
    products = ["10 km Summer 2026 (event=100)"]
    result = parse_products(products)
    assert result["event_distance"] == "10 км"


def test_parse_products_empty():
    result = parse_products([])
    assert result == {"event_distance": "", "event_name": "", "event_year": ""}


def test_parse_products_detsky_zabeg():
    products = ["Детский забег 2027 (child)=200"]
    result = parse_products(products, birthday="2021-06-01")
    assert result["event_name"] == "Детский забег"
    assert result["event_distance"] == "1 км"
    assert result["event_year"] == "2027"


def test_parse_payment():
    payment_str = (
        '{"sys":"cloudpayments","systranid":"3521002298","orderid":"1869817991",'
        '"products":["5 км Весна 2027 (Vesna5b-2027)=490"],'
        '"promocode":"TEST","discount":"485.1","amount":"4.9"}'
    )
    result = parse_payment(payment_str)
    assert result["payment_system"] == "cloudpayments"
    assert result["transaction_id"] == "3521002298"
    assert result["amount"] == pytest.approx(4.9)
    assert result["discount"] == pytest.approx(485.1)


def test_transform_full_payload():
    body = {
        "surname": "ИВАНОВ",
        "name": "иван",
        "sex": "мужской",
        "city": "Красноярск",
        "birthday": "01.01.1990",
        "email": "test@test.ru",
        "phone": "+7-900-000-0000",
        "payment": (
            '{"sys":"cloudpayments","systranid":"123","orderid":"456",'
            '"products":["5 км Весна 2027 (test)=490"],'
            '"promocode":"","discount":"0","amount":"490"}'
        ),
    }
    result = transform_tilda_payload(body)
    assert result["surname"] == "Иванов"
    assert result["name"] == "Иван"
    assert result["birthday"] == "1990-01-01"
    assert result["event_name"] == "Весна"
    assert result["event_distance"] == "5 км"
    assert result["is_name_suspicious"] == 0
    assert result["client_id"] == 0
    assert result["event_id"] == 0
