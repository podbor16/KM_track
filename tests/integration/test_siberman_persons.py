"""
Реестр людей на локальной БД siberman (.env.local): синхронизация, ДР из заявок, ручные решения
и отмена. Тестовые годы 2090–2099 (от PID), фамилии «Тестреестров…» — чистятся до и после.
Первый прогон привязывает и весь локальный архив — это и есть первичное заполнение.
Годы идут по возрастанию (YEAR < Y2 < Y3): привязка зависит от порядка лет.
"""
import datetime
import os

import pytest

from src.siberman.db import get_siberman_connection
from src.siberman.persons import db as pdb
from src.siberman.persons import service
from src.siberman.persons.linking import Applicant

YEAR = 2090 + os.getpid() % 8   # изоляция параллельных прогонов, YEAR..Y3 ≤ 2099
Y2, Y3 = YEAR + 1, YEAR + 2


def _ins(conn, year, bib, surname, name, fmt="individual", stage="none", gender="M", team=None, city="Красноярск"):
    conn.cursor().execute(
        "INSERT INTO participants (race_year, bib, surname, name, gender, country, city, format, "
        "relay_team_name, relay_stage, status) VALUES (%s,%s,%s,%s,%s,'Россия',%s,%s,%s,%s,'active')",
        (year, str(bib), surname, name, gender, city, fmt, team, stage))


def _clean(conn):
    cur = conn.cursor()
    cur.execute("DELETE FROM siberman_person_links WHERE race_year IN (%s,%s,%s)", (YEAR, Y2, Y3))
    cur.execute("DELETE FROM participants WHERE race_year IN (%s,%s,%s)", (YEAR, Y2, Y3))
    cur.execute("DELETE FROM siberman_person_reviews WHERE race_year IN (%s,%s,%s) OR detail LIKE 'test-%%'",
                (YEAR, Y2, Y3))
    cur.execute("DELETE FROM siberman_applicants WHERE tranid LIKE 'test-%%'")
    cur.execute("DELETE FROM siberman_person_audit WHERE summary LIKE '%%Тестреестров%%'")
    cur.execute("DELETE s FROM siberman_persons s LEFT JOIN siberman_person_links l ON l.person_id=s.id "
                "WHERE l.person_id IS NULL AND s.surname LIKE 'Тестреестров%%'")


def _pid(conn, year, bib, stage="none"):
    cur = conn.cursor()
    cur.execute("SELECT person_id FROM siberman_person_links WHERE race_year=%s AND bib=%s AND relay_stage=%s",
                (year, str(bib), stage))
    row = cur.fetchone()
    return row[0] if row else None


@pytest.fixture
def conn():
    c = get_siberman_connection()
    if c is None:
        pytest.skip("Нет локальной БД siberman")
    cur = c.cursor()
    cur.execute("SHOW TABLES LIKE 'siberman_person_links'")
    if not cur.fetchone():
        c.close()
        pytest.skip("Миграция 014_persons не применена")
    _clean(c)
    yield c
    _clean(c)
    c.close()


def test_sync_links_and_is_idempotent(conn):
    _ins(conn, YEAR, 9001, "Тестреестров", "Олег")
    _ins(conn, Y2, 9001, "Тестреестров", "Олег")
    _ins(conn, YEAR, 9101, "Тестреестрова", "Анна", fmt="relay", stage="swim", gender="F", team="Тест")
    _ins(conn, YEAR, 9101, "Тестреестрова", "Анна", fmt="relay", stage="bike", gender="F", team="Тест")
    first = service.sync(conn)
    assert first["linked"] >= 4
    assert _pid(conn, YEAR, 9001) == _pid(conn, Y2, 9001)
    assert _pid(conn, YEAR, 9101, "swim") == _pid(conn, YEAR, 9101, "bike")
    assert pdb.get_person(conn, _pid(conn, YEAR, 9001))["bib_individual"] == "9001"
    second = service.sync(conn)
    assert second["linked"] == 0 and second["new_persons"] == 0


def test_namesakes_by_individual_bib(conn):
    _ins(conn, YEAR, 9001, "Тестреестров", "Иван")
    _ins(conn, Y2, 9002, "Тестреестров", "Иван")
    service.sync(conn)
    assert _pid(conn, YEAR, 9001) != _pid(conn, Y2, 9002)


