"""
«Качество данных» как дела о людях (спецификация docs/superpowers/specs/2026-10-28-data-quality-cases-design.md).

Дело — связная группа карточек: карточки одной находки связаны; тёзки с находками (та же фамилия,
совместимое имя: «Саша» — «Александр») — в одном деле. Вопросы дела идут ступенями: кто есть кто →
лишние строки → поля. Ответ на вопрос выполняет цепочку действий из dq_actions (журнал и отмена — там).
"""

import collections

from src.analytics.dq_actions import propose_final
from src.analytics.dq_checks import NOT_STARTED, _is_kid, jan1, merge_blockers, names_compatible, real_bd
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


# ---------------------------------------------------------------- вопросы

POSTPONE = {"id": "postpone", "label": "Не знаю — отложить дело", "recommended": False, "inputs": []}
TWIN_REASONS = {"ДР-заглушка": "у одной из карточек ДР не указана",
                "«ГГГГ-01-01» того же года": "у одной из карточек вместо ДР только год (1 января)",
                "похожие ФИ, та же ДР": "похожие фамилия и имя, та же ДР"}


def _a(id_, label, recommended=False, inputs=()):
    return {"id": id_, "label": label, "recommended": recommended, "inputs": list(inputs)}


def _fio_inputs(surname, name, birthday):
    return [{"name": "surname", "label": "Фамилия", "value": surname, "type": "text"},
            {"name": "name", "label": "Имя", "value": name, "type": "text"},
            {"name": "birthday", "label": "ДР", "value": birthday or "", "type": "date"}]


def _bd(bd):
    return f"ДР {bd}" if real_bd(bd) else "ДР не указана"


def _card(data, cid):
    c = data.clients.get(cid, {})
    return f'{c.get("surname", "")} {c.get("name", "")} ({_bd(c.get("birthday", ""))})'.strip()


def _years(n):
    if n % 10 == 1 and n % 100 != 11:
        return f"{n} год"
    return f"{n} года" if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14 else f"{n} лет"


def _ev(data, f):
    return f"«{data.event_label(f.event_id)}»"


def _bib(row):
    return f' №{row["start_number"]}' if row.get("start_number") else ""


def _why(f):
    """Причина из сообщения находки «<забег №…>: <причина> — <карточки>»."""
    return f.message.split(": ", 1)[-1].split(" — ")[0]


def _caution(blockers):
    return "Осторожно: " + "; ".join(blockers) if blockers else ""


def _row(data, f):
    if f.result_id:
        return "results", data.result_by_id.get(f.result_id)
    return "leads", data.lead_by_id.get(f.lead_id)


def _q_twin(f, data):
    a, b = f.client_ids
    _, s, n, bd = propose_final([a, b], data)
    blockers = merge_blockers([a, b], data)
    la, lb = _card(data, a), _card(data, b)
    text = f"{la} и {lb} — один человек?" if la != lb else f"Две карточки «{la}» — один человек?"
    why = _why(f)
    return text, _caution(blockers) or TWIN_REASONS.get(why, why), [
        _a("merge", "Да — одна карточка", not blockers, _fio_inputs(s, n, bd)),
        _a("different", "Нет, разные люди")]


def _q_lead(f, data):
    _, row = _row(data, f)
    res_card, lead_card = f.client_ids
    same_bib = f.severity == "high"
    blockers = merge_blockers([res_card, lead_card], data)
    text = (f"{_ev(data, f)}{_bib(row)}: результат записан на {_card(data, res_card)}, "
            f"а заявка — на {_card(data, lead_card)}. Это один человек?")
    _, s, n, bd = propose_final([res_card, lead_card], data)
    hint = "Номер в протоколе совпадает с номером заявки" if same_bib else "Совпадают фамилия и имя"
    return text, _caution(blockers) or hint, [
        _a("merge", "Да — одна карточка", same_bib and not blockers, _fio_inputs(s, n, bd)),
        _a(f"to:{lead_card}", f"Нет — результат принадлежит {_card(data, lead_card)}"),
        _a("keep", "Нет, всё верно — разные люди")]


def _q_foreign(f, data):
    table, row = _row(data, f)
    owner, others = f.client_ids[0], f.client_ids[1:]
    bd = data.clients[owner]["birthday"]
    age = f" — возраст по карточке: {_years(data.year(f.event_id) - int(bd[:4]))}" if real_bd(bd) else ""
    what, verb, whose = ("результат", "записан", "Чей") if table == "results" else ("заявка", "записана", "Чья")
    text = f"{_ev(data, f)}: {what}{_bib(row)} {verb} на {_card(data, owner)}{age}. {whose} это {what}?"
    answers = [_a(f"to:{i}", _card(data, i), k == 0) for k, i in enumerate(others)]
    answers += [_a("new", "Другой человек — новая карточка", False, _fio_inputs(row["surname"], row["name"], "")),
                _a("keep", "Всё верно — оставить")]
    return text, _why(f), answers


def _q_dup(f, data):
    _, row = _row(data, f)
    cid = f.client_ids[0]
    who = _card(data, cid)
    fin = [r for r in data.res_by_card[cid] if r["event_id"] == f.event_id and r["race_status"] != NOT_STARTED]
    if f.auto and fin:
        return (f"{who}: в забеге {_ev(data, f)} есть «не стартовал»{_bib(row)} и другой результат. "
                f"Удалить «не стартовал»?", "Обычно это старый номер",
                [_a("delete", "Да, удалить", True), _a("keep", "Оставить")])
    if f.auto:
        bibs = sorted(l["start_number"] for l in data.leads_by_card[cid]
                      if l["event_id"] == f.event_id and l["start_number"])
        return (f"{who}: в забеге {_ev(data, f)} результат{_bib(row)}, а в заявке номер "
                f'{", ".join(map(str, bibs))}. Удалить результат{_bib(row)}?', "Обычно это старый номер",
                [_a("delete", "Да, удалить", True), _a("keep", "Оставить")])
    return (f'{who}: два финиша в забеге {_ev(data, f)} (№{" и №".join(str(r["start_number"]) for r in fin)}). '
            f"Это два разных человека?", "", [
                _a("new", f"Да — вынести{_bib(row)} на новую карточку", False,
                   _fio_inputs(row["surname"], row["name"], "")),
                _a("keep", "Нет, оставить", True)])


