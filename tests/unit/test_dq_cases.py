"""Дела и вопросы «Качества данных» (src/analytics/dq_cases.py) — без БД."""
import datetime
import itertools
import re

import pytest

from src.analytics import dq_actions, dq_cases
from src.analytics.dq_cases import STAGES, build_question, case_view, group_cases, is_live, questions_for
from src.analytics.dq_checks import Data, Finding, _needs, run_checks, with_namesakes
from src.common.names import Names, norm

EVENTS = [
    {"id": 10, "event_name": "Детский забег", "event_distance": 1.0, "event_year": 2016, "event_date": datetime.date(2016, 8, 28)},
    {"id": 11, "event_name": "Жара", "event_distance": 21.1, "event_year": 2016, "event_date": datetime.date(2016, 8, 27)},
    {"id": 12, "event_name": "Детский забег", "event_distance": 1.0, "event_year": 2015, "event_date": None},
]


def C(i, s, n, bd):
    return {"id": i, "surname": s, "name": n, "birthday": bd}


def R(i, cid, s, n, bd, eid, bib, cat="", status="Finished", sex="Мужчина", time=None):
    return {"id": i, "client_id": cid, "surname": s, "name": n, "birthday": bd, "sex": sex, "event_id": eid,
            "start_number": bib, "category": cat, "race_status": status, "time_clear_finish": time}


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


YEAR = datetime.date.today().year


def everything():
    """Все 8 кодов, C-TWIN с предохранителем, номер None, событие без года."""
    events = EVENTS + [
        {"id": 20, "event_name": "Детский забег", "event_distance": 1.0, "event_year": YEAR, "event_date": None},
        {"id": 31, "event_name": "Детский забег", "event_distance": 1.0, "event_year": None, "event_date": None}]
    clients = [C(1, "Пцарев", "Александр", "1980-03-09"), C(2, "Пцарев", "Саша", "2013-12-20"),
               C(3, "Пцарев", "Александр", "2013-01-01"),
               C(5, "Иванов", "Иван", "1985-07-14"), C(6, "Иванов", "Иван", "1900-01-01"),
               C(7, "Сидоров", "Петр", "1990-05-05"), C(8, "Сидоров", "Пётр", "1990-05-05"),
               C(9, "Козлов", "Олег", "1985-07-14"), C(10, "Козлов", "Олег", "1990-01-01"),
               C(11, "Ветрова", "Елизавета", "2014-12-12"), C(12, "ПЕТРОВ", "петр", "1970-02-02"),
               C(13, "Орлов", "Олег", "1990-02-02")]
    leads = [L(1, 8, "Сидоров", "Пётр", "1990-05-05", 11, bib=1012), L(2, 1, "Пцарев", "Александр", "1980-03-09", 20)]
    results = [R(100, 1, "Пцарев", "Александр", "1980-03-09", 11, 3470, "М35-39"),
               R(101, 1, "Пцарев", "Александр", "1980-03-09", 10, 1012, "Мальчики 2005 г.р. и младше"),
               R(103, 3, "Пцарев", "Александр", "2013-01-01", 12, 104, "Мальчики"),
               R(1, 5, "Иванов", "Иван", "1985-07-14", 11, 5), R(2, 6, "Иванов", "Иван", "1900-01-01", 11, None),
               R(3, 7, "Сидоров", "Петр", "1990-05-05", 11, 1012),
               R(4, 9, "Козлов", "Олег", "1985-07-14", 11, 5, time=datetime.timedelta(minutes=42, seconds=10)),
               R(5, 9, "Козлов", "Олег", "1985-07-14", 11, 8),
               R(6, 11, "Ветрова", "Елизавета", "2014-01-01", 10, 4102, sex="Женщина"),
               R(7, 12, "ПЕТРОВ", "петр", "1970-02-02", 11, 9),
               R(8, 13, "Орлов", "Олег", "1990-02-02", 31, None)]
    d = Data(clients, leads, results, events)
    d.names = Names([("Пцарев", "Александр", "Мужчина"), ("Петров", "Петр", "Мужчина")] * 5)
    return d


