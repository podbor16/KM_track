"""Вебхук Tilda не теряет заявки: спул на диске + повтор (27.09.2026 три заявки ушли в «db error» с HTTP 200)."""
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app import app
from src.krasmarafon.routers import webhook

W = "src.krasmarafon.routers.webhook"
BODY = "name=Иван&surname=Иванов&payment=x"


@pytest.fixture(autouse=True)
def spool(tmp_path, monkeypatch):
    monkeypatch.setattr(webhook, "SPOOL_DIR", tmp_path)
    monkeypatch.setattr(webhook.settings, "TILDA_WEBHOOK_SECRET", "s3cret")
    return tmp_path


client = TestClient(app)


def post(body=BODY):
    return client.post("/webhook/tilda/s3cret", content=body.encode("utf-8"),
                       headers={"Content-Type": "application/x-www-form-urlencoded"})


def test_db_error_keeps_request_and_replay_writes_it(spool):
    with patch(f"{W}.process_tilda_body", side_effect=RuntimeError("pool exhausted")):
        r = post()
    assert r.status_code == 200 and r.json()["error"] == "queued for retry"
    [f] = list(spool.glob("*.json"))
    with patch(f"{W}.process_tilda_body", return_value={"surname": "Иванов"}) as proc:
        done = webhook.replay_spool(min_age_s=0)
    assert done["replayed"] == 1 and not f.exists()
    body, received_at = proc.call_args.args
    assert body["surname"] == "Иванов" and received_at.year >= 2026


def test_success_leaves_nothing(spool):
    with patch(f"{W}.process_tilda_body", return_value={}):
        assert post().json() == {"ok": True}
    assert not list(spool.glob("*"))


def test_bad_payload_goes_to_failed_not_retried(spool):
    with patch(f"{W}.transform_tilda_payload", side_effect=ValueError("нет продукта")):
        r = post()
    assert r.json()["error"] == "transform failed"
    assert not list(spool.glob("*.json")) and len(list((spool / "failed").glob("*.json"))) == 1


def test_tilda_test_ping_not_spooled(spool):
    with patch(f"{W}.process_tilda_body") as proc:
        assert post("test=test").json() == {"ok": True}
    proc.assert_not_called()
    assert not list(spool.glob("*.json"))


def test_replay_skips_fresh_files(spool):
    with patch(f"{W}.process_tilda_body", side_effect=RuntimeError("db")):
        post()
    with patch(f"{W}.process_tilda_body") as proc:
        assert webhook.replay_spool()["replayed"] == 0      # моложе 2 минут — может обрабатываться живым запросом
    proc.assert_not_called()


def test_process_does_not_duplicate_existing_lead():
    data = {"surname": "Иванов", "name": "Иван", "event_name": "Весна", "event_year": 2027,
            "transaction_id": "tx1", "order_id": None}
    with patch(f"{W}.transform_tilda_payload", return_value=dict(data)), \
            patch(f"{W}._lead_exists", return_value=True), patch(f"{W}._insert_lead") as ins:
        webhook.process_tilda_body({}, webhook.datetime(2026, 9, 27, 19, 54))
    ins.assert_not_called()


def test_lead_exists_without_ids_does_not_query():
    with patch(f"{W}.get_pooled_connection") as gp:
        assert webhook._lead_exists({"transaction_id": "", "order_id": None}) is False
    gp.assert_not_called()


def test_lead_exists_closes_connection():
    conn = MagicMock()
    conn.cursor.return_value.fetchone.return_value = (1,)
    with patch(f"{W}.get_pooled_connection", return_value=conn):
        assert webhook._lead_exists({"surname": "И", "name": "И", "event_name": "Е", "event_year": 2027,
                                     "transaction_id": "tx", "order_id": None}) is True
    conn.close.assert_called_once()
