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