def test_reload_of_year_keeps_person_ids(conn):
    _ins(conn, YEAR, 9001, "Тестреестров", "Олег")
    _ins(conn, YEAR, 9101, "Тестреестрова", "Анна", fmt="relay", stage="run", gender="F", team="Тест")
    service.sync(conn)
    before = (_pid(conn, YEAR, 9001), _pid(conn, YEAR, 9101, "run"))
    conn.cursor().execute("DELETE FROM participants WHERE race_year=%s", (YEAR,))   # как clear_race_year
    _ins(conn, YEAR, 9001, "Тестреестров", "Олег")
    _ins(conn, YEAR, 9101, "Тестреестрова", "Анна", fmt="relay", stage="run", gender="F", team="Тест")
    service.sync(conn)
    assert (_pid(conn, YEAR, 9001), _pid(conn, YEAR, 9101, "run")) == before


def test_birthdate_from_applicant_and_conflict(conn):
    _ins(conn, YEAR, 9001, "Тестреестров", "Олег")
    pdb.upsert_applicants(conn, [Applicant("test-1", "Тестреестров", "Олег", "M", datetime.date(1980, 5, 1), "Красноярск",
                                           claimed_starts=1)])
    service.sync(conn)
    pid = _pid(conn, YEAR, 9001)
    assert pdb.get_person(conn, pid)["birthdate"] == datetime.date(1980, 5, 1)
    pdb.upsert_applicants(conn, [Applicant("test-2", "Тестреестров", "Олег", "M", datetime.date(1981, 5, 1), "Красноярск",
                                           claimed_starts=1)])
    service.sync(conn)
    kinds = [r["kind"] for r in pdb.list_reviews(conn, "open") if r["person_id"] == pid]
    assert "bd_conflict" in kinds


def test_import_applicants_csv(conn):
    _ins(conn, YEAR, 9001, "Тестреестров", "Олег", city="Томск")
    cols = ["tranid", "Date", "surname", "Name", "sex", "birthday", "city", "siberman_individual_starts"]
    body = ";".join(cols) + "\n" + ";".join(["test-9", "2026-10-01 10:00:00", "Тестреестров", "Олег",
                                             "Мужской", "02.03.1979", "Томск", "1"])
    report = service.import_applicants((chr(0xFEFF) + body).encode("utf-8"))
    assert report["people"] == 1 and report["sync"]["birthdates"] >= 1
    assert pdb.get_person(conn, _pid(conn, YEAR, 9001))["birthdate"] == datetime.date(1979, 3, 2)


def test_auto_sync_notices_renamed_relay_member(conn):
    _ins(conn, YEAR, 9101, "Тестреестрова", "Анна", fmt="relay", stage="swim", gender="F", team="Тест")
    service.sync(conn)
    old = _pid(conn, YEAR, 9101, "swim")
    service.auto_sync()                                   # запомнить отпечаток протокола
    assert service.auto_sync() is None                    # протокол не менялся — синхронизации нет
    conn.cursor().execute("UPDATE participants SET surname='Тестреестров', name='Пётр', gender='M' "
                          "WHERE race_year=%s AND bib='9101'", (YEAR,))
    assert service.auto_sync() is not None
    assert _pid(conn, YEAR, 9101, "swim") != old
    kinds = [r["kind"] for r in pdb.list_reviews(conn, "open") if r["race_year"] == YEAR]
    assert "relinked" in kinds


def test_auto_sync_skips_while_protocol_is_rewritten(conn):
    _ins(conn, YEAR, 9001, "Тестреестров", "Олег")
    other = get_siberman_connection()
    try:
        with service.protocol_rewrite(other):
            assert service.auto_sync() is None
            assert _pid(conn, YEAR, 9001) is None
    finally:
        other.close()
    assert service.auto_sync() is not None and _pid(conn, YEAR, 9001) is not None


