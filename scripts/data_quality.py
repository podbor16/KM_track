#!/usr/bin/env python3
"""
Проверка привязки заявок и результатов к карточкам клиентов (только чтение).

Карточку триггеры ищут по точному «фамилия + имя + ДР», поэтому заглушка ДР в
протоколе, опечатка или «Ира» вместо «Ирина» создают новую карточку. Проверки
находят такие случаи; предохранители говорят, когда склеивать нельзя.
Правило ДР: хронометраж важнее заявки (решение пользователя 2026-10-01).

  python scripts/data_quality.py                         # вся база
  python scripts/data_quality.py --event-id 116          # результаты одного забега
  python scripts/data_quality.py --json findings.json
"""

import argparse
import collections
import dataclasses
import itertools
import json
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.clean_clients import SENTINELS, Names, _near_bd, canonical_fio, lev, norm

NOT_STARTED = "Not started"

# уменьшительные и разговорные формы -> полное имя (в обе стороны не нужно: сравниваем пары)
SHORT_NAMES = {
    "ира": "ирина", "иришка": "ирина", "аня": "анна", "анюта": "анна", "нюта": "анна", "софа": "софия",
    "софка": "софия", "саша": "александр", "женя": "евгений", "катя": "екатерина", "наташа": "наталья",
    "лена": "елена", "оля": "ольга", "таня": "татьяна", "юля": "юлия", "юлька": "юлия", "юлечка": "юлия",
    "дима": "дмитрий", "макс": "максим", "сема": "семен", "серега": "сергей", "вова": "владимир",
    "леша": "алексей", "миша": "михаил", "коля": "николай", "паша": "павел", "настя": "анастасия",
    "маша": "мария", "даша": "дарья", "валера": "валерий", "карюша": "карина", "гора": "егор",
    "светла": "светлана",
}


@dataclasses.dataclass
class Finding:
    code: str
    severity: str                       # high / medium / low
    message: str
    client_ids: tuple = ()
    result_id: int = None
    event_id: int = None
    auto: bool = False                  # можно исправить без ревью


# ---------------------------------------------------------------- данные

class Data:
    """Строки clients/leads/results/events (dict) + индексы."""

    def __init__(self, clients, leads, results, events):
        self.clients = {int(c["id"]): c for c in clients}
        self.events = {int(e["id"]): e for e in events}
        self.leads, self.results = leads, results
        self.leads_by_card = collections.defaultdict(list)
        self.res_by_card = collections.defaultdict(list)
        self.leads_by_event = collections.defaultdict(list)
        for l in leads:
            self.leads_by_card[l["client_id"]].append(l)
            self.leads_by_event[l["event_id"]].append(l)
        for r in results:
            self.res_by_card[r["client_id"]].append(r)
        self.cards_by_fio = collections.defaultdict(list)
        for i, c in self.clients.items():
            self.cards_by_fio[fio_key(c)].append(i)
        self.names = Names([(r["surname"], r["name"], r.get("sex", "")) for r in leads + results])

    def year(self, event_id):
        return int(self.events.get(event_id, {}).get("event_year") or 0)

    def event_label(self, event_id):
        e = self.events.get(event_id, {})
        return f'{e.get("event_name", "?")} {e.get("event_distance", "")} {e.get("event_year", "")}'.replace("  ", " ").strip()

    def card_label(self, i):
        c = self.clients.get(i, {})
        return f'#{i} {c.get("surname", "")} {c.get("name", "")} {c.get("birthday", "")}'


def fio_key(row):
    return norm(row["surname"]), norm(row["name"])


def load(conn):
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT id, surname, name, birthday FROM clients WHERE id <> 0")
    clients = cur.fetchall()
    cur.execute("SELECT id, client_id, surname, name, birthday, sex, event_id, start_number FROM leads")
    leads = cur.fetchall()
    cur.execute("""SELECT id, client_id, surname, name, birthday, sex, event_id, start_number, category, race_status
                   FROM results""")
    results = cur.fetchall()
    cur.execute("SELECT id, event_name, event_distance, event_year FROM events")
    events = cur.fetchall()
    cur.close()
    for r in clients + leads + results:
        r["birthday"] = str(r["birthday"])
    return Data(clients, leads, results, events)


# ---------------------------------------------------------------- правила

def jan1(bd):
    return bd.endswith("-01-01")


def real_bd(bd):
    return bool(bd) and bd not in SENTINELS


def compatible_bd(x, y):
    """Две ДР могут быть у одного человека: заглушка, «ГГГГ-01-01» того же года,
    опечатка в цифре / день↔месяц, год регистрации вместо года рождения."""
    if not real_bd(x) or not real_bd(y) or x == y or _near_bd(x, y):
        return True
    if x[:4] == y[:4] and (jan1(x) or jan1(y)):
        return True
    return x[5:] == y[5:] and max(int(x[:4]), int(y[:4])) >= 2023


