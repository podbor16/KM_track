"""
«Качество данных» как дела о людях (спецификация docs/superpowers/specs/2026-10-28-data-quality-cases-design.md).

Дело — связная группа карточек: карточки одной находки связаны; тёзки с находками (та же фамилия,
совместимое имя: «Саша» — «Александр») — в одном деле. Вопросы дела идут ступенями: кто есть кто →
лишние строки → поля. Ответ на вопрос выполняет цепочку действий из dq_actions (журнал и отмена — там).
"""

import collections
import datetime as _dt
import functools
import itertools
import logging
import re
import threading
import time

from src.analytics import dq_actions
from src.analytics.dq_actions import edit_record_view, propose_final
from src.analytics.dq_checks import (NOT_STARTED, bd_support, card_fits_category, ext_of, is_kid, jan1, load,
                                     load_row_scoped, load_scoped, merge_blockers, names_compatible, real_bd,
                                     remember_refs, run_checks, same_contact, with_namesakes)
from src.common.names import norm
from src.config.settings import KRASNOYARSK_TZ

logger = logging.getLogger(__name__)

STAGES = {"C-TWIN": 1, "R-LEAD": 1, "R-FOREIGN": 1, "X-PHONE": 1, "R-DUP": 2, "R-CARD": 3, "R-CAT": 3, "HYG": 3,
          "L-KID": 3, "X-BD": 3, "X-BDDIFF": 3}
STAGE_TITLES = {1: "Кто есть кто", 2: "Лишние строки", 3: "Поля"}


def _rows_count(data, cid):
    return len(data.res_by_card[cid]) + len(data.leads_by_card[cid])


def _namesakes_of(data, cid, ok=lambda bd: True):
    """Другие карточки с той же фамилией и совместимым именем («Саша» — «Александр»), ДР которых подходит ok."""
    c = data.clients.get(cid)
    if not c:
        return []
    return [i for i in data.cards_by_surname[norm(c["surname"])] if i != cid
            and names_compatible(c["name"], data.clients[i]["name"], data.names) and ok(data.clients[i]["birthday"])]


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
    for i in cards:
        for j in _namesakes_of(data, i):
            if j in parent:
                union(i, j)
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


def _age(bd, year):
    """Возраст в год забега; None — нет ДР или у события нет года."""
    return year - int(bd[:4]) if year and real_bd(bd) else None


def _ev(data, f):
    return f"«{data.event_label(f.event_id)}»"


def _bib(row):
    return f' №{row["start_number"]}' if row.get("start_number") else ""


def _why(f):
    """Причина из сообщения находки «<забег №…>: <причина> — <карточки>»."""
    return f.message.split(": ", 1)[-1].split(" — ")[0]


def _blocker_text(b, data):
    if b.startswith("обе финишировали в одном забеге: "):
        return "у обеих карточек есть финиш в одном забеге: " + b.split(": ", 1)[1]
    if b.startswith("несовместимые ДР: "):
        return "даты рождения не похожи на одного человека: " + b.split(": ", 1)[1]
    if b == "разный пол в протоколах":
        return "в протоколах разный пол"
    if b.startswith("разные имена: "):
        return "разные имена: " + b.split(": ", 1)[1].replace(" / ", " и ")
    if m := re.fullmatch(r"ДР-заглушка #(\d+) подходит нескольким людям", b):
        return (f"у карточки {_card(data, int(m[1]))} ДР не указана, а тёзок с разными ДР несколько — "
                f"непонятно, чья она")
    return re.sub(r"\s*#\d+", "", b)