def _q_card(f, data):
    _, row = _row(data, f)
    if not row:
        return f.message[:1].upper() + f.message[1:], "", []
    if not f.client_ids:
        return (f'{_ev(data, f)}{_bib(row)}: {row["surname"]} {row["name"]}, {_bd(row["birthday"])} — '
                f"результат не привязан ни к одной карточке.", "", [])
    c = data.clients[f.client_ids[0]]
    diff = [k for k in ("surname", "name") if norm(row[k]) != norm(c[k])]
    if row["birthday"] != c["birthday"]:
        diff.append("birthday")

    def show(o):
        fio = " ".join(o[k] for k in diff if k != "birthday")
        return ", ".join(x for x in (fio, _bd(o["birthday"]) if "birthday" in diff else "") if x)

    placeholder = ("birthday" in diff and real_bd(c["birthday"])
                   and (not real_bd(row["birthday"]) or (jan1(row["birthday"]) and not jan1(c["birthday"]))))
    who = "" if {"surname", "name"} & set(diff) else f' {row["surname"]} {row["name"]}'
    text = f"{_ev(data, f)}{_bib(row)}{who}: в протоколе «{show(row)}», в карточке «{show(c)}». Как правильно?"
    return text, "В протоколе вместо ДР заглушка или только год" if placeholder else "", [
        _a("row_from_card", f"Как в карточке: {show(c)}", placeholder or "birthday" not in diff),
        _a("card_from_row", f"Как в протоколе: {show(row)}"),
        _a("other", "Другое значение", False, _fio_inputs(row["surname"], row["name"], row["birthday"]))]


def _q_cat(f, data):
    _, row = _row(data, f)
    sex = {"М": "мужской", "Ж": "женский"}.get((row.get("sex") or "")[:1].upper(), "не указан")
    text = (f'{_ev(data, f)}{_bib(row)}: {row["surname"]} {row["name"]}, {_bd(row["birthday"])}, '
            f'пол {sex} — категория «{row["category"]}». Что неверно?')
    hint = "Категория не для этого пола" if _why(f).startswith("пол ") else "ДР не подходит к категории"
    return text, hint, [
        _a("birthday", "ДР", False, [{"name": "birthday", "label": "ДР", "value": row["birthday"], "type": "date"}]),
        _a("category", "Категория", False, [{"name": "category", "label": "Категория", "value": row["category"],
                                             "type": "select", "options": "category_options"}]),
        _a("sex", "Пол", False, [{"name": "sex", "label": "Пол", "value": row["sex"], "type": "select",
                                  "options": ["Мужчина", "Женщина"]},
                                 {"name": "category", "label": "Категория", "value": "", "type": "select",
                                  "options": "category_options"}]),
        _a("keep", "Всё верно — оставить")]


def _q_hyg(f, data):
    _, row = _row(data, f)
    s, n = f.fix
    return (f'{_ev(data, f)}{_bib(row)}: в протоколе «{row["surname"]} {row["name"]}». Записать как «{s} {n}»?', "", [
        _a("fix", "Да", True), _a("manual", "Вписать вручную", False, _fio_inputs(s, n, "")[:2]),
        _a("keep", "Оставить как есть")])


def _q_kid(f, data):
    _, row = _row(data, f)
    owner, year = data.clients.get(row["client_id"]), data.year(f.event_id)
    kids = [i for i in data.cards_by_surname[norm(owner["surname"])] if i != row["client_id"]
            and names_compatible(owner["name"], data.clients[i]["name"], data.names)
            and _is_kid(data.clients[i]["birthday"], year)] if owner else []
    why = f.message.split(" — ", 1)[-1]
    text = (f'Заявка на {_ev(data, f)}: {row["surname"]} {row["name"]}, {_bd(row["birthday"])}. '
            f"{why[:1].upper() + why[1:]}. Что исправить?")
    return text, "", [
        _a("birthday", "ДР ребёнка", False, [{"name": "birthday", "label": "ДР", "value": "", "type": "date"}]),
        *[_a(f"to:{i}", f"Перенести на {_card(data, i)}") for i in kids],
        _a("distance", "Дистанция", False, [{"name": "event_distance", "label": "Дистанция",
                                             "value": row.get("event_distance", ""), "type": "select",
                                             "options": "distance_options"}]),
        _a("keep", "Всё верно — оставить")]


BUILDERS = {"C-TWIN": _q_twin, "R-LEAD": _q_lead, "R-FOREIGN": _q_foreign, "R-DUP": _q_dup, "R-CARD": _q_card,
            "R-CAT": _q_cat, "HYG": _q_hyg, "L-KID": _q_kid}


def build_question(f, data):
    """Находка -> вопрос человеческим языком с готовыми ответами (recommended — не больше одного)."""
    text, hint, answers = BUILDERS[f.code](f, data)
    return {"id": f.key, "code": f.code, "stage": STAGES[f.code], "text": text, "hint": hint,
            "result_id": f.result_id, "lead_id": f.lead_id, "answers": answers + [dict(POSTPONE)]}
