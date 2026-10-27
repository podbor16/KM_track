"""
Заявки Siberman на локальной БД siberman: приём (вебхук/CSV/спул), статусы с журналом, публичный список без
контактов, Excel, маршруты. Год 2090–2099 (от PID), чистится до и после.
"""
import datetime
import io
import os

import mysql.connector
import openpyxl
import pytest

from app import app
from src.config import settings
from src.core.auth import api_require_auth
from src.siberman.db import get_siberman_connection
from src.siberman.entries import service, spool
from src.siberman.entries.service import EntryError

YEAR = 2090 + os.getpid() % 10
SIBERMAN = {"host": "siberman.localhost"}
T0 = datetime.datetime(2026, 11, 1, 10, 0)


def body(tranid, surname, name="Тест", fmt="Индивидуальное участие", sex="Мужской", **extra):
    return {"tranid": tranid, "formid": "f", "format": fmt, "surname": surname, "Name": name, "sex": sex,
            "birthday": "05.03.1985", "city": "Красноярск", "Email": f"{tranid}@ex.ru", "Phone": "+7 900", **extra}


def _clean():
    conn = get_siberman_connection()
    conn.cursor().execute("DELETE FROM siberman_entries WHERE race_year=%s", (YEAR,))
    conn.close()


@pytest.fixture
def entries():
    conn = get_siberman_connection()
    if conn is None:
        pytest.skip("Нет локальной БД siberman")
    cur = conn.cursor()
    cur.execute("SHOW TABLES LIKE 'siberman_entries'")
    if not cur.fetchone():
        conn.close()
        pytest.skip("Миграция 018 не применена")
    conn.close()
    _clean()
    service.clear_cache()
    service.ingest(YEAR, body(f"{YEAR}:1", "Яковлев"), T0)
    service.ingest(YEAR, body(f"{YEAR}:2", "Ёлкина", sex="Женский"), T0 + datetime.timedelta(minutes=5))
    service.ingest(YEAR, body(f"{YEAR}:3", "Абрамов", fmt="Эстафетная команда", sex="", team_name="Столбы"),
                   T0 + datetime.timedelta(minutes=10))
    yield {e["surname"]: e["id"] for e in service.admin_list(YEAR)["entries"]}
    _clean()
    service.clear_cache()


def test_admin_list_in_arrival_order_with_review_status(entries):
    s = service.admin_list(YEAR)
    assert [(e["n"], e["surname"], e["status"]) for e in s["entries"]] == [
        (1, "Яковлев", "review"), (2, "Ёлкина", "review"), (3, "Абрамов", "review")]
    assert s["counts"] == {"total": 3, "review": 3, "admitted": 0, "rejected": 0, "withdrawn": 0}
    assert YEAR in s["years"] and s["entries"][0]["email"] == f"{YEAR}:1@ex.ru"


def test_redelivery_updates_form_fields_but_keeps_status(entries):
    service.set_status(YEAR, entries["Яковлев"], "admitted", "director")
    service.set_comment(YEAR, entries["Яковлев"], "проверил", "director")
    assert service.ingest(YEAR, body(f"{YEAR}:1", "Яковлев", city="Омск"), T0 + datetime.timedelta(days=1)) is False
    e = service.admin_list(YEAR)["entries"][0]
    assert (e["city"], e["status"], e["comment"], e["submitted_at"]) == ("Омск", "admitted", "проверил", T0)
    card = service.entry_card(YEAR, entries["Яковлев"])
    assert [(a["action"], a["old_value"], a["new_value"], a["admin_user"]) for a in card["audit"]] == [
        ("status", "review", "admitted", "director"), ("comment", "", "проверил", "director")]


def test_status_errors(entries):
    with pytest.raises(EntryError, match="нет такого статуса"):
        service.set_status(YEAR, entries["Яковлев"], "maybe", "u")
    with pytest.raises(EntryError, match="нет такой заявки"):
        service.set_status(YEAR + 1, entries["Яковлев"], "admitted", "u")     # чужой год


def test_public_list_alphabetical_without_contacts(entries):
    service.set_status(YEAR, entries["Абрамов"], "withdrawn", "u")
    p = service.public_list(YEAR)
    assert (p["total"], p["admitted"]) == (3, 0)
    assert p["entries"] == [{"n": 1, "fio": "Абрамов Тест", "format": "Эстафетная команда", "status": "withdrawn"},
                            {"n": 2, "fio": "Ёлкина Тест", "format": "Индивидуальное участие", "status": "review"},
                            {"n": 3, "fio": "Яковлев Тест", "format": "Индивидуальное участие", "status": "review"}]
    assert "@ex.ru" not in str(p) and "1985" not in str(p)


