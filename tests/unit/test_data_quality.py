"""Проверки привязки к карточкам — на реальных случаях аудита 2026-10-01."""
import pytest

from src.analytics.data_quality import (Data, check_category, check_duplicates, check_hygiene,
                                        check_lead_on_other_card, check_twins, compatible_bd, merge_blockers, names_compatible,
                                        propose_birthday, run_checks)
from src.common.names import Names

_FILL = ([("Иванов", n, "Мужчина") for n in ("Виктор", "Сергей", "Владимир", "Вадим", "Иван", "Матвей")] * 6
         + [("Иванова", n, "Женщина") for n in ("Виктория", "Ирина", "Анна", "Марина", "Юлия", "Дарья", "Мария")] * 6)
NAMES = Names(_FILL)

EVENTS = [
    {"id": 1, "event_name": "Снежная семерка", "event_distance": 7.0, "event_year": 2025},
    {"id": 2, "event_name": "Жара", "event_distance": 5.0, "event_year": 2026},
    {"id": 3, "event_name": "Ночной забег", "event_distance": 5.0, "event_year": 2024},
    {"id": 4, "event_name": "Ночной забег", "event_distance": 5.0, "event_year": 2026},
]


def C(i, s, n, bd):
    return {"id": i, "surname": s, "name": n, "birthday": bd}


def L(i, cid, s, n, bd, eid, bib=None):
    return {"id": i, "client_id": cid, "surname": s, "name": n, "birthday": bd, "sex": "", "event_id": eid,
            "start_number": bib}


def R(i, cid, s, n, bd, eid, bib, cat="", status="Finished", sex="Мужчина"):
    return {"id": i, "client_id": cid, "surname": s, "name": n, "birthday": bd, "sex": sex, "event_id": eid,
            "start_number": bib, "category": cat, "race_status": status}


def data(clients, leads=(), results=()):
    d = Data(list(clients), list(leads), list(results), EVENTS)
    d.names = NAMES
    return d


# ---------------------------------------------------------------- правила

@pytest.mark.parametrize("x, y, ok", [
    ("1983-04-08", "1983-01-01", True),      # год из протокола
    ("1900-01-01", "1979-06-26", True),      # заглушка
    ("1981-06-09", "1980-06-09", True),      # цифра
    ("1990-02-14", "2024-02-14", True),      # год регистрации
    ("1986-09-19", "2011-02-17", False),     # отец и сын
    ("1991-05-11", "1991-07-17", False),     # разные полные даты
])
def test_compatible_bd(x, y, ok):
    assert compatible_bd(x, y) is ok


@pytest.mark.parametrize("a, b, ok", [
    ("Ира", "Ирина", True), ("Анюта", "Анна", True), ("Светла", "Светлана", True), ("Гора", "Егор", True),
    ("Марина", "Марта", False), ("Виктор", "Виктория", False), ("Ратмир", "Ратмира", False), ("Дарья", "Мария", False),
])
def test_names_compatible(a, b, ok):
    assert names_compatible(a, b, NAMES) is ok


def test_propose_birthday_trusts_timing_majority():
    # Коноваленко: в карточке ДР из заявки, в протоколах — другая
    d = data([C(1, "Коноваленко", "Юлия", "1991-07-17")],
             results=[R(i, 1, "Коноваленко", "Юлия", "1991-05-11", 2, 10 + i, sex="Женщина") for i in range(3)])
    assert propose_birthday([1], d) == "1991-05-11"


def test_propose_birthday_skips_placeholders_and_registration_year():
    # Курпас: «2024-02-14» в Ночном 2024 — год регистрации; «01-01» и 1900 — заглушки
    d = data([C(1, "Курпас", "Татьяна", "1900-01-01")],
             results=[R(1, 1, "Курпас", "Татьяна", "2024-02-14", 3, 1), R(2, 1, "Курпас", "Татьяна", "1990-02-14", 4, 2),
                      R(3, 1, "Курпас", "Татьяна", "1990-01-01", 2, 3)])
    assert propose_birthday([1], d) == "1990-02-14"


def test_propose_birthday_ambiguous_timing_returns_none():
    # Мордвинова: хронометраж противоречит сам себе
    d = data([C(1, "Мордвинова", "Елена", "1986-03-30"), C(2, "Мордвинова", "Елена", "1986-03-03")],
             results=[R(1, 1, "Мордвинова", "Елена", "1986-03-30", 4, 1), R(2, 2, "Мордвинова", "Елена", "1986-03-03", 2, 2)])
    assert propose_birthday([1, 2], d) is None


# ---------------------------------------------------------------- предохранители

def test_blocker_both_finished_same_event():
    # Иванова Елена 1987 и 1990 — обе финишировали в одной Жаре
    d = data([C(1, "Иванова", "Елена", "1987-03-04"), C(2, "Иванова", "Елена", "1987-03-14")],
             results=[R(1, 1, "Иванова", "Елена", "1987-03-04", 2, 1), R(2, 2, "Иванова", "Елена", "1987-03-14", 2, 2)])
    assert any("одном забеге" in b for b in merge_blockers([1, 2], d))