def names_compatible(a, b, names):
    """Одно и то же имя: равны, уменьшительное, обрезанное («Светла»), но не пара по полу (Виктор/Виктория)."""
    a, b = norm(a), norm(b)
    if a == b or SHORT_NAMES.get(a) == b or SHORT_NAMES.get(b) == a:
        return True
    short, long_ = sorted((a, b), key=len)
    if long_ in (short + "а", short + "я", short + "ия"):       # Ратмир/Ратмира, Виктор/Виктория
        return False
    sa, sb = names.sex.get(a), names.sex.get(b)
    if sa and sb and sa != sb:
        return False
    return len(short) >= 3 and long_.startswith(short)


def cat_rule(cat, year):
    """Категория -> (пол, мин. год рождения, макс. год рождения)."""
    c = (cat or "").strip().lower()
    sex = "Ж" if re.match(r"(ж|жен|дев)", c) else "М" if re.match(r"(м|муж|мал)", c) else ""
    lo = hi = None
    if m := re.search(r"(\d{2})\s*(лет|года?)\s*и\s*старше", c):      # годы в скобках у таких категорий бывают ошибочны
        hi = year - int(m[1])
    elif m := re.search(r"(\d{4})\s*-\s*(\d{4})\s*г\.?р", c):
        lo, hi = int(m[1]), int(m[2])
    elif m := re.search(r"(\d{4})\s*г\.?р\.?\s*и\s*младше", c):
        lo = int(m[1])
    elif m := re.search(r"(\d{4})\s*г\.?р\.?\s*и\s*старше", c):
        hi = int(m[1])
    elif m := re.search(r"(\d{4})\s*г\.?р", c):
        lo = hi = int(m[1])
    elif m := re.search(r"(\d{2})\s*-\s*(\d{2})", c):
        lo, hi = year - int(m[2]), year - int(m[1])
    elif m := re.search(r"(\d{2})\s*\+", c):
        hi = year - int(m[1])
    elif (m := re.search(r"до\s*(\d{2})", c)) or (m := re.match(r"[мж]\s*(\d{2})$", c)):
        lo = year - int(m[1])
    return sex, lo, hi


def bd_fits_category(bd, cat, year, tol=1):
    """None — не проверить (заглушка/нет возраста в категории)."""
    _, lo, hi = cat_rule(cat, year)
    if not real_bd(bd) or (lo is None and hi is None):
        return None
    y = int(bd[:4])
    return (lo is None or y >= lo - tol) and (hi is None or y <= hi + tol)


def finished_events(data, i):
    return {r["event_id"] for r in data.res_by_card[i] if r["race_status"] != NOT_STARTED}


def result_sex(data, i):
    return {(r.get("sex") or "")[:1].upper() for r in data.res_by_card[i]} - {""}


def merge_blockers(ids, data):
    """Причины, по которым карточки нельзя склеивать автоматически (пусто — можно)."""
    ids = sorted(ids)
    out = []
    seen = collections.Counter(e for i in ids for e in finished_events(data, i))
    both = sorted(data.event_label(e) for e, k in seen.items() if k > 1)
    if both:
        out.append("обе финишировали в одном забеге: " + ", ".join(both))
    bds = {data.clients[i]["birthday"] for i in ids}
    bad = sorted({x for x, y in itertools.combinations(bds, 2) if not compatible_bd(x, y)}
                 | {y for x, y in itertools.combinations(bds, 2) if not compatible_bd(x, y)})
    if bad:
        out.append("несовместимые ДР: " + ", ".join(bad))
    sexes = [result_sex(data, i) for i in ids]
    single = {next(iter(s)) for s in sexes if len(s) == 1}
    if len(single) > 1:
        out.append("разный пол в протоколах")
    for a, b in itertools.combinations(ids, 2):
        if not names_compatible(data.clients[a]["name"], data.clients[b]["name"], data.names):
            out.append(f'разные имена: {data.clients[a]["name"]} / {data.clients[b]["name"]}')
            break
    for i in ids:
        if not real_bd(data.clients[i]["birthday"]):
            others = {data.clients[j]["birthday"] for j in data.cards_by_fio[fio_key(data.clients[i])]
                      if j != i and real_bd(data.clients[j]["birthday"])}
            if any(not compatible_bd(x, y) for x, y in itertools.combinations(others, 2)):
                out.append(f"ДР-заглушка #{i} подходит нескольким людям")
                break
    return out


