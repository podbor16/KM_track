"""
Действия по находкам «Качества данных»: решения (dq_decisions), склейка, перенос строки, правка полей,
удаление «Not started», ФИО в канонический вид; журнал dq_actions и отмена любого действия.
"""

import collections
import dataclasses
from datetime import datetime
import json
import os
import re
import tempfile

from src.analytics.client_merge import apply as apply_merge, recompute_aggregates
from src.analytics.db_results import recompute_duplicates
from src.analytics.dq_checks import (NOT_STARTED, SHORT_NAMES, cat_rule, load, merge_blockers,
                                     propose_birthday, real_bd, run_checks)
from src.common.names import norm, normalize_person_name

# ---------------------------------------------------------------- решения и действия (dq_decisions, dq_actions)

MERGEABLE = ("C-TWIN", "R-LEAD")
DECISIONS = ("different_people", "keep", "postponed")


def load_decisions(conn):
    cur = conn.cursor()
    cur.execute("SELECT finding_key, decision FROM dq_decisions")
    out = dict(cur.fetchall())
    cur.close()
    return out


def pending_findings(conn, event_ids=None):
    """Находки без запомненного решения -> (findings, data)."""
    data = load(conn)
    decided = load_decisions(conn)
    return [f for f in run_checks(data, event_ids) if f.key not in decided], data


def propose_final(ids, data):
    """Итог склейки -> (основная карточка, фамилия, имя, ДР): фамилия основной карточки,
    полная форма имени, ДР по хронометражу (None — не определить)."""
    surv = max(ids, key=lambda i: (len(data.leads_by_card[i]) + len(data.res_by_card[i]), -i))
    names = [data.clients[i]["name"] for i in ids]
    full = [n for n in names if norm(n) not in SHORT_NAMES] or names
    name = max(full, key=lambda n: (data.names.first.get(norm(n), 0), len(n)))
    surv_bd = data.clients[surv]["birthday"]
    bd = propose_birthday(ids, data) or (surv_bd if real_bd(surv_bd) else None)
    return surv, normalize_person_name(data.clients[surv]["surname"]), normalize_person_name(name), bd


def finding_view(f, data):
    """Находка для /admin: карточки с забегами, предохранители, предложение склейки."""
    cards = []
    for i in f.client_ids:
        c = data.clients.get(i)
        if not c:
            continue
        cards.append({
            "id": i, "surname": c["surname"], "name": c["name"], "birthday": c["birthday"],
            "results": sorted({f'{data.event_label(r["event_id"])} №{r["start_number"]} ({r["birthday"]}, {r["race_status"]})'
                               for r in data.res_by_card[i]}),
            "leads": sorted({data.event_label(l["event_id"]) for l in data.leads_by_card[i]}),
        })
    out = {**dataclasses.asdict(f), "key": f.key, "cards": cards,
           "event": data.event_label(f.event_id) if f.event_id else ""}
    out["record"] = edit_record_view(f, data)
    if f.code in MERGEABLE and len(cards) > 1:
        ids = [c["id"] for c in cards]
        _, s, n, bd = propose_final(ids, data)
        out["blockers"] = merge_blockers(ids, data)
        out["proposal"] = {"surname": s, "name": n, "birthday": bd or ""}
    return out


def edit_record_view(f, data):
    """Строка находки для формы «Исправить…»: результат или заявка с правимыми полями (None — нет строки)."""
    if f.lead_id and f.lead_id in data.lead_by_id:
        l = data.lead_by_id[f.lead_id]
        ev = data.events.get(l["event_id"], {})
        same = {i for i, e in data.events.items()
                if (e["event_name"], e["event_year"]) == (ev.get("event_name"), ev.get("event_year"))}
        options = sorted({x["event_distance"] for x in data.leads if x["event_id"] in same and x["event_distance"]},
                         key=lambda d: (distance_km(d) is None, distance_km(d) or 0, d))
        return {"table": "leads", "id": l["id"], **{k: l[k] for k in EDITABLE["leads"]}, "distance_options": options}
    if f.result_id and f.result_id in data.result_by_id:
        r = data.result_by_id[f.result_id]
        return {"table": "results", "id": r["id"], **{k: r[k] for k in EDITABLE["results"]},
                "category_options": category_options(data.res_by_event[r["event_id"]])}
    return None


def category_sex(category, sexes):
    """Пол категории: по названию («Ж30-34», «Девочки…»), иначе — единственный пол бежавших в ней; «» — любой."""
    sex = cat_rule(category, 0)[0]
    if sex:
        return SEXES[0] if sex == "М" else SEXES[1]
    sexes = {x for x in sexes if x in SEXES}
    return sexes.pop() if len(sexes) == 1 else ""


def _natural(text):
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", text)]


def category_options(results):
    """Категории протокола забега (одна дистанция = одно событие) с полом — для выпадающего списка."""
    sexes = collections.defaultdict(set)
    for r in results:
        if r["category"]:
            sexes[r["category"]].add(r["sex"])
    return [{"label": c, "sex": category_sex(c, sx)} for c, sx in sorted(sexes.items(), key=lambda x: _natural(x[0]))]


