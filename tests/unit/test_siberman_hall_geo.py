import datetime
from types import SimpleNamespace as NS

from src.siberman.hall.data import Entry
from src.siberman.hall.geo import City, applicant_cities, build_geo, city_of, load_cities, missing_report, resolve_places

SPB = City("Санкт-Петербург", "Россия", "643", 59.94, 30.31)
KRS = City("Красноярск", "Россия", "643", 56.01, 92.85)
ALA = City("Алматы", "Казахстан", "398", 43.24, 76.95)
DIR = {"санкт петербург": SPB, "красноярск": KRS, "алматы": ALA, "алма аты": ALA}
BD = datetime.date(1985, 5, 5)


def start(year, surname, city="", country="Россия", pid=None, fmt="individual", stage="none", status="active",
          team="", has_time=True):
    return Entry(year=year, bib="1", stage=stage, format=fmt, surname=surname, name="Тест", gender="M",
                 city=city, country=country, status=status, team=team, person_id=pid, has_time=has_time)


def person(pid, surname, manual="", bd=None):
    return NS(id=pid, surname=surname, name="Тест", birthdate=bd, city="", city_manual=manual)


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


def test_place_priority_manual_then_last_start_then_applicant():
    entries = [start(2019, "Первый", "Красноярск", pid=1),
               start(2023, "Первый", fmt="relay", stage="swim", pid=1),       # эстафета без города
               start(2024, "Второй", fmt="relay", stage="run", pid=2),        # город введён в админке
               start(2024, "Третий", fmt="relay", stage="run", pid=3),        # город из заявки
               start(2024, "Четвёртый", fmt="relay", stage="run", pid=4),     # неизвестно
               start(2024, "Пятый", "Алма-Аты", "Казахстан", pid=5, status="dns"),   # не стартовал
               start(2024, "Шестой", "Санкт Петербург"),                      # без реестра — по ФИ
               start(2024, "Седьмой", fmt="relay", stage="run", pid=11)]      # город заявки не из справочника
    persons = [person(1, "Первый", "Москва"), person(2, "Второй", "Красноярск"), person(3, "Третий", bd=BD),
               person(4, "Четвёртый"), person(11, "Седьмой", bd=BD)]
    places = resolve_places(entries, persons, [app("Третий", "Санкт-Петербург", BD),
                                               app("Седьмой", "Неизвестный посёлок", BD)], DIR)
    assert {k: (c.name if c else None) for k, c in places.items()} == {
        1: "Москва", 2: "Красноярск", 3: "Санкт-Петербург", 4: None, "шестой тест": "Санкт-Петербург", 11: None}


def test_geo_counts_people_once_by_last_city():
    entries = [start(2019, "Первый", "Красноярск", pid=1), start(2023, "Первый", "Красноярск", pid=1),
               start(2023, "Второй", "Алма-Аты", "Казахстан", pid=2), start(2024, "Третий", "Вантаа", "Финляндия", pid=3),
               start(2024, "Четвёртый", fmt="relay", stage="run", pid=4)]
    g = build_geo(entries, resolve_places(entries, [], [], DIR))
    assert (g["total"], g["known"]) == (4, 3)
    assert [(c["name"], c["iso"], c["count"]) for c in g["countries"]] == [
        ("Казахстан", "398", 1), ("Россия", "643", 1), ("Финляндия", "", 1)]
    krs = next(c for c in g["cities"] if c["name"] == "Красноярск")
    assert (krs["count"], krs["lat"], krs["people"]) == (1, 56.01, [{"person_id": 1, "fio": "Первый Тест"}])
    assert next(c for c in g["cities"] if c["name"] == "Вантаа")["lat"] is None


def test_missing_report_people_without_city_and_cities_without_coords():
    entries = [start(2023, "Второй", fmt="relay", stage="run", pid=2, team="Команда"),
               start(2024, "Третий", "Вантаа", "Финляндия", pid=3),
               start(2024, "Шестой", fmt="relay", stage="swim", team="Без реестра")]
    rep = missing_report(entries, resolve_places(entries, [], [], DIR))
    assert [(p["person_id"], p["fio"]) for p in rep["people"]] == [(2, "Второй Тест"), (None, "Шестой Тест")]
    assert rep["people"][0]["starts"] == [{"year": 2023, "format": "relay", "stage": "run", "team": "Команда"}]
    assert rep["no_coords"] == [{"name": "Вантаа", "country": "Финляндия", "count": 1}]


def test_no_marks_is_not_a_start_and_country_from_protocol():
    entries = [start(2026, "Неявка", "Омск", pid=7, has_time=False),    # стартовый протокол живого года
               start(2025, "Сосед", "Абакан", pid=8),
               start(2025, "Эстафетчик", fmt="relay", stage="run", pid=9),
               start(2025, "Сошедший", "Омск", pid=10, status="dnf", has_time=False)]
    places = resolve_places(entries, [person(9, "Эстафетчик", "абакан")], [], DIR)
    assert 7 not in places and places[10].name == "Омск"
    assert (places[9].name, places[9].country) == ("абакан", "Россия")      # страна — как у Абакана в протоколах
    g = build_geo(entries, places)
    assert [(c["name"], c["country"], c["count"]) for c in g["cities"]] == [("Абакан", "Россия", 2), ("Омск", "Россия", 1)]


def test_broken_or_missing_cities_json_is_ignored(tmp_path):
    bad = tmp_path / "cities.json"
    bad.write_text("[{", encoding="utf-8")
    assert load_cities(bad) == {} and load_cities(tmp_path / "нет.json") == {}


def test_cities_json_is_consistent():
    import json
    import re
    from src.siberman.hall.geo import CITIES_PATH
    from src.siberman.persons.linking import norm_city
    seen = {}
    for r in json.loads(CITIES_PATH.read_text(encoding="utf-8")):
        assert set(r) == {"name", "country", "iso", "lat", "lon", "aliases"} and r["name"] and r["country"], r
        assert re.fullmatch(r"\d{3}", r["iso"]) or r["iso"] == "", r
        assert (r["lat"] is None) == (r["lon"] is None), r
        if r["lat"] is not None:
            assert -90 <= r["lat"] <= 90 and -180 <= r["lon"] <= 180, r
        for spelling in (r["name"], *r["aliases"]):    # одно написание — один город (Железногорск!)
            assert seen.setdefault(norm_city(spelling), (r["name"], r["country"])) == (r["name"], r["country"]), spelling