def propose_birthday(ids, data):
    """ДР по хронометражу (большинство), без заглушек, «01-01» при наличии полной даты и года = года забега;
    нет данных хронометража — ДР карточек по тем же правилам; неоднозначно — None."""
    def pick(pairs):                    # [(ДР, год забега)]
        c = collections.Counter(bd for bd, y in pairs if real_bd(bd) and (not y or int(bd[:4]) < y - 1))
        if any(not jan1(bd) for bd in c):
            c = collections.Counter({bd: k for bd, k in c.items() if not jan1(bd)})
        top = c.most_common(2)
        if not top or (len(top) == 2 and top[0][1] == top[1][1]):
            return None
        return top[0][0]

    timing = [(r["birthday"], data.year(r["event_id"])) for i in ids for r in data.res_by_card[i]]
    return pick(timing) or pick([(data.clients[i]["birthday"], 0) for i in ids])


# ---------------------------------------------------------------- проверки

def fio_close(a, b):
    return a == b or a == b[::-1] or lev(a[0], b[0], 2) + lev(a[1], b[1], 2) <= 2


def check_lead_on_other_card(data, results):
    out = []
    for r in results:
        if any(l["event_id"] == r["event_id"] for l in data.leads_by_card[r["client_id"]]):
            continue
        key = fio_key(r)
        for l in data.leads_by_event[r["event_id"]]:
            if l["client_id"] == r["client_id"] or any(x["event_id"] == r["event_id"] for x in data.res_by_card[l["client_id"]]):
                continue                # у владельца заявки свой результат в этом забеге — тёзки
            same_bib = r["start_number"] and l["start_number"] == r["start_number"]
            if same_bib and fio_close(key, fio_key(l)):
                sev, why = "high", "тот же номер"
            elif fio_key(l) in (key, key[::-1]):
                sev, why = "medium", "те же ФИ"
            else:
                continue
            out.append(Finding("R-LEAD", sev, f'{data.event_label(r["event_id"])} №{r["start_number"]}: результат на '
                               f'{data.card_label(r["client_id"])}, заявка на {data.card_label(l["client_id"])} ({why})',
                               (r["client_id"], l["client_id"]), r["id"], r["event_id"]))
    return out


def check_duplicates(data, results):
    out = []
    groups = collections.defaultdict(list)
    for r in results:
        groups[(r["client_id"], r["event_id"])].append(r)
    for (cid, eid), rs in groups.items():
        if len(rs) < 2:
            continue
        fin = [r for r in rs if r["race_status"] != NOT_STARTED]
        lead_bibs = {l["start_number"] for l in data.leads_by_card[cid] if l["event_id"] == eid and l["start_number"]}
        for r in rs:
            if fin and r["race_status"] == NOT_STARTED:
                out.append(Finding("R-DUP", "high", f'{data.event_label(eid)}: «Not started» №{r["start_number"]} у '
                                   f'{data.card_label(cid)}, есть другой результат', (cid,), r["id"], eid, auto=True))
            elif not fin and lead_bibs and r["start_number"] not in lead_bibs:
                out.append(Finding("R-DUP", "high", f'{data.event_label(eid)}: №{r["start_number"]} не из заявки '
                                   f'{data.card_label(cid)} (номер заявки {sorted(lead_bibs)})', (cid,), r["id"], eid, auto=True))
        if len(fin) > 1:
            out.append(Finding("R-DUP", "low", f'{data.event_label(eid)}: два финиша у {data.card_label(cid)} '
                               f'(№{", №".join(str(r["start_number"]) for r in fin)}) — вероятно, разные люди',
                               (cid,), fin[0]["id"], eid))
    return out


def check_result_vs_card(data, results):
    out = []
    for r in results:
        c = data.clients.get(r["client_id"])
        if not c:
            out.append(Finding("R-CARD", "high", f'результат #{r["id"]} без карточки', (), r["id"], r["event_id"]))
            continue
        diff = [f for f, ok in (("ФИ", fio_key(r) == fio_key(c)), ("ДР", r["birthday"] == c["birthday"])) if not ok]
        if diff:
            out.append(Finding("R-CARD", "medium", f'{data.event_label(r["event_id"])} №{r["start_number"]}: '
                               f'{r["surname"]} {r["name"]} {r["birthday"]} ≠ {data.card_label(r["client_id"])} ({", ".join(diff)})',
                               (r["client_id"],), r["id"], r["event_id"]))
    return out