def test_reassign_to_new_person_and_undo(conn):
    _ins(conn, YEAR, 9101, "Тестреестрова", "Анна", fmt="relay", stage="swim", gender="F", team="Тест")
    _ins(conn, Y2, 9102, "Тестреестрова", "Анна", fmt="relay", stage="run", gender="F", team="Тест")
    service.sync(conn)
    old = _pid(conn, YEAR, 9101, "swim")
    assert _pid(conn, Y2, 9102, "run") == old
    res = service.reassign([[Y2, "9102", "run"]], None, "test")
    assert _pid(conn, Y2, 9102, "run") == res["person_id"] != old
    card = service.person_card(res["person_id"])
    assert [p["manual"] for p in card["participations"]] == [1]
    service.undo(res["audit_id"], "test")
    assert _pid(conn, Y2, 9102, "run") == old
    assert pdb.get_person(conn, res["person_id"]) is None


def test_merge_and_undo(conn):
    _ins(conn, YEAR, 9101, "Тестреестрова", "Анна", fmt="relay", stage="swim", gender="F", team="Тест")
    _ins(conn, Y2, 9102, "Тестреестрова-Кузина", "Анна", fmt="relay", stage="run", gender="F", team="Тест")
    service.sync(conn)
    a, b = _pid(conn, YEAR, 9101, "swim"), _pid(conn, Y2, 9102, "run")
    assert a != b
    res = service.merge(b, a, "test")
    assert _pid(conn, Y2, 9102, "run") == a and pdb.get_person(conn, b) is None
    service.undo(res["audit_id"], "test")
    assert _pid(conn, Y2, 9102, "run") == b and pdb.get_person(conn, b)["surname"] == "Тестреестрова-Кузина"


def test_merge_refuses_two_individual_bibs(conn):
    _ins(conn, YEAR, 9001, "Тестреестров", "Иван")
    _ins(conn, Y2, 9002, "Тестреестров", "Иван")
    service.sync(conn)
    with pytest.raises(service.PersonsError):
        service.merge(_pid(conn, Y2, 9002), _pid(conn, YEAR, 9001), "test")


def test_undo_is_blocked_by_later_action_on_same_person(conn):
    _ins(conn, YEAR, 9001, "Тестреестров", "Олег")
    service.sync(conn)
    pid = _pid(conn, YEAR, 9001)
    first = service.set_birthdate(pid, datetime.date(1980, 1, 1), "test")
    second = service.set_birthdate(pid, datetime.date(1980, 1, 2), "test")
    with pytest.raises(service.PersonsError):
        service.undo(first["audit_id"], "test")
    service.undo(second["audit_id"], "test")
    service.undo(first["audit_id"], "test")
    assert pdb.get_person(conn, pid)["birthdate"] is None


def test_reviews_search_and_journal(conn):
    _ins(conn, YEAR, 9001, "Тестреестров", "Олег")
    _ins(conn, Y2, 9002, "Тестреестров", "Олег")
    _ins(conn, Y3, 9103, "Тестреестров", "Олег", fmt="relay", stage="bike", team="Тест")
    service.sync(conn)
    mine = [r for r in service.reviews("open") if r["participant"] and r["participant"]["year"] == Y3]
    assert [r["kind"] for r in mine] == ["namesake_candidate"]
    assert len(mine[0]["others"]) == 2 and mine[0]["title"]
    service.set_review_status(mine[0]["id"], "deferred", "test")
    assert all(r["id"] != mine[0]["id"] for r in service.reviews("open"))
    found = service.search("Тестреестров Олег")
    assert len(found) >= 3 and all("birthdate" in f for f in found)
    pid = _pid(conn, YEAR, 9001)
    service.set_birthdate(pid, datetime.date(1980, 1, 1), "test")
    assert any("Тестреестров" in j["summary"] for j in service.journal())


def test_keep_link_confirms_new_name(conn):
    _ins(conn, YEAR, 9101, "Тестреестрова", "Анна", fmt="relay", stage="swim", gender="F", team="Тест")
    service.sync(conn)
    pid = _pid(conn, YEAR, 9101, "swim")
    service.reassign([[YEAR, "9101", "swim"]], pid, "test")          # теперь привязка ручная
    conn.cursor().execute("UPDATE participants SET surname='Тестреестрова-Кузина' "
                          "WHERE race_year=%s AND bib='9101'", (YEAR,))
    service.sync(conn)

    def mine():
        return [r for r in service.reviews("open")
                if r["kind"] == "manual_name_changed" and r["participant"] and r["participant"]["year"] == YEAR]
    assert len(mine()) == 1 and _pid(conn, YEAR, 9101, "swim") == pid
    service.keep_link(mine()[0]["id"], "test")
    service.sync(conn)
    assert mine() == [] and _pid(conn, YEAR, 9101, "swim") == pid


