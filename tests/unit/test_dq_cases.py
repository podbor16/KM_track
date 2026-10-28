"""Дела и вопросы «Качества данных» (src/analytics/dq_cases.py) — без БД."""
import datetime

from src.analytics.dq_checks import Data, run_checks
from src.common.names import Names

EVENTS = [
    {"id": 10, "event_name": "Детский забег", "event_distance": 1.0, "event_year": 2016, "event_date": datetime.date(2016, 8, 28)},
    {"id": 11, "event_name": "Жара", "event_distance": 21.1, "event_year": 2016, "event_date": datetime.date(2016, 8, 27)},
    {"id": 12, "event_name": "Детский забег", "event_distance": 1.0, "event_year": 2015, "event_date": None},
]


def C(i, s, n, bd):
    return {"id": i, "surname": s, "name": n, "birthday": bd}


def R(i, cid, s, n, bd, eid, bib, cat="", status="Finished", sex="Мужчина"):
    return {"id": i, "client_id": cid, "surname": s, "name": n, "birthday": bd, "sex": sex, "event_id": eid,
            "start_number": bib, "category": cat, "race_status": status}


def L(i, cid, s, n, bd, eid, dist="1 км", bib=None):
    return {"id": i, "client_id": cid, "surname": s, "name": n, "birthday": bd, "sex": "Мужчина", "event_id": eid,
            "event_distance": dist, "start_number": bib}


def data(clients, leads=(), results=()):
    d = Data(list(clients), list(leads), list(results), EVENTS)
    d.names = Names([("Пцарев", "Александр", "Мужчина"), ("Пцарев", "Марк", "Мужчина")] * 5)
    return d


# Пцаревы (реальный случай 2026-10-28): детский результат 2016 на карточке отца, сын — «Саша» + заглушка
def pcarev():
    clients = [C(1, "Пцарев", "Александр", "1980-03-09"), C(2, "Пцарев", "Саша", "2013-12-20"),
               C(3, "Пцарев", "Александр", "2013-01-01"), C(4, "Пцарев", "Марк", "2006-06-20")]
    results = [R(100, 1, "Пцарев", "Александр", "1980-03-09", 11, 3470, "М35-39"),
               R(101, 1, "Пцарев", "Александр", "1980-03-09", 10, 1012, "Мальчики 2005 г.р. и младше"),
               R(102, 4, "Пцарев", "Марк", "2006-06-20", 10, 1013, "Мальчики 2005 г.р. и младше"),
               R(103, 3, "Пцарев", "Александр", "2013-01-01", 12, 104, "Мальчики")]
    return data(clients, results=results)


def test_run_checks_card_scope_keeps_only_findings_of_these_cards():
    d = pcarev()
    every = run_checks(d)
    scoped = run_checks(d, card_ids={1, 2})
    assert scoped and all(set(f.client_ids) & {1, 2} for f in scoped)
    assert {f.key for f in scoped} <= {f.key for f in every}
    assert any(f.code == "R-FOREIGN" and f.result_id == 101 for f in scoped)


from src.analytics.dq_cases import STAGES, group_cases
from src.analytics.dq_checks import Finding


def test_namesakes_with_findings_join_one_case_brother_does_not():
    d = pcarev()
    findings = run_checks(d)
    cases = group_cases(findings, d)
    p = next(c for c in cases if 1 in c["cards"])
    assert p["key"] == "c1" and set(p["cards"]) >= {1, 2, 3} and 4 not in p["cards"]
    assert p["title"] == "Пцарев Александр"              # карточка с наибольшим числом строк — отца
    assert {f.key for f in p["findings"]} == {f.key for f in findings if set(f.client_ids) & set(p["cards"])}


def test_finding_without_cards_is_own_case():
    d = pcarev()
    f = Finding("R-CARD", "high", "результат #999 без карточки", (), 999, 10)
    [case] = group_cases([f], d)
    assert case["key"] == "r999" and case["cards"] == [] and case["title"] == "Результат #999 без карточки"