def _log_action(cur, action, key, details, user):
    """-> id записи журнала (по нему действие отменяется)."""
    cur.execute("INSERT INTO dq_actions (action, finding_key, details, done_by) VALUES (%s, %s, %s, %s)",
                (action, key or "", json.dumps(details, ensure_ascii=False, default=str), user or ""))
    return cur.lastrowid


def _save_decision(cur, key, decision, note, user):
    cur.execute("""INSERT INTO dq_decisions (finding_key, decision, note, decided_by) VALUES (%s, %s, %s, %s)
                   ON DUPLICATE KEY UPDATE decision = VALUES(decision), note = VALUES(note),
                                           decided_by = VALUES(decided_by), decided_at = NOW()""",
                (key, decision, note or "", user or ""))


def dismiss(conn, key, decision, note, user):
    """Запомнить решение по находке — больше не показывается. -> id записи журнала."""
    if decision not in DECISIONS:
        raise ValueError(f"решение: {', '.join(DECISIONS)}")
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT decision, note FROM dq_decisions WHERE finding_key = %s", (key,))
    prev = cur.fetchone()
    _save_decision(cur, key, decision, note, user)
    action_id = _log_action(cur, "dismiss", key, {"decision": decision, "note": note, "prev": prev}, user)
    conn.commit()
    cur.close()
    return action_id


def merge_cards(conn, ids, surname, name, birthday, user, key=""):
    """Склеить карточки в одну с итоговыми ФИ/ДР. Основная — с наибольшим числом заявок и результатов.
    Снимок «до» — в dq_actions. -> (основная карточка, id записи журнала)."""
    ids = sorted({int(i) for i in ids})
    surname, name = normalize_person_name(surname or ""), normalize_person_name(name or "")
    if len(ids) < 2:
        raise ValueError("нужно минимум две карточки")
    if not surname or not name or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", birthday or ""):
        raise ValueError("нужны фамилия, имя и ДР в формате ГГГГ-ММ-ДД")
    cur = conn.cursor(dictionary=True)
    ph = ",".join(["%s"] * len(ids))
    cur.execute(f"""SELECT c.id, (SELECT COUNT(*) FROM leads l WHERE l.client_id = c.id)
                                 + (SELECT COUNT(*) FROM results r WHERE r.client_id = c.id) n
                    FROM clients c WHERE c.id IN ({ph})""", ids)
    weight = {r["id"]: r["n"] for r in cur.fetchall()}
    if len(weight) != len(ids):
        cur.close()
        raise ValueError(f"нет карточек: {sorted(set(ids) - set(weight))}")
    cur.execute(f"SELECT id FROM clients WHERE surname = %s AND name = %s AND birthday = %s AND id NOT IN ({ph})",
                [surname, name, birthday] + ids)
    other = [r["id"] for r in cur.fetchall()]
    cur.close()
    if other:
        raise ValueError(f"такие ФИ и ДР уже у карточки #{other[0]} — добавьте её в склейку")
    surv = max(ids, key=lambda i: (weight[i], -i))
    merged_into = {i: surv for i in ids if i != surv}
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    try:
        apply_merge(conn, None, {surv: (surname, name, birthday)}, merged_into, path)
        with open(path, encoding="utf-8") as fh:
            snapshot = json.load(fh)
    finally:
        os.remove(path)
    cur = conn.cursor()
    action_id = _log_action(cur, "merge", key, {"survivor": surv, "merged": sorted(merged_into),
                                                "final": [surname, name, birthday], "before": snapshot}, user)
    conn.commit()
    cur.close()
    return surv, action_id


def fix_fio(conn, result_id, surname, name, user, key=""):
    """HYG «Исправить ФИО»: ФИО результата -> каноническое. Карточка с тем же ФИО, что у результата
    (заведена по нему, «Tsimis Егор»), переименовывается со всеми заявками и результатами, а если
    такие ФИ и ДР уже у другой карточки — склеивается с ней. Карточка уже в каноническом виде
    («Маркус Роман» при «Роман Маркус» в протоколе) — правится только строка результата.
    -> (карточка, id записи журнала)."""
    surname, name = normalize_person_name(surname or ""), normalize_person_name(name or "")
    if not surname or not name:
        raise ValueError("нужны фамилия и имя")
    cur = conn.cursor(dictionary=True)
    cur.execute("""SELECT r.id, r.client_id, r.surname, r.name, c.surname c_surname, c.name c_name, c.birthday
                   FROM results r JOIN clients c ON c.id = r.client_id WHERE r.id = %s""", (int(result_id),))
    row = cur.fetchone()
    if not row:
        cur.close()
        raise ValueError(f"нет результата #{result_id}")
    cid, bd = row["client_id"], row["birthday"]
    details = {"result_id": row["id"], "client_id": cid, "before": [row["surname"], row["name"]],
               "after": [surname, name]}
    if (norm(row["c_surname"]), norm(row["c_name"])) == (norm(row["surname"]), norm(row["name"])):
        cur.execute("SELECT id FROM clients WHERE surname = %s AND name = %s AND birthday = %s AND id <> %s",
                    (surname, name, bd, cid))
        others = [r["id"] for r in cur.fetchall()]
        cur.close()
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        try:
            apply_merge(conn, None, {cid: (surname, name, bd)}, {o: cid for o in others}, path)
            with open(path, encoding="utf-8") as fh:
                details["card_before"] = json.load(fh)
        finally:
            os.remove(path)
        details["merged"] = others
        cur = conn.cursor()
    else:
        cur.close()
        cur = conn.cursor()
        cur.execute("UPDATE results SET surname = %s, name = %s WHERE id = %s", (surname, name, row["id"]))
    action_id = _log_action(cur, "fix_fio", key, details, user)
    conn.commit()
    cur.close()
    return cid, action_id