def test_every_finding_type_has_question_with_postpone():
    d = everything()
    found = run_checks(d) + run_checks(d, event_ids={31})
    assert {f.code for f in found} == set(STAGES)
    twin = next(f for f in found if f.code == "C-TWIN" and set(f.client_ids) == {5, 6})
    assert sum(a["recommended"] for a in build_question(twin, d)["answers"]) == 0
    for f in found:
        q = build_question(f, d)
        assert q["id"] == f.key and q["text"] and ids(q)[-1] == "postpone" and q["stage"] in (1, 2, 3)
        assert sum(a["recommended"] for a in q["answers"]) <= 1
        shown = " ".join([q["text"], q["hint"]] + [a["label"] for a in q["answers"]])
        assert not re.search(r"#\d", shown) and "None" not in shown, shown


def test_same_key_findings_make_one_question():
    d = data([C(1, "Белова", "Ева", "2010-05-05")],
             results=[R(1, 1, "Белова", "Ева", "2010-05-05", 11, 3, "М35-39", sex="Женщина")])
    found = [f for f in run_checks(d) if f.code == "R-CAT"]
    assert len(found) == 2 and found[0].key == found[1].key
    [q] = questions_for(found, d)
    assert q["id"] == found[0].key and q["hint"] == "Категория не для этого пола; ДР не подходит к категории"


def test_event_without_year_shows_no_age():
    d = everything()
    q = _q(d, "R-FOREIGN", result_id=8)
    assert "возраст" not in q["text"].lower() and "-" not in q["text"].split("Орлов")[1].replace("1990-02-02", "")
    d = Data(list(d.clients.values()), d.leads + [L(3, 13, "Орлов", "Олег", "1990-02-02", 31)], d.results,
             list(d.events.values()))
    f = next(f for f in run_checks(d, event_ids={31}) if f.code == "L-KID")
    assert "-" not in build_question(f, d)["text"].split("Орлов Олег")[1].replace("1990-02-02", "")


def test_twin_blockers_in_plain_words():
    q = _q(everything(), "C-TWIN", client_ids=(5, 6))
    assert q["hint"].startswith("Осторожно: ") and "#" not in q["hint"] and "в одном забеге" in q["hint"]


def test_two_finishes_offer_namesake_and_row_choice():
    q = _q(everything(), "R-DUP", result_id=4)
    assert ids(q) == ["to:10", "new", "keep", "postpone"] and q["answers"][2]["recommended"]
    for a in q["answers"][:2]:
        row = next(i for i in a["inputs"] if i["name"] == "row_id")
        assert row["type"] == "select" and row["value"] == "4"
        assert row["options"] == [{"value": "4", "label": "№5 (0:42:10)"}, {"value": "5", "label": "№8"}]


def test_card_question_recommends_protocol_when_card_has_placeholder():
    d = data([C(1, "Ветрова", "Елизавета", "1900-01-01")],
             results=[R(1, 1, "Ветрова", "Елизавета", "2014-12-12", 10, 4102, sex="Женщина")])
    q = _q(d, "R-CARD")
    assert [a["id"] for a in q["answers"] if a["recommended"]] == ["card_from_row"]
    d = data([C(1, "Ветрова", "Елизавета", "2014-12-12")],
             results=[R(1, 1, "Ветрова", "Елизавета", "2015-01-01", 10, 4102, sex="Женщина")])
    assert not any(a["recommended"] for a in _q(d, "R-CARD")["answers"])


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


def test_two_finishes_skip_namesake_who_finished_this_race():
    d = everything()
    d = Data(list(d.clients.values()), d.leads, d.results + [R(9, 10, "Козлов", "Олег", "1990-01-01", 11, 12)],
             list(d.events.values()))
    assert ids(_q(d, "R-DUP", result_id=4)) == ["new", "keep", "postpone"]



def pcarev_case(d):
    return next(c for c in group_cases(run_checks(d), d) if 1 in c["cards"])


def test_case_view_rows_by_year_and_locked_stages():
    d = pcarev()
    v = case_view(pcarev_case(d), d, decided={}, today=datetime.date(2026, 10, 28))
    father = next(c for c in v["cards"] if c["id"] == 1)
    assert [r["year"] for r in father["rows"]] == sorted((r["year"] for r in father["rows"]), reverse=True)
    assert any(r["problem"] for r in father["rows"] if r["id"] == 101)
    stages = [q["stage"] for q in v["questions"]]
    assert stages == sorted(stages)
    first = min(stages)
    assert all(q["state"] == ("current" if q["stage"] == first else "locked") for q in v["questions"])


