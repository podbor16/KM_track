from datetime import date

from src.siberman.draw import service
from src.siberman.entries import identity


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


def test_billing_uses_the_source_application_id_even_for_equal_names():
    contacts = {1: {"email": "first@example.invalid"}, 2: {"email": "second@example.invalid"}}
    namesake = {"surname": "Тестовый", "name": "Участник"}
    assert service.contact_for(dict(namesake, entry_id=1), contacts) == contacts[1]
    assert service.contact_for(dict(namesake, entry_id=2), contacts) == contacts[2]
    assert service.contact_for(namesake, contacts) is None


def test_namesake_does_not_inherit_another_persons_draw_balance():
    history = {2028: {"applicants": [{"person_id": 1, "draw_accumulated": 3}]}}
    kwargs = {"started": set(), "archive_years": set()}
    assert service._accumulated_for(history, 2, is_new=False, archived_draws=[], **kwargs)[0] is None
    assert service._accumulated_for(history, 2, is_new=True, archived_draws=[], **kwargs)[0] == 0
    assert service._accumulated_for(history, 2, is_new=True, archived_draws=[2027], **kwargs)[0] is None