def test_blocker_father_and_son():
    d = data([C(1, "Титов", "Иван", "1986-09-19"), C(2, "Титов", "Иван", "2011-02-17")])
    assert any("несовместимые ДР" in b for b in merge_blockers([1, 2], d))


def test_blocker_twins_by_name_and_sex():
    d = data([C(1, "Генергардт", "Виктор", "1994-12-27"), C(2, "Генергардт", "Виктория", "1994-12-27")],
             results=[R(1, 1, "Генергардт", "Виктор", "1994-12-27", 3, 1, sex="Мужчина"),
                      R(2, 2, "Генергардт", "Виктория", "1994-12-27", 4, 2, sex="Женщина")])
    blockers = merge_blockers([1, 2], d)
    assert "разный пол в протоколах" in blockers
    assert any("разные имена" in b for b in blockers)


def test_blocker_placeholder_fits_several_people():
    d = data([C(1, "Иванов", "Владимир", "1900-01-01"), C(2, "Иванов", "Владимир", "1979-06-26"),
              C(3, "Иванов", "Владимир", "1995-03-24")])
    assert any("подходит нескольким" in b for b in merge_blockers([1, 2], d))


def test_no_blockers_for_same_person():
    d = data([C(1, "Хазов", "Сергей", "1983-04-08"), C(2, "Хазов", "Серега", "1983-04-08"), C(3, "Хазов", "Сергей", "1983-01-01")])
    assert merge_blockers([1, 2, 3], d) == []


# ---------------------------------------------------------------- проверки

def test_lead_on_other_card_same_bib_is_high():
    # Подборский: результат пришёл с другой ДР и создал карточку, заявка с тем же номером — на настоящей
    d = data([C(1, "Подборский", "Матвей", "2001-05-02"), C(2, "Подборский", "Матвей", "2000-08-11")],
             leads=[L(1, 1, "Подборский", "Матвей", "2001-05-02", 1, 626)],
             results=[R(1, 2, "Подборский", "Матвей", "2000-08-11", 1, 626)])
    [f] = check_lead_on_other_card(d, d.results)
    assert (f.code, f.severity, f.client_ids) == ("R-LEAD", "high", (2, 1))


def test_lead_on_other_card_same_fio_without_bib_is_medium():
    d = data([C(1, "Сидоренко", "Екатерина", "1983-08-26"), C(2, "Сидоренко", "Екатерина", "1986-01-01")],
             leads=[L(1, 1, "Сидоренко", "Екатерина", "1983-08-26", 3)],
             results=[R(1, 2, "Сидоренко", "Екатерина", "1986-01-01", 3, 77)])
    [f] = check_lead_on_other_card(d, d.results)
    assert f.severity == "medium"


def test_lead_with_same_bib_but_other_person_is_ignored():
    d = data([C(1, "Петров", "Иван", "1980-01-05"), C(2, "Сидоров", "Олег", "1990-02-02")],
             leads=[L(1, 1, "Петров", "Иван", "1980-01-05", 2, 15)],
             results=[R(1, 2, "Сидоров", "Олег", "1990-02-02", 2, 15)])
    assert check_lead_on_other_card(d, d.results) == []


def test_lead_owner_with_own_result_is_namesake():
    # Волков 1988 и 1983 — оба бежали Весну 2025, заявка есть только у одного
    d = data([C(1, "Волков", "Александр", "1983-09-13"), C(2, "Волков", "Александр", "1988-02-19")],
             leads=[L(1, 1, "Волков", "Александр", "1983-09-13", 3)],
             results=[R(1, 1, "Волков", "Александр", "1983-09-13", 3, 199), R(2, 2, "Волков", "Александр", "1988-02-19", 3, 137)])
    assert check_lead_on_other_card(d, d.results) == []


def test_category_mismatch_kopachev():
    # отец записал себя на Жару с ДР сына: категория М50-59, ДР 2009
    d = data([C(1, "Копачев", "Игорь", "2009-06-02")], results=[R(1, 1, "Копачев", "Игорь", "2009-06-02", 2, 3926, "М50-59")])
    assert [f.code for f in check_category(d, d.results)] == ["R-CAT"]


@pytest.mark.parametrize("bd, cat, sex", [
    ("2016-09-03", "Ж12-13", "Женщина"),                                    # ребёнок в младшей доступной категории
    ("1940-01-03", "мужчины 75 лет и старше (1952-1956 г.р.)", "Мужчина"),  # годы в названии категории ошибочны
])
def test_category_ok(bd, cat, sex):
    d = data([C(1, "Х", "Y", bd)], results=[R(1, 1, "Х", "Y", bd, 2, 1, cat, sex=sex)])
    assert check_category(d, d.results) == []


