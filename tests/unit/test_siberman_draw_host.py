from src.siberman.draw.service import host_token, host_token_ok, match_person


def test_host_token_is_stable_per_year():
    t = host_token(2028)
    assert len(t) == 32 and t == host_token(2028) and t != host_token(2029)
    assert host_token_ok(2028, t)
    assert not host_token_ok(2028, t[:-1] + ("0" if t[-1] != "0" else "1"))
    assert not host_token_ok(2029, t) and not host_token_ok(2028, "")


def test_match_person_both_orders_and_namesakes():
    by_key = {"иванов иван": 5, "петров петр": None}
    assert match_person({"surname": "Иванов", "name": "Иван"}, by_key) == 5
    assert match_person({"surname": "Иван", "name": "Иванов"}, by_key) == 5        # ФИ наоборот
    assert match_person({"surname": "Петров", "name": "Пётр"}, by_key) is None     # тёзки в реестре
    assert match_person({"surname": "Сидоров", "name": "Сидор"}, by_key) is None