def test_undo_merge_reopens_review(conn):
    _ins(conn, YEAR, 9001, "Тестреестров", "Олег")
    _ins(conn, Y2, 9002, "Тестреестров", "Олег")
    _ins(conn, Y3, 9103, "Тестреестров", "Олег", fmt="relay", stage="bike", team="Тест")
    service.sync(conn)
    r = [x for x in service.reviews("open") if x["participant"] and x["participant"]["year"] == Y3][0]
    source, target = r["person"]["id"], r["others"][0]["id"]
    res = service.merge(source, target, "test", review_id=r["id"])
    assert all(x["id"] != r["id"] for x in service.reviews("open"))
    service.undo(res["audit_id"], "test")
    back = [x for x in service.reviews("open") if x["id"] == r["id"]]
    assert back and back[0]["person"]["id"] == source
    assert _pid(conn, Y3, 9103, "bike") == source


def test_keep_link_is_undoable_and_blocks_earlier_undo(conn):
    _ins(conn, YEAR, 9101, "Тестреестрова", "Анна", fmt="relay", stage="swim", gender="F", team="Тест")
    service.sync(conn)
    pid = _pid(conn, YEAR, 9101, "swim")
    first = service.reassign([[YEAR, "9101", "swim"]], pid, "test")
    conn.cursor().execute("UPDATE participants SET surname='Тестреестрова-Кузина' "
                          "WHERE race_year=%s AND bib='9101'", (YEAR,))
    service.sync(conn)
    rv = [r for r in service.reviews("open") if r["kind"] == "manual_name_changed"
          and r["participant"] and r["participant"]["year"] == YEAR][0]
    kept = service.keep_link(rv["id"], "test")
    with pytest.raises(service.PersonsError):
        service.undo(first["audit_id"], "test")
    service.undo(kept["audit_id"], "test")
    link = pdb.links_for_keys(conn, [(YEAR, "9101", "swim")])[(YEAR, "9101", "swim")]
    assert link["name_key"] == "тестреестрова анна"
    assert any(r["id"] == rv["id"] for r in service.reviews("open"))


def test_finish_counts_on_archive_match_name_based(conn):
    """После синхронизации реестра «N-й финиш» в архиве такой же, как при подсчёте по ФИ
    (в архиве нет тёзок-личников). Различия печатаются без ФИО — год и номер."""
    from src.siberman.db import get_finished_years_by_name, get_results_for_year
    from src.siberman.finish_counts import get_finish_count
    service.sync(conn)
    by_name = get_finished_years_by_name(conn)
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT race_year FROM participants WHERE race_year < 2090 ORDER BY race_year")
    diffs = []
    for (year,) in cur.fetchall():
        for p in get_results_for_year(conn, year)["individual"]:
            if p["finish_count"] != get_finish_count(p["surname"], p["name"], year, by_name):
                diffs.append((year, p["bib"]))
    assert diffs == []


def test_admin_api_requires_auth_and_works(conn):
    from fastapi.testclient import TestClient
    from app import app
    from src.core.auth import api_require_auth
    client = TestClient(app)
    assert client.get("/api/siberman/admin/people/reviews").status_code == 401
    _ins(conn, YEAR, 9001, "Тестреестров", "Олег")
    service.sync(conn)
    app.dependency_overrides[api_require_auth] = lambda: "test"
    try:
        r = client.get("/api/siberman/admin/people/search", params={"q": "Тестреестров"})
        assert r.status_code == 200 and r.json()
        pid = _pid(conn, YEAR, 9001)
        assert client.get(f"/api/siberman/admin/people/{pid}").json()["person"]["id"] == pid
        r = client.post(f"/api/siberman/admin/people/{pid}/birthdate", json={"birthdate": "1980-01-01"})
        assert r.status_code == 200
        assert client.post("/api/siberman/admin/people/merge", json={"source_id": pid, "target_id": pid}).status_code == 409
        assert client.get("/api/siberman/admin/people/journal").status_code == 200
    finally:
        app.dependency_overrides.clear()
