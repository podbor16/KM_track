"""
Проверки привязки заявок и результатов к карточкам клиентов (только чтение).

Карточку триггеры ищут по точному «фамилия + имя + ДР» (результат — сначала
через заявку того же забега с тем же номером, см. migrations/results_link_via_lead.sql),
поэтому заглушка ДР в протоколе, опечатка или «Ира» вместо «Ирина» создают новую
карточку. Проверки находят такие случаи; предохранители говорят, когда склеивать
нельзя. Правило ДР: хронометраж важнее заявки (решение пользователя 2026-10-01).
"""

import collections
import dataclasses
from datetime import datetime
import itertools
import json
import os
import re
import tempfile

from src.analytics.client_merge import apply as apply_merge, recompute_aggregates
from src.analytics.db_results import recompute_duplicates
from src.common.names import SENTINELS, Names, _near_bd, canonical_fio, lev, norm, normalize_person_name

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
    lead_id: int = None
    fix: tuple = ()                     # HYG: каноническое (фамилия, имя) для кнопки «Исправить ФИО»

    @property
    def key(self):
        """Стабильный ключ находки — для запомненных решений (dq_decisions)."""
        rid = f"r{self.result_id}" if self.result_id else (f"l{self.lead_id}" if self.lead_id else "")
        return f'{self.code}:{rid}:{"-".join(map(str, sorted(self.client_ids)))}'


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
        self.result_by_id = {r["id"]: r for r in results}
        self.res_by_event = collections.defaultdict(list)
        for r in results:
            self.res_by_event[r["event_id"]].append(r)
        self.lead_by_id = {l["id"]: l for l in leads}
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
    cur.execute("SELECT id, client_id, surname, name, birthday, sex, event_id, event_distance, start_number FROM leads")
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

    timing = pick([(r["birthday"], data.year(r["event_id"])) for i in ids for r in data.res_by_card[i]])
    cards = pick([(data.clients[i]["birthday"], 0) for i in ids])
    # в протоколе только год («2017-01-01», Детский 2023) — полная дата того же года из карточки
    # (Климентий Роман 2017-09-10, склеен с заглушкой 2026-10-08)
    if timing and jan1(timing) and cards and not jan1(cards) and cards[:4] == timing[:4]:
        return cards
    return timing or cards


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
        swapped = data.cards_by_fio.get(key[::-1], []) if key != key[::-1] else []
        for b in data.cards_by_fio[key] + swapped:
            if b == a:
                continue
            why = twin_reason(c["birthday"], data.clients[b]["birthday"])
            if not why and b in swapped and c["birthday"] == data.clients[b]["birthday"]:
                why = "имя и фамилия переставлены"          # «Андрей Сафонов» из формы Tilda
            if why:
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
                               f'«{r["surname"]} {r["name"]}» -> «{s} {n}»', (r["client_id"],), r["id"], r["event_id"],
                               fix=(s, n)))
    return out


KIDS_EVENT = "Детский забег"
KIDS_MAX_AGE = 14


def check_kids_leads(data, event_ids=None, from_year=None):
    """Заявки Детского забега: возраст не детский (часто — ДР родителя: «ребёнок» 1986 г.р.) или
    дистанция не по возрасту (младше 6 на 31.12 года старта — 500 м, иначе 1 км). Без event_ids —
    только старты from_year и позже (прошлые уже не исправить). Решение пользователя 2026-10-05:
    подсвечивать, исправлять вручную."""
    from src.krasmarafon.services.tilda_webhook import _kids_distance
    out = []
    for l in data.leads:
        ev = data.events.get(l["event_id"]) or {}
        if ev.get("event_name") != KIDS_EVENT or (event_ids and l["event_id"] not in event_ids):
            continue
        year = int(ev.get("event_year") or 0)
        if not event_ids and from_year and year < from_year:
            continue
        who = f'{data.event_label(l["event_id"])}: {l["surname"]} {l["name"]} {l["birthday"]}'
        if not real_bd(l["birthday"]):
            sev, why = "medium", "нет даты рождения"
        else:
            age = year - int(l["birthday"][:4])
            expected = _kids_distance(year, l["birthday"])
            if age < 1 or age > KIDS_MAX_AGE:
                sev, why = "medium", f"возраст {age} — не детский (возможно, ДР родителя)"
            elif expected and str(l["event_distance"]).strip() != expected:
                sev, why = "low", f"дистанция {l['event_distance']}, а по возрасту ({age}) — {expected}"
            else:
                continue
        out.append(Finding("L-KID", sev, f"{who} — {why}", (l["client_id"],), event_id=l["event_id"], lead_id=l["id"]))
    return out