def test_is_live_today_or_yesterday():
    ev = {"event_date": datetime.date(2026, 10, 27)}
    assert is_live(ev, datetime.date(2026, 10, 27)) and is_live(ev, datetime.date(2026, 10, 28))
    assert not is_live(ev, datetime.date(2026, 10, 29)) and not is_live({"event_date": None}, datetime.date(2026, 10, 28))


def test_live_race_keeps_only_moves_and_postpone():
    d = pcarev()
    v = case_view(pcarev_case(d), d, decided={}, today=datetime.date(2016, 8, 29))   # Детский 2016-08-28 — вчера
    live = [q for q in v["questions"] if q["live"]]
    assert live
    assert all(a == "new" or a == "postpone" or a.startswith("to:") for q in live for a in ids(q))
    foreign = next(q for q in live if q["code"] == "R-FOREIGN" and q["result_id"] == 101)
    assert ids(foreign)[0].startswith("to:")
    later = case_view(pcarev_case(d), d, decided={}, today=datetime.date(2016, 8, 30))
    assert not any(q["live"] for q in later["questions"])


# ---------------------------------------------------------------- проверки по карточкам дела

def leads_only():
    """Тёзки только с заявками (одна — с ДР-заглушкой) и пара «карточка с результатом — карточка без»."""
    clients = [C(1, "Пцарев", "Александр", "1900-01-01"), C(2, "Пцарев", "Александр", "1985-04-04"),
               C(3, "Ветров", "Олег", "1990-05-05"), C(4, "Ветров", "Олег", "1990-01-01")]
    leads = [L(1, 1, "Пцарев", "Александр", "1900-01-01", 11), L(2, 2, "Пцарев", "Александр", "1985-04-04", 11),
             L(3, 4, "Ветров", "Олег", "1990-01-01", 11, bib=77)]
    results = [R(1, 3, "Ветров", "Олег", "1990-05-05", 11, 77)]
    return data(clients, leads=leads, results=results)


@pytest.mark.parametrize("make", [pcarev, everything, leads_only])
def test_card_scope_equals_full_run_restricted_to_cards(make):
    d = make()
    full = run_checks(d)
    ids_ = sorted(d.clients)
    for S in [{i} for i in ids_] + [set(p) for p in itertools.combinations(ids_, 2)]:
        want = {f.key for f in full if set(f.client_ids) & S}
        assert {f.key for f in run_checks(d, card_ids=S)} == want, S


# ---------------------------------------------------------------- ответы (БД заменена данными в памяти)

def scoped_subset(full, card_ids, event_ids=()):
    """Что выбрала бы load_scoped из базы full (те же правила, в памяти) — Data с настоящим scope для covers()."""
    ids, event_ids = set(card_ids), set(event_ids)
    surnames = {norm(full.clients[i]["surname"]) for i in ids if i in full.clients}
    base = with_namesakes(Data([c for c in full.clients.values() if norm(c["surname"]) in surnames], [], [], [],
                               full.names), ids)
    keys, bds, bibs = _needs(full, base)
    cards = base | {i for i, c in full.clients.items() if norm(c["surname"]) in keys or c["birthday"] in bds}
    cards |= {r["client_id"] for r in full.leads + full.results if r["client_id"] in cards
              or norm(r["surname"]) in keys or (r["event_id"], r["start_number"]) in bibs}
    same = {(e["event_name"], e["event_year"]) for i, e in full.events.items() if i in event_ids}
    lead_events = {i for i, e in full.events.items() if (e["event_name"], e["event_year"]) in same}
    return Data([c for i, c in full.clients.items() if i in cards],
                [l for l in full.leads if l["client_id"] in cards or l["event_id"] in lead_events],
                [r for r in full.results if r["client_id"] in cards or r["event_id"] in event_ids],
                list(full.events.values()), full.names,
                scope={"cards": base, "keys": keys, "bds": bds, "bibs": bibs, "events": event_ids})


