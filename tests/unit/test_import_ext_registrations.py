import datetime
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "import_ext_registrations", Path(__file__).parents[2] / "scripts" / "import_ext_registrations.py")
m = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(m)


def test_birthday():
    assert m.parse_birthday(datetime.datetime(1985, 7, 14)) == datetime.date(1985, 7, 14)
    assert m.parse_birthday("14.07.1985") == datetime.date(1985, 7, 14)
    assert m.parse_birthday("1985-07-14") == datetime.date(1985, 7, 14)
    assert m.parse_birthday("1985-07-14 00:00:00") == datetime.date(1985, 7, 14)
    assert m.parse_birthday("мусор") is None
    assert m.parse_birthday("31.02.1985") is None
    assert m.parse_birthday(datetime.datetime(1905, 1, 1)) is None
    assert m.parse_birthday(None) is None


def test_phone():
    assert m.parse_phone("+7 (923) 123-45-87") == "9231234587"
    assert m.parse_phone(89231234587.0) == "9231234587"
    assert m.parse_phone("12345") == ""
    assert m.parse_phone(None) == ""


def test_year():
    assert m.parse_year("РЖД 2019, 5 км") == 2019
    assert m.parse_year("без года") is None
    assert m.parse_year(None) is None


def test_email():
    assert m.parse_email("  A@Mail.RU ") == "a@mail.ru"
    assert m.parse_email("example@mail.ru") == ""
    assert m.parse_email("нет") == ""