def delete_result(conn, result_id, user, key=""):
    """Удалить «Not started», если у карточки есть другой результат в этом забеге (старый номер).
    -> id записи журнала."""
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM results WHERE id = %s", (int(result_id),))
    row = cur.fetchone()
    if not row:
        cur.close()
        raise ValueError(f"нет результата #{result_id}")
    cur.execute("SELECT COUNT(*) n FROM results WHERE client_id = %s AND event_id = %s AND id <> %s",
                (row["client_id"], row["event_id"], row["id"]))
    others = cur.fetchone()["n"]
    if row["race_status"] != NOT_STARTED or not others:
        cur.close()
        raise ValueError("удаляется только «Not started», когда у карточки есть другой результат в этом забеге")
    cur.execute("DELETE FROM results WHERE id = %s", (row["id"],))
    recompute_aggregates(cur, [row["client_id"]])
    action_id = _log_action(cur, "delete_result", key, {"before": row}, user)
    conn.commit()
    cur.close()
    return action_id


EDITABLE = {
    "results": ("surname", "name", "birthday", "sex", "category"),
    "leads": ("surname", "name", "birthday", "event_distance"),
    "clients": ("surname", "name", "birthday"),
}
SEXES = ("Мужчина", "Женщина")


def _clean_edit(table, fields):
    """Проверка и нормализация полей правки -> dict (только разрешённые поля таблицы)."""
    if table not in EDITABLE:
        raise ValueError(f"правка таблицы {table} не поддерживается")
    unknown = set(fields) - set(EDITABLE[table])
    if unknown:
        raise ValueError(f"поля {', '.join(sorted(unknown))} не правятся")
    out = {}
    for k, v in fields.items():
        v = str(v or "").strip()
        if k in ("surname", "name"):
            v = normalize_person_name(v)
            if not v:
                raise ValueError("фамилия и имя не могут быть пустыми")
        elif k == "birthday":
            try:
                datetime.strptime(v, "%Y-%m-%d")
            except ValueError:
                raise ValueError("ДР — в формате ГГГГ-ММ-ДД") from None
        elif k == "sex" and v not in SEXES:
            raise ValueError(f"пол: {', '.join(SEXES)}")
        elif k in ("category", "event_distance") and not v:
            raise ValueError("категория и дистанция не могут быть пустыми")
        out[k] = v
    if not out:
        raise ValueError("нет полей для правки")
    return out


def _lead_event_id(cur, row, distance):
    """Событие того же забега и года с другой дистанцией (новые события не заводим)."""
    cur.execute("""SELECT e2.id FROM events e JOIN events e2 ON e2.event_name = e.event_name AND e2.event_year = e.event_year
                   WHERE e.id = %s AND e2.event_distance = %s""", (row["event_id"], distance_km(distance)))
    found = cur.fetchone()
    if not found:
        raise ValueError(f"у этого забега нет дистанции «{distance}»")
    return found["id"]


def distance_km(text):
    """«500 м» -> 0.5, «1 км» / «21.1» -> число (как trg_leads_before_insert)."""
    t = str(text).strip().replace(",", ".")
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(км|м)?", t)
    if not m:
        return None
    v = float(m.group(1))
    return round(v / 1000, 1) if m.group(2) == "м" else v


def _check_category_sex(cur, row_id, category, sex):
    cur.execute("""SELECT DISTINCT r2.sex FROM results r JOIN results r2 ON r2.event_id = r.event_id
                   WHERE r.id = %s AND r2.category = %s AND r2.id <> r.id""", (int(row_id), category))
    need = category_sex(category, {x["sex"] for x in cur.fetchall()})
    if need and need != sex:
        raise ValueError(f"категория «{category}» — для пола «{need}»")


RANK_COLS = {"category": ("rank_category", "rank_category_clean"), "sex": ("rank_sex", "rank_sex_clean")}
RANK_FIELDS = RANK_COLS["category"] + RANK_COLS["sex"]


def _finish_key(t, ms):
    return None if t is None else (int(t.total_seconds()), (ms % 1000) if ms is not None else 0)


def _neighbor_rank(me_key, group, rank_col, time_key):
    """Место первого не быстрее (место на двоих); медленнее никого — последнее + 1 (пустая группа — 1)."""
    others = [r for r in group if r[time_key] is not None and r[rank_col] is not None]
    slower = [r for r in others if r[time_key] >= me_key]
    if slower:
        return min(slower, key=lambda r: (r[time_key], r[rank_col]))[rank_col]
    return max((r[rank_col] for r in others), default=0) + 1


