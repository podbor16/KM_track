"""scripts/apply_ext_birthdays.py — выбор находок и строки таблицы (без БД)."""
import importlib.util
from pathlib import Path

from src.analytics.dq_checks import Data, Finding, run_checks
from src.common.names import Names

_spec = importlib.util.spec_from_file_location(
    "apply_ext_birthdays", Path(__file__).parents[2] / "scripts" / "apply_ext_birthdays.py")
m = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(m)

EVENTS = [{"id": 1, "event_name": "Жара", "event_distance": 5.0, "event_year": 2025}]


def card(cid, surname, phone="", email=""):
    return ({"id": cid, "surname": surname, "name": "Иван", "birthday": "1900-01-01"},
            {"id": cid, "client_id": cid, "surname": surname, "name": "Иван", "birthday": "1900-01-01", "sex": "",
             "event_id": 1, "event_distance": "5", "start_number": None, "phone": phone, "email": email},
            {"id": cid, "client_id": cid, "surname": surname, "name": "Иван", "birthday": "1900-01-01", "sex": "Мужчина",
             "event_id": 1, "start_number": cid, "category": "", "race_status": "Finished", "time_clear_finish": None})


def ext(i, surname, bd, phone="", email=""):
    return {"id": i, "surname": surname, "name": "Иван", "birthday": bd, "sex": "", "phone": phone, "email": email,
            "product": "", "event_year": 2019}


def test_pick_only_reliable_undecided_and_describe_without_contacts():
    rows = [card(1, "Иванов", phone="+79230000001"), card(2, "Петров", email="p@mail.ru"), card(3, "Сидоров"),
            card(4, "Козлов", phone="+79230000004")]
    d = Data([r[0] for r in rows], [r[1] for r in rows], [r[2] for r in rows], EVENTS,
             ext=[ext(1, "Иванов", "1985-07-14", phone="9230000001"),
                  ext(2, "Петров", "1990-03-03", email="p@mail.ru"),
                  ext(3, "Сидоров", "1970-02-02"),                                       # только ФИО — medium
                  ext(4, "Козлов", "1980-01-05", phone="9230000004")])
    d.names = Names([("Иванов", "Иван", "Мужчина")] * 5)
    found = run_checks(d)
    chosen = m.pick(found, {"X-BD::4": "postponed"})
    assert [f.key for f in chosen] == ["X-BD::1", "X-BD::2"]
    assert m.pick([Finding("X-BD", "high", "", (5,), fix=("1985-07-14", "1986-07-14"))], {}) == []
    assert m.describe(d, chosen[0]) == {"fio": "Иванов Иван", "was": "1900-01-01", "will": "1985-07-14",
                                        "events": "Жара 5.0 2025", "by": "телефон"}
    shown = " ".join(map(str, m.describe(d, chosen[1]).values()))
    assert m.describe(d, chosen[1])["by"] == "почта" and "@" not in shown and "923" not in shown


def test_outcome_partial_write_is_skipped_with_written_ids():
    assert m.outcome("Иванов Иван", "1985-07-14", {"action_ids": [5, 6]}) == (
        "done", "Иванов Иван → 1985-07-14: действия журнала 5, 6")
    kind, line = m.outcome("Иванов Иван", "1985-07-14", {"action_ids": [5], "error": "нет строки #9"})
    assert kind == "skipped" and line == "Иванов Иван 1985-07-14: записано частично (действия журнала 5): нет строки #9"
    assert m.outcome("Иванов Иван", "1985-07-14", {"action_ids": [], "conflict": {"message": "Склеить?"}})[0] == "conflict"
