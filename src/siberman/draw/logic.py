"""
Чистая логика жеребьёвки: пулы раундов, списки зачётов, проверка вытягивания, счётчики.

Раунды (ответы пользователя 2026-10-13): 0 — wild card (красные шарики), 1 — эстафеты
(синие), 2 — повторные личники (чёрные, ёмкость 1), 3 — новички (чёрные, ёмкость 2),
4 — все оставшиеся личники (обе ёмкости вместе). Мужчины и женщины одного цвета —
зачёт определяется по полу. Порядок в зачёте — порядок вытягивания (position_key);
№1…мест — «победитель», дальше — «лист ожидания».
Квоты раундов 2–3 (правила 2028, 2026-10-19): повторных не меньше quota_repeat, новичков —
quota_novice; общие на оба пола и вместе с wild card, считаются по победителям. Набрана —
шарики вида ждут раунда 4. Места пола кончились — вытянутый сразу в лист ожидания, квоту не занимает.
"""
CATEGORIES = ("men", "women", "relay")
CATEGORY_LABELS = {"men": "Мужчины", "women": "Женщины", "relay": "Эстафеты"}
ROUND_LABELS = {0: "Wild card", 1: "Эстафеты", 2: "Повторные", 3: "Новички", 4: "Все личники"}
POOL_LABELS = {"wildcard": "wild card", "relay": "эстафета", "repeat": "повторный", "novice": "новичок"}


def category_of(app: dict) -> str:
    if app["format"] == "relay":
        return "relay"
    return "men" if app["gender"] == "M" else "women"


def kind_of(app: dict) -> str:
    """Повторный/новичок — по стартам в личном зачёте; wild card тоже засчитывается в квоту."""
    return "repeat" if app["starts_individual"] > 0 else "novice"


def in_round_pool(app: dict, rnd: int) -> bool:
    if rnd == 0:
        return app["is_wildcard"]
    if app["is_wildcard"]:
        return False
    if rnd == 1:
        return app["pool"] == "relay"
    if rnd == 2:
        return app["pool"] == "repeat"
    if rnd == 3:
        return app["pool"] == "novice"
    if rnd == 4:
        return app["pool"] in ("repeat", "novice")
    return False


def build_lists(apps_by_id: dict, picks: list[dict], config: dict) -> dict[str, list[dict]]:
    lists: dict[str, list[dict]] = {c: [] for c in CATEGORIES}
    active = sorted((p for p in picks if p["cancelled_at"] is None),
                    key=lambda p: (p["position_key"], p["id"]))
    for p in active:
        a = apps_by_id[p["applicant_id"]]
        lists[p["category"]].append({
            "pick_id": p["id"], "position_key": p["position_key"], "applicant_id": a["id"],
            "surname": a["surname"], "name": a["name"], "city": a["city"],
            "is_wildcard": a["is_wildcard"], "round": p["round"], "created_at": p["created_at"],
            "payment_status": a["payment_status"],
        })
    for c, rows in lists.items():
        cap = config.get(f"capacity_{c}")
        for i, row in enumerate(rows, start=1):
            row["position"] = i
            row["section"] = None if cap is None else ("winner" if i <= cap else "waitlist")
    return lists


def placement(lists: dict, applicant_id: int) -> tuple[str, int] | None:
    for c, rows in lists.items():
        for r in rows:
            if r["applicant_id"] == applicant_id:
                return c, r["position"]
    return None


KIND_LABELS = {"repeat": "повторных", "novice": "новичков"}


def winners_of_kind(lists: dict, apps_by_id: dict, kind: str) -> int:
    """Победители личного зачёта вида kind (повторные / новички) — оба пола, вместе с wild card;
    лист ожидания не считается."""
    return sum(1 for c in ("men", "women") for r in lists[c]
               if r["section"] != "waitlist" and kind_of(apps_by_id[r["applicant_id"]]) == kind)


def quota_block(app: dict, rnd: int, lists: dict, config: dict, apps_by_id: dict) -> str | None:
    """Раунды 2–3: квота вида набрана → шарик откладывается до раунда 4. Места пола кончились — не
    отказ: вытянутый встаёт в лист ожидания и квоту не занимает (решение организаторов 2026-10-19)."""
    if rnd not in (2, 3) or app["format"] == "relay":
        return None
    kind = "repeat" if rnd == 2 else "novice"
    quota = config.get(f"quota_{kind}")
    taken = winners_of_kind(lists, apps_by_id, kind)
    if quota is not None and taken >= quota:
        return f"квота {KIND_LABELS[kind]} набрана ({taken}/{quota}) — шарик откладывается до раунда 4"
    return None


def check_pick(app: dict, rnd: int, lists: dict, config: dict | None = None,
               apps_by_id: dict | None = None) -> str | None:
    """Причина отказа или None, если участника можно вытянуть в раунде rnd."""
    placed = placement(lists, app["id"])
    if placed:
        return f"уже вытянут — {CATEGORY_LABELS[placed[0]]} №{placed[1]}"
    if not in_round_pool(app, rnd):
        return f"не в этом раунде: {POOL_LABELS[app['pool']]}"
    if config is not None:
        return quota_block(app, rnd, lists, config, apps_by_id)
    return None


def round_counters(apps: list[dict], lists: dict, rnd: int) -> dict:
    by_id = {a["id"]: a for a in apps}
    kinds = {k: winners_of_kind(lists, by_id, k) for k in ("repeat", "novice")}
    placed = {r["applicant_id"] for rows in lists.values() for r in rows}
    pool = [a for a in apps if a["id"] not in placed and in_round_pool(a, rnd)]
    return {
        "categories": {c: len(rows) for c, rows in lists.items()},
        "kinds": kinds,
        "pool_people": len(pool),
        "pool_balls": sum(a["chances"] for a in pool),
    }