def _neighbor_ranks(cur, row_id, category, sex, fields):
    """Места строки результата в новой категории (и при смене пола — среди пола) по правилу «как у соседа снизу»
    (решение пользователя 2026-10-28): места остальных участников не трогаем. Колонку места ставим, только если
    в забеге места есть (у строки или у кого-то в событии); чистое — ещё и при чистом времени строки. -> {колонка: место}."""
    cur.execute(f"""SELECT event_id, race_status, time_gun_finish, time_gun_finish_ms, time_clear_finish,
                           time_clear_finish_ms, {', '.join(RANK_FIELDS)} FROM results WHERE id = %s""", (row_id,))
    me = cur.fetchone()
    if not me or me["race_status"] != "Finished" or me["time_gun_finish"] is None:
        return {}
    cur.execute("""SELECT id, sex, category, time_gun_finish, time_gun_finish_ms, time_clear_finish, time_clear_finish_ms,
                          rank_category, rank_category_clean, rank_sex, rank_sex_clean
                   FROM results WHERE event_id = %s AND id <> %s AND race_status = 'Finished'
                     AND time_gun_finish IS NOT NULL""", (me["event_id"], row_id))
    rows = cur.fetchall()
    for r in rows + [me]:
        r["g"] = _finish_key(r["time_gun_finish"], r["time_gun_finish_ms"])
        r["c"] = _finish_key(r["time_clear_finish"], r["time_clear_finish_ms"])
    def has_ranks(col):
        return me[col] is not None or any(r[col] is not None for r in rows)

    out = {}
    for field, value in (("category", category), ("sex", sex)):
        if field not in fields:
            continue
        group = [r for r in rows if r[field] == value]
        gun_col, clean_col = RANK_COLS[field]
        if has_ranks(gun_col):
            out[gun_col] = _neighbor_rank(me["g"], group, gun_col, "g")
        if me["c"] is not None and has_ranks(clean_col):
            out[clean_col] = _neighbor_rank(me["c"], group, clean_col, "c")
    return out


def edit_record(conn, table, row_id, fields, user, key=""):
    """Правка полей строки находки: результата, заявки или карточки. В журнал — значения «до» и «после»
    изменённых полей; отмена возвращает «до». Карточке нельзя дать ФИ+ДР другой карточки — это склейка.
    -> (карточка, id записи журнала)."""
    fields = _clean_edit(table, fields)
    cols = list(EDITABLE[table]) + (["event_id"] if table == "leads" else []) + (list(RANK_FIELDS) if table == "results" else [])
    cur = conn.cursor(dictionary=True)
    try:
        cid_col = "id" if table == "clients" else "client_id"
        cur.execute(f"SELECT {cid_col} AS cid, {', '.join(cols)} FROM {table} WHERE id = %s", (int(row_id),))
        row = cur.fetchone()
        if not row or (table == "clients" and not row["cid"]):
            raise ValueError(f"нет строки #{row_id}")
        before = {k: str(row[k]) if row[k] is not None else None for k in cols}
        changed = {k: v for k, v in fields.items() if before.get(k) != v}
        if table == "leads" and "event_distance" in changed:
            changed["event_id"] = _lead_event_id(cur, row, changed["event_distance"])
        if not changed:
            raise ValueError("значения не изменились")
        if table == "results" and {"sex", "category"} & set(changed):
            _check_category_sex(cur, row_id, changed.get("category", before["category"]), changed.get("sex", before["sex"]))
            ranks = _neighbor_ranks(cur, row_id, changed.get("category", before["category"]),
                                    changed.get("sex", before["sex"]), set(changed))
            changed.update({k: v for k, v in ranks.items() if str(v) != before.get(k)})
        if table == "clients":
            final = {k: changed.get(k, before[k]) for k in ("surname", "name", "birthday")}
            cur.execute("SELECT id FROM clients WHERE surname = %s AND name = %s AND birthday = %s AND id <> %s",
                        (final["surname"], final["name"], final["birthday"], row["cid"]))
            other = cur.fetchone()
            if other:
                raise ValueError(f"такие ФИ и ДР уже у карточки #{other['id']} — склейте карточки")
        cur.execute(f"UPDATE {table} SET {', '.join(f'`{k}` = %s' for k in changed)} WHERE id = %s",
                    [*changed.values(), int(row_id)])
        if "event_id" in changed:
            recompute_duplicates(cur, [row["cid"]])
        action_id = _log_action(cur, "edit", key, {"table": table, "id": int(row_id), "client_id": row["cid"],
                                                    "before": {k: before[k] for k in changed},
                                                    "after": {k: str(v) for k, v in changed.items()}}, user)
        conn.commit()
        return row["cid"], action_id
    except Exception:
        if conn.in_transaction:
            conn.rollback()
        raise
    finally:
        cur.close()


CARD_SEARCH_LIMIT = 20


