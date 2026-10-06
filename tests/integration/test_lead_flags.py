"""
Флаги заявок на реальной БД (локальный снимок, .env.local): триггеры подозрительного ФИО
и «Имя в порядке», основная заявка / дубли, «Сделать основной», контакты карточки не
затираются пересчётом. Тестовые заявки — на событии 2099 года, убираются после теста.
Без миграции lead_flags_main_name_ok (нет колонки name_ok) — skip.
"""

import pytest

from src.analytics.db_pool import get_pooled_connection
from src.analytics.db_results import recompute_duplicates, set_lead_main, set_lead_name_ok

EV, SUR = "Тест флагов", "Тестфлагов"


@pytest.fixture
def db():
    conn = get_pooled_connection()
    if not conn:
        pytest.skip("Нет локальной БД")
    cur = conn.cursor(dictionary=True)
    cur.execute("SHOW COLUMNS FROM leads LIKE 'name_ok'")
    if not cur.fetchone():
        conn.close()
        pytest.skip("Миграция lead_flags_main_name_ok не применена")

    def cleanup():
        cur.execute("SELECT DISTINCT client_id FROM leads WHERE event_name = %s", (EV,))
        ids = [r["client_id"] for r in cur.fetchall()]
        cur.execute("DELETE FROM leads WHERE event_name = %s", (EV,))
        if ids:
            cur.execute(f"DELETE FROM clients WHERE id IN ({','.join(map(str, ids))})")
        cur.execute("DELETE FROM events WHERE event_name = %s", (EV,))
        conn.commit()

    cleanup()
    yield conn, cur
    cleanup()
    cur.close()
    conn.close()


def add(cur, name, created, surname=SUR, dist="5 км", phone="+70000000000"):
    cur.execute("""INSERT INTO leads (surname, name, sex, city, club, birthday, email, phone, event_name, event_distance,
                   event_year, products, amount, client_id, event_id, is_duplicate, status, is_new, is_new_event,
                   is_name_suspicious, created_at)
                   VALUES (%s, %s, 'Мужчина', '', '', '1990-01-01', 'flags@test.ru', %s, %s, %s, 2099, '', 0, 0, 0,
                           0, 0, 0, 0, 0, %s)""", (surname, name, phone, EV, dist, created))
    return cur.lastrowid


def flags(cur, lead_id):
    cur.execute("SELECT is_name_suspicious, name_ok, is_duplicate, dup_main FROM leads WHERE id = %s", (lead_id,))
    return cur.fetchone()


def test_suspicious_name_computed_by_db_and_name_ok(db):
    conn, cur = db
    latin = add(cur, "Ivan", "2026-01-01 10:00:00")
    space = add(cur, "Иван Петрович", "2026-01-01 10:00:00", dist="10 км")
    clean = add(cur, "Пётр", "2026-01-01 10:00:00", dist="21.1 км")         # «ё» → «е» до проверки
    conn.commit()
    assert flags(cur, latin)["is_name_suspicious"] == 1
    assert flags(cur, space)["is_name_suspicious"] == 1                    # пробел — всегда подозрительно
    assert flags(cur, clean)["is_name_suspicious"] == 0

    assert set_lead_name_ok(latin)
    assert flags(cur, latin)["is_name_suspicious"] == 0
    cur.execute("UPDATE leads SET city = 'Красноярск' WHERE id = %s", (latin,))       # правка не ФИО — отметка жива
    conn.commit()
    assert flags(cur, latin) == {"is_name_suspicious": 0, "name_ok": 1, "is_duplicate": 0, "dup_main": 0}
    cur.execute("UPDATE leads SET name = 'Ivan2' WHERE id = %s", (latin,))           # смена ФИО — сброс
    conn.commit()
    assert flags(cur, latin)["name_ok"] == 0 and flags(cur, latin)["is_name_suspicious"] == 1
    assert not set_lead_name_ok(10 ** 12)


def test_latest_lead_is_main_others_duplicates(db):
    conn, cur = db
    old = add(cur, "Дубль", "2026-01-01 10:00:00")
    mid = add(cur, "Дубль", "2026-01-02 10:00:00")
    new = add(cur, "Дубль", "2026-01-03 10:00:00")
    other_dist = add(cur, "Дубль", "2026-01-04 10:00:00", dist="10 км")
    conn.commit()
    cur.execute("SELECT client_id FROM leads WHERE id = %s", (old,))
    client = cur.fetchone()["client_id"]
    recompute_duplicates(cur, [client])
    conn.commit()
    assert [flags(cur, i)["is_duplicate"] for i in (old, mid, new, other_dist)] == [1, 1, 0, 0]

    set_lead_main(old)                                                     # ручной выбор важнее даты
    assert [flags(cur, i)["is_duplicate"] for i in (old, mid, new)] == [0, 1, 1]
    assert flags(cur, old)["dup_main"] == 1
    assert recompute_duplicates(cur, [client]) == 0                        # выбор переживает пересчёт
    assert set_lead_main(10 ** 12) is None


