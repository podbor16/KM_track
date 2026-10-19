import datetime

from src.siberman.persons.linking import (
    Applicant, Person, Registry, Review, attach_birthdates, link_participants, norm_city, plain_key,
)


def row(year, bib, surname, name, fmt="individual", stage="none", gender="M", city="Красноярск"):
    return {"race_year": year, "bib": str(bib), "relay_stage": stage, "surname": surname, "name": name,
            "gender": gender, "format": fmt, "city": city, "country": "Россия"}


def relay(year, bib, stage, surname, name, gender="M"):
    return row(year, bib, surname, name, fmt="relay", stage=stage, gender=gender)


def key(r):
    return (r["race_year"], r["bib"], r["relay_stage"])


def saved(rows, new_links, manual=0):
    """Как сохранит service: {natkey: (person_id, manual, name_key)}."""
    names = {key(r): plain_key(r["surname"], r["name"]) for r in rows}
    return {k: (p.id, manual, names[k]) for k, p in new_links.items()}


def run(rows, persons=(), links=None):
    reg = Registry(list(persons))
    new_links, reviews = link_participants(reg, rows, links or {})
    return reg, new_links, reviews


def fresh(persons):
    return [Person(id=p.id, surname=p.surname, name=p.name, gender=p.gender, bib_individual=p.bib_individual)
            for p in persons]


def test_plain_key_and_city():
    assert plain_key("ПЕЧЁНКИНА ", " Екатерина") == "печенкина екатерина"
    assert plain_key("Князева (Заволокина)", "Олеся") == "князева заволокина олеся"
    assert norm_city("г. Красноярск") == norm_city("красноярск") == norm_city("Город Красноярск") == "красноярск"
    assert norm_city("Ростов-на-Дону") == "ростов на дону"


def test_individual_same_bib_is_one_person_even_if_name_changes():
    a, b = row(2020, 7, "Иванова", "Анна", gender="F"), row(2024, 7, "Петрова (Иванова)", "Анна", gender="F")
    reg, links, reviews = run([a, b])
    assert links[key(a)] is links[key(b)]
    assert links[key(a)].bib_individual == "7"
    assert [r.kind for r in reviews] == ["bib_name_change"]
    assert reviews[0].natkey == key(b)


def test_same_bib_other_gender_is_flagged_separately():
    a, b = row(2020, 7, "Иванов", "Саша", gender="M"), row(2024, 7, "Иванова", "Саша", gender="F")
    reg, links, reviews = run([a, b])
    assert links[key(a)] is links[key(b)]
    assert [r.kind for r in reviews] == ["bib_gender_mismatch"]


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


def test_individual_and_relay_namesakes_same_year_are_two_people():
    a, b = row(2022, 7, "Смирнов", "Илья"), relay(2022, 101, "run", "Смирнов", "Илья")
    reg, links, reviews = run([a, b])
    assert links[key(a)] is not links[key(b)]


def test_relay_then_individual_links_and_asks_to_check():
    a, b = relay(2020, 101, "run", "Петров", "Андрей"), row(2021, 7, "Петров", "Андрей")
    reg, links, reviews = run([a, b])
    assert links[key(a)] is links[key(b)]
    assert links[key(b)].bib_individual == "7"
    assert [r.kind for r in reviews] == ["format_switch"]


def test_individual_then_relay_links_and_asks_to_check():
    a, b = row(2020, 7, "Петров", "Андрей"), relay(2021, 101, "run", "Петров", "Андрей")
    reg, links, reviews = run([a, b])
    assert links[key(a)] is links[key(b)]
    assert [r.kind for r in reviews] == ["format_switch"]


def test_two_candidates_make_new_person_and_review():
    rows = [row(2020, 7, "Кузнецов", "Олег"), row(2021, 58, "Кузнецов", "Олег"),
            relay(2022, 103, "bike", "Кузнецов", "Олег")]
    reg, links, reviews = run(rows)
    third = links[key(rows[2])]
    assert third not in (links[key(rows[0])], links[key(rows[1])])
    assert [r.kind for r in reviews] == ["namesake_candidate"]
    assert reviews[0].person is third and len(reviews[0].others) == 2


