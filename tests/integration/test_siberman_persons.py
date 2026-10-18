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
                "WHERE l.person_id IS NULL")


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
