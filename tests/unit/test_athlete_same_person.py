import datetime as dt

from src.krasmarafon.services.athlete_claims import same_person

CARD = {"surname": "Иванов", "name": "Пётр", "birthday": dt.date(1986, 5, 1)}


def row(surname="Иванов", name="Пётр", birthday=dt.date(1986, 5, 1)):
    return {"surname": surname, "name": name, "birthday": birthday}


def test_same_and_case_yo_insensitive():
    assert same_person(CARD, row())
    assert same_person(CARD, row("ИВАНОВ", " петр "))


def test_typos_swapped_and_sentinel_birthday_are_same_person():
    assert same_person(CARD, row("Иванова", "Пётр"))            # опечатка в фамилии
    assert same_person(CARD, row("Пётр", "Иванов"))             # фамилия и имя переставлены
    assert same_person(CARD, row(birthday=dt.date(1900, 1, 1)))  # ДР-заглушка
    assert same_person(CARD, row(birthday=None))
    assert same_person(CARD, row(birthday=dt.date(1986, 5, 2)))  # опечатка в цифре
    assert same_person(CARD, row(birthday=dt.date(1986, 1, 5)))  # день и месяц наоборот


def test_other_person_in_same_slot_is_not():
    assert not same_person(CARD, row("Сидорова", "Мария", dt.date(2018, 3, 2)))
    assert not same_person(CARD, row("Иванов", "Пётр", dt.date(2018, 3, 2)))   # тёзка (сын), другая ДР
    assert not same_person(CARD, row("Сидоров", "Пётр"))


def test_card_without_birthday_matches_any_birthday():
    assert same_person(dict(CARD, birthday=dt.date(1900, 1, 1)), row(birthday=dt.date(2018, 3, 2)))
