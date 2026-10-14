from src.siberman.draw.logic import build_lists
from src.siberman.draw.simulation import win_probabilities


def app(i, pool="novice", gender="M", fmt="individual", wc=False, starts=0, chances=1):
    return {"id": i, "surname": f"Ф{i}", "name": "И", "city": "Г", "format": fmt,
            "gender": gender if fmt == "individual" else None, "pool": pool, "is_wildcard": wc,
            "starts_individual": starts, "chances": chances, "payment_status": "none"}


def cfg(men=1, women=1, relay=1, rep_m=0, rep_f=0, nov_m=0, nov_f=0):
    return {"capacity_men": men, "capacity_women": women, "capacity_relay": relay,
            "quota_repeat_men": rep_m, "quota_repeat_women": rep_f,
            "quota_novice_men": nov_m, "quota_novice_women": nov_f}


def probs(apps, config, rnd=0, picks=(), sims=4000, seed=7):
    lists = build_lists({a["id"]: a for a in apps}, list(picks), config)
    return win_probabilities(apps, lists, config, rnd, sims=sims, seed=seed)


def test_none_until_config_complete():
    assert probs([app(1)], {"capacity_men": 1}) is None


def test_enough_places_everyone_wins():
    p = probs([app(1), app(2)], cfg(men=5))
    assert p == {1: 1.0, 2: 1.0}


def test_weights_three_to_one():
    p = probs([app(1, chances=3), app(2, chances=1)], cfg(men=1))
    assert abs(p[1] - 0.75) < 0.03 and abs(p[2] - 0.25) < 0.03


def test_unrevealed_wildcard_takes_place():
    p = probs([app(1, "wildcard", wc=True), app(2)], cfg(men=1))
    assert p == {2: 0.0}          # wild card не в результате (скрыт), но место занял


def test_repeat_quota_then_round4():
    # 1 место у мужчин уходит повторному по квоте; новичок выигрывает только при 2 местах
    apps = [app(1, "repeat", starts=1), app(2)]
    assert probs(apps, cfg(men=1, rep_m=1)) == {1: 1.0, 2: 0.0}
    assert probs(apps, cfg(men=2, rep_m=1)) == {1: 1.0, 2: 1.0}


def test_relay_only_until_round1():
    apps = [app(1, "relay", fmt="relay"), app(2, "relay", fmt="relay")]
    assert probs(apps, cfg(relay=1), rnd=1)[1] > 0
    assert probs(apps, cfg(relay=1), rnd=2) == {1: 0.0, 2: 0.0}


def test_reproducible_with_seed():
    apps = [app(i, chances=i % 4 + 1) for i in range(1, 30)]
    assert probs(apps, cfg(men=5)) == probs(apps, cfg(men=5))


def test_unrevealed_repeat_wildcard_eats_repeat_quota():
    apps = [app(1, "wildcard", wc=True, starts=1), app(2, "repeat", starts=1), app(3)]
    # квота повторных занята wild card: повторник идёт в общий 4-й раунд наравне с новичком (без wild card было бы 1.0)
    p = probs(apps, cfg(men=2, rep_m=1))
    assert abs(p[2] - 0.5) < 0.04 and abs(p[3] - 0.5) < 0.04


def test_round3_repeaters_already_gone():
    apps = [app(1, "repeat", starts=1), app(2), app(3)]
    p = probs(apps, cfg(men=1, nov_m=0), rnd=3, sims=4000)
    assert all(abs(v - 1 / 3) < 0.04 for v in p.values())


def test_women_weights():
    p = probs([app(1, gender="F", chances=3), app(2, gender="F")], cfg(women=1))
    assert abs(p[1] - 0.75) < 0.04 and abs(p[2] - 0.25) < 0.04


def test_zero_capacity_nobody_wins():
    assert probs([app(1), app(2)], cfg(men=0)) == {1: 0.0, 2: 0.0}
