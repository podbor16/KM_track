from src.siberman.draw.logic import (
    build_lists, category_of, check_pick, in_round_pool, placement, round_counters,
)


def app(i, pool="novice", gender="M", fmt="individual", wc=False, starts=0, chances=1, pay="none"):
    return {"id": i, "surname": f"Ф{i}", "name": "И", "city": "Г", "format": fmt,
            "gender": gender if fmt == "individual" else None, "pool": pool, "is_wildcard": wc,
            "starts_individual": starts, "chances": chances, "payment_status": pay}


def pick(i, applicant_id, category="men", rnd=4, pos=None, cancelled=False):
    return {"id": i, "applicant_id": applicant_id, "round": rnd, "category": category,
            "position_key": pos or i, "created_at": None, "cancelled_at": "x" if cancelled else None}


CFG = {"capacity_men": 2, "capacity_women": 1, "capacity_relay": 1}


def test_category_of():
    assert category_of(app(1)) == "men"
    assert category_of(app(1, gender="F")) == "women"
    assert category_of(app(1, fmt="relay", pool="relay")) == "relay"


def test_round_pools():
    wc, rel, rep, nov = app(1, "wildcard", wc=True), app(2, "relay", fmt="relay"), app(3, "repeat", starts=1), app(4)
    assert [in_round_pool(a, 0) for a in (wc, rel, rep, nov)] == [True, False, False, False]
    assert [in_round_pool(a, 1) for a in (wc, rel, rep, nov)] == [False, True, False, False]
    assert [in_round_pool(a, 2) for a in (wc, rel, rep, nov)] == [False, False, True, False]
    assert [in_round_pool(a, 3) for a in (wc, rel, rep, nov)] == [False, False, False, True]
    assert [in_round_pool(a, 4) for a in (wc, rel, rep, nov)] == [False, False, True, True]


def test_build_lists_order_sections_and_cancelled():
    apps = {i: app(i) for i in range(1, 5)}
    picks = [pick(1, 1), pick(2, 2, cancelled=True), pick(3, 3), pick(4, 4), pick(5, 2, pos=1)]
    lists = build_lists(apps, picks, CFG)
    men = lists["men"]
    # исправление (position_key=1) встаёт на место исходной записи, отменённая не учитывается
    assert [(r["position"], r["applicant_id"], r["section"]) for r in men] == [
        (1, 1, "winner"), (2, 2, "winner"), (3, 3, "waitlist"), (4, 4, "waitlist")]


def test_sections_unknown_without_capacity():
    lists = build_lists({1: app(1)}, [pick(1, 1)], {})
    assert lists["men"][0]["section"] is None


def test_check_pick_reasons():
    apps = {1: app(1), 2: app(2, "relay", fmt="relay")}
    lists = build_lists(apps, [pick(1, 1)], CFG)
    assert check_pick(apps[1], 4, lists) == "уже вытянут — Мужчины №1"
    assert check_pick(apps[2], 4, lists) == "не в этом раунде: эстафета"
    assert check_pick(apps[2], 1, lists) is None
    assert placement(lists, 1) == ("men", 1) and placement(lists, 2) is None


def test_round_counters():
    apps = [app(1, "wildcard", wc=True, starts=2), app(2, "repeat", starts=1, chances=3),
            app(3, gender="F"), app(4, chances=2)]
    lists = build_lists({a["id"]: a for a in apps}, [pick(1, 1, rnd=0), pick(2, 3, "women", rnd=3)], CFG)
    c = round_counters(apps, lists, 4)
    assert c["categories"] == {"men": 1, "women": 1, "relay": 0}
    assert c["kinds"] == {"repeat_M": 1, "repeat_F": 0, "novice_M": 0, "novice_F": 1}
    assert (c["pool_people"], c["pool_balls"]) == (2, 5)
