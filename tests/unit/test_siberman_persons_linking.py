import datetime

from src.siberman.persons.linking import (
    Applicant, Person, Registry, attach_birthdates, link_participants, norm_city, plain_key,
)


def row(year, bib, surname, name, fmt="individual", stage="none", gender="M", city="Красноярск"):
    return {"race_year": year, "bib": str(bib), "relay_stage": stage, "surname": surname, "name": name,
            "gender": gender, "format": fmt, "city": city, "country": "Россия"}


def relay(year, bib, stage, surname, name, gender="M"):
    return row(year, bib, surname, name, fmt="relay", stage=stage, gender=gender)


def run(rows, persons=(), links=None):
    reg = Registry(list(persons))
    new_links, reviews = link_participants(reg, rows, links or {})
    return reg, new_links, reviews


def key(r):
    return (r["race_year"], r["bib"], r["relay_stage"])


def test_plain_key_and_city():
    assert plain_key("ПЕЧЁНКИНА ", " Екатерина") == "печенкина екатерина"
    assert plain_key("Князева (Заволокина)", "Олеся") == "князева заволокина олеся"
    assert norm_city("г. Красноярск") == norm_city("красноярск") == "красноярск"
    assert norm_city("Ростов-на-Дону") == "ростов на дону"


def test_individual_same_bib_is_one_person_even_if_name_changes():
    a, b = row(2020, 7, "Иванова", "Анна", gender="F"), row(2024, 7, "Петрова (Иванова)", "Анна", gender="F")
    reg, links, reviews = run([a, b])
    assert links[key(a)] is links[key(b)]
    assert links[key(a)].bib_individual == "7"
    assert [r.kind for r in reviews] == ["bib_name_change"]
    assert reviews[0].natkey == key(b)


def test_namesakes_with_different_individual_bibs_are_two_people_without_review():
    a, b = row(2020, 7, "Кузнецов", "Олег"), row(2021, 58, "Кузнецов", "Олег")
    reg, links, reviews = run([a, b])
    assert links[key(a)] is not links[key(b)]
    assert reviews == []


def test_relay_member_two_stages_same_year_is_one_person():
    a, b = relay(2022, 101, "swim", "Смирнов", "Илья"), relay(2022, 101, "bike", "Смирнов", "Илья")
    reg, links, reviews = run([a, b])
    assert links[key(a)] is links[key(b)]
    assert reviews == []


def test_relay_namesakes_in_different_teams_same_year_are_two_people():
    a, b = relay(2022, 101, "swim", "Смирнов", "Илья"), relay(2022, 102, "run", "Смирнов", "Илья")
    reg, links, reviews = run([a, b])
    assert links[key(a)] is not links[key(b)]
    assert reviews == []


def test_relay_then_individual_links_and_asks_to_check():
    a, b = relay(2020, 101, "run", "Петров", "Андрей"), row(2021, 7, "Петров", "Андрей")
    reg, links, reviews = run([a, b])
    assert links[key(a)] is links[key(b)]
    assert links[key(b)].bib_individual == "7"
    assert [r.kind for r in reviews] == ["format_switch"]


def test_two_candidates_make_new_person_and_review():
    rows = [row(2020, 7, "Кузнецов", "Олег"), row(2021, 58, "Кузнецов", "Олег"),
            relay(2022, 103, "bike", "Кузнецов", "Олег")]
    reg, links, reviews = run(rows)
    third = links[key(rows[2])]
    assert third not in (links[key(rows[0])], links[key(rows[1])])
    assert [r.kind for r in reviews] == ["namesake_candidate"]
    assert reviews[0].person is third and len(reviews[0].others) == 2


def test_gender_mismatch_is_not_the_same_person():
    a, b = relay(2020, 101, "swim", "Белых", "Саша", gender="F"), relay(2021, 105, "run", "Белых", "Саша", gender="M")
    reg, links, reviews = run([a, b])
    assert links[key(a)] is not links[key(b)]


def test_existing_links_are_kept_and_used():
    p = Person(id=5, surname="Орлова", name="Мария", gender="F", bib_individual="23")
    a, b = row(2023, 23, "Орлова", "Мария", gender="F"), row(2024, 23, "Орлова", "Мария", gender="F")
    reg, links, reviews = run([a, b], persons=[p], links={key(a): 5})
    assert list(links) == [key(b)] and links[key(b)] is reg.by_id[5]
    assert reg.new == [] and reviews == []