def search_cards(conn, q, limit=CARD_SEARCH_LIMIT):
    """Карточки по ФИО (начало фамилии и имени, в любом порядке) -> [{id, surname, name, birthday, events}]."""
    words = [w for w in re.split(r"\s+", normalize_person_name(q or "")) if w][:2]
    if not words or len(words[0]) < 2:
        return []
    like = [w.replace("%", "").replace("_", "") + "%" for w in words]
    if len(like) == 1:
        where, args = "surname LIKE %s", like
    else:
        where, args = "(surname LIKE %s AND name LIKE %s) OR (surname LIKE %s AND name LIKE %s)", like + like[::-1]
    cur = conn.cursor(dictionary=True)
    cur.execute(f"SELECT id, surname, name, birthday FROM clients WHERE id <> 0 AND ({where}) "
                f"ORDER BY surname, name, birthday LIMIT %s", (*args, int(limit)))
    cards = cur.fetchall()
    if cards:
        ph = ",".join(str(c["id"]) for c in cards)
        cur.execute(f"""SELECT x.client_id, e.event_name, e.event_distance, e.event_year, x.kind FROM (
                            SELECT client_id, event_id, 'результат' kind FROM results WHERE client_id IN ({ph})
                            UNION SELECT client_id, event_id, 'заявка' FROM leads WHERE client_id IN ({ph})) x
                        JOIN events e ON e.id = x.event_id ORDER BY e.event_year, e.event_name""")
        events = collections.defaultdict(list)
        for r in cur.fetchall():
            events[r["client_id"]].append(f'{r["event_name"]} {r["event_distance"]} {r["event_year"]} ({r["kind"]})'
                                          .replace(".0 ", " "))
        for c in cards:
            c["birthday"] = str(c["birthday"])
            c["events"] = events[c["id"]]
    cur.close()
    return cards


def _card_by_fio(cur, surname, name, birthday, exclude=0):
    cur.execute("SELECT id FROM clients WHERE surname = %s AND name = %s AND birthday = %s AND id <> %s",
                (surname, name, birthday, exclude))
    row = cur.fetchone()
    return row["id"] if row else None


MOVABLE = {"results": "результат", "leads": "заявка"}
CONTACTS = ("phone", "email", "city", "club")


def move_row(conn, table, row_id, user, key="", to_client_id=None, new_card=None, align=False):
    """Перенести результат или заявку на другую карточку — существующую (to_client_id) или новую (new_card: фамилия,
    имя, ДР). ФИ и ДР строки не меняются. Опустевшая прежняя карточка удаляется (отмена её вернёт). Заявка
    переносит на карточку свои контакты (trg_leads_after_update) — снимок контактов обеих карточек в журнале.
    align=True — строка получает ФИ и ДР новой карточки (снимок «до» — в журнале).
    -> (карточка, id записи журнала)."""
    if table not in MOVABLE:
        raise ValueError(f"перенос из {table} не поддерживается")
    what = MOVABLE[table]
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute(f"SELECT id, client_id FROM {table} WHERE id = %s", (int(row_id),))
        row = cur.fetchone()
        if not row:
            raise ValueError(f"нет строки #{row_id}")
        src = row["client_id"]
        created = False
        if new_card:
            f = _clean_edit("clients", {k: new_card.get(k, "") for k in ("surname", "name", "birthday")})
            if len(f) < 3:
                raise ValueError("для новой карточки нужны фамилия, имя и ДР")
            other = _card_by_fio(cur, f["surname"], f["name"], f["birthday"])
            if other:
                raise ValueError(f"такие ФИ и ДР уже у карточки #{other} — выберите её")
            cur.execute("INSERT INTO clients (surname, name, birthday) VALUES (%s, %s, %s)",
                        (f["surname"], f["name"], f["birthday"]))
            target, created = cur.lastrowid, True
        else:
            target = int(to_client_id or 0)
            cur.execute("SELECT id FROM clients WHERE id = %s AND id <> 0", (target,))
            if not cur.fetchone():
                raise ValueError(f"нет карточки #{to_client_id}")
        if target == src:
            raise ValueError(f"{what} уже на этой карточке")
        cur.execute(f"SELECT id, {', '.join(CONTACTS)} FROM clients WHERE id IN (%s, %s)", (src, target))
        contacts = {str(c.pop("id")): c for c in cur.fetchall()}
        cur.execute(f"UPDATE {table} SET client_id = %s WHERE id = %s", (target, row["id"]))
        row_before = None
        if align:
            cur.execute(f"SELECT surname, name, birthday FROM {table} WHERE id = %s", (row["id"],))
            row_before = {k: str(v) for k, v in cur.fetchone().items()}
            cur.execute(f"""UPDATE {table} r JOIN clients c ON c.id = %s
                            SET r.surname = c.surname, r.name = c.name, r.birthday = c.birthday WHERE r.id = %s""",
                        (target, row["id"]))
        deleted = None
        cur.execute("""SELECT c.* FROM clients c WHERE c.id = %s
                       AND NOT EXISTS (SELECT 1 FROM leads l WHERE l.client_id = c.id)
                       AND NOT EXISTS (SELECT 1 FROM results r WHERE r.client_id = c.id)""", (src,))
        empty = cur.fetchone()
        if empty:
            deleted = dict(empty)
            cur.execute("DELETE FROM clients WHERE id = %s", (src,))
        live = [target] if empty else [src, target]
        recompute_aggregates(cur, live)
        if table == "leads":
            recompute_duplicates(cur, live)
        action_id = _log_action(cur, "move_result", key, {"table": table, "row_id": row["id"], "from": src, "to": target,
                                                           "created": created, "deleted_card": deleted,
                                                           "contacts": contacts, "row_before": row_before}, user)
        conn.commit()
        return target, action_id
    except Exception:
        if conn.in_transaction:
            conn.rollback()
        raise
    finally:
        cur.close()