class Fake:
    """dq_cases.load/load_scoped и dq_actions.load_decisions — из памяти; действия dq_actions — записывающие заглушки.
    loads — вызовы load_scoped, full_loads — полной load; scoped — load_scoped отдаёт подмножество (scoped_subset),
    иначе всю базу (covers() — всегда да)."""
    ACTIONS = {"merge_cards": (0, 1), "move_row": (0, 1), "edit_record": (0, 1), "dismiss": 1, "delete_result": 1,
               "fix_fio": (0, 1)}

    def __init__(self, monkeypatch, d, scoped=False):
        self.scoped = scoped
        self.d, self.decided, self.calls, self.loads, self.full_loads, self.fail = d, {}, [], 0, 0, None
        monkeypatch.setattr(dq_cases, "load", self._load)
        monkeypatch.setattr(dq_cases, "load_scoped", self._load_scoped)
        dq_cases.invalidate()
        monkeypatch.setattr(dq_actions, "load_decisions", lambda conn: dict(self.decided))
        monkeypatch.setattr(dq_cases, "_today", lambda: datetime.date(2026, 10, 28))
        for name, ret in self.ACTIONS.items():
            monkeypatch.setattr(dq_actions, name, self._stub(name, ret))

    def _load(self, conn):
        self.full_loads += 1
        return self.d

    def _load_scoped(self, conn, card_ids, event_ids=()):
        self.loads += 1
        return scoped_subset(self.d, card_ids, event_ids) if self.scoped else self.d

    def _stub(self, name, ret):
        def act(conn, *args, **kw):
            if self.fail and self.fail(name, args):
                raise ValueError("такие ФИ и ДР уже у карточки #14 — склейте карточки")
            self.calls.append((name, args, kw))
            return ret
        return act

    def answer(self, key, answer_id, inputs=None, only=True):
        """Ответ на вопрос key; only — прочие вопросы дела отложены (вопрос не закрыт ступенью)."""
        case = next(c for c in group_cases(run_checks(self.d), self.d) if any(f.key == key for f in c["findings"]))
        self.decided = {f.key: "postponed" for f in case["findings"] if f.key != key} if only else {}
        self.calls, self.loads, self.full_loads = [], 0, 0
        return dq_cases.apply_answer(None, case["key"], key, answer_id, inputs or {}, "u")


def dup_auto():
    return data([C(1, "Иванов", "Иван", "1985-07-14")], leads=[L(1, 1, "Иванов", "Иван", "1985-07-14", 11, bib=7)],
                results=[R(1, 1, "Иванов", "Иван", "1985-07-14", 11, 5, status="Not started"),
                         R(2, 1, "Иванов", "Иван", "1985-07-14", 11, 9, status="Not started")])


def kid_lead():
    year = datetime.date.today().year
    return Data([C(1, "Пцарев", "Александр", "1980-03-09"), C(2, "Пцарев", "Саша", f"{year - 8}-12-20")],
                [L(1, 1, "Пцарев", "Александр", "1980-03-09", 20)], [],
                [{"id": 20, "event_name": "Детский забег", "event_distance": 1.0, "event_year": year, "event_date": None}])


def vetrova_twin():
    """R-CARD Ветровой и карточка #14 с ФИ+ДР строки — склейка после конфликта."""
    return data([C(11, "Ветрова", "Елизавета", "2014-12-12"), C(14, "Ветрова", "Елизавета", "2014-01-01")],
                results=[R(6, 11, "Ветрова", "Елизавета", "2014-01-01", 10, 4102, sex="Женщина")])