def test_lead_with_bib_is_main_and_card_contacts_kept(db):
    conn, cur = db
    with_bib = add(cur, "Номер", "2026-01-01 10:00:00", phone="+71111111111")
    later = add(cur, "Номер", "2026-01-02 10:00:00", phone="+72222222222")
    cur.execute("UPDATE leads SET start_number = 777 WHERE id = %s", (with_bib,))
    cur.execute("SELECT client_id FROM leads WHERE id = %s", (with_bib,))
    client = cur.fetchone()["client_id"]
    cur.execute("UPDATE clients SET phone = 'CARD', email = 'card@test.ru' WHERE id = %s", (client,))
    conn.commit()
    recompute_duplicates(cur, [client])
    conn.commit()
    assert flags(cur, with_bib)["is_duplicate"] == 0 and flags(cur, later)["is_duplicate"] == 1
    # пересчёт флага — UPDATE заявки; trg_leads_after_update больше не переписывает контакты карточки
    cur.execute("SELECT phone, email FROM clients WHERE id = %s", (client,))
    assert cur.fetchone() == {"phone": "CARD", "email": "card@test.ru"}
    cur.execute("UPDATE leads SET phone = '+73333333333' WHERE id = %s", (later,))  # контакт сменился — переносится
    conn.commit()
    cur.execute("SELECT phone FROM clients WHERE id = %s", (client,))
    assert cur.fetchone()["phone"] == "+73333333333"


def test_refund_out_of_duplicates_site_and_bibs(db, client):
    from src.analytics import bibs
    from src.analytics.db_results import set_lead_refund
    conn, cur = db
    cur.execute("SHOW COLUMNS FROM leads LIKE 'refund'")
    if not cur.fetchone():
        pytest.skip("Миграция lead_refund не применена")
    old = add(cur, "Возврат", "2026-01-01 10:00:00")
    new = add(cur, "Возврат", "2026-01-02 10:00:00")
    conn.commit()
    assert set_lead_refund(new, True)                         # вернули деньги за свежую заявку
    cur.execute("SELECT id, refund, is_duplicate FROM leads WHERE id IN (%s, %s) ORDER BY id", (old, new))
    assert [tuple(r.values()) for r in cur.fetchall()] == [(old, 0, 0), (new, 1, 0)]   # основная — оставшаяся
    runners = client.get("/api/registered-runners", params={"event_name": EV, "event_year": 2099}).json()["runners"]
    assert [r["lead_id"] for r in runners] == [old]           # возврат скрыт с сайта
    assert [l["id"] for l in bibs.load_leads(conn, EV, 2099)] == [old]   # и без номера
    assert set_lead_refund(new, False)
    cur.execute("SELECT is_duplicate FROM leads WHERE id IN (%s, %s) ORDER BY id", (old, new))
    assert [r["is_duplicate"] for r in cur.fetchall()] == [1, 0]


def test_delete_lead_logged_and_main_recomputed(db):
    import json
    from src.analytics.db_results import delete_lead
    conn, cur = db
    old = add(cur, "Удаление", "2026-01-01 10:00:00")
    new = add(cur, "Удаление", "2026-01-02 10:00:00")
    conn.commit()
    cur.execute("SELECT client_id FROM leads WHERE id = %s", (old,))
    recompute_duplicates(cur, [cur.fetchone()["client_id"]])
    conn.commit()
    assert flags(cur, old)["is_duplicate"] == 1
    try:
        assert delete_lead(new, "pytest")
        assert flags(cur, new) is None
        assert flags(cur, old)["is_duplicate"] == 0          # единственная — основная
        cur.execute("SELECT details FROM dq_actions WHERE action = 'delete_lead' AND finding_key = %s", (f"lead:{new}",))
        assert json.loads(cur.fetchone()["details"])["name"] == "Удаление"
        assert not delete_lead(10 ** 12, "pytest")
    finally:
        cur.execute("DELETE FROM dq_actions WHERE action = 'delete_lead' AND done_by = 'pytest'")
        conn.commit()