def apply_auto(conn, user):
    """Очевидное без ревью: «Not started» со старым номером; двойники и R-LEAD уровня high,
    если склейке не мешает ни один предохранитель и ДР определяется."""
    findings, data = pending_findings(conn)
    done = {"deleted": [], "merged": [], "skipped": []}
    for f in findings:
        if f.code == "R-DUP" and f.auto:
            try:
                delete_result(conn, f.result_id, user, f.key)
                done["deleted"].append(f.message)
            except ValueError as e:
                done["skipped"].append(f"{f.message}: {e}")
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for f in findings:
        if f.code in MERGEABLE and f.severity == "high":
            a, b = f.client_ids
            parent[find(a)] = find(b)
    comps = collections.defaultdict(set)
    for i in list(parent):
        comps[find(i)].add(i)
    for ids in comps.values():
        ids = sorted(ids)
        label = " + ".join(data.card_label(i) for i in ids)
        blockers = merge_blockers(ids, data)
        _, s, n, bd = propose_final(ids, data)
        if blockers or not bd:
            done["skipped"].append(f'{label}: {"; ".join(blockers) or "ДР не определить"}')
            continue
        try:
            merge_cards(conn, ids, s, n, bd, user, "auto")
            done["merged"].append(f"{label} -> {s} {n} {bd}")
        except ValueError as e:
            done["skipped"].append(f"{label}: {e}")
    return done


# ---------------------------------------------------------------- отмена действий (запись «undo» в dq_actions)

UNDOABLE = ("merge", "fix_fio", "delete_result", "dismiss", "edit", "move_result")


def _cards_of(action, d):
    """Карточки, которых касалось действие (для порядка отмен)."""
    if action == "merge":
        return {d["survivor"], *d["merged"]}
    if action == "fix_fio":
        return {d["client_id"], *d.get("merged", [])}
    if action == "delete_result":
        return {d["before"]["client_id"]}
    if action == "edit":
        return {d["client_id"]}
    if action == "move_result":
        return {d["from"], d["to"]}
    return set()


def _describe(action, d):
    if action == "merge":
        cards = " + ".join(f'#{c["id"]} {c["surname"]} {c["name"]} {c["birthday"]}'
                           for c in d.get("before", {}).get("clients", []))
        return f'Склейка: {cards} → #{d["survivor"]} {" ".join(map(str, d["final"]))}'
    if action == "fix_fio":
        return f'Исправление ФИО: {" ".join(d["before"])} → {" ".join(d["after"])} (карточка #{d["client_id"]})'
    if action == "delete_result":
        b = d["before"]
        return f'Удалён «Not started»: {b["surname"]} {b["name"]} №{b["start_number"]} (забег #{b["event_id"]})'
    if action == "edit":
        what = {"results": "результат", "leads": "заявка", "clients": "карточка"}[d["table"]]
        diff = ", ".join(f'{EDIT_LABELS.get(k, k)} {d["before"][k]} → {d["after"][k]}'
                         for k in d["after"] if k in EDIT_LABELS)
        card = "" if d["table"] == "clients" else f', карточка #{d["client_id"]}'
        return f'Правка ({what} #{d["id"]}{card}): {diff}'
    if action == "move_result":
        how = "новую карточку" if d["created"] else "карточку"
        tail = f' (пустая карточка #{d["from"]} удалена)' if d.get("deleted_card") else ""
        what = "заявки" if d.get("table") == "leads" else "результата"
        return f'Перенос {what} #{d.get("row_id", d.get("result_id"))}: с карточки #{d["from"]} на {how} #{d["to"]}{tail}'
    if action == "dismiss":
        label = {"different_people": "разные люди", "keep": "оставить как есть", "postponed": "отложено"}.get(d["decision"], d["decision"])
        return f"Решение: {label}" + (f' ({d["note"]})' if d.get("note") else "")
    return action


def _load_actions(cur, since_id=0):
    """Действия журнала с id >= since_id по порядку + множество отменённых id."""
    cur.execute("SELECT id, action, finding_key, details, done_by, done_at FROM dq_actions WHERE id >= %s ORDER BY id",
                (int(since_id),))
    rows = cur.fetchall()
    for r in rows:
        if isinstance(r["details"], (str, bytes, bytearray)):
            r["details"] = json.loads(r["details"])
    undone = {r["details"].get("undo_of") for r in rows if r["action"] == "undo"}
    return rows, undone


def _undo_blocker(row, later, undone):
    """Почему действие нельзя отменить (None — можно)."""
    if row["action"] not in UNDOABLE:
        return "это действие не отменяется"
    if row["id"] in undone:
        return "уже отменено"
    cards = _cards_of(row["action"], row["details"])
    for x in later:
        if x["action"] in UNDOABLE and x["id"] not in undone and cards & _cards_of(x["action"], x["details"]):
            return f'сначала отмените более позднее действие #{x["id"]} с теми же карточками'
    return None