FIO = {"surname": "Ветрова", "name": "Елизавета"}
U = "u"
ANSWERS = [
    (everything, "C-TWIN::5-6", "merge", {"surname": "Иванов", "name": "Иван", "birthday": "1985-07-14"},
     [("merge_cards", ([5, 6], "Иванов", "Иван", "1985-07-14", U), {})]),
    (everything, "C-TWIN::5-6", "different", {}, [("dismiss", ("different_people", "", U), {})]),
    (everything, "R-LEAD:r3:7-8", "to:8", {}, [("move_row", ("results", 3, U), {"align": True, "to_client_id": 8})]),
    (everything, "R-FOREIGN:r101:1-2-3", "to:2", {},
     [("move_row", ("results", 101, U), {"align": True, "to_client_id": 2})]),
    (everything, "R-FOREIGN:l2:1-2-3", "to:3", {}, [("move_row", ("leads", 2, U), {"align": True, "to_client_id": 3})]),
    (kid_lead, "L-KID:l1:1", "to:2", {}, [("move_row", ("leads", 1, U), {"align": True, "to_client_id": 2})]),
    (everything, "R-FOREIGN:r8:13", "new", {"surname": "Орлов", "name": "Олег", "birthday": "2010-02-02"},
     [("move_row", ("results", 8, U), {"align": True, "new_card": {"surname": "Орлов", "name": "Олег",
                                                                   "birthday": "2010-02-02"}})]),
    (everything, "R-DUP:r4:9", "to:10", {"row_id": "5"},
     [("move_row", ("results", 5, U), {"align": True, "to_client_id": 10})]),
    (everything, "R-DUP:r4:9", "new", {"row_id": 5, "surname": "Козлов", "name": "Олег", "birthday": "1990-03-03"},
     [("move_row", ("results", 5, U), {"align": True, "new_card": {"surname": "Козлов", "name": "Олег",
                                                                   "birthday": "1990-03-03"}})]),
    (everything, "HYG:r7:12", "keep", {}, [("dismiss", ("keep", "", U), {})]),
    (dup_auto, "R-DUP:r1:1", "delete", {}, [("delete_result", (1, U), {})]),
    (everything, "R-CARD:r6:11", "row_from_card", {}, [("edit_record", ("results", 6, {"birthday": "2014-12-12"}, U), {})]),
    (everything, "R-CARD:r6:11", "card_from_row", {}, [("edit_record", ("clients", 11, {"birthday": "2014-01-01"}, U), {})]),
    (everything, "R-CARD:r6:11", "other", {**FIO, "birthday": "2014-06-06"},
     [("edit_record", ("clients", 11, {"birthday": "2014-06-06"}, U), {}),
      ("edit_record", ("results", 6, {"birthday": "2014-06-06"}, U), {})]),
    (everything, "R-CARD:r6:11", "other", {**FIO, "birthday": "2014-12-12"},       # как в карточке — правится строка
     [("edit_record", ("results", 6, {"birthday": "2014-12-12"}, U), {})]),
    (vetrova_twin, "R-CARD:r6:11", "merge_with:14", {**FIO, "birthday": "2014-01-01"},
     [("merge_cards", ([11, 14], "Ветрова", "Елизавета", "2014-01-01", U), {})]),
    (everything, "R-CAT:r101:1", "birthday", {"birthday": "2010-01-01", "category": "лишнее"},
     [("edit_record", ("results", 101, {"birthday": "2010-01-01"}, U), {})]),
    (everything, "R-CAT:r101:1", "category", {"category": "М35-39", "sex": "лишнее"},
     [("edit_record", ("results", 101, {"category": "М35-39"}, U), {})]),
    (everything, "R-CAT:r101:1", "sex", {"sex": "Женщина", "category": "Ж35-39", "birthday": "лишнее"},
     [("edit_record", ("results", 101, {"sex": "Женщина", "category": "Ж35-39"}, U), {})]),
    (everything, "L-KID:l2:1", "distance", {"event_distance": "500 м"},
     [("edit_record", ("leads", 2, {"event_distance": "500 м"}, U), {})]),
    (everything, "HYG:r7:12", "manual", {"surname": "Петров", "name": "Пётр"},
     [("fix_fio", (7, "Петров", "Пётр", U), {})]),
    (everything, "HYG:r7:12", "postpone", {}, [("dismiss", ("postponed", "не знаю ДР", U), {})]),
]


def _with_key(calls, key):
    """Ожидаемые вызовы: ключ находки — последним аргументом (у dismiss — первым)."""
    return [(name, (key, *args) if name == "dismiss" else (*args, key), kw) for name, args, kw in calls]


@pytest.mark.parametrize("make,key,answer_id,inputs,calls", ANSWERS,
                         ids=[f"{a[1].split(':')[0]}-{a[2]}" for a in ANSWERS])
def test_answer_runs_its_chain(monkeypatch, make, key, answer_id, inputs, calls):
    fake = Fake(monkeypatch, make())
    fake.answer(key, answer_id, inputs)
    assert fake.calls == _with_key(calls, key)
    assert (fake.loads, fake.full_loads) == (2, 0)


def test_fix_takes_canonical_fio(monkeypatch):
    fake = Fake(monkeypatch, everything())
    f = next(f for f in run_checks(fake.d) if f.key == "HYG:r7:12")
    fake.answer(f.key, "fix")
    assert fake.calls == [("fix_fio", (7, *f.fix, U, f.key), {})]


def test_other_without_changes_writes_nothing(monkeypatch):
    fake = Fake(monkeypatch, everything())
    with pytest.raises(ValueError, match="значения не изменились"):
        fake.answer("R-CARD:r6:11", "other", {})
    assert fake.calls == []


