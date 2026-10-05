"""
Присвоение стартовых номеров кнопкой в /admin (решения пользователя 2026-10-05):

- диапазон номеров — на дистанцию; у Детского забега — на год рождения (мальчики и
  девочки вместе, как в 2026: 2019 г.р. — 9000+), 500 м Детского — без номеров;
- диапазоны задаются в админке перед присвоением и запоминаются для события (bib_ranges);
- номер — одному человеку на дистанции: самая ранняя заявка (created_at, id), дубли — без номера;
- уже присвоенные номера не трогаются и заняты; новым — первые свободные номера диапазона
  в порядке подачи заявок; номер уникален на всё событие года (все дистанции);
- не хватает номеров или не задан диапазон — ничего не записывается, ошибка по группе.
"""

import dataclasses
import json
from datetime import datetime

KIDS_EVENT = "Детский забег"
NO_BIB_DISTANCES = {(KIDS_EVENT, "500 м")}


@dataclasses.dataclass
class Group:
    distance: str
    key: str                       # "" — вся дистанция; год рождения — для Детского
    leads: list                    # без номера, по порядку подачи — им присваиваем
    with_bib: int = 0              # людей с номером
    duplicates: int = 0            # лишних заявок тех же людей (без номера останутся)

    @property
    def label(self):
        return f"{self.distance}, {self.key} г.р." if self.key else self.distance


def first_lead_per_person(leads):
    """Одна заявка на человека на дистанции — самая ранняя (created_at, id): та же, что получает
    номер. Для «Экспорт CSV»: фильтр is_duplicate=0 выкидывал человека с дублем целиком (флаг
    ставится на все его заявки) — он не попадал в Copernico (решение пользователя 2026-10-05)."""
    first = {}
    for lead in sorted(leads, key=lambda l: (str(l.get("created_at")), l["id"])):
        first.setdefault((lead["client_id"], lead["event_id"]), lead)
    return list(first.values())


def _has_bib(lead):
    return bool(lead.get("start_number"))


def group_key(event_name, lead):
    if event_name == KIDS_EVENT:
        return str(lead["birthday"])[:4]
    return ""


def build_groups(event_name, leads):
    """leads: dict(id, client_id, event_id, event_distance, birthday, created_at, start_number)."""
    groups = {}
    taken = set()
    by_person = {}
    for lead in sorted(leads, key=lambda l: (str(l["created_at"]), l["id"])):
        if (event_name, lead["event_distance"]) in NO_BIB_DISTANCES:
            continue
        if _has_bib(lead):
            taken.add(int(lead["start_number"]))
        by_person.setdefault((lead["client_id"], lead["event_id"]), []).append(lead)
    for person_leads in by_person.values():
        first = person_leads[0]
        key = (first["event_distance"], group_key(event_name, first))
        g = groups.setdefault(key, Group(first["event_distance"], key[1], []))
        g.duplicates += len(person_leads) - 1
        if any(_has_bib(l) for l in person_leads):
            g.with_bib += 1
        else:
            g.leads.append(first)
    for g in groups.values():
        g.leads.sort(key=lambda l: (str(l["created_at"]), l["id"]))
    return sorted(groups.values(), key=lambda g: (g.distance, g.key)), taken


def plan(groups, ranges, taken):
    """ranges: {(distance, key): (start, end)}. -> (результат по группам, назначения [(lead_id, номер)], ошибок нет?)"""
    result, assignments, ok = [], [], True
    spans = []
    for (dist, key), (start, end) in ranges.items():
        if start is not None and end is not None:
            spans.append((int(start), int(end), dist, key))
    used = set(taken)
    for g in groups:
        row = {"distance": g.distance, "key": g.key, "label": g.label, "need": len(g.leads),
               "with_bib": g.with_bib, "duplicates": g.duplicates, "error": "", "first": None, "last": None, "free": 0}
        rng = ranges.get((g.distance, g.key))
        if not g.leads:
            result.append(row)
            continue
        if not rng or rng[0] is None or rng[1] is None:
            row["error"] = "не задан диапазон"
        else:
            start, end = int(rng[0]), int(rng[1])
            overlap = [f"{d}{', ' + k + ' г.р.' if k else ''}" for s, e, d, k in spans
                       if (d, k) != (g.distance, g.key) and s <= end and start <= e]
            if start < 1 or end < start:
                row["error"] = f"неверный диапазон {start}–{end}"
            elif overlap:
                row["error"] = f"диапазон {start}–{end} пересекается с: {', '.join(overlap)}"
            else:
                free = [n for n in range(start, end + 1) if n not in used]
                row["free"] = len(free)
                if len(free) < len(g.leads):
                    row["error"] = f"не хватает номеров: нужно {len(g.leads)}, свободно {len(free)} в {start}–{end}"
                else:
                    pairs = list(zip([l["id"] for l in g.leads], free))
                    used.update(n for _, n in pairs)
                    assignments += pairs
                    row["first"], row["last"] = pairs[0][1], pairs[-1][1]
        ok = ok and not row["error"]
        result.append(row)
    return result, (assignments if ok else []), ok


