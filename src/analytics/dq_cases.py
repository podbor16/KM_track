"""
«Качество данных» как дела о людях (спецификация docs/superpowers/specs/2026-10-28-data-quality-cases-design.md).

Дело — связная группа карточек: карточки одной находки связаны; тёзки с находками (та же фамилия,
совместимое имя: «Саша» — «Александр») — в одном деле. Вопросы дела идут ступенями: кто есть кто →
лишние строки → поля. Ответ на вопрос выполняет цепочку действий из dq_actions (журнал и отмена — там).
"""

import collections

from src.analytics.dq_checks import names_compatible
from src.common.names import norm

STAGES = {"C-TWIN": 1, "R-LEAD": 1, "R-FOREIGN": 1, "R-DUP": 2, "R-CARD": 3, "R-CAT": 3, "HYG": 3, "L-KID": 3}
STAGE_TITLES = {1: "Кто есть кто", 2: "Лишние строки", 3: "Поля"}


def _rows_count(data, cid):
    return len(data.res_by_card[cid]) + len(data.leads_by_card[cid])


def _namesakes(data, a, b):
    ca, cb = data.clients.get(a), data.clients.get(b)
    return bool(ca and cb and norm(ca["surname"]) == norm(cb["surname"])
                and names_compatible(ca["name"], cb["name"], data.names))


def group_cases(findings, data):
    """Находки -> дела [{key, title, cards, findings}], ключ — «c<наименьшая карточка>» или «r<результат>»."""
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        parent[find(a)] = find(b)

    orphans = []
    for f in findings:
        ids = [i for i in f.client_ids if i]
        if not ids:
            orphans.append(f)
            continue
        for i in ids:
            find(i)
        for i in ids[1:]:
            union(ids[0], i)
    cards = sorted(parent)
    by_surname = collections.defaultdict(list)
    for i in cards:
        c = data.clients.get(i)
        if c:
            by_surname[norm(c["surname"])].append(i)
    for same in by_surname.values():
        for x, y in ((x, y) for k, x in enumerate(same) for y in same[k + 1:]):
            if _namesakes(data, x, y):
                union(x, y)
    groups = collections.defaultdict(list)
    for i in cards:
        groups[find(i)].append(i)
    out = []
    for ids in groups.values():
        ids = sorted(ids)
        own = [f for f in findings if set(f.client_ids) & set(ids)]
        main = max(ids, key=lambda i: (_rows_count(data, i), -i))
        c = data.clients.get(main, {})
        out.append({"key": f"c{ids[0]}", "title": f'{c.get("surname", "")} {c.get("name", "")}'.strip() or f"#{main}",
                    "cards": ids, "findings": own})
    for f in orphans:
        out.append({"key": f"r{f.result_id}" if f.result_id else f"l{f.lead_id}",
                    "title": f.message[:1].upper() + f.message[1:], "cards": [], "findings": [f]})
    return out