def test_card_conflict_writes_nothing_and_offers_merge(monkeypatch):
    fake = Fake(monkeypatch, everything())
    fake.fail = lambda name, args: name == "edit_record" and args[0] == "clients"
    out = fake.answer("R-CARD:r6:11", "other", {**FIO, "birthday": "2014-06-06"})
    assert fake.calls == [] and out["action_ids"] == []
    assert out["conflict"]["merge_with"] == 14 and "Склеить" in out["conflict"]["message"]
    assert out["conflict"]["birthday"] == "2014-06-06"


def test_merge_with_needs_card_with_same_fio_and_bd(monkeypatch):
    fake = Fake(monkeypatch, vetrova_twin())
    with pytest.raises(ValueError, match="те же ФИ и ДР"):
        fake.answer("R-CARD:r6:11", "merge_with:14", {**FIO, "birthday": "2014-02-02"})
    assert fake.calls == []


def test_dup_row_must_be_finish_of_this_card(monkeypatch):
    fake = Fake(monkeypatch, everything())
    with pytest.raises(ValueError, match="финиш этой карточки"):
        fake.answer("R-DUP:r4:9", "to:10", {"row_id": "1"})
    assert fake.calls == []


def test_locked_stage_answer_rejected_postpone_allowed(monkeypatch):
    fake = Fake(monkeypatch, everything())
    with pytest.raises(ValueError, match="сначала ответьте на вопросы ступени «Кто есть кто»"):
        fake.answer("R-CAT:r101:1", "keep", only=False)
    fake.answer("R-CAT:r101:1", "postpone", only=False)
    assert {c[1][0] for c in fake.calls} == {"R-CAT:r101:1", "L-KID:l2:1", "R-FOREIGN:r101:1-2-3",
                                             "R-FOREIGN:l2:1-2-3"}


def test_live_race_rejects_all_but_moves(monkeypatch):
    fake = Fake(monkeypatch, pcarev())
    monkeypatch.setattr(dq_cases, "_today", lambda: datetime.date(2016, 8, 29))
    with pytest.raises(ValueError, match="загружается"):
        fake.answer("R-FOREIGN:r101:1-2-3", "keep")
    fake.answer("R-FOREIGN:r101:1-2-3", "to:2")
    assert [c[0] for c in fake.calls] == ["move_row"]


def test_unknown_answer_and_stale_question(monkeypatch):
    fake = Fake(monkeypatch, everything())
    with pytest.raises(ValueError, match="неизвестный ответ"):
        fake.answer("R-FOREIGN:r101:1-2-3", "to:1")
    with pytest.raises(dq_cases.StaleQuestion):
        dq_cases.apply_answer(None, "c1", "R-FOREIGN:r999:1", "keep", {}, U)


def test_loads_once_per_read(monkeypatch):
    fake = Fake(monkeypatch, everything())
    for call in (lambda: dq_cases.get_case(None, "c1"), lambda: dq_cases.case_for_card(None, 1),
                 lambda: dq_cases.postpone_case(None, "c1", "", U)):
        fake.loads = 0
        call()
        assert (fake.loads, fake.full_loads) == (1, 0)


def test_queue_is_cached_until_an_action(monkeypatch):
    fake = Fake(monkeypatch, everything())

    def full_loads(call):
        before = fake.full_loads
        call()
        return fake.full_loads - before

    assert full_loads(lambda: dq_cases.list_cases(None, "open")) == 1
    assert full_loads(lambda: dq_cases.list_cases(None, "postponed")) == 0
    fake.answer("HYG:r7:12", "keep")                    # answer() обнуляет счётчики
    assert full_loads(lambda: dq_cases.list_cases(None, "open")) == 1
    dq_cases.postpone_case(None, "c1", "", U)
    assert full_loads(lambda: dq_cases.list_cases(None, "open")) == 1


def test_invalidate_during_load_is_not_lost(monkeypatch):
    """Поток A грузит базу, поток B ответил и сбросил кеш — данные A (до ответа) в кеш не попадают."""
    fake = Fake(monkeypatch, everything())

    def load_while_answered(conn):
        fake.full_loads += 1
        dq_cases.invalidate()
        return fake.d

    monkeypatch.setattr(dq_cases, "load", load_while_answered)
    dq_cases.list_cases(None, "open")
    dq_cases.list_cases(None, "open")
    assert fake.full_loads == 2


