"""mask_runner — публичный вид участника без согласия на публикацию ПД."""
from src.krasmarafon.services.public_pd import PLACEHOLDER, mask_runner

ROW = {"surname": "Иванов", "name": "Иван", "full_name": "Иванов Иван", "birthday": "1990-01-01",
       "client_id": 5, "start_number": 101, "sex": "Мужчина", "category": "М", "rank_absolute": 3}


def test_refused_hides_name_birthday_card():
    out = mask_runner(ROW, True)
    assert (out["surname"], out["name"], out["full_name"]) == (PLACEHOLDER, "", PLACEHOLDER)
    assert out["birthday"] is None and out["client_id"] is None
    assert (out["start_number"], out["sex"], out["category"], out["rank_absolute"]) == (101, "Мужчина", "М", 3)


def test_not_refused_returns_row_as_is():
    assert mask_runner(ROW, False) is ROW
    assert mask_runner(ROW, None) is ROW


def test_source_row_not_modified_and_missing_keys_not_added():
    mask_runner(ROW, True)
    assert ROW["surname"] == "Иванов"
    assert mask_runner({"surname": "Петров", "time": "20:00"}, 1) == {"surname": PLACEHOLDER, "time": "20:00"}


def test_placeholder_text():
    assert PLACEHOLDER == "Спортсмен"