def recent_actions(conn, limit=50):
    """Последние действия для /admin (новые сверху): описание, отменено ли, можно ли отменить."""
    cur = conn.cursor(dictionary=True)
    ph = ",".join(["%s"] * len(UNDOABLE))
    cur.execute(f"SELECT COALESCE(MIN(id), 0) m FROM (SELECT id FROM dq_actions WHERE action IN ({ph}) "
                "ORDER BY id DESC LIMIT %s) t", (*UNDOABLE, int(limit)))
    rows, undone = _load_actions(cur, cur.fetchone()["m"])
    cur.close()
    acts = [r for r in rows if r["action"] in UNDOABLE]
    out = []
    for k, r in enumerate(acts):
        blocker = _undo_blocker(r, acts[k + 1:], undone)
        out.append({"id": r["id"], "action": r["action"], "key": r["finding_key"],
                    "text": _describe(r["action"], r["details"]), "done_by": r["done_by"],
                    "done_at": str(r["done_at"]), "undone": r["id"] in undone,
                    "can_undo": blocker is None, "why_not": blocker or ""})
    return out[::-1]


def _restore_cards(cur, snap):
    """Карточки, заявки и результаты — как в снимке client_merge.apply (удалённые карточки — с прежними id)."""
    clients = snap.get("clients", [])
    ids = [c["id"] for c in clients]
    ph = ",".join(["%s"] * len(ids))
    cur.execute(f"SELECT id FROM clients WHERE id IN ({ph})", ids)
    existing = {r["id"] for r in cur.fetchall()}
    for c in clients:
        cur.execute(f"SELECT id FROM clients WHERE surname = %s AND name = %s AND birthday = %s AND id NOT IN ({ph})",
                    [c["surname"], c["name"], c["birthday"]] + ids)
        other = cur.fetchone()
        if other:
            raise ValueError(f'{c["surname"]} {c["name"]} {c["birthday"]} уже у карточки #{other["id"]} — отмена невозможна')
    # два шага, как в client_merge.apply: не упереться в uk_client при обмене ФИ/ДР
    for i in existing:
        cur.execute("UPDATE clients SET surname = CONCAT('~', id) WHERE id = %s", (i,))
    for c in clients:
        cols = [k for k in c if k != "id"]
        if c["id"] in existing:
            cur.execute(f"UPDATE clients SET {', '.join(f'`{k}` = %s' for k in cols)} WHERE id = %s",
                        [c[k] for k in cols] + [c["id"]])
        else:
            cur.execute(f"INSERT INTO clients (`id`, {', '.join(f'`{k}`' for k in cols)}) "
                        f"VALUES ({', '.join(['%s'] * (len(cols) + 1))})", [c["id"]] + [c[k] for k in cols])
    for table in ("leads", "results"):
        for r in snap.get(table, []):
            cur.execute(f"UPDATE {table} SET client_id = %s, surname = %s, name = %s, birthday = %s WHERE id = %s",
                        (r["client_id"], r["surname"], r["name"], r["birthday"], r["id"]))
    # trg_leads_after_update переписывает телефон/почту карточки данными заявки — вернуть как было
    for c in clients:
        cur.execute("UPDATE clients SET phone = %s, email = %s WHERE id = %s", (c.get("phone"), c.get("email"), c["id"]))
    recompute_aggregates(cur, ids)
    recompute_duplicates(cur, ids)


def _restore_result(cur, row):
    """Удалённый результат — обратно с прежним id и карточкой (триггер вставки сам выбирает карточку)."""
    cur.execute("SELECT id FROM clients WHERE id = %s", (row["client_id"],))
    if not cur.fetchone():
        raise ValueError(f'карточки #{row["client_id"]} уже нет — отмена невозможна')
    cur.execute("SELECT COALESCE(MAX(id), 0) m FROM clients")
    max_client = cur.fetchone()["m"]
    cols = list(row)
    cur.execute(f"INSERT INTO results ({', '.join(f'`{k}`' for k in cols)}) VALUES ({', '.join(['%s'] * len(cols))})",
                [row[k] for k in cols])
    cur.execute("SELECT client_id FROM results WHERE id = %s", (row["id"],))
    picked = cur.fetchone()["client_id"]
    cur.execute("UPDATE results SET client_id = %s WHERE id = %s", (row["client_id"], row["id"]))
    cur.execute("""DELETE c FROM clients c WHERE c.id > %s
                   AND NOT EXISTS (SELECT 1 FROM leads l WHERE l.client_id = c.id)
                   AND NOT EXISTS (SELECT 1 FROM results r WHERE r.client_id = c.id)""", (max_client,))
    cur.execute("SELECT id FROM clients WHERE id IN (%s, %s)", (row["client_id"], picked))
    recompute_aggregates(cur, [r["id"] for r in cur.fetchall()])