def test_failed_chain_still_invalidates_queue(monkeypatch):
    fake = Fake(monkeypatch, everything())
    dq_cases.list_cases(None, "open")
    fake.fail = lambda name, args: name == "edit_record" and args[0] == "results"     # карточка записана, строка — нет
    with pytest.raises(ValueError):
        fake.answer("R-CARD:r6:11", "other", {**FIO, "birthday": "2014-06-06"})
    before = fake.full_loads
    dq_cases.list_cases(None, "open")
    assert fake.full_loads - before == 1


def test_case_not_converged_falls_back_to_full_run(monkeypatch, caplog):
    fake = Fake(monkeypatch, everything(), scoped=True)
    want = dq_cases.get_case(None, "c5")             # 5 -> тёзка 6 -> неподвижная точка на второй итерации
    monkeypatch.setattr(dq_cases, "EXPAND", 1)
    fake.loads = fake.full_loads = 0
    with caplog.at_level("WARNING"):
        assert dq_cases.get_case(None, "c5") == want
    assert fake.full_loads == 1 and "[5]" in caplog.text


def test_scoped_case_equals_full_run_case(monkeypatch):
    d = everything()
    Fake(monkeypatch, d, scoped=True)
    today = datetime.date(2026, 10, 28)
    for case in group_cases(run_checks(d), d):
        assert dq_cases.get_case(None, case["key"]) == case_view(case, d, {}, today), case["key"]


def merge_other_surname():
    """R-CARD Ветровой; карточка с итоговыми ФИ+ДР — другой фамилии (Орлова)."""
    return data([C(11, "Ветрова", "Елизавета", "2014-12-12"), C(14, "Орлова", "Елизавета", "2014-06-06")],
                results=[R(6, 11, "Ветрова", "Елизавета", "2014-01-01", 10, 4102, sex="Женщина")])


# фактическое число load_scoped на ответ (поиск дела + дело после ответа) при настоящем covers()
SCOPED_ANSWERS = [
    (everything, "R-FOREIGN:r101:1-2-3", "to:2", {}, 2),                       # перенос на тёзку
    (merge_other_surname, "R-CARD:r6:11", "merge_with:14",                       # склейка с другой фамилией
     {"surname": "Орлова", "name": "Елизавета", "birthday": "2014-06-06"}, 2),
]


@pytest.mark.parametrize("make,key,answer_id,inputs,loads", SCOPED_ANSWERS, ids=["to-namesake", "merge-other-surname"])
def test_answer_load_count_with_real_scope(monkeypatch, make, key, answer_id, inputs, loads):
    whole = Fake(monkeypatch, make()).answer(key, answer_id, inputs)
    fake = Fake(monkeypatch, make(), scoped=True)
    out = fake.answer(key, answer_id, inputs)
    assert fake.calls and (fake.loads, fake.full_loads) == (loads, 0)
    assert out == whole


def test_case_for_card_joins_namesake_case_else_unknown_key(monkeypatch):
    d = data([C(1, "Пцарев", "Александр", "1980-03-09"), C(2, "Пцарев", "Саша", "2013-12-20"),
              C(3, "Орлов", "Олег", "1990-02-02")],
             results=[R(100, 1, "Пцарев", "Александр", "1980-03-08", 11, 3470)])
    Fake(monkeypatch, d)
    case = dq_cases.case_for_card(None, 2)
    assert case["key"] == "c1" and {c["id"] for c in case["cards"]} == {1, 2}
    assert [q["id"] for q in case["questions"]] == ["R-CARD:r100:1"]
    alone = dq_cases.case_for_card(None, 3)
    assert alone["key"] == "p3" and alone["questions"] == []
    with pytest.raises(dq_cases.StaleQuestion):
        dq_cases.postpone_case(None, "p3", "", U)


def test_list_cases_event_filter_by_card_rows(monkeypatch):
    Fake(monkeypatch, everything())
    assert "c5" in {c["key"] for c in dq_cases.list_cases(None, "open", event_id=11)}       # C-TWIN без забега
    assert "c5" not in {c["key"] for c in dq_cases.list_cases(None, "open", event_id=10)}


def test_find_case_prefers_largest_overlap():
    cases = [{"key": "c1", "cards": [1]}, {"key": "c2", "cards": [2, 3]}]
    assert dq_cases._find_case(cases, "c9", [1, 2, 3])["key"] == "c2"


