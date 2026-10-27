import datetime

import pytest

from src.siberman.entries.parser import BadEntry, is_test_ping, parse_csv, parse_entry

TODAY = datetime.date(2026, 10, 27)
IND = {"tranid": "123:456", "formid": "form1", "format": "Индивидуальное участие", "surname": " Иванов ",
       "Name": "Иван", "sex": "Мужской", "birthday": "05.03.1985", "city": "Красноярск", "Email": "i@ex.ru",
       "Phone": "+7 900 000-00-00", "wildcard_reason": "", "Расскажите_о_ваших_результатах": "Финишер 2019",
       "result_url": "https://ex.ru/r", "tattoo": "да"}


def test_individual_fields():
    e = parse_entry(IND, TODAY)
    assert (e["tranid"], e["format"], e["surname"], e["name"], e["gender"]) == ("123:456", "individual", "Иванов", "Иван", "M")
    assert e["birthdate"] == datetime.date(1985, 3, 5) and e["city"] == "Красноярск"
    assert (e["email"], e["phone"], e["results_text"], e["result_url"]) == ("i@ex.ru", "+7 900 000-00-00", "Финишер 2019", "https://ex.ru/r")
    assert e["relay_swim"] == "" and e["raw"]["tattoo"] == "да"          # всё тело — в raw (для части B)


def test_relay_team_and_no_gender():
    e = parse_entry({**IND, "format": "Эстафетная команда", "sex": "", "team_name": "Столбы",
                     "surname_swim": "Пловцов", "name_swim": "Пётр", "surname_bike": "Велов", "name_bike": "Вася",
                     "surname_run": "", "name_run": ""}, TODAY)
    assert (e["format"], e["gender"], e["team_name"]) == ("relay", None, "Столбы")
    assert (e["relay_swim"], e["relay_bike"], e["relay_run"]) == ("Пловцов Пётр", "Велов Вася", "")


def test_bad_birthday_is_none_not_error():
    assert parse_entry({**IND, "birthday": "31.02.1985"}, TODAY)["birthdate"] is None


@pytest.mark.parametrize("patch", [{"tranid": ""}, {"format": "Непонятно"}, {"surname": ""}, {"Name": " "}])
def test_not_an_entry(patch):
    with pytest.raises(BadEntry):
        parse_entry({**IND, **patch}, TODAY)


def test_test_ping():
    assert is_test_ping({"test": "test"}) and not is_test_ping(IND)


def test_csv_utf8_and_cp1251_with_dates():
    head = "surname;Name;Email;Phone;Date;format;sex;birthday;city;tranid"
    rows = ["Иванов;Иван;i@ex.ru;1;2026-11-01 10:00:00;Индивидуальное участие;Мужской;05.03.1985;Красноярск;1:1",
            "Петрова;Анна;p@ex.ru;2;2026-11-02 11:00:00;Индивидуальное участие;Женский;;Москва;1:2",
            "Кривой;Формат;k@ex.ru;3;2026-11-02 12:00:00;Что-то;Мужской;;Омск;1:3"]
    for enc in ("utf-8-sig", "cp1251"):
        entries, errors = parse_csv("\n".join([head, *rows]).encode(enc), TODAY)
        assert [(e["surname"], at) for e, at in entries] == [
            ("Иванов", datetime.datetime(2026, 11, 1, 10)), ("Петрова", datetime.datetime(2026, 11, 2, 11))]
        assert len(errors) == 1 and errors[0].startswith("строка 4")


def test_csv_not_tilda():
    with pytest.raises(BadEntry, match="tranid"):
        parse_csv(b"a;b\n1;2", TODAY)
