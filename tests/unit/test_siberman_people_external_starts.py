from contextlib import nullcontext
from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core.auth import api_require_auth
from src.siberman.draw.chances import external_start_bonus
from src.siberman.persons import service
from src.siberman.persons.linking import plain_key
from src.siberman.persons.router import router


PERSON = "/api/siberman/admin/people/1/external-starts"
STAMP = datetime(2025, 9, 27, 12)
TEAM = {
    "event_id": 4, "result_id": 31, "race_year": 2025, "start_number": 1001,
    "participant": "Команда «Пример»", "category": "Эстафета",
    "roster": ["Тестова Анна", "Тестов Алексей"], "is_team": True, "birthdate": STAMP.date(),
}
SOLO = {
    **TEAM, "event_id": 2, "result_id": 9, "start_number": 15, "participant": "Тестов Алексей",
    "category": "Личный зачёт", "roster": [], "is_team": False,
}


@pytest.fixture
def admin(monkeypatch):
    app = FastAPI()
    app.include_router(router)
    links = {}
    audits = []

    monkeypatch.setattr(service, "_connection", lambda: nullcontext(object()))
    monkeypatch.setattr(service, "_locked_tx", lambda conn: nullcontext())
    monkeypatch.setattr(service, "load_protocol", lambda source: [SOLO] if source == "duathlon_222" else [TEAM])
    monkeypatch.setattr(service.pdb, "get_person", lambda conn, person: {"surname": "Тестов", "name": "Алексей"})
    monkeypatch.setattr(service.pdb, "external_start_links", lambda conn, person: [
        {"source": source, "event_id": event, "result_id": result, "confirmed_at": confirmed_at}
        for (owner, source, event, result), confirmed_at in links.items() if owner == person
    ])
    monkeypatch.setattr(service.pdb, "external_start_owners", lambda conn, source, event, result: {
        key[0]: value for key, value in links.items() if key[1:] == (source, event, result)
    })
    monkeypatch.setattr(service.pdb, "add_external_start",
                        lambda conn, *key, confirmed_at=None: links.__setitem__(key, confirmed_at or STAMP))
    monkeypatch.setattr(service.pdb, "delete_external_start", lambda conn, *key: links.pop(key))
    monkeypatch.setattr(service.pdb, "add_audit",
                        lambda conn, action, summary, payload, scope, user: audits.append({
                            "payload": payload, "scope": ",".join(sorted(scope)), "undone_at": None, "user": user,
                        }))
    monkeypatch.setattr(service.pdb, "get_audit", lambda conn, audit_id: audits[audit_id - 1])
    monkeypatch.setattr(service.pdb, "later_conflicts", lambda *args: [])
    monkeypatch.setattr(service.pdb, "mark_undone",
                        lambda conn, audit_id, user: audits[audit_id - 1].update(undone_at=STAMP))
    return app, TestClient(app), links, audits


def test_admin_search_checks_auth_and_finds_relay_member_or_number(admin):
    app, client, _, _ = admin
    assert client.get(PERSON).status_code == 401
    app.dependency_overrides[api_require_auth] = lambda: "test-admin"

    for query in ("алексей тестов", "№1001"):
        response = client.get(f"{PERSON}/search", params={"source": "race_24h", "year": 2025, "q": query})
        rows = response.json()["results"]
        assert len(rows) == 1 and rows[0]["roster"] == TEAM["roster"]
        assert rows[0]["result_id"] == 31 and "birthdate" not in rows[0]
    assert client.get(PERSON).json()["years"] == {"duathlon_222": [2025], "race_24h": [2025]}


def test_link_is_idempotent_individual_has_one_owner_and_unlink_is_audited(admin):
    app, client, links, audits = admin
    app.dependency_overrides[api_require_auth] = lambda: "test-admin"
    solo = {"source": "duathlon_222", "event_id": 2, "result_id": 9}
    assert client.post(PERSON, json={**solo, "result_id": 42}).status_code == 409
    assert client.post(PERSON, json=solo).json() == {"ok": True}
    assert client.post(PERSON, json=solo).json() == {"ok": True}
    assert len(audits) == 1 and audits[0]["user"] == "test-admin"
    assert client.post(PERSON.replace("/1/", "/2/"), json=solo).status_code == 409
    assert client.get(PERSON).json()["links"][0]["available"]

    assert client.delete(f"{PERSON}/duathlon_222/2/9").json() == {"ok": True}
    assert not links and len(audits) == 2
    assert client.post("/api/siberman/admin/people/undo/2").json() == {"ok": True}
    assert links[(1, "duathlon_222", 2, 9)] == STAMP

    team = {"source": "race_24h", "event_id": 4, "result_id": 31}
    assert client.post(PERSON, json=team).json() == {"ok": True}
    assert client.post(PERSON.replace("/1/", "/2/"), json=team).json() == {"ok": True}


def test_linked_individual_result_is_not_auto_counted_for_another_card():
    row = dict(SOLO, surname="Тестов", name="Алексей")
    bonus, _, issue = external_start_bonus(
        [row], race="Дуатлон 222", name_key=plain_key("Тестов", "Алексей"), birthdate=STAMP.date(),
        reported=1, through_year=2028, assigned_elsewhere={(2, 9)},
    )
    assert bonus is None
    assert "привязан к другой карточке" in issue