def test_rows_result_before_lead_in_one_event_and_category_options_with_sex():
    d = data([C(1, "Пцарев", "Александр", "1980-03-09")], leads=[L(1, 1, "Пцарев", "Александр", "1980-03-09", 11)],
             results=[R(100, 1, "Пцарев", "Александр", "1980-03-09", 11, 3470)])
    assert [r["table"] for r in dq_cases._rows(d, 1, {"results": set(), "leads": set()})] == ["results", "leads"]
    d = pcarev()
    q = next(q for q in case_view(pcarev_case(d), d, {}, datetime.date(2026, 10, 28))["questions"]
             if q["code"] == "R-CAT")
    opts = next(a for a in q["answers"] if a["id"] == "category")["inputs"][0]["options"]
    assert opts and all(set(o) == {"label", "sex"} for o in opts)


def test_other_compares_fio_case_insensitively(monkeypatch):
    fake = Fake(monkeypatch, everything())
    fake.answer("R-CARD:r6:11", "other", {"surname": "ветрова", "name": "ЕЛИЗАВЕТА", "birthday": "2014-06-06"})
    assert [(n, a[:3]) for n, a, _ in fake.calls] == [("edit_record", ("clients", 11, {"birthday": "2014-06-06"})),
                                                      ("edit_record", ("results", 6, {"birthday": "2014-06-06"}))]
    with pytest.raises(ValueError, match="значения не изменились"):
        fake.answer("R-CARD:r6:11", "other", {"surname": "ветрова", "name": "елизавета"})


def test_extra_cards_are_kept_in_case_after_answer(monkeypatch):
    fake = Fake(monkeypatch, everything())
    seen = []
    real = dq_cases.run_checks
    monkeypatch.setattr(dq_cases, "run_checks", lambda d, **kw: seen.append(kw.get("card_ids")) or real(d, **kw))
    case = next(c for c in group_cases(run_checks(fake.d), fake.d) if any(f.key == "R-CARD:r6:11" for f in c["findings"]))
    assert 3 not in case["cards"]
    dq_cases.apply_answer(None, case["key"], "R-CARD:r6:11", "card_from_row", {}, U, extra_cards=[3])
    assert 3 in seen[-1]


def row_subset(full, table, row_id):
    """Что выбрала бы load_row_scoped из базы full (в БД строку без карточки не создать: client_id NOT NULL + FK)."""
    row = (full.result_by_id if table == "results" else full.lead_by_id).get(row_id)
    if not row:
        return None
    keys = {norm(row["surname"]), norm(row["name"])}

    def near(r):
        return r["event_id"] == row["event_id"] and (not r["client_id"] or norm(r["surname"]) in keys or bool(
            row["start_number"] and r["start_number"] == row["start_number"]))

    cards = {r["client_id"] for r in full.leads + full.results if near(r)} - {0, None}
    return Data([c for i, c in full.clients.items() if i in cards],
                [x for x in full.leads if near(x) or x["client_id"] in cards],
                [x for x in full.results if near(x) or x["client_id"] in cards], list(full.events.values()), full.names)


def test_orphan_row_case_equals_full_run(monkeypatch):
    """Дела «r<id>» — результаты без карточки (client_id 0): R-DUP «два финиша» группы (0, забег), R-CARD."""
    d = data([C(1, "Пцарев", "Александр", "1980-03-09")],
             results=[R(100, 0, "Пцарев", "Александр", "1980-03-09", 11, 1), R(101, 0, "Орлов", "Олег", "1990-02-02", 11, 2),
                      R(102, 1, "Пцарев", "Александр", "1980-03-09", 12, 3)])
    fake = Fake(monkeypatch, d)
    monkeypatch.setattr(dq_cases, "load_row_scoped", lambda conn, table, row_id: row_subset(d, table, row_id))
    orphans = [c for c in group_cases(run_checks(d), d) if not c["cards"]]
    assert {"R-DUP", "R-CARD"} <= {f.code for c in orphans if c["key"] == "r100" for f in c["findings"]}
    for key in {c["key"] for c in orphans}:
        want = next(c for c in orphans if c["key"] == key)
        assert dq_cases.get_case(None, key) == case_view(want, d, {}, datetime.date(2026, 10, 28)), key
    assert dq_cases.get_case(None, "r999") is None
    assert (fake.loads, fake.full_loads) == (0, 0)
