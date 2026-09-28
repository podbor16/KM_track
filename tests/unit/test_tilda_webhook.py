import pytest
from src.krasmarafon.services.tilda_webhook import (
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


def test_convert_birthday_space_separated():
    """Реальный инцидент (обработанный вручную Excel-стартовый список,
    2026-08-19): организатор вписал дату с пробелами вместо точек —
    "27 08 1988" по длине совпадает с ISO-форматом (10 символов) и раньше
    проходило как "валидная" дата прямиком в SQL-сравнение с DATE-колонкой,
    роняя импорт с MySQL 1525 "Incorrect DATE value"."""
    assert convert_birthday("27 08 1988") == "1988-08-27"


def test_convert_birthday_dash_separated():
    assert convert_birthday("27-08-1988") == "1988-08-27"


def test_convert_birthday_slash_separated():
    assert convert_birthday("27/08/1988") == "1988-08-27"


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


def test_parse_products_no_year_in_text_falls_back_to_slug_year():
    """Реальная находка на боевой выгрузке Tilda: год в видимом тексте
    названия есть не всегда (Tilda пишет его не всегда) — но всегда есть в
    служебном slug-коде в скобках."""
    products = ["5 км Жара (zhara2026-5, Выберите категорию: Основная категория) x 1 ≡ 1390"]
    result = parse_products(products)
    assert result["event_distance"] == "5 км"
    assert result["event_name"] == "Жара"
    assert result["event_year"] == "2026"


def test_parse_products_no_visible_name_falls_back_to_config_by_slug():
    """Ещё реже название события отсутствует в тексте вовсе — только slug.
    'zhara' -> config/events/zhara.yaml -> name 'Жара'."""
    products = ["5 км (zhara2026-5y, Выберите категорию: Дети 12-17 лет) x 1 ≡ 490"]
    result = parse_products(products)
    assert result["event_distance"] == "5 км"
    assert result["event_name"] == "Жара"
    assert result["event_year"] == "2026"


def test_parse_products_no_year_anywhere_and_unknown_slug_returns_empty():
    products = ["5 км Неизвестное (unknownslug, категория) x 1 ≡ 100"]
    result = parse_products(products)
    assert result == {"event_distance": "", "event_name": "", "event_year": ""}


def test_parse_products_nested_parens_in_extras_still_finds_slug_year():
    """Реальная строка с вложенными скобками у доп. опции (гравировка) —
    год всё равно должен извлечься из начала slug-кода."""
    products = [
        "5 км Жара (zhara2026-5b, Выберите категорию: Пенсионеры, "
        "Дополнительно: Гравировка (470 руб.)) x 1 ≡ 960"
    ]
    result = parse_products(products)
    assert result["event_distance"] == "5 км"
    assert result["event_name"] == "Жара"
    assert result["event_year"] == "2026"


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
        "club": "ILSS",
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
    assert result["club"] == "ILSS"
    assert result["birthday"] == "1990-01-01"
    assert result["event_name"] == "Весна"
    assert result["event_distance"] == "5 км"
    assert result["is_name_suspicious"] == 0
    assert result["client_id"] == 0
    assert result["event_id"] == 0


@pytest.mark.parametrize("product, expected_distance", [
    ("5 км Забег Икс 2026 (xtrail5-2026, Гравировка на медали + 470 р.: Не нужно)", "5 км"),
    ("2 км Забег Икс северная ходьба 2026 (xtrail2w-2026, ...)", "2 км"),
    ("10 км X Trail (xtrail10-2026, Гравировка на медали + 470 рублей: Нет)", "10 км"),
    ("2 км Х Трейл 2026 (xtrail2y-2026, ...)", "2 км"),
])
def test_parse_products_xtrail_aliases_resolve_to_db_event_name(product, expected_distance):
    """«Забег Икс» (2026) и «X Trail» — то же событие, что «Х Трейл» в БД."""
    info = parse_products([product])
    assert info["event_name"] == "Х Трейл"
    assert info["event_distance"] == expected_distance
    assert info["event_year"] == "2026"


def test_parse_products_without_slug_tail_year_at_end():
    """«5 км Забег Икс 2026» — продукт без служебного хвоста Tilda в скобках."""
    info = parse_products(["5 км Забег Икс 2026"])
    assert (info["event_name"], info["event_year"], info["event_distance"]) == ("Х Трейл", "2026", "5 км")


def test_parse_products_amount_at_end_is_not_taken_as_year():
    info = parse_products(["5 км Жара (zhara2026-5, Выберите категорию: Основная категория) x 1 ≡ 1390"])
    assert (info["event_name"], info["event_year"]) == ("Жара", "2026")


def test_parse_products_slug_year_wins_over_title_year():
    """Страницу продукта скопировали с прошлого года: в названии 2026, в slug 2027."""
    products = ["Слот на участие в Детском забеге 2026 (kids2027, Выберите категорию: Основная категория)"]
    result = parse_products(products, birthday="2021-05-01")
    assert result["event_name"] == "Детский забег"
    assert result["event_year"] == "2027"
    assert result["event_distance"] == "1 км"          # 2027 - 2021 = 6 лет


def test_parse_products_slug_year_other_events():
    result = parse_products(["5 км Красочный забег 2026 (color5-2027, Выберите категорию)"])
    assert (result["event_name"], result["event_year"], result["event_distance"]) == ("Красочный забег", "2027", "5 км")
    same = parse_products(["21.1 км Жара 2026 (zhara2026-21, …)"])
    assert same["event_year"] == "2026"


from datetime import date

_RACES = {("Детский забег", 2026): date(2026, 8, 22), ("Детский забег", 2027): date(2027, 8, 28),
          ("Жара", 2024): date(2024, 8, 24), ("Жара", 2025): date(2025, 8, 23),
          ("Снежная семерка", 2024): date(2024, 12, 1), ("Снежная семерка", 2025): date(2025, 12, 7),
          ("Ночной забег", 2027): date(2027, 3, 27)}
_race = lambda name, year: _RACES.get((name, int(year)))


@pytest.mark.parametrize("name, cands, bought, expected", [
    ("Детский забег", [2026, 2027], date(2026, 8, 23), 2027),     # название 2026, slug 2027, куплен после старта 2026
    ("Детский забег", [2026, 2027], date(2026, 8, 1), 2026),      # до старта 2026 — ближайший ещё не прошедший
    ("Жара", [2024], date(2024, 8, 26), 2025),                    # slug zhara2024 после Жары 2024 -> 2025
    ("Снежная семерка", [2024], date(2024, 12, 1), 2025),         # в день старта — следующий сезон
    ("Ночной забег", [2027, 2076], date(2026, 3, 29), 2027),      # опечатка в slug
    ("Весна", [2028], date(2027, 6, 1), 2028),                    # события 2028 в БД ещё нет
])
def test_resolve_event_year(name, cands, bought, expected):
    from src.krasmarafon.services.tilda_webhook import resolve_event_year
    assert resolve_event_year(name, cands, bought, _race) == expected


def test_transform_uses_purchase_date_for_year_and_kids_distance():
    import json
    from src.krasmarafon.services.tilda_webhook import transform_tilda_payload
    body = {"surname": "Иванов", "name": "Петр", "birthday": "05.05.2021",
            "payment": json.dumps({"products": ["Слот на участие в Детском забеге 2026 (kids2026, Основная)"]})}
    early = transform_tilda_payload(body, _race, date(2026, 8, 1))
    assert (early["event_year"], early["event_distance"]) == (2026, "500 м")      # 2026-2021 = 5
    late = transform_tilda_payload(body, _race, date(2026, 8, 23))
    assert (late["event_year"], late["event_distance"]) == (2027, "1 км")        # 2027-2021 = 6
