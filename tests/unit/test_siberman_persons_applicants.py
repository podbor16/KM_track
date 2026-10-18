import datetime

import pytest

from src.siberman.persons.applicants import parse_applicants_csv, parse_birthdate

COLS = ("Email;Name;Phone;Date;city;format;tranid;formid;sex;surname;birthday;city_2;"
        "siberman_individual_starts;siberman_individual_starts_2;siberman_relay_starts;"
        "surname_swim;name_swim;birthday_swim;surname_bike;name_bike;birthday_bike;"
        "surname_run;name_run;birthday_run").split(";")
TODAY = datetime.date(2026, 10, 18)


def line(**kw):
    return ";".join(kw.get(c, "") for c in COLS)


def csv_bytes(*lines, encoding="utf-8", bom=True, sep="\n"):
    return ((chr(0xFEFF) if bom else "") + ";".join(COLS) + sep + sep.join(lines)).encode(encoding)


def test_individual_with_birthdate_and_claimed_starts():
    apps, stats = parse_applicants_csv(csv_bytes(line(
        Email="a@x", Name="Анна", Date="2025-10-28 08:06:01", city="Красноярск", tranid="1:2",
        format="Индивидуальное участие", sex="Женский", surname="Тестова", birthday="20.01.1978",
        siberman_individual_starts="1", siberman_relay_starts="2")), today=TODAY)
    assert len(apps) == 1
    a = apps[0]
    assert (a.tranid, a.surname, a.name, a.gender, a.birthdate, a.city, a.claimed_starts) == (
        "1:2", "Тестова", "Анна", "F", datetime.date(1978, 1, 20), "Красноярск", 3)
    assert a.submitted_at == datetime.datetime(2025, 10, 28, 8, 6, 1)
    assert stats == {"rows": 1, "people": 1, "no_birthday": 0, "bad_birthday": 0}


def test_men_gender_and_city_2_and_no_starts():
    apps, _ = parse_applicants_csv(csv_bytes(line(
        Name="Иван", tranid="1:8", sex="Мужской", surname="Тестов", birthday="01.01.1980", city_2="Томск",
        siberman_individual_starts_2="")), today=TODAY)
    assert (apps[0].gender, apps[0].city, apps[0].claimed_starts) == ("M", "Томск", 0)


def test_old_form_without_surname_is_skipped():
    apps, stats = parse_applicants_csv(csv_bytes(line(Name="Иван Тестов", Date="2023-11-24 00:01:40", tranid="1:1")),
                                       today=TODAY)
    assert apps == [] and stats["rows"] == 1 and stats["people"] == 0


def test_relay_members_get_own_records_and_captain_is_skipped():
    apps, _ = parse_applicants_csv(csv_bytes(line(
        Name="Ирина", tranid="1:3", format="Эстафетная команда", surname="Тестова", birthday="20.01.1978",
        surname_swim="Пловцова", name_swim="Элина", birthday_swim="01.02.2005",
        surname_bike="Велосипедов", name_bike="Андрей", birthday_bike="20-04-1977",
        surname_run="Бегунова", name_run="Ирина", birthday_run="")), today=TODAY)
    by_id = {a.tranid: a for a in apps}
    assert set(by_id) == {"1:3:swim", "1:3:bike"}
    assert by_id["1:3:bike"].birthdate == datetime.date(1977, 4, 20)
    assert by_id["1:3:swim"].gender is None and by_id["1:3:swim"].claimed_starts is None


def test_bad_and_too_young_dates_are_counted():
    apps, stats = parse_applicants_csv(csv_bytes(
        line(tranid="1:4", surname="Тестов", Name="А", birthday="31.02.1990"),
        line(tranid="1:5", surname="Тестов", Name="Б", birthday="09.01.2025"),
        line(tranid="1:6", surname="Тестов", Name="В", birthday="")), today=TODAY)
    assert apps == []
    assert stats["bad_birthday"] == 2 and stats["no_birthday"] == 1


def test_min_age_boundary():
    assert parse_birthdate("31.12.2012", TODAY) == datetime.date(2012, 12, 31)
    assert parse_birthdate("01.01.2013", TODAY) is None


def test_same_tranid_twice_keeps_last():
    apps, _ = parse_applicants_csv(csv_bytes(
        line(tranid="1:7", surname="Тестов", Name="Иван", birthday="01.01.1980"),
        line(tranid="1:7", surname="Тестов", Name="Иван", birthday="02.01.1980")), today=TODAY)
    assert len(apps) == 1 and apps[0].birthdate == datetime.date(1980, 1, 2)


def test_quoted_newline_crlf_and_cp1251():
    text_line = line(tranid="1:9", surname="Тестов", Name="Иван", birthday="01.01.1980")
    quoted = text_line.replace("1:9", '"1:9"', 1)
    for data in (csv_bytes(quoted, sep="\r\n"), csv_bytes(text_line, encoding="cp1251", bom=False)):
        apps, _ = parse_applicants_csv(data, today=TODAY)
        assert [(a.tranid, a.surname) for a in apps] == [("1:9", "Тестов")]
    multiline = line(tranid="1:10", surname="Тестов", Name="Иван", birthday="01.01.1980").replace(
        "a@x", "", 1)
    data = (";".join(COLS) + "\n" + multiline.replace(";;", ';"две\nстроки";', 1)).encode("utf-8")
    apps, _ = parse_applicants_csv(data, today=TODAY)
    assert [a.tranid for a in apps] == ["1:10"]


def test_not_a_tilda_export():
    with pytest.raises(ValueError):
        parse_applicants_csv(b"a;b\n1;2", today=TODAY)


def test_parse_birthdate_formats():
    assert parse_birthdate("01.05.1981", TODAY) == datetime.date(1981, 5, 1)
    assert parse_birthdate("01-05-1981", TODAY) == datetime.date(1981, 5, 1)
    assert parse_birthdate("1981-05-01", TODAY) is None
    assert parse_birthdate("01.05.1920", TODAY) is None
