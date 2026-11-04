"""Админка: эндпоинты обращений кабинета (Б3) на локальной БД; данные — фикстуры test_athlete_requests."""
import pytest
from fastapi.testclient import TestClient

from app import app
from src.core.auth import api_require_auth
from src.krasmarafon.services import athlete_claims as ac
from src.krasmarafon.services import athlete_requests as rq
from tests.integration.test_athlete_requests import (  # noqa: F401  (фикстуры)
    BD1, FINDER, ME, OWNER, PARENT, cards, claimed, db, mail, request_row)

BASE = "/api/admin/athlete-requests"


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def admin():
    app.dependency_overrides[api_require_auth] = lambda: "testuser"
    yield
    app.dependency_overrides.pop(api_require_auth, None)


@pytest.mark.parametrize("method,url", [("get", BASE), ("get", BASE + "/count"), ("post", BASE + "/1/resolve")])
def test_endpoints_require_login(client, method, url):
    assert getattr(client, method)(url).status_code == 401


def test_list_and_count(db, claimed, mail, client, admin):
    rid = rq.create(ME, "dispute", client_id=claimed["a"], comment="моя")
    nf = rq.create(FINDER, "not_found", payload={"surname": "Тестбтри", "bib": 77})
    before = client.get(BASE + "/count").json()["count"]
    rows = {r["id"]: r for r in client.get(BASE).json()["requests"]}
    assert rows[rid]["email"] == ME and rows[rid]["kind"] == "dispute" and rows[rid]["comment"] == "моя"
    assert rows[rid]["card"].startswith("Тестбтри") and rows[nf]["payload"]["bib"] == 77
    assert before >= 2
    rq.resolve(nf, "close", "op")
    assert client.get(BASE + "/count").json()["count"] == before - 1
    assert nf not in [r["id"] for r in client.get(BASE).json()["requests"]]
    closed = {r["id"]: r for r in client.get(BASE + "?status=closed").json()["requests"]}
    assert closed[nf]["resolution"] == "close" and rid not in closed


def test_resolve_transfer_moves_card_and_mails_in_background(db, claimed, mail, client, admin):
    rid = rq.create(ME, "dispute", client_id=claimed["a"])
    r = client.post(f"{BASE}/{rid}/resolve", json={"action": "transfer", "answer": "проверили"})
    assert r.status_code == 200 and r.json()["ok"] is True
    conn, cur = db
    cur.execute("SELECT email FROM athlete_claims WHERE client_id = %s", (claimed["a"],))
    assert [x["email"] for x in cur.fetchall()] == [ME]
    row = request_row(cur, rid)
    assert (row["status"], row["resolution"], row["answer"], row["resolved_by"]) == ("resolved", "transfer", "проверили", "testuser")
    assert {c.args[0] for c in mail.call_args_list} == {ME, OWNER}


def test_resolve_reject_and_close(db, claimed, mail, client, admin):
    rid = rq.create(ME, "dispute", client_id=claimed["a"])
    assert client.post(f"{BASE}/{rid}/resolve", json={"action": "reject", "answer": "нет"}).status_code == 200
    nf = rq.create(FINDER, "not_found", payload={"bib": 1})
    assert client.post(f"{BASE}/{nf}/resolve", json={"action": "close"}).status_code == 200
    conn, cur = db
    assert request_row(cur, rid)["resolution"] == "reject" and request_row(cur, nf)["resolution"] == "close"
    cur.execute("SELECT COUNT(*) n FROM athlete_claims WHERE email = %s", (ME,))
    assert cur.fetchone()["n"] == 0      # отклонение привязку не создаёт
    assert {c.args[0] for c in mail.call_args_list} == {ME, FINDER}


def test_resolve_attach(db, cards, mail, client, admin):
    nf = rq.create(FINDER, "not_found", payload={"bib": 9201})
    r = client.post(f"{BASE}/{nf}/resolve", json={"action": "attach", "client_id": cards["a"]})
    assert r.status_code == 200
    assert ac.claimed_cards(FINDER)[0] == [cards["a"]]


@pytest.mark.parametrize("body,code", [
    ({"action": "attach"}, "no_card"),
    ({"action": "transfer"}, "bad_action"),
    ({"action": "nonsense"}, "bad_action"),
])
def test_resolve_errors_are_400_with_code(db, cards, mail, client, admin, body, code):
    nf = rq.create(FINDER, "not_found", payload={"bib": 1})
    r = client.post(f"{BASE}/{nf}/resolve", json=body)
    assert r.status_code == 400 and r.json()["detail"] == code
    assert not mail.called


def test_resolve_unknown_and_already_closed(db, cards, mail, client, admin):
    assert client.post(f"{BASE}/999999999/resolve", json={"action": "close"}).json()["detail"] == "not_found"
    nf = rq.create(FINDER, "not_found", payload={"bib": 1})
    assert client.post(f"{BASE}/{nf}/resolve", json={"action": "close"}).status_code == 200
    r = client.post(f"{BASE}/{nf}/resolve", json={"action": "close"})
    assert r.status_code == 400 and r.json()["detail"] == "closed"
