"""
Проверки привязки заявок и результатов к карточкам клиентов (только чтение): данные, правила, находки.

Карточку триггеры ищут по точному «фамилия + имя + ДР» (результат — сначала
через заявку того же забега с тем же номером, см. migrations/results_link_via_lead.sql),
поэтому заглушка ДР в протоколе, опечатка или «Ира» вместо «Ирина» создают новую
карточку. Проверки находят такие случаи; предохранители говорят, когда склеивать
нельзя. Правило ДР: хронометраж важнее заявки (решение пользователя 2026-10-01).
Действия по находкам — src/analytics/dq_actions.py, дела и вопросы — src/analytics/dq_cases.py.
"""

import collections
import dataclasses
from datetime import datetime
import itertools
import re

from src.common.names import SENTINELS, Names, _near_bd, canonical_fio, lev, norm

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
        self.cards_by_surname = collections.defaultdict(list)
        for i, c in self.clients.items():
            self.cards_by_surname[norm(c["surname"])].append(i)
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
    cur.execute("SELECT id, event_name, event_distance, event_year, event_date FROM events")
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
        """Та же фамилия и то же имя, в том числе уменьшительное («Саша» — «Александр»)."""
        c = data.clients[cid]
        return [i for i in data.cards_by_surname[norm(c["surname"])] if i != cid
                and names_compatible(c["name"], data.clients[i]["name"], data.names) and ok(data.clients[i]["birthday"])]

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


def run_checks(data, event_ids=None, card_ids=None):
    """Без event_ids — вся база (двойники — для карточек с результатами); с event_ids —
    результаты этих забегов, двойники — и для карточек их заявок (проверка после импорта).
    card_ids — только находки, касающиеся этих карточек (дело после ответа на вопрос)."""
    results = [r for r in data.results if not event_ids or r["event_id"] in event_ids]
    leads = [l for l in data.leads if not event_ids or l["event_id"] in event_ids]
    if card_ids:
        results = [r for r in results if r["client_id"] in card_ids]
        leads = [l for l in leads if l["client_id"] in card_ids]
    cards = {r["client_id"] for r in results}
    if event_ids:
        cards |= {l["client_id"] for l in leads}
    if card_ids:
        cards = set(card_ids)
    cards = sorted(cards)
    found = (check_lead_on_other_card(data, results) + check_duplicates(data, results) + check_result_vs_card(data, results)
             + check_category(data, results) + check_twins(data, cards) + check_hygiene(data, results)
             + check_kids_leads(data, event_ids, from_year=datetime.now().year) + check_foreign(data, results, leads))
    if card_ids:
        found = [f for f in found if set(f.client_ids) & set(card_ids)]
    return found