FOREIGN_GAP = 5          # лет мимо категории — и без подходящего тёзки строка явно чужая


def _kid_age(bd, year):
    return None if not real_bd(bd) else year - int(bd[:4])


def _is_kid(bd, year):
    """Возраст детского забега: 0 лет — тоже (категории «2013-2018 г.р.» на старте 2018)."""
    age = _kid_age(bd, year)
    return age is not None and 0 <= age <= KIDS_MAX_AGE


def card_fits_category(bd, cat, year):
    """Категория подходит к ДР (допуск 1 год; ребёнок в младшей доступной категории — норма); None — не проверить."""
    fits = bd_fits_category(bd, cat, year)
    if fits is not False:
        return fits
    _, lo, hi = cat_rule(cat, year)
    return lo is not None and int(bd[:4]) > lo + 1 and (hi is None or year - hi <= 18)


def _category_gap(bd, cat, year):
    _, lo, hi = cat_rule(cat, year)
    y = int(bd[:4])
    return (lo - y) if lo is not None and y < lo else (y - hi) if hi is not None and y > hi else 0


def check_foreign(data, results, leads):
    """Строка, похоже, на карточке тёзки (как Черновы): детский результат/заявка на карточке не ребёнка, результат
    взрослого забега, чья категория не подходит ДР карточки. Подходящие тёзки — вторыми карточками находки."""
    out = []

    def namesakes(cid, ok):
        c = data.clients[cid]
        return [i for i in data.cards_by_fio[fio_key(c)] if i != cid and ok(data.clients[i]["birthday"])]

    def add(row, why, others, lead=False):
        bib = "" if lead else f' №{row["start_number"]}'
        msg = f'{data.event_label(row["event_id"])}{bib}: {why} — {data.card_label(row["client_id"])}'
        if others:
            msg += "; подходит: " + ", ".join(data.card_label(i) for i in others[:3])
        out.append(Finding("R-FOREIGN", "high" if others else "medium", msg, (row["client_id"], *others[:3]),
                           None if lead else row["id"], row["event_id"], lead_id=row["id"] if lead else None))

    for r in results:
        c = data.clients.get(r["client_id"])
        if not c or not real_bd(c["birthday"]):
            continue
        ev = data.events.get(r["event_id"], {})
        year = int(ev.get("event_year") or 0)
        if ev.get("event_name") == KIDS_EVENT:
            age = _kid_age(c["birthday"], year)
            if not _is_kid(c["birthday"], year):
                kids = namesakes(r["client_id"], lambda bd: _is_kid(bd, year))
                add(r, f"детский забег, а по ДР карточки возраст {age}", kids)
            continue
        if card_fits_category(c["birthday"], r["category"], year) is not False:
            continue
        fit = namesakes(r["client_id"], lambda bd: real_bd(bd) and card_fits_category(bd, r["category"], year) is True)
        gap = _category_gap(c["birthday"], r["category"], year)
        # ДР строки = ДР карточки и тёзки нет — это уже R-CAT; здесь — только явно чужое
        if fit or (r["birthday"] != c["birthday"] and gap > FOREIGN_GAP) or gap > 2 * FOREIGN_GAP:
            add(r, f'категория «{r["category"]}» не подходит к ДР карточки', fit)
    for l in leads:
        ev = data.events.get(l["event_id"], {})
        c = data.clients.get(l["client_id"])
        if ev.get("event_name") != KIDS_EVENT or not c or not real_bd(c["birthday"]):
            continue
        year = int(ev.get("event_year") or 0)
        age = _kid_age(c["birthday"], year)
        if _is_kid(c["birthday"], year):
            continue
        kids = namesakes(l["client_id"], lambda bd: _is_kid(bd, year))
        if kids:
            add(l, f"заявка на детский забег, а по ДР карточки возраст {age}", kids, lead=True)
    return out