def test_second_run_links_nothing():
    rows = [row(2020, 7, "Кузнецов", "Олег"), row(2021, 58, "Кузнецов", "Олег"),
            relay(2022, 101, "swim", "Смирнов", "Илья"), relay(2022, 101, "bike", "Смирнов", "Илья")]
    reg, links, _ = run(rows)
    for i, p in enumerate(reg.new, start=100):
        p.id = i
    persons = [Person(id=p.id, surname=p.surname, name=p.name, gender=p.gender,
                      bib_individual=p.bib_individual) for p in reg.new]
    saved = {k: p.id for k, p in links.items()}
    reg2, links2, reviews2 = run(rows, persons=persons, links=saved)
    assert links2 == {} and reg2.new == [] and reviews2 == []


def app(tranid, surname, name, bd, gender=None, city=""):
    return Applicant(tranid=tranid, surname=surname, name=name, gender=gender, birthdate=bd, city=city)


def test_birthdate_attached_to_single_match():
    p = Person(id=1, surname="Иванов", name="Алексей", gender="M", city="Москва")
    reg = Registry([p])
    updates, reviews = attach_birthdates(reg, [app("t1", "Иванов", "Алексей", datetime.date(1985, 5, 30), "M", "Москва")])
    assert updates == [(p, datetime.date(1985, 5, 30))] and p.birthdate == datetime.date(1985, 5, 30)
    assert reviews == []


def test_swapped_surname_and_name_still_match():
    p = Person(id=1, surname="Herinckx", name="Wijnand", gender="M")
    updates, _ = attach_birthdates(Registry([p]), [app("t1", "Wijnand", "Herinckx", datetime.date(1984, 5, 12))])
    assert updates and p.birthdate == datetime.date(1984, 5, 12)


def test_other_birthdate_makes_conflict_review():
    p = Person(id=1, surname="Иванов", name="Алексей", gender="M", birthdate=datetime.date(1985, 5, 30))
    updates, reviews = attach_birthdates(Registry([p]), [app("t2", "Иванов", "Алексей", datetime.date(1986, 5, 30))])
    assert updates == [] and [r.kind for r in reviews] == ["bd_conflict"]
    assert reviews[0].person is p and reviews[0].detail == "t2"


def test_ambiguous_applicant_between_namesakes():
    a = Person(id=1, surname="Иванов", name="Никита", gender="M")
    b = Person(id=2, surname="Иванов", name="Никита", gender="M")
    updates, reviews = attach_birthdates(Registry([a, b]), [app("t3", "Иванов", "Никита", datetime.date(1994, 7, 12))])
    assert updates == [] and [r.kind for r in reviews] == ["applicant_ambiguous"]
    assert set(reviews[0].others) == {a, b}


def test_namesake_with_matching_birthdate_needs_nothing():
    a = Person(id=1, surname="Иванов", name="Никита", gender="M", birthdate=datetime.date(1994, 7, 12))
    b = Person(id=2, surname="Иванов", name="Никита", gender="M")
    updates, reviews = attach_birthdates(Registry([a, b]), [app("t3", "Иванов", "Никита", datetime.date(1994, 7, 12))])
    assert updates == [] and reviews == []


def test_city_mismatch_is_not_attached():
    p = Person(id=1, surname="Иванов", name="Никита", gender="M", city="Томск")
    updates, reviews = attach_birthdates(Registry([p]), [app("t4", "Иванов", "Никита", datetime.date(1989, 8, 21), city="Красноярск")])
    assert updates == [] and [r.kind for r in reviews] == ["applicant_city_mismatch"]


def test_review_dedupe_keys():
    a = row(2024, 7, "Петрова", "Анна", gender="F")
    reg, links, _ = run([row(2020, 7, "Иванова", "Анна", gender="F"), a])
    p = links[key(a)]
    p.id = 42
    from src.siberman.persons.linking import Review
    assert Review("bib_name_change", natkey=key(a), person=p).dedupe_key() == "bib_name_change:2024:7:none"
    assert Review("bd_conflict", person=p, detail="t9").dedupe_key() == "bd_conflict:42:t9"
