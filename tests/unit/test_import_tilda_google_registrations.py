import datetime
from collections import Counter

import pytest

from scripts.import_tilda_google_registrations import (
    distance_from_sku, is_fio_glued, merge_year, normalize_sex, plan, _contact_key, _fio_key, _key,
)

BATCH = datetime.datetime(2025, 1, 21, 4, 50)
IS_BATCH = lambda db: db["created_at"] == BATCH


@pytest.mark.parametrize("product, expected", [
    ("5 км Ночной забег (night5y-2025, Выберите категорию", "5 км"),
    ("2 км Забег-спутник (night2walkb-2025, Выберите", "2 км"),
    ("Полумарафон (zhara21-2026, ...", "21.1 км"),
    ("Слот на участие в Женской семерке на 7 км (Girlrun2022, Выберите", "7 км"),
    ("7 км Женская семерка (girl7, Выберите категорию", "7 км"),
    ("1", None),
    (None, None),
])
def test_distance_from_sku(product, expected):
    assert distance_from_sku(product) == expected


@pytest.mark.parametrize("raw, expected", [
    ("жен", "Женщина"), ("Ж", "Женщина"), ("Женский", "Женщина"), ("Женщина", "Женщина"),
    ("муж", "Мужчина"), ("М", "Мужчина"), ("мужской", "Мужчина"),
    ("1", ""), (None, ""),
])
def test_normalize_sex(raw, expected):
    assert normalize_sex(raw) == expected


def rec(surname="Иванов", name="Иван", birthday="1990-01-01", distance="5 км", date=None, amount=0.0,
        email="ivan@example.com", year=2025):
    return {"surname": surname, "name": name, "birthday": birthday, "event_name": "Ночной забег",
            "event_year": year, "event_distance": distance, "registered_at": date, "amount": amount,
            "email": email}


def db_row(id_, created_at=BATCH, amount=0, **kw):
    r = rec(**kw)
    return {**r, "id": id_, "client_id": id_, "created_at": created_at, "amount": amount}


def index(rows):
    by_key, by_fio, by_contact = {}, {}, {}
    for r in rows:
        by_key.setdefault(_key(r), []).append(r)
        by_fio.setdefault(_fio_key(r), []).append(r)
        if _contact_key(r):
            by_contact.setdefault(_contact_key(r), []).append(r)
    return by_key, by_fio, by_contact


def test_merge_year_takes_date_and_amount_from_tilda_then_neighbor():
    d1, d2 = datetime.datetime(2025, 1, 5), datetime.datetime(2025, 2, 1)
    google = [rec(date=d1, surname="А"), rec(surname="Б"), rec(surname="В")]
    tilda = [rec(surname="Б", date=d2, amount=1890.0), rec(surname="Г", date=d2)]
    stats = Counter()
    out = merge_year(google, tilda, stats)
    assert [r["surname"] for r in out] == ["А", "Б", "В", "Г"]
    assert out[1]["registered_at"] == d2 and out[1]["amount"] == 1890.0
    assert out[2]["registered_at"] == d2  # соседняя строка выше
    assert stats["date_from_tilda"] == 1 and stats["tilda_only"] == 1


def test_plan_updates_all_batch_duplicates_and_leaves_webhook_rows():
    d = datetime.datetime(2025, 2, 1)
    db = [db_row(1), db_row(2), db_row(3, created_at=datetime.datetime(2024, 5, 1), amount=1890, surname="Петров")]
    ins, upd, sus = plan([rec(date=d, amount=500.0), rec(surname="Петров", date=d, amount=500.0)], *index(db), IS_BATCH)
    assert ins == [] and sus == []
    assert sorted((u[0]["id"], u[1], u[2]) for u in upd) == [(1, d, 500.0), (2, d, 500.0)]


def test_plan_matches_glued_fio_by_contact_instead_of_inserting():
    glued = rec(surname="Иван Иванов", name="Иван Иванов", date=datetime.datetime(2025, 3, 1))
    ins, upd, sus = plan([glued], *index([db_row(7)]), IS_BATCH)
    assert ins == [] and len(sus) == 1 and upd[0][0]["id"] == 7
    assert is_fio_glued(glued)


def test_plan_inserts_unknown_person():
    ins, upd, _ = plan([rec(surname="Новый", email="new@example.com")], *index([db_row(1)]), IS_BATCH)
    assert len(ins) == 1 and upd == []


def test_distance_from_sku_case_insensitive_and_suffix_after_year():
    assert distance_from_sku("5 км Весна (Vesna5-2025y, Выберите категорию") == "5 км"
    assert distance_from_sku("2 км Северная ходьба (Vesna2w-2025, ...") == "2 км"