def test_csv_import_adds_new_and_skips_known(entries):
    head = "surname;Name;Email;Phone;Date;format;sex;birthday;city;tranid"
    data = "\n".join([head, f"Яковлев;Тест;x@ex.ru;1;2026-10-30 09:00:00;Индивидуальное участие;Мужской;;Красноярск;{YEAR}:1",
                      f"Новенький;Тест;n@ex.ru;2;2026-10-31 09:00:00;Индивидуальное участие;Мужской;;Омск;{YEAR}:9",
                      "Кривой;Тест;k@ex.ru;3;2026-10-31 09:00:00;Что-то;Мужской;;Омск;x"]).encode("utf-8")
    r = service.import_csv(YEAR, data)
    assert (r["rows"], r["new"], r["known"], len(r["errors"])) == (3, 1, 1, 1)
    assert service.admin_list(YEAR)["entries"][0]["surname"] == "Новенький"     # по Date из CSV — раньше всех


def test_csv_import_skips_entry_already_in_other_year(entries):
    head = "surname;Name;Email;Phone;Date;format;sex;birthday;city;tranid"
    data = "\n".join([head, f"Яковлев;Тест;x@ex.ru;1;2026-10-30 09:00:00;Индивидуальное участие;Мужской;;Красноярск;{YEAR}:1"]
                     ).encode("utf-8")
    try:
        r = service.import_csv(YEAR + 1, data)
        assert (r["new"], r["known"]) == (0, 0)
        assert any(f"уже учтена в {YEAR} году" in er for er in r["errors"])
        assert service.admin_list(YEAR + 1)["counts"]["total"] == 0
    finally:
        conn = get_siberman_connection()
        conn.cursor().execute("DELETE FROM siberman_entries WHERE race_year=%s", (YEAR + 1,))
        conn.close()


def test_export_xlsx_does_not_execute_formulas(entries):
    service.ingest(YEAR, body(f"{YEAR}:11", "=1+1"), T0)
    ws = openpyxl.load_workbook(io.BytesIO(service.export_xlsx(YEAR))).active
    cell = next(r[2] for r in ws.iter_rows(min_row=2) if str(r[2].value).startswith("=1+1"))
    assert cell.data_type == "s" and cell.value.startswith("=1+1")


def test_unavailable_db_raises_entries_unavailable(entries, monkeypatch):
    monkeypatch.setattr(service, "get_siberman_connection", lambda: None)
    with pytest.raises(service.EntriesUnavailable):
        service.admin_list(YEAR)


def test_db_error_midway_raises_entries_unavailable(entries, monkeypatch):
    class Broken:
        def cursor(self, *a, **k):
            raise mysql.connector.errors.OperationalError("оборвалось")

        def close(self):
            pass
    service.clear_cache()
    monkeypatch.setattr(service, "get_siberman_connection", lambda: Broken())
    with pytest.raises(service.EntriesUnavailable):
        service.public_list(YEAR)


def test_identical_redelivery_returns_false(entries):
    assert service.ingest(YEAR, body(f"{YEAR}:1", "Яковлев"), T0) is False


def test_unchanged_comment_not_audited(entries):
    service.set_comment(YEAR, entries["Яковлев"], "x", "u")
    service.set_comment(YEAR, entries["Яковлев"], "x", "u")
    audit = service.entry_card(YEAR, entries["Яковлев"])["audit"]
    assert [a["action"] for a in audit] == ["comment"]


def test_export_xlsx(entries):
    service.set_comment(YEAR, entries["Ёлкина"], "уточнить ДР", "u")
    ws = openpyxl.load_workbook(io.BytesIO(service.export_xlsx(YEAR))).active
    rows = [[c.value for c in r] for r in ws.iter_rows()]
    assert rows[0][:4] == ["№", "Дата заявки", "Фамилия Имя", "Формат участия"]
    assert [r[2] for r in rows[1:]] == ["Яковлев Тест", "Ёлкина Тест", "Абрамов Тест"]
    assert "уточнить ДР" in rows[2] and "⌛️ на изучении" in rows[1]


def test_spool_replay_saves_entry_and_moves_bad_to_failed(entries, tmp_path, monkeypatch):
    monkeypatch.setattr(spool, "SPOOL_DIR", tmp_path)
    good = spool.save(body(f"{YEAR}:7", "Повторный"), YEAR, T0)
    bad = spool.save({"tranid": f"{YEAR}:8", "format": "???"}, YEAR, T0)
    assert spool.replay(service.ingest, min_age_s=0) == {"replayed": 1, "failed": 0, "bad": 1, "oldest_failed_age_s": 0}
    assert not good.exists() and (tmp_path / "failed" / bad.name).exists()
    assert "Повторный" in [e["surname"] for e in service.admin_list(YEAR)["entries"]]


def test_spool_keeps_file_when_db_fails(entries, tmp_path, monkeypatch):
    monkeypatch.setattr(spool, "SPOOL_DIR", tmp_path)
    path = spool.save(body(f"{YEAR}:7", "Повторный"), YEAR, T0)

    def broken(*a):
        raise RuntimeError("БД упала")
    done = spool.replay(broken, min_age_s=0)
    assert (done["replayed"], done["failed"]) == (0, 1) and path.exists()


def test_spool_corrupt_file_goes_to_failed(entries, tmp_path, monkeypatch):
    monkeypatch.setattr(spool, "SPOOL_DIR", tmp_path)
    (tmp_path / "x.json").write_text("{не json", encoding="utf-8")
    done = spool.replay(service.ingest, min_age_s=0)
    assert done["bad"] == 1 and done["failed"] == 0
    assert not (tmp_path / "x.json").exists() and (tmp_path / "failed" / "x.json").exists()


