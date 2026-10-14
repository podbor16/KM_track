"""
Вероятность попасть в победители — Monte Carlo от текущего состояния жеребьёвки.

Шарик с весом = шансы, после выигрыша остальные шарики человека не участвуют =
взвешенная выборка людей без возвращения (Efraimidis–Spirakis: ключ random()**(1/вес),
по убыванию). Ещё не объявленные wild card — гарантированные места (сами в результат
не попадают: публично их нет до объявления).

Без numpy (решение 2026-10-14): ~0,5–0,8 с на 240 участников × 5000 прогонов, считается
в фоне раз на изменение. Выборка — только в _weighted_order (заменяема на numpy).
"""
import random

from src.siberman.draw.logic import category_of, kind_of

REQUIRED_CONFIG = ("capacity_men", "capacity_women", "capacity_relay", "quota_repeat_men",
                   "quota_repeat_women", "quota_novice_men", "quota_novice_women")
GENDER_CATEGORY = {"M": "men", "F": "women"}


def _weighted_order(people: list[tuple[int, int]], rnd) -> list[int]:
    return [pid for _, pid in sorted(((rnd() ** (1.0 / w), pid) for pid, w in people), reverse=True)]


def win_probabilities(apps: list[dict], lists: dict, config: dict, current_round: int,
                      sims: int = 5000, seed=None) -> dict[int, float] | None:
    """{applicant_id: P(победитель)} для ещё не вытянутых не-wild card; None — места/квоты не заданы."""
    if any(config.get(k) is None for k in REQUIRED_CONFIG):
        return None
    rnd = random.Random(seed).random
    by_id = {a["id"]: a for a in apps}
    cap = {c: config[f"capacity_{c}"] for c in ("men", "women", "relay")}
    quota = {f"{k}_{g}": config[f"quota_{k}_{GENDER_CATEGORY[g]}"] for k in ("repeat", "novice") for g in ("M", "F")}
    placed = {r["applicant_id"] for rows in lists.values() for r in rows}

    count0 = {c: len(lists[c]) for c in cap}
    kind0 = dict.fromkeys(quota, 0)
    for c in ("men", "women"):
        for r in lists[c]:
            a = by_id[r["applicant_id"]]
            kind0[f"{kind_of(a)}_{a['gender']}"] += 1
    for a in apps:
        if a["is_wildcard"] and a["id"] not in placed:
            c = category_of(a)
            count0[c] += 1
            if c != "relay":
                kind0[f"{kind_of(a)}_{a['gender']}"] += 1

    undrawn = [a for a in apps if a["id"] not in placed and not a["is_wildcard"]]
    relay = [(a["id"], a["chances"]) for a in undrawn if a["pool"] == "relay"]
    by_kind = {k: [(a["id"], a["chances"]) for a in undrawn if a["pool"] == k] for k in ("repeat", "novice")}
    wins = dict.fromkeys((a["id"] for a in undrawn), 0)

    for _ in range(sims):
        count, kinds = dict(count0), dict(kind0)
        if current_round <= 1:
            free = max(0, cap["relay"] - count["relay"])
            for pid in _weighted_order(relay, rnd)[:free]:
                wins[pid] += 1
        leftovers: list[int] = []
        for round_no, kind in ((2, "repeat"), (3, "novice")):
            people = by_kind[kind]
            if current_round > round_no:
                leftovers.extend(pid for pid, _ in people)
                continue
            for pid in _weighted_order(people, rnd):
                g = by_id[pid]["gender"]
                c = GENDER_CATEGORY[g]
                if kinds[f"{kind}_{g}"] < quota[f"{kind}_{g}"] and count[c] < cap[c]:
                    wins[pid] += 1
                    kinds[f"{kind}_{g}"] += 1
                    count[c] += 1
                else:
                    leftovers.append(pid)
        if count["men"] >= cap["men"] and count["women"] >= cap["women"]:
            continue
        for pid in _weighted_order([(pid, by_id[pid]["chances"]) for pid in leftovers], rnd):
            c = GENDER_CATEGORY[by_id[pid]["gender"]]
            if count[c] < cap[c]:
                wins[pid] += 1
                count[c] += 1
    return {pid: w / sims for pid, w in wins.items()}