EDIT_LABELS = {"surname": "фамилия", "name": "имя", "birthday": "ДР", "sex": "пол", "category": "категория",
               "event_distance": "дистанция", "rank_category": "место в категории",
               "rank_category_clean": "место в категории (чистое)", "rank_sex": "место среди пола",
               "rank_sex_clean": "место среди пола (чистое)"}


def _restore_edit(cur, d):
    """Правку — обратно к значениям «до»; карточке — если её прежние ФИ+ДР не заняла другая."""
    b = d["before"]
    if d["table"] == "clients":
        cur.execute("SELECT surname, name, birthday FROM clients WHERE id = %s", (d["client_id"],))
        now = cur.fetchone()
        if not now:
            raise ValueError(f'карточки #{d["client_id"]} уже нет — отмена невозможна')
        final = {k: b.get(k, str(now[k])) for k in ("surname", "name", "birthday")}
        cur.execute("SELECT id FROM clients WHERE surname = %s AND name = %s AND birthday = %s AND id <> %s",
                    (final["surname"], final["name"], final["birthday"], d["client_id"]))
        other = cur.fetchone()
        if other:
            raise ValueError(f'{" ".join(final.values())} уже у карточки #{other["id"]} — отмена невозможна')
    cur.execute(f'UPDATE {d["table"]} SET {", ".join(f"`{k}` = %s" for k in b)} WHERE id = %s',
                [*b.values(), d["id"]])
    if "event_id" in b:
        recompute_duplicates(cur, [d["client_id"]])


def _restore_move(cur, d):
    """Строку — обратно на прежнюю карточку (удалённую — вернуть с прежним id); созданную переносом — удалить;
    контакты карточек — как до переноса (их переписывает триггер заявок)."""
    table, row_id = d.get("table", "results"), d.get("row_id", d.get("result_id"))
    card = d.get("deleted_card")
    if card:
        if _card_by_fio(cur, card["surname"], card["name"], card["birthday"]):
            raise ValueError(f'{card["surname"]} {card["name"]} {card["birthday"]} уже у другой карточки — отмена невозможна')
        cols = list(card)
        cur.execute(f"INSERT INTO clients ({', '.join(f'`{k}`' for k in cols)}) VALUES ({', '.join(['%s'] * len(cols))})",
                    [card[k] for k in cols])
    cur.execute(f"UPDATE {table} SET client_id = %s WHERE id = %s", (d["from"], row_id))
    if d.get("row_before"):
        b = d["row_before"]
        cur.execute(f"UPDATE {table} SET surname = %s, name = %s, birthday = %s WHERE id = %s",
                    (b["surname"], b["name"], b["birthday"], row_id))
    if d["created"]:
        cur.execute("""DELETE c FROM clients c WHERE c.id = %s
                       AND NOT EXISTS (SELECT 1 FROM leads l WHERE l.client_id = c.id)
                       AND NOT EXISTS (SELECT 1 FROM results r WHERE r.client_id = c.id)""", (d["to"],))
    for cid, c in (d.get("contacts") or {}).items():
        cur.execute(f"UPDATE clients SET {', '.join(f'{k} = %s' for k in c)} WHERE id = %s", [*c.values(), int(cid)])
    cur.execute("SELECT id FROM clients WHERE id IN (%s, %s)", (d["from"], d["to"]))
    live = [r["id"] for r in cur.fetchall()]
    recompute_aggregates(cur, live)
    if table == "leads":
        recompute_duplicates(cur, live)


def undo_action(conn, action_id, user):
    """Отменить действие из журнала по снимку «до». Нельзя, если уже отменено или после него было
    неотменённое действие с теми же карточками (сначала отменить его). -> id записи «undo»."""
    cur = conn.cursor(dictionary=True)
    try:
        rows, undone = _load_actions(cur, action_id)
        if not rows or rows[0]["id"] != int(action_id):
            raise ValueError(f"нет действия #{action_id}")
        row, d = rows[0], rows[0]["details"]
        blocker = _undo_blocker(row, rows[1:], undone)
        if blocker:
            raise ValueError(blocker)
        if conn.in_transaction:
            conn.commit()
        conn.start_transaction()
        if row["action"] == "merge":
            _restore_cards(cur, d["before"])
        elif row["action"] == "fix_fio":
            if "card_before" in d:
                _restore_cards(cur, d["card_before"])
            else:
                cur.execute("UPDATE results SET surname = %s, name = %s WHERE id = %s", (*d["before"], d["result_id"]))
        elif row["action"] == "delete_result":
            _restore_result(cur, d["before"])
        elif row["action"] == "edit":
            _restore_edit(cur, d)
        elif row["action"] == "move_result":
            _restore_move(cur, d)
        elif d.get("prev"):
            _save_decision(cur, row["finding_key"], d["prev"]["decision"], d["prev"]["note"], user)
        else:
            cur.execute("DELETE FROM dq_decisions WHERE finding_key = %s AND decision = %s",
                        (row["finding_key"], d["decision"]))
        undo_id = _log_action(cur, "undo", row["finding_key"], {"undo_of": row["id"], "action": row["action"]}, user)
        conn.commit()
        return undo_id
    except Exception:
        if conn.in_transaction:
            conn.rollback()
        raise
    finally:
        cur.close()
