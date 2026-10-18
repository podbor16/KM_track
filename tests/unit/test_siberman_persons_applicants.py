import datetime

import pytest

from src.siberman.persons.applicants import parse_applicants_csv, parse_birthdate

COLS = ("Email;Name;Phone;Date;city;format;tranid;formid;sex;surname;birthday;"
        "surname_swim;name_swim;birthday_swim;surname_bike;name_bike;birthday_bike;"
        "surname_run;name_run;birthday_run").split(";")
TODAY = datetime.date(2026, 10, 18)


def line(**kw):
    return ";".join(kw.get(c, "") for c in COLS)


def csv_bytes(*lines):
    return (chr(0xFEFF) + ";".join(COLS) + "\n" + "\n".join(lines)).encode("utf-8")


def test_individual_with_birthdate():
    apps, stats = parse_applicants_csv(csv_bytes(line(
        Email="a@x", Name="Анна", Date="2025-10-28 08:06:01", city="Красноярск", tranid="1:2",
        sex="Женский", surname="Тестова", birthday="20.01.1978")), today=TODAY)
    assert len(apps) == 1
    a = apps[0]
    assert (a.tranid, a.surname, a.name, a.gender, a.birthdate, a.city) == (
        "1:2", "Тестова", "Анна", "F", datetime.date(1978, 1, 20), "Красноярск")
    assert a.submitted_at == datetime.datetime(2025, 10, 28, 8, 6, 1)
    assert stats == {"rows": 1, "people": 1, "no_birthday": 0, "bad_birthday": 0}


def test_old_form_without_surname_is_skipped():
    apps, stats = parse_applicants_csv(csv_bytes(line(Name="Иван Тестов", Date="2023-11-24 00:01:40", tranid="1:1")),
                                       today=TODAY)
    assert apps == [] and stats["rows"] == 1 and stats["people"] == 0


def test_relay_members_get_own_records():
    apps, _ = parse_applicants_csv(csv_bytes(line(
        Name="Ирина", tranid="1:3", surname="Тестова", birthday="20.01.1978",
        surname_swim="Пловцова", name_swim="Элина", birthday_swim="01.02.2005",
        surname_bike="Велосипедов", name_bike="Андрей", birthday_bike="20-04-1977",
        surname_run="Бегунова", name_run="Ирина", birthday_run="")), today=TODAY)
    by_id = {a.tranid: a for a in apps}
    assert set(by_id) == {"1:3", "1:3:swim", "1:3:bike"}
    assert by_id["1:3:bike"].birthdate == datetime.date(1977, 4, 20)
    assert by_id["1:3:swim"].gender is None


def test_bad_and_too_young_dates_are_counted():
    apps, stats = parse_applicants_csv(csv_bytes(
        line(tranid="1:4", surname="Тестов", Name="А", birthday="31.02.1990"),
        line(tranid="1:5", surname="Тестов", Name="Б", birthday="09.01.2025"),
        line(tranid="1:6", surname="Тестов", Name="В", birthday="")), today=TODAY)
    assert apps == []
    assert stats["bad_birthday"] == 2 and stats["no_birthday"] == 1


def test_same_tranid_twice_keeps_last():
    apps, _ = parse_applicants_csv(csv_bytes(
        line(tranid="1:7", surname="Тестов", Name="Иван", birthday="01.01.1980"),
        line(tranid="1:7", surname="Тестов", Name="Иван", birthday="02.01.1980")), today=TODAY)
    assert len(apps) == 1 and apps[0].birthdate == datetime.date(1980, 1, 2)


def test_not_a_tilda_export():
    with pytest.raises(ValueError):
        parse_applicants_csv(b"a;b\n1;2", today=TODAY)


def test_parse_birthdate_formats():
    assert parse_birthdate("01.05.1981", TODAY) == datetime.date(1981, 5, 1)
    assert parse_birthdate("01-05-1981", TODAY) == datetime.date(1981, 5, 1)
    assert parse_birthdate("1981-05-01", TODAY) is None
    assert parse_birthdate("01.05.1920", TODAY) is None