def test_webhook_secret_ping_and_entry(entries, client, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "SIBERMAN_WEBHOOK_SECRET", "s3cret")
    monkeypatch.setattr(spool, "SPOOL_DIR", tmp_path)
    url = f"/webhook/siberman/s3cret/{YEAR}"
    assert client.post(f"/webhook/siberman/wrong/{YEAR}", data={"test": "test"}).status_code == 403
    assert client.post("/webhook/siberman/s3cret/1999", data={"test": "test"}).status_code == 404
    r = client.post(url, data={"test": "test"})
    assert r.status_code == 200 and r.text == "ok"
    assert client.post(url, data=body(f"{YEAR}:5", "Вебхуков")).status_code == 200
    assert client.post(url, data={"tranid": f"{YEAR}:6", "format": "???"}).status_code == 200   # не заявка — 200, в failed/
    assert "Вебхуков" in [e["surname"] for e in service.admin_list(YEAR)["entries"]]
    assert not list(tmp_path.glob("*.json")) and len(list((tmp_path / "failed").glob("*.json"))) == 1


def test_admin_api_requires_auth_and_works(entries, client):
    base = f"/api/siberman/admin/entries/{YEAR}"
    assert client.get(base).status_code == 401
    app.dependency_overrides[api_require_auth] = lambda: "director"
    try:
        assert client.get(base).json()["counts"]["total"] == 3
        eid = entries["Ёлкина"]
        assert client.post(f"{base}/{eid}/status", json={"status": "rejected"}).status_code == 200
        assert client.post(f"{base}/{eid}/status", json={"status": "maybe"}).status_code == 409
        assert client.post(f"{base}/{eid}/comment", json={"comment": "нет ДР"}).status_code == 200
        card = client.get(f"{base}/{eid}").json()
        assert card["status"] == "rejected" and card["comment"] == "нет ДР" and len(card["audit"]) == 2
        assert client.get(f"{base}/999999999").status_code == 409
        x = client.get(f"{base}/export.xlsx")
        assert x.status_code == 200 and x.headers["content-type"].startswith("application/vnd.openxml")
        up = client.post(f"{base}/import", files={"file": ("a.csv", b"a;b\n1;2", "text/csv")})
        assert up.status_code == 409 and "tranid" in up.json()["detail"]
    finally:
        app.dependency_overrides.pop(api_require_auth, None)


def test_public_api_and_page(entries, client):
    service.clear_cache()
    data = client.get(f"/api/siberman/entries/{YEAR}").json()
    assert data["total"] == 3 and set(data["entries"][0]) == {"n", "fio", "format", "status"}
    assert client.get(f"/entries/{YEAR}", headers=SIBERMAN).status_code == 200
    assert client.get(f"/entries/{YEAR}").status_code == 404                  # только домен Siberman
    assert client.get("/api/siberman/entries/1999").status_code == 404


def test_webhook_spool_save_fails_still_ingests(entries, client, monkeypatch):
    monkeypatch.setattr(settings, "SIBERMAN_WEBHOOK_SECRET", "s3cret")

    def broken_save(*a, **k):
        raise OSError("диск")
    monkeypatch.setattr(spool, "save", broken_save)
    r = client.post(f"/webhook/siberman/s3cret/{YEAR}", data=body(f"{YEAR}:9", "Безспула"))
    assert r.status_code == 200
    assert "Безспула" in [e["surname"] for e in service.admin_list(YEAR)["entries"]]


def test_webhook_ingest_fails_keeps_spool_and_returns_200(entries, client, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "SIBERMAN_WEBHOOK_SECRET", "s3cret")
    monkeypatch.setattr(spool, "SPOOL_DIR", tmp_path)

    def broken_ingest(*a, **k):
        raise RuntimeError("БД упала")
    monkeypatch.setattr(service, "ingest", broken_ingest)
    r = client.post(f"/webhook/siberman/s3cret/{YEAR}", data=body(f"{YEAR}:9", "Повторится"))
    assert r.status_code == 200 and len(list(tmp_path.glob("*.json"))) == 1


def test_webhook_nothing_saved_returns_500(entries, client, monkeypatch):
    monkeypatch.setattr(settings, "SIBERMAN_WEBHOOK_SECRET", "s3cret")

    def broken(*a, **k):
        raise RuntimeError("сбой")
    monkeypatch.setattr(spool, "save", broken)
    monkeypatch.setattr(service, "ingest", broken)
    assert client.post(f"/webhook/siberman/s3cret/{YEAR}", data=body(f"{YEAR}:9", "Потерян")).status_code == 500


def test_public_api_503_when_db_unavailable(entries, client, monkeypatch):
    monkeypatch.setattr(service, "get_siberman_connection", lambda: None)
    service.clear_cache()
    assert client.get(f"/api/siberman/entries/{YEAR}").status_code == 503
    service.clear_cache()