def _caution(blockers, data):
    return "Осторожно: " + "; ".join(_blocker_text(b, data) for b in blockers) if blockers else ""


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
    return text, _caution(blockers, data) or TWIN_REASONS.get(why, why), [
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
    return text, _caution(blockers, data) or hint, [
        _a("merge", "Да — одна карточка", same_bib and not blockers, _fio_inputs(s, n, bd)),
        _a(f"to:{lead_card}", f"Нет — результат принадлежит {_card(data, lead_card)}"),
        _a("keep", "Нет, всё верно — разные люди")]


def _q_foreign(f, data):
    table, row = _row(data, f)
    owner, others = f.client_ids[0], f.client_ids[1:]
    age = _age(data.clients[owner]["birthday"], data.year(f.event_id))
    shown = f" — возраст по карточке: {_years(age)}" if age is not None else ""
    what, verb, whose = ("результат", "записан", "Чей") if table == "results" else ("заявка", "записана", "Чья")
    text = f"{_ev(data, f)}: {what}{_bib(row)} {verb} на {_card(data, owner)}{shown}. {whose} это {what}?"
    why = _why(f)
    hint = "" if "возраст" in why else why[:1].upper() + why[1:]      # детский забег: возраст уже в тексте
    answers = [_a(f"to:{i}", _card(data, i), k == 0) for k, i in enumerate(others)]
    answers += [_a("new", "Другой человек — новая карточка", False, _fio_inputs(row["surname"], row["name"], "")),
                _a("keep", "Всё верно — оставить")]
    return text, hint, answers


def _finish_label(r):
    t = r.get("time_clear_finish")
    bib = f'№{r["start_number"]}' if r.get("start_number") else "без номера"
    return f"{bib} ({t})" if t else bib


def _q_dup(f, data):
    """Лишняя строка. Два финиша: у ответов «вынести на …» (to:<карточка>, new) поле row_id — какой из финишей
    выносить (по умолчанию строка находки); apply_answer берёт строку из inputs["row_id"]."""
    _, row = _row(data, f)
    cid = f.client_ids[0]
    who = _card(data, cid)
    fin = [r for r in data.res_by_card[cid] if r["event_id"] == f.event_id and r["race_status"] != NOT_STARTED]
    if f.auto and fin:
        return (f"{who}: в забеге {_ev(data, f)} есть «не стартовал(а)»{_bib(row)} и другой результат. "
                f"Удалить «не стартовал(а)»?", "Обычно это старый номер",
                [_a("delete", "Да, удалить", True), _a("keep", "Оставить")])
    if f.auto:
        bibs = sorted(l["start_number"] for l in data.leads_by_card[cid]
                      if l["event_id"] == f.event_id and l["start_number"])
        return (f"{who}: в забеге {_ev(data, f)} результат{_bib(row)}, а в заявке номер "
                f'{", ".join(map(str, bibs))}. Удалить результат{_bib(row)}?', "Обычно это старый номер",
                [_a("delete", "Да, удалить", True), _a("keep", "Оставить")])
    year = data.year(f.event_id)
    pick = {"name": "row_id", "label": "Какой результат", "type": "select", "value": str(row["id"]),
            "options": [{"value": str(r["id"]), "label": _finish_label(r)} for r in fin]}

    def fits(bd):
        return not (year and real_bd(bd)) or card_fits_category(bd, row["category"], year) is not False

    def finished(i):            # у тёзки уже есть финиш в этом забеге — перенос дал бы ему два финиша
        return any(r["event_id"] == f.event_id and r["race_status"] != NOT_STARTED for r in data.res_by_card[i])

    return (f'{who}: два финиша в забеге {_ev(data, f)} ({", ".join(_finish_label(r) for r in fin)}). '
            f"Это два разных человека?", "", [
                *[_a(f"to:{i}", f"Да — вынести на {_card(data, i)}", False, [pick])
                  for i in _namesakes_of(data, cid, fits) if not finished(i)],
                _a("new", "Да — вынести на новую карточку", False,
                   [pick, *_fio_inputs(row["surname"], row["name"], "")]),
                _a("keep", "Нет, оставить", True)])


def _q_card(f, data):
    _, row = _row(data, f)
    if not row:
        return re.sub(r"\s*#\d+", "", f.message[:1].upper() + f.message[1:]), "", []
    if not f.client_ids:
        return (f"Результат{_bib(row)} в {_ev(data, f)} ({row['surname']} {row['name']}, {_bd(row['birthday'])}) "
                f"не привязан ни к одной карточке — разберите вручную через «⋯»", "", [])
    c = data.clients[f.client_ids[0]]
    diff = [k for k in ("surname", "name") if norm(row[k]) != norm(c[k])]
    if row["birthday"] != c["birthday"]:
        diff.append("birthday")

    def show(o):
        fio = " ".join(o[k] for k in diff if k != "birthday")
        return ", ".join(x for x in (fio, _bd(o["birthday"]) if "birthday" in diff else "") if x)

    rbd, cbd = row["birthday"], c["birthday"]
    bd_diff = "birthday" in diff
    row_placeholder = bd_diff and real_bd(cbd) and (
        not real_bd(rbd) or (jan1(rbd) and not jan1(cbd) and rbd[:4] == cbd[:4]))
    card_placeholder = bd_diff and not real_bd(cbd) and real_bd(rbd)
    who = "" if {"surname", "name"} & set(diff) else f' {row["surname"]} {row["name"]}'
    text = f"{_ev(data, f)}{_bib(row)}{who}: в протоколе «{show(row)}», в карточке «{show(c)}». Как правильно?"
    hint = ("В протоколе вместо ДР заглушка или только год" if row_placeholder
            else "В карточке ДР не указана" if card_placeholder else "")
    return text, hint, [
        _a("row_from_card", f"Как в карточке: {show(c)}", row_placeholder or not bd_diff),
        _a("card_from_row", f"Как в протоколе: {show(row)}", card_placeholder),
        _a("other", "Другое значение", False, _fio_inputs(row["surname"], row["name"], rbd))]


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
    year = data.year(f.event_id)
    owner = data.clients.get(row["client_id"])
    kids = (_namesakes_of(data, row["client_id"], lambda bd: is_kid(bd, year))
            if year and owner and not is_kid(owner["birthday"], year) else [])
    age = _age(row["birthday"], year)
    why = f.message.split(" — ", 1)[-1]
    if not real_bd(row["birthday"]):
        why = "Нет даты рождения"
    elif why.startswith("возраст"):
        why = (f"Возраст {_years(age)} — не детский (возможно, ДР родителя)" if age is not None
               else "У забега не указан год — возраст не проверить")
    else:
        at = f" ({_years(age)})" if age is not None else ""
        why = f'Дистанция {row["event_distance"]}, а по возрасту{at} — {why.rsplit(" — ", 1)[-1]}'
    text = (f'Заявка на {_ev(data, f)}: {row["surname"]} {row["name"]}, {_bd(row["birthday"])}. '
            f"{why}. Что исправить?")
    return text, "", [
        _a("birthday", "ДР ребёнка", False, [{"name": "birthday", "label": "ДР", "value": "", "type": "date"}]),
        *[_a(f"to:{i}", f"Перенести на {_card(data, i)}") for i in kids],
        _a("distance", "Дистанция", False, [{"name": "event_distance", "label": "Дистанция",
                                             "value": str(row.get("event_distance") or ""), "type": "select",
                                             "options": "distance_options"}]),
        _a("keep", "Всё верно — оставить")]


def _plural(n, one, few, many):
    if n % 10 == 1 and n % 100 != 11:
        return f"{n} {one}"
    return f"{n} {few}" if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14 else f"{n} {many}"


EXT_EVENTS = 3                      # забегов регистрации в тексте вопроса X-BD


def _ext_events(rows):
    """Забеги регистраций (товар или год) — свежие первыми, до EXT_EVENTS: «Жара 2019», «РЖД 2021»."""
    out = []
    for x in sorted(rows, key=lambda x: -(x["event_year"] or 0)):
        label = (x["product"] or str(x["event_year"] or "")).strip()
        label = label if len(label) <= 40 else label[:39] + "…"
        if label and f"«{label}»" not in out:
            out.append(f"«{label}»")
    return ", ".join(out[:EXT_EVENTS])


def _q_ext_bd(f, data):
    cid = f.client_ids[0]
    c = data.clients[cid]
    have = f'только год {c["birthday"][:4]}' if real_bd(c["birthday"]) else "ДР не указана"
    rows = [x for x in ext_of(data, c) if x["birthday"] in f.fix]
    strong = any(same_contact(data, cid, x) for x in rows)
    found = []
    for bd in f.fix:
        where = _ext_events([x for x in rows if x["birthday"] == bd])
        found.append(f"{bd} ({where})" if where else bd)
    who = f'{c["surname"]} {c["name"]}: в карточке {have}.'
    if len(f.fix) == 1:
        where = _ext_events(rows)
        text = f"{who} В регистрациях{' на ' + where if where else ''}: ДР {f.fix[0]}. Записать?"
    else:
        text = f'{who} В регистрациях разные ДР: {", ".join(found)}. Какую записать?'
    hint = "Совпал телефон или почта из заявок" if strong else "Совпали только фамилия и имя — проверьте"
    return text, hint, [*[_a(f"bd:{bd}", f"Записать {bd}", f.severity == "high") for bd in f.fix],
                        _a("keep", "Оставить как есть")]


def _q_ext_phone(f, data):
    a, b = f.client_ids
    _, s, n, bd = propose_final([a, b], data)
    blockers = merge_blockers([a, b], data)
    phone = (data.card_phones.get(a, set()) & data.card_phones.get(b, set())) - data.busy
    email = (data.card_emails.get(a, set()) & data.card_emails.get(b, set())) - data.busy
    what = ("один и тот же телефон и почта" if phone and email else "один и тот же телефон" if phone
            else "одна и та же почта")
    text = f"В заявках у {_card(data, a)} и {_card(data, b)} {what}. Это один человек?"
    hint = _caution(blockers, data) or ("Обычно так регистрируют ребёнка с телефона родителя"
                                        if f.severity == "low" else "")
    return text, hint, [_a("merge", "Да — одна карточка", f.severity == "high" and not blockers, _fio_inputs(s, n, bd)),
                        _a("different", "Нет, разные люди")]


def _q_ext_bddiff(f, data):
    cid, other = f.client_ids[0], f.fix[0]
    c = data.clients[cid]
    ours, ours_last, theirs, theirs_last = bd_support(data, cid, other)

    def last(y):
        return f", последняя — {y}" if y else ""

    text = (f'{c["surname"]} {c["name"]}: ДР в карточке {c["birthday"]} (подтверждена '
            f'{_plural(ours, "строкой", "строками", "строками")}{last(ours_last)}), в регистрациях — {other} '
            f'({_plural(theirs, "раз", "раза", "раз")}{last(theirs_last)}). Какая верная?')
    return text, "Совпал телефон или почта из заявок", [_a(f"bd:{other}", f"Как в регистрациях: {other}"),
                                                         _a("keep", f'Как в карточке: {c["birthday"]}')]


BUILDERS = {"C-TWIN": _q_twin, "R-LEAD": _q_lead, "R-FOREIGN": _q_foreign, "R-DUP": _q_dup, "R-CARD": _q_card,
            "R-CAT": _q_cat, "HYG": _q_hyg, "L-KID": _q_kid, "X-BD": _q_ext_bd, "X-PHONE": _q_ext_phone,
            "X-BDDIFF": _q_ext_bddiff}


def build_question(f, data):
    """Находка -> вопрос человеческим языком с готовыми ответами (recommended — не больше одного)."""
    text, hint, answers = BUILDERS[f.code](f, data)
    return {"id": f.key, "code": f.code, "stage": STAGES[f.code], "text": text, "hint": hint,
            "result_id": f.result_id, "lead_id": f.lead_id, "answers": answers + [dict(POSTPONE)]}


def questions_for(findings, data):
    """Находки -> вопросы без повторов: находки с одним ключом (R-CAT по полу и по ДР одной строки) — один вопрос,
    подсказки через «; »."""
    out = {}
    for f in findings:
        q = build_question(f, data)
        if f.key not in out:
            out[f.key] = q
        elif q["hint"] and q["hint"] not in out[f.key]["hint"].split("; "):
            out[f.key]["hint"] = "; ".join(x for x in (out[f.key]["hint"], q["hint"]) if x)
    return list(out.values())


# ---------------------------------------------------------------- дело целиком

FIELDS = {"birthday": ("birthday",), "category": ("category",), "sex": ("sex", "category"),
          "distance": ("event_distance",)}
FIO = ("surname", "name", "birthday")
LIVE_HINT = "Забег ещё загружается: исправьте в Copernico — загрузчик перезапишет ФИО, ДР, пол, категорию и места"


def is_live(event, today):
    """Забег «живой» — дата сегодня или вчера (Красноярск): загрузчик Copernico ещё перезаписывает его строки."""
    d = event.get("event_date")
    return bool(d) and 0 <= (today - d).days <= 1


def _today():
    return _dt.datetime.now(KRASNOYARSK_TZ).date()


def _live(f, data, today):
    """Вопрос о строке результата «живого» забега (заявки загрузчик не трогает)."""
    return bool(f.result_id and f.event_id and is_live(data.events.get(f.event_id, {}), today))


def _live_ok(answer_id):
    """В «живом» забеге — только перенос строки (загрузчик не трогает client_id) и «отложить»."""
    return answer_id.startswith("to:") or answer_id in ("new", "postpone")


def _rows(data, cid, problems):
    rows = [{"table": "results", "id": r["id"], "year": data.year(r["event_id"]), "event": data.event_label(r["event_id"]),
             "start_number": r["start_number"], "category": r["category"], "status": r["race_status"],
             "birthday": r["birthday"], "problem": r["id"] in problems["results"]} for r in data.res_by_card[cid]]
    rows += [{"table": "leads", "id": l["id"], "year": data.year(l["event_id"]), "event": data.event_label(l["event_id"]),
              "start_number": l["start_number"], "category": "", "status": "заявка", "birthday": l["birthday"],
              "problem": l["id"] in problems["leads"]} for l in data.leads_by_card[cid]]
    return sorted(rows, key=lambda r: (-r["year"], r["event"], r["table"] != "results"))


def case_view(case, data, decided, today):
    """Дело для экрана: карточки со строками по годам (проблемные подсвечены), вопросы по ступеням."""
    problems = {"results": {f.result_id for f in case["findings"]}, "leads": {f.lead_id for f in case["findings"]}}
    findings = sorted(case["findings"],
                      key=lambda f: (STAGES[f.code], -data.year(f.event_id) if f.event_id else 0, f.key))
    by_key = {}
    for f in findings:
        by_key.setdefault(f.key, f)
    questions = questions_for(findings, data)
    for q in questions:
        f = by_key[q["id"]]
        rec = None
        for a in q["answers"]:
            for inp in a["inputs"]:
                if isinstance(inp.get("options"), str):
                    rec = rec or edit_record_view(f, data) or {}
                    inp["options"] = rec.get(inp["options"], [])      # категории — {label, sex}, дистанции — строки
        q["live"] = _live(f, data, today)
        if q["live"]:
            q["answers"] = [a for a in q["answers"] if _live_ok(a["id"])]
            q["hint"] = LIVE_HINT
        q["state"] = "postponed" if decided.get(f.key) == "postponed" else "open"
    open_stages = [q["stage"] for q in questions if q["state"] == "open"]
    current = min(open_stages) if open_stages else None
    for q in questions:
        if q["state"] == "open":
            q["state"] = "current" if q["stage"] == current else "locked"
    cards = [{**{k: data.clients[i][k] for k in ("id", "surname", "name", "birthday")},
              "rows": _rows(data, i, problems)} for i in case["cards"] if i in data.clients]
    return {"key": case["key"], "title": case["title"], "cards": cards, "questions": questions,
            "stage_titles": STAGE_TITLES}


# ---------------------------------------------------------------- ответы, отложить, очередь

class StaleQuestion(Exception):
    """Вопроса больше нет (дело изменилось в другой вкладке) — 409 «обновите дело»."""


QUEUE_TTL = 600                     # с: полный прогон очереди (~8 с на проде); 3 процесса сервера — свой процесс сбрасывает кеш после действия, в других дело-«призрак» откроется как «дело закрыто» (get_case проверяет заново)
EXPAND = 4                          # итераций расширения дела карточками его находок
OPTION_CODES = ("R-CAT", "L-KID")   # вопросы с выбором категории/дистанции — нужны строки забега целиком
_queue_lock = threading.Lock()
_generations = itertools.count(1)   # next() атомарен: invalidate() не ждёт загрузку
_gen = 0
_queue = None                       # (когда, поколение, data, находки) — заменяется целиком


def invalidate():
    """Сбросить кеш очереди этого процесса — после любого действия «Качества данных»; загрузка, начатая до сброса,
    в кеш не попадёт."""
    global _gen, _queue
    _gen = next(_generations)
    _queue = None


def _cached():
    q = _queue
    return q if q and q[1] == _gen and time.monotonic() - q[0] <= QUEUE_TTL else None


def _invalidating(fn):
    """Действие пишет в базу — кеш очереди сбрасывается и при ошибке посреди цепочки."""
    @functools.wraps(fn)
    def run(*args, **kw):
        try:
            return fn(*args, **kw)
        finally:
            invalidate()
    return run


def _full(conn):
    """Полный прогон (данные, находки) — кеш процесса на QUEUE_TTL с; холодную загрузку делает один поток."""
    global _queue
    if q := _cached():
        return q[2], q[3]
    with _queue_lock:
        if q := _cached():
            return q[2], q[3]
        gen = _gen
        data = load(conn)
        findings = run_checks(data)
        remember_refs(data)
        if gen == _gen:
            _queue = (time.monotonic(), gen, data, findings)
        return data, findings


def _open(findings, decided):
    return [f for f in findings if decided.get(f.key) in (None, "postponed")]


def _cases(data, findings, decided):
    """Дела из нерешённых и отложенных находок; «разные люди»/«оставить» — решены."""
    return group_cases(_open(findings, decided), data)


def _key_cards(key):
    """Карточки из ключа дела «c<id>»/«p<id>» или из ключа находки (после последнего «:» — id через «-»)."""
    if re.fullmatch(r"[cp]\d+", key):
        return {int(key[1:])}
    return {int(x) for x in key.rsplit(":", 1)[-1].split("-") if x.isdigit()} if ":" in key else set()


def _scoped(conn, cards, events=(), view=False):
    """Дела вокруг карточек cards без полной загрузки -> (data, дела, решения): набор карточек расширяется
    карточками находок и тёзками до неподвижной точки (не больше EXPAND итераций); view — и забегами вопросов
    с вариантами категорий/дистанций. load_scoped — только когда загруженного не хватает."""
    decided = dq_actions.load_decisions(conn)
    cards, events, data = set(cards), set(events), None
    start = sorted(cards)
    for _ in range(EXPAND):
        if data is None or not data.covers(cards, events):
            data = load_scoped(conn, cards, events)
        found = _open(run_checks(data, card_ids=cards), decided)
        more = with_namesakes(data, cards | {i for f in found for i in f.client_ids if i})
        more_events = events | ({f.event_id for f in found if f.code in OPTION_CODES and f.event_id} if view else set())
        if more <= cards and more_events <= events:
            return data, group_cases(found, data), decided
        cards, events = cards | more, more_events
    logger.warning("Дело карточек %s не сошлось за %d итераций (%d карточек) — полный прогон", start, EXPAND, len(cards))
    data, findings = _full(conn)
    return data, _cases(data, findings, decided), decided


def _row_case(conn, key):
    """Дело «r<id>»/«l<id>» — находка строки без карточки -> (data, дела, решения)."""
    decided = dq_actions.load_decisions(conn)
    data = load_row_scoped(conn, "results" if key[0] == "r" else "leads", int(key[1:]))
    if data is None:
        return None, [], decided
    return data, _cases(data, [f for f in run_checks(data) if not any(f.client_ids)], decided), decided


def _case_by_key(conn, key, more_cards=(), events=(), view=False, cards=()):
    """-> (data, дело или None, решения) по ключу дела; more_cards — тоже загрузить (карточки вопроса и ответа),
    cards — для _find_case, если ключ сменился."""
    if re.fullmatch(r"[rl]\d+", key):
        data, cases, decided = _row_case(conn, key)
    else:
        data, cases, decided = _scoped(conn, _key_cards(key) | set(more_cards), events, view)
    return data, _find_case(cases, key, set(cards) & set(data.clients) if data else ()), decided


def _find_case(cases, key, cards=()):
    """Дело по ключу; ключ сменился (склейка или перенос убрали наименьшую карточку) — дело с наибольшим числом
    общих карточек."""
    same = next((c for c in cases if c["key"] == key), None)
    if same or not cards:
        return same
    best = max(cases, key=lambda c: len(set(c["cards"]) & set(cards)), default=None)
    return best if best and set(best["cards"]) & set(cards) else None


def _case_after(conn, case, extra_cards=()):
    """Дело после ответа: проверки только по карточкам дела, его тёзкам и карточкам, куда ушли строки."""
    invalidate()                    # откат к полному прогону (_scoped) должен увидеть записанное
    cards = {*case["cards"], *extra_cards}
    events = {f.event_id for f in case["findings"] if f.code in OPTION_CODES and f.event_id}
    data, found, decided = _case_by_key(conn, case["key"], cards, events, view=True, cards=cards)
    return case_view(found, data, decided, _today()) if found else None


def _postpone(conn, case, decided, reason, user):
    keys = dict.fromkeys(f.key for f in case["findings"] if decided.get(f.key) != "postponed")
    return [dq_actions.dismiss(conn, k, "postponed", reason or "не знаю ДР", user) for k in keys]


def _differs(field, new, old):
    """Значение поля меняется: ФИ сравниваются без учёта регистра и ё, ДР — строкой."""
    return (norm(new) != norm(old)) if field in ("surname", "name") else new != str(old)


def _dup_row(data, f, row, inputs):
    """R-DUP «два финиша»: какой финиш выносить — inputs["row_id"] (финиш этой карточки в этом забеге)."""
    if f.code != "R-DUP" or not inputs.get("row_id"):
        return row
    r = data.result_by_id.get(int(inputs["row_id"]))
    if not r or r["client_id"] != f.client_ids[0] or r["event_id"] != f.event_id or r["race_status"] == NOT_STARTED:
        raise ValueError("выберите финиш этой карточки в этом забеге")
    return r


def _edit_card(conn, f, c, fields, user):
    """Правка карточки -> (id записи журнала, None) или (None, конфликт): ФИ+ДР уже у другой карточки —
    предложение склеить (спецификация, «Цепочки»); ничего не записано."""
    try:
        return dq_actions.edit_record(conn, "clients", c["id"], fields, user, f.key)[1], None
    except ValueError as e:
        other = re.search(r"уже у карточки #(\d+)", str(e))
        if not other:
            raise
        final = {k: fields.get(k, str(c[k])) for k in FIO}
        return None, {"message": f"{final['surname']} {final['name']} {final['birthday']} — уже есть такая карточка. "
                                 f"Склеить с ней?", "merge_with": int(other[1]), **final}


def _merge_target(data, f, answer_id, fio):
    """merge_with:<id> — только карточка, у которой ФИ+ДР совпадают с итоговыми значениями конфликта."""
    other = int(answer_id.split(":", 1)[1])
    o = data.clients.get(other)
    same = o and other != f.client_ids[0] and (norm(o["surname"]), norm(o["name"]), o["birthday"]) == (
        norm(fio.get("surname", "")), norm(fio.get("name", "")), fio.get("birthday"))
    if not same:
        raise ValueError("склеить можно только с карточкой, у которой те же ФИ и ДР")
    return other


def _locked_by(case, f, decided):
    """Название ступени, вопросы которой ещё открыты раньше вопроса f (None — вопрос можно решать)."""
    open_ = [STAGES[x.code] for x in case["findings"] if decided.get(x.key) is None]
    if decided.get(f.key) is None and open_ and STAGES[f.code] > min(open_):
        return STAGE_TITLES[min(open_)]
    return None


@_invalidating
def apply_answer(conn, case_key, question_id, answer_id, inputs, user, extra_cards=()):
    """Выполнить цепочку ответа -> {"action_ids": [...], "case": дело после ответа (None — дело закрыто)};
    правка карточки упёрлась в чужие ФИ+ДР -> ничего не записано, ещё
    "conflict": {message, merge_with, surname, name, birthday}."""
    inputs = {k: str(v if v is not None else "").strip() for k, v in (inputs or {}).items()}
    # карточки вопроса и цели ответа (to:<id>, merge_with:<id> — у неё может быть другая фамилия)
    more = _key_cards(question_id) | (_key_cards(answer_id) if ":" in answer_id else set())
    data, case, decided = _case_by_key(conn, case_key, more)
    f = next((x for x in (case or {}).get("findings", ()) if x.key == question_id), None)
    if f is None:
        raise StaleQuestion("Дело изменилось — обновите")
    if answer_id == "postpone":
        return {"action_ids": _postpone(conn, case, decided, inputs.get("reason", ""), user),
                "case": _case_after(conn, case, extra_cards)}
    offered = {a["id"] for a in build_question(f, data)["answers"]}
    # merge_with:<id> — после конфликта правки карточки (ответы card_from_row/other, bd:<дата>)
    if answer_id not in offered and not (answer_id.startswith("merge_with:") and (
            "card_from_row" in offered or any(a.startswith("bd:") for a in offered))):
        raise ValueError(f"неизвестный ответ {answer_id}")
    stage = _locked_by(case, f, decided)
    if stage:
        raise ValueError(f"сначала ответьте на вопросы ступени «{stage}»")
    if not _live_ok(answer_id) and _live(f, data, _today()):
        raise ValueError("забег ещё загружается из хронометража — поля правьте в Copernico, иначе загрузчик перезапишет")
    table, row = _row(data, f)
    fio = {k: inputs[k] for k in FIO if inputs.get(k)}
    aid, moved = [], []
    if answer_id in ("keep", "different"):
        aid.append(dq_actions.dismiss(conn, f.key, "different_people" if answer_id == "different" else "keep", "", user))
    elif answer_id == "merge":
        aid.append(dq_actions.merge_cards(conn, list(f.client_ids), fio.get("surname"), fio.get("name"),
                                          fio.get("birthday"), user, f.key)[1])
    elif answer_id.startswith("to:") or answer_id == "new":
        row = _dup_row(data, f, row, inputs)
        to = {"new_card": fio} if answer_id == "new" else {"to_client_id": int(answer_id[3:])}
        target, a = dq_actions.move_row(conn, table, row["id"], user, f.key, align=True, **to)
        aid.append(a)
        moved.append(target)
    elif answer_id == "delete":
        aid.append(dq_actions.delete_result(conn, row["id"], user, f.key))
    elif answer_id == "row_from_card":
        c = data.clients[f.client_ids[0]]
        diff = {k: str(c[k]) for k in FIO if str(row[k]) != str(c[k])}
        aid.append(dq_actions.edit_record(conn, "results", row["id"], diff, user, f.key)[1])
    elif answer_id in ("card_from_row", "other"):
        # только отличающиеся поля; сначала карточка (конфликт — ничего не записано), потом строка
        c = data.clients[f.client_ids[0]]
        want = fio if answer_id == "other" else {k: str(row[k]) for k in FIO}
        card_diff = {k: v for k, v in want.items() if _differs(k, v, c[k])}
        row_diff = {k: v for k, v in fio.items() if _differs(k, v, row[k])} if answer_id == "other" else {}
        if not card_diff and not row_diff:
            raise ValueError("значения не изменились")
        if card_diff:
            a, conflict = _edit_card(conn, f, c, card_diff, user)
            if conflict:
                return {"action_ids": [], "case": _case_after(conn, case, extra_cards), "conflict": conflict}
            aid.append(a)
        if row_diff:
            aid.append(dq_actions.edit_record(conn, "results", row["id"], row_diff, user, f.key)[1])
    elif answer_id.startswith("bd:"):
        # ДР карточки, затем её строки с заглушкой, «ГГГГ-01-01» того же года или прежней ДР карточки
        c = data.clients[f.client_ids[0]]
        new, old = answer_id[3:], c["birthday"]
        a, conflict = _edit_card(conn, f, c, {"birthday": new}, user)
        if conflict:
            return {"action_ids": [], "case": _case_after(conn, case, extra_cards), "conflict": conflict}
        aid.append(a)
        for t, rows in (("results", data.res_by_card[c["id"]]), ("leads", data.leads_by_card[c["id"]])):
            for r in rows:
                bd = r["birthday"]
                if bd != new and (not real_bd(bd) or bd == old or (jan1(bd) and bd[:4] == new[:4])):
                    aid.append(dq_actions.edit_record(conn, t, r["id"], {"birthday": new}, user, f.key)[1])
    elif answer_id.startswith("merge_with:"):
        other = _merge_target(data, f, answer_id, fio)
        aid.append(dq_actions.merge_cards(conn, [f.client_ids[0], other], fio["surname"], fio["name"],
                                          fio["birthday"], user, f.key)[1])
    elif answer_id in FIELDS:
        fields = {k: inputs[k] for k in FIELDS[answer_id] if inputs.get(k)}
        aid.append(dq_actions.edit_record(conn, table, row["id"], fields, user, f.key)[1])
    elif answer_id == "fix":
        aid.append(dq_actions.fix_fio(conn, row["id"], f.fix[0], f.fix[1], user, f.key)[1])
    elif answer_id == "manual":
        aid.append(dq_actions.fix_fio(conn, row["id"], fio.get("surname", ""), fio.get("name", ""), user, f.key)[1])
    return {"action_ids": aid, "case": _case_after(conn, case, [*moved, *extra_cards])}


@_invalidating
def postpone_case(conn, case_key, reason, user):
    """Отложить все вопросы дела (решение «postponed» с причиной, по умолчанию «не знаю ДР») -> id записей журнала."""
    _, case, decided = _case_by_key(conn, case_key)
    if not case:
        raise StaleQuestion("Дело изменилось — обновите")
    return _postpone(conn, case, decided, reason, user)


def list_cases(conn, status="open", event_id=None):
    """Очередь дел: open — есть нерешённые неотложенные вопросы; postponed — все вопросы отложены."""
    data, findings = _full(conn)
    decided = dq_actions.load_decisions(conn)
    out = []
    for c in _cases(data, findings, decided):
        open_ = {f.key for f in c["findings"] if f.key not in decided}
        if (status == "open") != bool(open_):
            continue
        if event_id and not any(f.event_id == event_id for f in c["findings"]) and not any(
                x["event_id"] == event_id for i in c["cards"] for x in data.res_by_card[i] + data.leads_by_card[i]):
            continue
        out.append({"key": c["key"], "title": c["title"], "cards": len(c["cards"]),
                    "questions_left": len(open_ or {f.key for f in c["findings"]}),
                    "events": sorted({data.event_label(f.event_id) for f in c["findings"] if f.event_id})})
    return sorted(out, key=lambda c: (c["title"], c["key"]))


def get_case(conn, case_key):
    """Дело по ключу (None — дела больше нет: все вопросы решены)."""
    data, case, decided = _case_by_key(conn, case_key, view=True)
    return case_view(case, data, decided, _today()) if case else None


def case_for_card(conn, client_id):
    """Дело человека по карточке — для поиска по ФИО: дело, где есть карточка или её тёзка (карточка добавляется
    к делу); нет такого — карточка и тёзки без вопросов (ключ «p<карточка>» — отвечать в нём не на что)."""
    data, cases, decided = _scoped(conn, {client_id}, view=True)
    if client_id not in data.clients:
        return None
    mine = {client_id, *_namesakes_of(data, client_id)}
    case = (next((c for c in cases if client_id in c["cards"]), None)
            or next((c for c in cases if mine & set(c["cards"])), None))
    if case:
        return case_view({**case, "cards": sorted({*case["cards"], client_id})}, data, decided, _today())
    c = data.clients[client_id]
    return case_view({"key": f"p{client_id}", "title": f'{c["surname"]} {c["name"]}', "cards": sorted(mine),
                      "findings": []}, data, decided, _today())