def test_stages_order():
    assert [STAGES[c] for c in ("C-TWIN", "R-LEAD", "R-FOREIGN")] == [1, 1, 1]
    assert STAGES["R-DUP"] == 2
    assert {STAGES[c] for c in ("R-CARD", "R-CAT", "HYG", "L-KID")} == {3}


from src.analytics.dq_cases import build_question


def _q(d, code, **kw):
    f = next(f for f in run_checks(d) if f.code == code and all(getattr(f, k) == v for k, v in kw.items()))
    return build_question(f, d)


def ids(q):
    return [a["id"] for a in q["answers"]]


def test_foreign_question_suggests_namesake_first():
    q = _q(pcarev(), "R-FOREIGN", result_id=101)
    assert q["stage"] == 1 and "Чей это результат" in q["text"] and "36 лет" in q["text"]
    assert ids(q)[0] in ("to:2", "to:3") and q["answers"][0]["recommended"]
    assert ids(q)[-3:] == ["new", "keep", "postpone"]
    assert [i["name"] for i in q["answers"][-3]["inputs"]] == ["surname", "name", "birthday"]


def test_twin_question_prefills_proposal():
    d = data([C(1, "Иванов", "Иван", "1985-07-14"), C(2, "Иванов", "Иван", "1900-01-01")],
             results=[R(1, 1, "Иванов", "Иван", "1985-07-14", 11, 5), R(2, 2, "Иванов", "Иван", "1900-01-01", 10, 6)])
    q = _q(d, "C-TWIN")
    assert "один человек" in q["text"] and ids(q) == ["merge", "different", "postpone"]
    merge = q["answers"][0]
    assert merge["recommended"] and {i["name"]: i["value"] for i in merge["inputs"]}["birthday"] == "1985-07-14"


def test_card_question_recommends_card_bd_for_placeholder_row():
    d = data([C(1, "Ветрова", "Елизавета", "2014-12-12")],
             results=[R(1, 1, "Ветрова", "Елизавета", "2014-01-01", 10, 4102, sex="Женщина")])
    q = _q(d, "R-CARD")
    assert "2014-01-01" in q["text"] and "2014-12-12" in q["text"]
    assert ids(q) == ["row_from_card", "card_from_row", "other", "postpone"] and q["answers"][0]["recommended"]


def test_every_finding_type_has_question_with_postpone():
    d = pcarev()
    for f in run_checks(d):
        q = build_question(f, d)
        assert q["id"] == f.key and q["text"] and ids(q)[-1] == "postpone" and q["stage"] in (1, 2, 3)
        assert sum(a["recommended"] for a in q["answers"]) <= 1


def test_dup_question_tells_not_started_from_foreign_bib():
    d = data([C(1, "Иванов", "Иван", "1985-07-14")], leads=[L(1, 1, "Иванов", "Иван", "1985-07-14", 11, bib=7)],
             results=[R(1, 1, "Иванов", "Иван", "1985-07-14", 11, 5, status="Not started"),
                      R(2, 1, "Иванов", "Иван", "1985-07-14", 11, 9, status="Not started")])
    q = _q(d, "R-DUP", result_id=1)
    assert "в заявке номер 7" in q["text"] and "не стартовал" not in q["text"]
    assert ids(q) == ["delete", "keep", "postpone"] and q["answers"][0]["recommended"]


def test_kid_lead_question_keeps_abbreviation_and_offers_kid_namesake():
    year = datetime.date.today().year
    d = Data([C(1, "Пцарев", "Александр", "1980-03-09"), C(2, "Пцарев", "Саша", f"{year - 8}-12-20")],
             [L(1, 1, "Пцарев", "Александр", "1980-03-09", 20)], [],
             [{"id": 20, "event_name": "Детский забег", "event_distance": 1.0, "event_year": year, "event_date": None}])
    q = _q(d, "L-KID")
    assert "ДР родителя" in q["text"] and "to:2" in ids(q) and ids(q)[-1] == "postpone"
