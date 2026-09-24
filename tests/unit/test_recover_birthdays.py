from collections import defaultdict

from scripts.recover_birthdays import classify


def lead(email="", phone="", city=""):
    return {"surname": "Иванов", "name": "Иван", "email": email, "phone": phone, "city": city}


def known(*rows):
    k = defaultdict(list)
    for bd, email, phone, city in rows:
        k[("иванов", "иван")].append({"bd": bd, "email": email, "phone": phone, "city": city})
    return k


def test_a_email_match_single_date():
    assert classify(lead(email="Ivan@Mail.ru"), known(("1990-01-01", "ivan@mail.ru", "", ""))) == ("A", "1990-01-01", None)


def test_a_phone_match_ignores_formatting():
    k = known(("1990-01-01", "", "8 (913) 123-45-67", ""))
    assert classify(lead(phone="+79131234567"), k)[:2] == ("A", "1990-01-01")


def test_placeholder_email_does_not_count_as_contact():
    k = known(("1990-01-01", "example@mail.ru", "", ""))
    assert classify(lead(email="example@mail.ru"), k)[0] == "B2"


def test_x_contact_match_but_several_dates():
    k = known(("1990-01-01", "ivan@mail.ru", "", ""), ("1990-01-10", "ivan@mail.ru", "", ""), ("1990-01-01", "ivan@mail.ru", "", ""))
    tier, bd, dates = classify(lead(email="ivan@mail.ru"), k)
    assert tier == "X" and bd is None and dates == {"1990-01-01": 2, "1990-01-10": 1}


def test_b1_city_match_single_date():
    assert classify(lead(city="Красноярск "), known(("1990-01-01", "", "", "красноярск"))) == ("B1", "1990-01-01", None)


def test_b3_other_city_not_applied():
    assert classify(lead(city="Ачинск"), known(("1990-01-01", "", "", "Красноярск")))[:2] == ("B3", None)


def test_c_several_dates_and_d_no_match():
    assert classify(lead(), known(("1990-01-01", "", "", ""), ("1985-05-05", "", "", "")))[0] == "C"
    assert classify(lead(), defaultdict(list))[0] == "D"
