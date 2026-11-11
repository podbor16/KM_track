"""km_order_parts (migrations/order_parts.sql) на локальной БД (.env.local): разбор состава заказа на слот / допы / взнос.
Тестовые данные — событие 2099 «Тест заказов <суффикс>», фамилия «Тестзаказов<суффикс>», убираются после теста."""
import uuid

import pytest

from src.analytics.db_pool import get_pooled_connection

RUN = uuid.uuid4().hex[:6].translate(str.maketrans("0123456789abcdef", "бвгджзклмнпрстфх"))
EV, SUR = f"Тест заказов {RUN}", f"Тестзаказов{RUN}"


@pytest.fixture
def db():
    conn = get_pooled_connection()
    if not conn:
        pytest.skip("Нет локальной БД")
    cur = conn.cursor(dictionary=True)
    cur.execute("SHOW PROCEDURE STATUS WHERE Db = DATABASE() AND Name = 'refresh_order_parts'")
    if not cur.fetchall():
        pytest.fail("Нет процедуры refresh_order_parts — примените migrations/order_parts.sql к локальной БД")

    def cleanup():
        cur.execute("SELECT id FROM events WHERE event_name = %s", (EV,))
        evs = [r["id"] for r in cur.fetchall()]
        if evs:
            ph = ",".join(map(str, evs))
            cur.execute(f"DELETE FROM leads WHERE event_id IN ({ph})")
            cur.execute(f"DELETE FROM events WHERE id IN ({ph})")
        cur.execute("DELETE FROM clients WHERE surname = %s", (SUR,))
        conn.commit()

    cleanup()
    cur.execute("INSERT INTO events (event_name, event_distance, event_year, event_date) VALUES (%s, 7, 2099, '2099-12-06')", (EV,))
    ev = cur.lastrowid

    def lead(name, products, amount, discount=0):
        cur.execute("""INSERT INTO leads (surname, name, sex, city, birthday, phone, email, event_name, event_distance,
                       event_year, products, amount, discount, client_id, event_id, start_number, created_at)
                       VALUES (%s, %s, 'Мужчина', '', '1990-01-01', '+70000000097', 'op@test.ru', %s, '7 км',
                               2099, %s, %s, %s, 0, %s, NULL, '2026-01-01 10:00:00')""",
                    (SUR, name, EV, products, amount, discount, ev))
        return cur.lastrowid

    yield cur, lead
    cleanup()
    cur.execute("CALL refresh_order_parts()")
    conn.commit()
    conn.close()


def _parts(cur, lead_id):
    cur.execute("CALL refresh_order_parts()")
    cur.execute("SELECT * FROM km_order_parts WHERE lead_id = %s", (lead_id,))
    return cur.fetchone()


def test_addons_charity_and_slot(db):
    cur, lead = db
    lid = lead("Иван", "7 км Снежная семерка 2099 (snow7-2099, Выберите категорию: Основная категория, "
                       "Гравировка на медали + 670 р.: Добавить, Бафф + 670 р: Не нужно, Пояс для номера + 670 р.: Не нужно, "
                       "Благотворительный взнос в фонд «Счастливые дети»: 500 рублей) x 1 ≡ 2860", 2860)
    p = _parts(cur, lid)
    assert (float(p["gross"]), float(p["addons"]), float(p["charity"]), float(p["slot"])) == (2860, 670, 500, 1690)
    assert p["complete"] == 1


def test_tshirt_size_counts_as_chosen_and_discount_kept(db):
    cur, lead = db
    lid = lead("Петр", "21.1 км (zhara2099-21, Выберите категорию: Основная категория, Футболка + 1490 рублей: 48, "
                       "Баф + 470 рублей: Не нужен, Благотворительный взнос в фонд «Счастливые дети»: Не нужно) - 1x3780 ≡ 3780",
               378, 3402)
    p = _parts(cur, lid)
    assert float(p["gross"]) == 3780 and float(p["discount"]) == 3402 and float(p["paid"]) == 378
    assert (float(p["addons"]), float(p["charity"]), float(p["slot"])) == (149, 0, 229)


def test_promo_discount_spread_over_slot_addons_and_charity(db):
    cur, lead = db
    lid = lead("Семен", "7 км Снежная семерка 2099 (snow7-2099, Выберите категорию: Основная категория, "
                        "Гравировка на медали + 670 р.: Добавить, "
                        "Благотворительный взнос в фонд «Счастливые дети»: 500 рублей) x 1 ≡ 2860", 1430, 1430)
    p = _parts(cur, lid)
    assert (float(p["addons"]), float(p["charity"]), float(p["slot"])) == (335, 250, 845)


def test_parts_sum_to_paid_when_price_differs_from_amount(db):
    cur, lead = db
    lid = lead("Глеб", "10 км (xtrail2099-10, Футболка + 470 рублей: 50, "
                       "Благотворительный взнос в фонд «Счастливые дети»: 500 рублей) x 1 ≡ 3260", 500)
    p = _parts(cur, lid)
    assert float(p["gross"]) == 3260
    assert (float(p["addons"]), float(p["charity"])) == (72.09, 76.69)
    assert p["slot"] + p["addons"] + p["charity"] == 500


def test_truncated_products_go_to_slot_and_flagged(db):
    cur, lead = db
    lid = lead("Олег", "5 км Ночной забег 2099 (night5-2099", 1990)
    p = _parts(cur, lid)
    assert float(p["gross"]) == 1990 and float(p["addons"]) == 0 and float(p["slot"]) == 1990
    assert p["complete"] == 0