def run_checks(data, event_ids=None):
    """Без event_ids — вся база (двойники — для карточек с результатами); с event_ids —
    результаты этих забегов, двойники — и для карточек их заявок (проверка после импорта)."""
    results = [r for r in data.results if not event_ids or r["event_id"] in event_ids]
    cards = {r["client_id"] for r in results}
    if event_ids:
        cards |= {l["client_id"] for l in data.leads if l["event_id"] in event_ids}
    cards = sorted(cards)
    return (check_lead_on_other_card(data, results) + check_duplicates(data, results) + check_result_vs_card(data, results)
            + check_category(data, results) + check_twins(data, cards) + check_hygiene(data, results)
            + check_kids_leads(data, event_ids, from_year=datetime.now().year)
            + check_foreign(data, results, [l for l in data.leads if not event_ids or l["event_id"] in event_ids]))


# ---------------------------------------------------------------- решения и действия (dq_decisions, dq_actions)

MERGEABLE = ("C-TWIN", "R-LEAD")
DECISIONS = ("different_people", "keep")


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


def dismiss(conn, key, decision, note, user):
    """Запомнить решение по находке — больше не показывается. -> id записи журнала."""
    if decision not in DECISIONS:
        raise ValueError(f"решение: {', '.join(DECISIONS)}")
    cur = conn.cursor()
    cur.execute("""INSERT INTO dq_decisions (finding_key, decision, note, decided_by) VALUES (%s, %s, %s, %s)
                   ON DUPLICATE KEY UPDATE decision = VALUES(decision), note = VALUES(note),
                                           decided_by = VALUES(decided_by), decided_at = NOW()""",
                (key, decision, note or "", user or ""))
    action_id = _log_action(cur, "dismiss", key, {"decision": decision, "note": note}, user)
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


def edit_record(conn, table, row_id, fields, user, key=""):
    """Правка полей строки находки: результата, заявки или карточки. В журнал — значения «до» и «после»
    изменённых полей; отмена возвращает «до». Карточке нельзя дать ФИ+ДР другой карточки — это склейка.
    -> (карточка, id записи журнала)."""
    fields = _clean_edit(table, fields)
    cols = list(EDITABLE[table]) + (["event_id"] if table == "leads" else [])
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


def move_row(conn, table, row_id, user, key="", to_client_id=None, new_card=None):
    """Перенести результат или заявку на другую карточку — существующую (to_client_id) или новую (new_card: фамилия,
    имя, ДР). ФИ и ДР строки не меняются. Опустевшая прежняя карточка удаляется (отмена её вернёт). Заявка
    переносит на карточку свои контакты (trg_leads_after_update) — снимок контактов обеих карточек в журнале.
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
                                                           "contacts": contacts}, user)
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
                         for k in d["after"] if k != "event_id")
        card = "" if d["table"] == "clients" else f', карточка #{d["client_id"]}'
        return f'Правка ({what} #{d["id"]}{card}): {diff}'
    if action == "move_result":
        how = "новую карточку" if d["created"] else "карточку"
        tail = f' (пустая карточка #{d["from"]} удалена)' if d.get("deleted_card") else ""
        what = "заявки" if d.get("table") == "leads" else "результата"
        return f'Перенос {what} #{d.get("row_id", d.get("result_id"))}: с карточки #{d["from"]} на {how} #{d["to"]}{tail}'
    if action == "dismiss":
        return "Решение: " + ("разные люди" if d["decision"] == "different_people" else "оставить как есть")
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
               "event_distance": "дистанция"}


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
