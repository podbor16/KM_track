"""
Заявки Siberman на локальной БД siberman: приём (вебхук/CSV/спул), статусы с журналом, публичный список без
контактов, Excel, маршруты. Год 2090–2099 (от PID), чистится до и после.
"""
import datetime
import io
import os

import openpyxl
import pytest

from app import app
from src.config import settings
from src.core.auth import api_require_auth
from src.siberman.db import get_siberman_connection
from src.siberman.entries import service
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
    service.clear_cache()
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


def test_export_xlsx(entries):
    service.set_comment(YEAR, entries["Ёлкина"], "уточнить ДР", "u")
    ws = openpyxl.load_workbook(io.BytesIO(service.export_xlsx(YEAR))).active
    rows = [[c.value for c in r] for r in ws.iter_rows()]
    assert rows[0][:4] == ["№", "Дата заявки", "Фамилия Имя", "Формат участия"]
    assert [r[2] for r in rows[1:]] == ["Яковлев Тест", "Ёлкина Тест", "Абрамов Тест"]
    assert "уточнить ДР" in rows[2] and "⌛️ на изучении" in rows[1]
