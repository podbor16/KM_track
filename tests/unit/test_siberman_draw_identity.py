from contextlib import nullcontext
from datetime import date
from io import BytesIO
from unittest.mock import Mock

from openpyxl import load_workbook

from src.siberman.draw import service
from src.siberman.entries import identity
from src.siberman.entries import service as entry_service


def test_same_name_with_missing_or_conflicting_birthdate_is_not_linked():
    first = {"id": 1, "birthdate": date(1985, 1, 1)}
    second = {"id": 2, "birthdate": date(1976, 1, 1)}
    def resolve(dob, manual=None):
        return identity.resolve({"birthdate": dob}, [first, second], manual)

    assert resolve(first["birthdate"]) == {"person_id": 1, "state": "matched"}
    assert resolve(second["birthdate"]) == {"person_id": 2, "state": "matched"}
    assert resolve(None) == {"person_id": None, "state": "review"}
    assert resolve(second["birthdate"], 1) == {"person_id": None, "state": "review"}
    assert resolve(second["birthdate"], 2) == {"person_id": 2, "state": "manual"}


def test_confirming_an_already_saved_identity_is_a_noop(monkeypatch):
    conn = object()
    person = {"id": 7, "birthdate": date(1985, 1, 1)}
    entry = {"id": 2, "birthdate": person["birthdate"]}
    record = Mock()
    monkeypatch.setattr(entry_service, "_db", lambda: nullcontext(conn))
    monkeypatch.setattr(entry_service, "lock_people", lambda _: nullcontext())
    monkeypatch.setattr(entry_service, "_entry", lambda *_: entry)
    monkeypatch.setattr(entry_service.edb, "record_identity", record)
    for state in ("manual", "new"):
        decision = {2: {"person_id": 7, "state": state, "candidates": [person]}}
        monkeypatch.setattr(identity, "decisions", lambda *_, **__: decision)
        assert entry_service.set_identity(2029, 2, "link", 7, "test") == {"ok": True}
    record.assert_not_called()


def test_billing_uses_the_source_application_id_even_for_equal_names():
    contacts = {1: {"email": "first@example.invalid"}, 2: {"email": "second@example.invalid"}}
    namesake = {"surname": "Тестовый", "name": "Участник"}
    assert service.contact_for(dict(namesake, entry_id=1), contacts) == contacts[1]
    assert service.contact_for(dict(namesake, entry_id=2), contacts) == contacts[2]
    assert service.contact_for(namesake, contacts) is None


def test_payment_export_restores_only_unambiguous_2028_contacts(monkeypatch):
    def applicant(row_id, surname, **fields):
        return {"id": row_id, "surname": surname, "name": "Тест", "format": "individual",
                "city": "", "is_wildcard": False, "payment_status": "paid", "payment_comment": "", **fields}

    applicants = [
        applicant(1, "Архивный"),
        applicant(2, "Связанный", entry_id=200),
        applicant(3, "Тёзка"),
        applicant(4, "Дубликат"),
        applicant(5, "Дубликат"),
        applicant(6, "БезЗаявки", entry_id=201),
        applicant(7, "Капитан", format="relay"),
    ]
    archived = {"email": "archive@example.invalid", "phone": "+7 000 000-00-00"}
    linked = {"email": "linked@example.invalid", "phone": "=123"}
    archive = {("individual", f"{a['surname'].lower()} тест"): archived for a in applicants}
    archive["relay", "тест капитан"] = archived
    monkeypatch.setattr(service.ddb, "load_contacts", lambda *_: archive)
    monkeypatch.setattr(service.ddb, "entry_contacts", lambda *_: {200: linked})
    monkeypatch.setattr(service.ddb, "person_ids_by_key", lambda *_: {"тезка тест": None})
    monkeypatch.setattr(service, "_connect", Mock)
    lists = {c: [] for c in service.CATEGORIES}
    lists["men"] = [{"applicant_id": a["id"], "position": a["id"], "section": "winner", "round": 4}
                    for a in applicants]
    monkeypatch.setattr(service, "_snapshot", lambda *_: {"applicants": applicants, "lists": lists})

    sheet = load_workbook(BytesIO(service.payment_export(2028))).active
    assert [tuple(cell.value for cell in row) for row in sheet["F2:G8"]] == [
        (archived["email"], archived["phone"]), (linked["email"], linked["phone"]),
        (None, None), (None, None), (None, None), (None, None),
        (archived["email"], archived["phone"]),
    ]
    assert sheet["G3"].data_type == "s"
    assert sheet["F4"].fill.fgColor.rgb == "00FFF3C4"
    assert service._billing_contacts(None, 2029, applicants) == {2: linked}


def test_namesake_does_not_inherit_another_persons_draw_balance():
    history = {2028: {"applicants": [{"person_id": 1, "draw_accumulated": 3}]}}
    kwargs = {"started": set(), "archive_years": set()}
    assert service._accumulated_for(history, 2, is_new=False, archived_draws=[], **kwargs)[0] is None
    assert service._accumulated_for(history, 2, is_new=True, archived_draws=[], **kwargs)[0] == 0
    assert service._accumulated_for(history, 2, is_new=True, archived_draws=[2027], **kwargs)[0] is None