def test_gender_mismatch_is_not_merged_but_flagged():
    a, b = relay(2020, 101, "swim", "Белых", "Саша", gender="F"), relay(2021, 105, "run", "Белых", "Саша", gender="M")
    reg, links, reviews = run([a, b])
    assert links[key(a)] is not links[key(b)]
    assert [r.kind for r in reviews] == ["gender_mismatch"]
    assert reviews[0].others == (links[key(a)],)


def test_rows_without_surname_are_not_linked():
    a, b = relay(2020, 101, "swim", "", ""), relay(2021, 105, "swim", " ", "")
    reg, links, reviews = run([a, b])
    assert links == {} and reg.new == []


def test_existing_links_are_kept_and_used():
    p = Person(id=5, surname="Орлова", name="Мария", gender="F", bib_individual="23")
    a, b = row(2023, 23, "Орлова", "Мария", gender="F"), row(2024, 23, "Орлова", "Мария", gender="F")
    reg, links, reviews = run([a, b], persons=[p], links={key(a): (5, 0, "орлова мария")})
    assert list(links) == [key(b)] and links[key(b)] is reg.by_id[5]
    assert reg.new == [] and reviews == []


def test_second_run_links_nothing():
    rows = [row(2020, 7, "Кузнецов", "Олег"), row(2021, 58, "Кузнецов", "Олег"),
            relay(2022, 101, "swim", "Смирнов", "Илья"), relay(2022, 101, "bike", "Смирнов", "Илья")]
    reg, links, _ = run(rows)
    for i, p in enumerate(reg.new, start=100):
        p.id = i
    reg2, links2, reviews2 = run(rows, persons=fresh(reg.new), links=saved(rows, links))
    assert links2 == {} and reg2.new == [] and reviews2 == []


def test_relay_member_replaced_on_reload_is_resolved_again():
    """Перезагрузка года: на номере 101 этап плавания теперь у другого человека. Прежняя
    автопривязка не должна молча отдать его выступление и его ФИ прежнему человеку."""
    old = [relay(2020, 101, "swim", "Иванов", "Иван")]
    reg, links, _ = run(old)
    links[key(old[0])].id = 1
    store = saved(old, links)
    new = [relay(2020, 101, "swim", "Петров", "Пётр"), relay(2021, 107, "swim", "Петров", "Пётр")]
    reg2, links2, _ = run(new, persons=fresh(reg.new), links=store)
    assert links2[key(new[0])] is not reg2.by_id[1]
    assert links2[key(new[0])] is links2[key(new[1])]
    assert "петров петр" not in reg2.by_id[1].keys


def test_manual_link_name_change_is_kept_but_flagged():
    p = Person(id=5, surname="Иванов", name="Иван", gender="M")
    r = relay(2020, 101, "swim", "Петров", "Пётр")
    reg, links, reviews = run([r], persons=[p], links={key(r): (5, 1, "иванов иван")})
    assert links == {}
    assert [(x.kind, x.person) for x in reviews] == [("manual_name_changed", reg.by_id[5])]
    assert reviews[0].detail == "петров петр"
    assert "петров петр" not in reg.by_id[5].keys


def app(tranid, surname, name, bd, gender=None, city="", starts=1, submitted=None):
    return Applicant(tranid=tranid, surname=surname, name=name, gender=gender, birthdate=bd, city=city,
                     submitted_at=submitted, claimed_starts=starts)


def test_birthdate_attached_to_single_match_with_claimed_starts():
    p = Person(id=1, surname="Иванов", name="Алексей", gender="M", city="Москва")
    reg = Registry([p])
    updates, reviews = attach_birthdates(reg, [app("t1", "Иванов", "Алексей", datetime.date(1985, 5, 30), "M", "Москва")])
    assert updates == [(p, datetime.date(1985, 5, 30))] and p.birthdate == datetime.date(1985, 5, 30)
    assert reviews == []