def test_duplicates_not_started_is_auto_two_finishes_are_review():
    d = data([C(1, "Челчушев", "Евгений", "1971-02-26"), C(2, "Зверюгин", "Вячеслав", "2010-04-15")],
             results=[R(1, 1, "Челчушев", "Евгений", "1971-02-26", 2, 1443), R(2, 1, "Челчушев", "Евгений", "1971-02-26", 2, 1334, status="Not started"),
                      R(3, 2, "Зверюгин", "Вячеслав", "2010-04-15", 2, 811), R(4, 2, "Зверюгин", "Вячеслав", "2010-04-15", 2, 1070)])
    found = {(f.result_id, f.severity, f.auto) for f in check_duplicates(d, d.results)}
    assert found == {(2, "high", True), (3, "low", False)}


def test_twins_similar_names_same_birthday():
    d = data([C(1, "Заводовская", "Ира", "1983-12-17"), C(2, "Заводовская", "Ирина", "1983-12-17"),
              C(3, "Белоблоцкая", "Даниил", "2001-08-08"), C(4, "Белоблоцкий", "Даниил", "2001-08-08")],
             results=[R(1, 1, "Заводовская", "Ира", "1983-12-17", 2, 1), R(2, 3, "Белоблоцкая", "Даниил", "2001-08-08", 2, 2)])
    found = {f.client_ids: f.severity for f in check_twins(d, [1, 3])}
    assert found == {(1, 2): "high", (3, 4): "high"}


def test_twins_placeholder_with_several_candidates_is_low():
    d = data([C(1, "Иванов", "Владимир", "1900-01-01"), C(2, "Иванов", "Владимир", "1979-06-26"),
              C(3, "Иванов", "Владимир", "1995-03-24")],
             results=[R(1, 2, "Иванов", "Владимир", "1979-06-26", 2, 1)])
    [f] = check_twins(d, [2])
    assert (f.client_ids, f.severity) == ((1, 2), "low")


def test_hygiene_case():
    d = data([C(1, "Галинин", "Вадим", "1983-06-30")], results=[R(1, 1, "галинин", "вадим", "1983-06-30", 4, 630)])
    [f] = check_hygiene(d, d.results)
    assert "Галинин Вадим" in f.message


def test_event_scope_checks_twins_of_lead_cards():
    # импорт заявок: «Катя» пришла новой карточкой рядом с «Екатериной» — результатов ещё нет
    d = data([C(1, "Сташкевич", "Екатерина", "2013-08-13"), C(2, "Сташкевич", "Катя", "2013-08-13")],
             leads=[L(1, 2, "Сташкевич", "Катя", "2013-08-13", 2)])
    assert [f.client_ids for f in run_checks(d, {2})] == [(1, 2)]
    assert run_checks(d) == []          # полный прогон — только карточки с результатами


def test_twins_swapped_fields_same_birthday():
    # форма Tilda: «Андрей» в поле фамилии — триггер создаёт отдельную карточку
    d = data([C(1, "Сафонов", "Андрей", "1968-06-07"), C(2, "Андрей", "Сафонов", "1968-06-07")],
             results=[R(1, 1, "Сафонов", "Андрей", "1968-06-07", 2, 7)])
    [f] = check_twins(d, [1])
    assert f.client_ids == (1, 2) and "переставлены" in f.message


def test_kids_leads_parent_birthday_and_distance_by_age():
    from src.analytics.data_quality import check_kids_leads
    d = data([C(1, "Иванов", "Петя", "2019-05-01"), C(2, "Сидоров", "Ваня", "1986-03-03"), C(3, "Котов", "Миша", "2023-01-01")],
             leads=[L(1, 1, "Иванов", "Петя", "2019-05-01", 9), L(2, 2, "Сидоров", "Ваня", "1986-03-03", 9),
                    L(3, 3, "Котов", "Миша", "2023-01-01", 9)])
    d.events[9] = {"id": 9, "event_name": "Детский забег", "event_distance": 1.0, "event_year": 2027}
    for l in d.leads:
        l["event_distance"] = "1 км"
    found = {f.lead_id: (f.code, f.severity) for f in check_kids_leads(d)}
    assert found == {2: ("L-KID", "medium"), 3: ("L-KID", "low")}   # 1986 г.р.; 4 года на 1 км (нужно 500 м)


def test_kids_check_skips_past_years_in_full_run():
    from src.analytics.data_quality import check_kids_leads
    d = data([C(2, "Сидоров", "Ваня", "1986-03-03")], leads=[L(2, 2, "Сидоров", "Ваня", "1986-03-03", 9)])
    d.events[9] = {"id": 9, "event_name": "Детский забег", "event_distance": 1.0, "event_year": 2024}
    assert check_kids_leads(d, from_year=2026) == [] and len(check_kids_leads(d, {9})) == 1