# ---------------------------------------------------------------- БД

def load_leads(conn, event_name, event_year):
    cur = conn.cursor(dictionary=True)
    cur.execute("""SELECT id, client_id, event_id, event_distance, birthday, created_at, start_number
                   FROM leads WHERE event_name = %s AND event_year = %s""", (event_name, int(event_year)))
    rows = cur.fetchall()
    cur.close()
    return rows


def load_ranges(conn, event_name):
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT distance, group_key, range_start, range_end FROM bib_ranges WHERE event_name = %s", (event_name,))
    rows = {(r["distance"], r["group_key"]): (r["range_start"], r["range_end"]) for r in cur.fetchall()}
    cur.close()
    return rows


def overview(conn, event_name, event_year):
    groups, taken = build_groups(event_name, load_leads(conn, event_name, event_year))
    saved = load_ranges(conn, event_name)
    return {
        "groups": [{"distance": g.distance, "key": g.key, "label": g.label, "need": len(g.leads), "with_bib": g.with_bib,
                    "duplicates": g.duplicates, "range": list(saved[(g.distance, g.key)]) if (g.distance, g.key) in saved else None,
                    "warning": _group_warning(event_name, event_year, g)}
                   for g in groups],
        "skipped": sorted(d for e, d in NO_BIB_DISTANCES if e == event_name),
        "taken": len(taken),
    }


KIDS_MAX_AGE = 14


def _group_warning(event_name, event_year, g):
    """Детский: год рождения группы даёт не детский возраст — почти всегда ДР родителя в заявке."""
    if event_name == KIDS_EVENT and g.key.isdigit():
        age = int(event_year) - int(g.key)
        if age < 1 or age > KIDS_MAX_AGE:
            return f"возраст {age} — проверьте даты рождения в заявках (вкладка «Качество данных»)"
    return ""


def preview(conn, event_name, event_year, ranges):
    groups, taken = build_groups(event_name, load_leads(conn, event_name, event_year))
    result, assignments, ok = plan(groups, ranges, taken)
    return {"groups": result, "ok": ok, "to_assign": len(assignments)}


def assign(conn, event_name, event_year, ranges, user):
    """Пересчитать план и записать одной транзакцией. Ошибка в любой группе — ничего не пишем.
    trg_leads_after_update переписывает телефон/email карточки контактами обновлённой заявки —
    контакты затронутых карточек сохраняются и возвращаются."""
    groups, taken = build_groups(event_name, load_leads(conn, event_name, event_year))
    result, assignments, ok = plan(groups, ranges, taken)
    if not ok:
        return {"groups": result, "ok": False, "assigned": 0}
    cur = conn.cursor(dictionary=True)
    try:
        if conn.in_transaction:                        # пул — autocommit=True: без явной транзакции
            conn.commit()                              # каждый UPDATE фиксировался бы сам по себе
        conn.start_transaction()
        ids = [lead_id for lead_id, _ in assignments]
        contacts = {}
        if ids:
            ph = ",".join(["%s"] * len(ids))
            cur.execute(f"""SELECT c.id, c.phone, c.email FROM clients c
                            WHERE c.id IN (SELECT client_id FROM leads WHERE id IN ({ph}))""", ids)
            contacts = {r["id"]: (r["phone"], r["email"]) for r in cur.fetchall()}
        written = 0
        for lead_id, bib in assignments:
            cur.execute("UPDATE leads SET start_number = %s WHERE id = %s AND (start_number IS NULL OR start_number = 0)",
                        (bib, lead_id))
            written += cur.rowcount
        if written != len(assignments):
            raise RuntimeError("заявки изменились во время присвоения — повторите")
        for cid, (phone, email) in contacts.items():
            cur.execute("UPDATE clients SET phone = %s, email = %s WHERE id = %s", (phone, email, cid))
        for (dist, key), (start, end) in ranges.items():
            if start is None or end is None:
                continue
            cur.execute("""INSERT INTO bib_ranges (event_name, distance, group_key, range_start, range_end, updated_by)
                           VALUES (%s, %s, %s, %s, %s, %s)
                           ON DUPLICATE KEY UPDATE range_start = VALUES(range_start), range_end = VALUES(range_end),
                                                   updated_by = VALUES(updated_by), updated_at = NOW()""",
                        (event_name, dist, key, int(start), int(end), user or ""))
        cur.execute("INSERT INTO dq_actions (action, finding_key, details, done_by) VALUES (%s, %s, %s, %s)",
                    ("assign_bibs", f"{event_name}:{event_year}",
                     json.dumps({"event_name": event_name, "event_year": event_year, "assigned": assignments,
                                 "at": datetime.now().isoformat()}, ensure_ascii=False), user or ""))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
    return {"groups": result, "ok": True, "assigned": len(assignments)}