def test_applicant_without_claimed_starts_is_only_suggested():
    p = Person(id=1, surname="Иванов", name="Алексей", gender="M")
    for starts in (0, None):
        updates, reviews = attach_birthdates(Registry([p]), [app("t1", "Иванов", "Алексей", datetime.date(1985, 5, 30),
                                                                 starts=starts)])
        assert updates == [] and [r.kind for r in reviews] == ["applicant_unconfirmed"]
        assert p.birthdate is None


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
    updates, reviews = attach_birthdates(Registry([p]), [app("t4", "Иванов", "Никита", datetime.date(1989, 8, 21),
                                                             city="Красноярск")])
    assert updates == [] and [r.kind for r in reviews] == ["applicant_city_mismatch"]


def test_earliest_application_wins():
    p = Person(id=1, surname="Иванов", name="Алексей", gender="M")
    early = app("9:1", "Иванов", "Алексей", datetime.date(1985, 5, 30), submitted=datetime.datetime(2024, 10, 20))
    late = app("10:1", "Иванов", "Алексей", datetime.date(1985, 5, 31), submitted=datetime.datetime(2025, 8, 1))
    updates, reviews = attach_birthdates(Registry([p]), [late, early])
    assert p.birthdate == datetime.date(1985, 5, 30)
    assert [(r.kind, r.detail) for r in reviews] == [("bd_conflict", "10:1")]


def test_review_dedupe_keys():
    a = row(2024, 7, "Петрова", "Анна", gender="F")
    reg, links, _ = run([row(2020, 7, "Иванова", "Анна", gender="F"), a])
    p = links[key(a)]
    p.id = 42
    assert Review("bib_name_change", natkey=key(a), person=p).dedupe_key() == "bib_name_change:2024:7:none"
    assert Review("bd_conflict", person=p, detail="t9").dedupe_key() == "bd_conflict:42:t9"
    first = Review("relinked", natkey=key(a), person=p, detail="петров петр").dedupe_key()
    second = Review("relinked", natkey=key(a), person=p, detail="петрова петра").dedupe_key()
    assert first == "relinked:2024:7:none:петров петр" and first != second


def test_cleared_surname_drops_auto_link_only():
    p = Person(id=1, surname="Иванов", name="Иван", gender="M")
    auto, manual = relay(2020, 101, "swim", "", ""), relay(2020, 102, "swim", " ", "")
    reg, links, reviews = run([auto, manual], persons=[p],
                              links={key(auto): (1, 0, "иванов иван"), key(manual): (1, 1, "иванов иван")})
    assert reg.dropped == [key(auto)]
    assert links == {}
    assert [(x.kind, x.natkey) for x in reviews] == [("manual_name_changed", key(manual))]


def test_relinked_after_typo_fix_keeps_trace():
    prev = Person(id=1, surname="Ивнов", name="Иван", gender="M")
    a, b = relay(2019, 100, "run", "Ивнов", "Иван"), relay(2020, 101, "swim", "Иванов", "Иван")
    reg, links, reviews = run([a, b], persons=[prev],
                              links={key(a): (1, 0, "ивнов иван"), key(b): (1, 0, "ивнов иван")})
    new = links[key(b)]
    assert new is not reg.by_id[1]
    assert [(x.kind, x.person, x.others) for x in reviews] == [("relinked", new, (reg.by_id[1],))]
    assert reviews[0].detail == "иванов иван"


def test_individual_namesake_with_own_bib_is_not_gender_mismatch():
    a, b = row(2020, 7, "Иванов", "Саша", gender="M"), row(2021, 8, "Иванов", "Саша", gender="F")
    reg, links, reviews = run([a, b])
    assert links[key(a)] is not links[key(b)]
    assert reviews == []