def check_category(data, results):
    out = []
    for r in results:
        year = data.year(r["event_id"])
        sex, lo, hi = cat_rule(r["category"], year)
        rsex = (r.get("sex") or "")[:1].upper()
        if sex and rsex in ("М", "Ж") and sex != rsex:
            out.append(Finding("R-CAT", "medium", f'{data.event_label(r["event_id"])} №{r["start_number"]}: пол {rsex}, '
                               f'категория «{r["category"]}» ({data.card_label(r["client_id"])})',
                               (r["client_id"],), r["id"], r["event_id"]))
        fits = bd_fits_category(r["birthday"], r["category"], year)
        # ребёнок в младшей доступной категории (нижняя граница возраста ≤ 18: «Ж12-13», «М18-49») — норма
        young = lo is not None and int(r["birthday"][:4]) > lo + 1 and (hi is None or year - hi <= 18)
        if fits is False and not young:
            out.append(Finding("R-CAT", "medium", f'{data.event_label(r["event_id"])} №{r["start_number"]}: ДР {r["birthday"]} '
                               f'не подходит к «{r["category"]}» ({data.card_label(r["client_id"])})',
                               (r["client_id"],), r["id"], r["event_id"]))
    return out


def similar_fio(a, b, names):
    """Похожие, но не одинаковые ФИ: до 2 правок суммарно; уменьшительное имя правкой не считается."""
    if a in (b, b[::-1]):
        return False
    dn = 0 if names_compatible(a[1], b[1], names) else lev(a[1], b[1], 2)
    return lev(a[0], b[0], 2) + dn <= 2


def twin_reason(x, y):
    if not real_bd(x) or not real_bd(y):
        return "ДР-заглушка"
    if _near_bd(x, y):
        return "ДР отличается на цифру / день↔месяц"
    if x[:4] == y[:4] and (jan1(x) or jan1(y)):
        return "«ГГГГ-01-01» того же года"
    if x[5:] == y[5:] and max(int(x[:4]), int(y[:4])) >= 2023:
        return "год регистрации вместо года рождения"
    return None


def check_twins(data, card_ids):
    out, seen = [], set()

    def add(a, b, why):
        k = (min(a, b), max(a, b))
        if k in seen:
            return
        seen.add(k)
        blockers = merge_blockers(k, data)
        sev = "low" if blockers else "high"
        msg = f'{data.card_label(a)} ↔ {data.card_label(b)}: {why}'
        if blockers:
            msg += " — не склеивать автоматически: " + "; ".join(blockers)
        else:
            bd = propose_birthday(k, data)
            msg += f" — итог ДР {bd or '?'}"
        out.append(Finding("C-TWIN", sev, msg, k))

    by_bd = collections.defaultdict(list)
    for i, c in data.clients.items():
        if real_bd(c["birthday"]):
            by_bd[c["birthday"]].append(i)
    for a in card_ids:
        c = data.clients.get(a)
        if not c:
            continue
        key = fio_key(c)
        for b in data.cards_by_fio[key] + data.cards_by_fio.get(key[::-1], []):
            if b != a and (why := twin_reason(c["birthday"], data.clients[b]["birthday"])):
                add(a, b, why)
        if real_bd(c["birthday"]):
            for b in by_bd[c["birthday"]]:
                if b != a and similar_fio(key, fio_key(data.clients[b]), data.names):
                    add(a, b, "похожие ФИ, та же ДР")
    return out


def check_hygiene(data, results):
    out = []
    for r in results:
        s, n, _ = canonical_fio(r["surname"], r["name"], data.names, r.get("sex", ""))
        if s and n and (s, n) != (r["surname"], r["name"]):
            out.append(Finding("HYG", "low", f'{data.event_label(r["event_id"])} №{r["start_number"]}: '
                               f'«{r["surname"]} {r["name"]}» -> «{s} {n}»', (r["client_id"],), r["id"], r["event_id"]))
    return out


def run_checks(data, event_ids=None):
    results = [r for r in data.results if not event_ids or r["event_id"] in event_ids]
    cards = sorted({r["client_id"] for r in results})
    return (check_lead_on_other_card(data, results) + check_duplicates(data, results) + check_result_vs_card(data, results)
            + check_category(data, results) + check_twins(data, cards) + check_hygiene(data, results))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--event-id", type=int, action="append", help="только результаты этого события (можно несколько)")
    ap.add_argument("--json", help="сохранить находки в json")
    args = ap.parse_args()

    from scripts.import_boom_historical import get_connection
    conn = get_connection()
    try:
        data = load(conn)
    finally:
        conn.close()
    findings = run_checks(data, set(args.event_id or []))
    order = {"high": 0, "medium": 1, "low": 2}
    findings.sort(key=lambda f: (f.code, order[f.severity], f.message))
    stat = collections.Counter((f.code, f.severity) for f in findings)
    print("Находки:", ", ".join(f"{c} {s}: {k}" for (c, s), k in sorted(stat.items())) or "нет")
    for f in findings:
        print(f'  [{f.code} {f.severity}{" auto" if f.auto else ""}] {f.message}')
    if args.json:
        Path(args.json).write_text(json.dumps([dataclasses.asdict(f) for f in findings], ensure_ascii=False, indent=1),
                                   encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
