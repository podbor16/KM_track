import datetime
from types import SimpleNamespace as NS

from src.siberman.hall.data import Entry
from src.siberman.hall.geo import City, applicant_cities, city_of, resolve_places

SPB = City("Санкт-Петербург", "Россия", "643", 59.94, 30.31)
KRS = City("Красноярск", "Россия", "643", 56.01, 92.85)
ALA = City("Алматы", "Казахстан", "398", 43.24, 76.95)
DIR = {"санкт петербург": SPB, "красноярск": KRS, "алматы": ALA, "алма аты": ALA}
BD = datetime.date(1985, 5, 5)


def start(year, surname, city="", country="Россия", pid=None, fmt="individual", stage="none", status="active",
          team=""):
    return Entry(year=year, bib="1", stage=stage, format=fmt, surname=surname, name="Тест", gender="M",
                 city=city, country=country, status=status, team=team, person_id=pid)


def person(pid, surname, city="", bd=None):
    return NS(id=pid, surname=surname, name="Тест", birthdate=bd, city=city)


def app(surname, city, bd, when=datetime.datetime(2025, 1, 1), name="Тест"):
    return NS(surname=surname, name=name, birthdate=bd, city=city, submitted_at=when)


def test_city_spellings_and_unknown_city():
    assert city_of("г. Санкт Петербург", "Россия", DIR) is SPB
    assert city_of("Алма-Аты", "Казахстан", DIR) is ALA
    unknown = city_of("  Вантаа ", "Финляндия", DIR)
    assert (unknown.name, unknown.country, unknown.iso, unknown.lat) == ("Вантаа", "Финляндия", "", None)
    assert city_of("-", "Россия", DIR) is None and city_of("", "Россия", DIR) is None


def test_applicant_city_needs_same_birthdate_and_one_person():
    persons = [person(1, "Иванов", bd=BD), person(2, "Петров", bd=BD), person(3, "Петров", bd=BD),
               person(4, "Сидоров"), person(5, "Кузнецов", bd=BD)]
    apps = [app("Иванов", "Абакан", BD, datetime.datetime(2024, 1, 1)),
            app("Иванов", "Красноярск", BD, datetime.datetime(2025, 3, 1)),   # последняя заявка
            app("Петров", "Омск", BD),                                        # два Петрова с той же ДР
            app("Сидоров", "Омск", BD),                                       # у человека нет ДР
            app("Иванов", "Чита", datetime.date(1990, 1, 1)),                 # другая ДР
            app("Тест", "Тула", BD, name="Кузнецов")]                         # ФИ наоборот
    assert applicant_cities(persons, apps) == {1: "Красноярск", 5: "Тула"}


def test_place_priority_last_start_then_registry_then_applicant():
    entries = [start(2019, "Первый", "Красноярск", pid=1),
               start(2023, "Первый", fmt="relay", stage="swim", pid=1),       # эстафета без города
               start(2024, "Второй", fmt="relay", stage="run", pid=2),        # город введён в админке
               start(2024, "Третий", fmt="relay", stage="run", pid=3),        # город из заявки
               start(2024, "Четвёртый", fmt="relay", stage="run", pid=4),     # неизвестно
               start(2024, "Пятый", "Алма-Аты", "Казахстан", pid=5, status="dns"),   # не стартовал
               start(2024, "Шестой", "Санкт Петербург")]                      # без реестра — по ФИ
    persons = [person(1, "Первый", "Москва"), person(2, "Второй", "Красноярск"), person(3, "Третий", bd=BD),
               person(4, "Четвёртый")]
    places = resolve_places(entries, persons, [app("Третий", "Санкт-Петербург", BD)], DIR)
    assert {k: (c.name if c else None) for k, c in places.items()} == {
        1: "Красноярск", 2: "Красноярск", 3: "Санкт-Петербург", 4: None, "шестой тест": "Санкт-Петербург"}
