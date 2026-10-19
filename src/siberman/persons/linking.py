"""
Реестр людей Siberman — чистая логика привязки выступлений к людям (без БД).

Спецификация hall §3: личник узнаётся по личному стартовому номеру (закреплён за человеком
навсегда, тот же номер = тот же человек даже при смене фамилии); эстафетчик — по ФИ среди
людей того же пола без противоречий. Неоднозначность → новый человек + запись «проверить».
Даты рождения приходят из заявок Тильды (attach_birthdates).
"""
import datetime
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

NatKey = tuple  # (race_year: int, bib: str, relay_stage: str) — строка participants


def plain_key(surname: str, name: str) -> str:
    """'фамилия имя': нижний регистр, ё→е, скобки → пробел, без лишних пробелов. Без псевдонимов —
    смену фамилии личника ловит номер, остальное решает админ."""
    raw = f"{surname or ''} {name or ''}".lower().replace("ё", "е").replace("(", " ").replace(")", " ")
    return " ".join(raw.split())


def norm_city(city: str) -> str:
    t = (city or "").lower().replace("ё", "е").strip()
    for prefix in ("город ", "г.", "г "):
        if t.startswith(prefix):
            t = t[len(prefix):]
    return " ".join(t.replace("-", " ").split())


def natkey(row: dict) -> NatKey:
    return (int(row["race_year"]), str(row["bib"]), str(row["relay_stage"]))


def _bib_order(bib: str) -> tuple:
    return (0, int(bib), "") if bib.isdigit() else (1, 0, bib)


def _row_order(row: dict) -> tuple:
    return (int(row["race_year"]), row["format"] != "individual", _bib_order(str(row["bib"])), str(row["relay_stage"]))


@dataclass(eq=False)
class Person:
    id: int                      # > 0 — в БД, < 0 — создан этим прогоном
    surname: str
    name: str
    gender: Optional[str] = None
    birthdate: Optional[datetime.date] = None
    bib_individual: Optional[str] = None
    city: str = ""
    city_manual: str = ""
    usage: dict = field(default_factory=dict)    # год -> {номера}
    formats: set = field(default_factory=set)    # {'individual', 'relay'}
    keys: set = field(default_factory=set)       # все ФИ, под которыми выступал
    last_year: int = 0


@dataclass(eq=False)
class Review:
    kind: str
    natkey: Optional[NatKey] = None
    person: Optional[Person] = None
    others: tuple = ()
    detail: str = ""

    def dedupe_key(self) -> str:
        if self.natkey:
            y, b, s = self.natkey
            # detail (новое ФИ строки) различает повторные правки одного и того же выступления
            return (f"{self.kind}:{y}:{b}:{s}" + (f":{self.detail}" if self.detail else ""))[:190]
        return f"{self.kind}:{self.person.id if self.person else ''}:{self.detail}"[:190]


@dataclass
class Applicant:
    tranid: str
    surname: str
    name: str
    gender: Optional[str]
    birthdate: datetime.date
    city: str = ""
    submitted_at: Optional[datetime.datetime] = None
    claimed_starts: Optional[int] = None   # сколько стартов на Siberman указал сам; None — этапник эстафеты


def _gender_ok(a: Optional[str], b: Optional[str]) -> bool:
    return a is None or b is None or a == b


class Registry:
    """Люди в памяти + индексы по личному номеру и ФИ."""

    def __init__(self, persons: list):
        self.by_id = {p.id: p for p in persons}
        self.by_bib = {p.bib_individual: p for p in persons if p.bib_individual}
        self.by_key = defaultdict(list)
        for p in persons:
            self._index_key(p, plain_key(p.surname, p.name))
        self.new: list = []
        self.bib_assigned: list = []   # люди из БД, которым этот прогон записал личный номер
        self.dropped: list = []        # автопривязки строк, у которых в протоколе стёрли фамилию
        self._next_tmp = -1

    def _index_key(self, p: Person, key: str) -> None:
        p.keys.add(key)
        if p not in self.by_key[key]:
            self.by_key[key].append(p)

    def add(self, surname: str, name: str, gender: Optional[str]) -> Person:
        p = Person(id=self._next_tmp, surname=surname, name=name, gender=gender)
        self._next_tmp -= 1
        self.by_id[p.id] = p
        self.new.append(p)
        self._index_key(p, plain_key(surname, name))
        return p

    def attach(self, p: Person, row: dict, index_name: bool = True) -> None:
        """Учесть выступление row за человеком p. index_name=False — ФИ строки не добавлять
        в ключи человека (ручная привязка, у которой ФИ в протоколе изменилось)."""
        year, bib = int(row["race_year"]), str(row["bib"])
        if index_name:
            self._index_key(p, plain_key(row["surname"], row["name"]))
        p.usage.setdefault(year, set()).add(bib)
        p.formats.add(row["format"])
        if p.gender is None and row.get("gender") in ("M", "F"):
            p.gender = row["gender"]
        if year >= p.last_year:
            p.last_year = year
            p.city = row.get("city") or p.city
        if row["format"] == "individual" and not p.bib_individual and bib not in self.by_bib:
            p.bib_individual = bib
            self.by_bib[bib] = p
            if p.id > 0:
                self.bib_assigned.append(p)


def _resolve(reg: Registry, r: dict) -> tuple:
    """Человек для непривязанного выступления r и записи «проверить»."""
    year, bib, nk = int(r["race_year"]), str(r["bib"]), natkey(r)
    g = r.get("gender") if r.get("gender") in ("M", "F") else None
    key = plain_key(r["surname"], r["name"])
    if r["format"] == "individual":
        p = reg.by_bib.get(bib)
        if p is not None:
            if g and p.gender and g != p.gender:
                return p, [Review("bib_gender_mismatch", natkey=nk, person=p)]
            return p, ([] if key in p.keys else [Review("bib_name_change", natkey=nk, person=p)])
    cands, other_gender = [], []
    for p in reg.by_key.get(key, []):
        if r["format"] == "individual" and p.bib_individual and p.bib_individual != bib:
            continue                          # у человека свой личный номер — это тёзка
        if not _gender_ok(g, p.gender):
            other_gender.append(p)
            continue
        used = p.usage.get(year)
        if used and bib not in used:          # в этом году уже выступал под другим номером
            continue
        cands.append(p)
    if len(cands) == 1:
        p = cands[0]
        switch = bool(p.formats) and r["format"] not in p.formats
        return p, ([Review("format_switch", natkey=nk, person=p)] if switch else [])
    p = reg.add(r["surname"], r["name"], g)
    if cands:
        return p, [Review("namesake_candidate", natkey=nk, person=p, others=tuple(cands))]
    if other_gender:                          # тот же ФИ, другой пол (в Excel пусто → парсер ставит M)
        return p, [Review("gender_mismatch", natkey=nk, person=p, others=tuple(other_gender))]
    return p, []


def link_participants(reg: Registry, rows: list, links: dict) -> tuple:
    """rows — все строки participants; links — сохранённые привязки {natkey: (person_id, manual, name_key)}.
    Автопривязка действует, пока ФИ строки то же, что при привязке; иначе строка разрешается заново
    (замена этапника, исправленный протокол) и, если ушла к другому человеку, — запись «relinked».
    Ручная привязка действует всегда; другое ФИ — запись «manual_name_changed». Строки без фамилии
    не привязываются, их автопривязки — в reg.dropped (удалить).
    → ({natkey: Person} новых и изменённых привязок, [Review])."""
    ordered = sorted(rows, key=_row_order)
    named = []
    kept, reviews = set(), []
    for r in ordered:
        if str(r["surname"] or "").strip():
            named.append(r)
            continue
        link = links.get(natkey(r))
        if not link:
            continue
        if not link[1]:
            reg.dropped.append(natkey(r))
        elif link[0] in reg.by_id:
            reviews.append(Review("manual_name_changed", natkey=natkey(r), person=reg.by_id[link[0]]))

    for r in named:
        link = links.get(natkey(r))
        if not link or link[0] not in reg.by_id:
            continue
        person_id, manual, name_key = link
        p = reg.by_id[person_id]
        same = name_key == plain_key(r["surname"], r["name"])
        if same or manual:
            reg.attach(p, r, index_name=same)
            kept.add(natkey(r))
            if not same:
                reviews.append(Review("manual_name_changed", natkey=natkey(r), person=p,
                                      detail=plain_key(r["surname"], r["name"])))

    new_links = {}
    for r in named:
        k = natkey(r)
        if k in kept:
            continue
        p, rv = _resolve(reg, r)
        reg.attach(p, r)
        new_links[k] = p
        reviews.extend(rv)
        link = links.get(k)
        prev = reg.by_id.get(link[0]) if link else None
        if prev is not None and prev is not p:
            reviews.append(Review("relinked", natkey=k, person=p, others=(prev,),
                                  detail=plain_key(r["surname"], r["name"])))
    return new_links, reviews


def _applicant_candidates(reg: Registry, a: Applicant) -> list:
    for key in (plain_key(a.surname, a.name), plain_key(a.name, a.surname)):
        c = [p for p in reg.by_key.get(key, []) if _gender_ok(a.gender, p.gender)]
        if c:
            return c
    return []


def attach_birthdates(reg: Registry, applicants: list) -> tuple:
    """ДР из заявок → ([(Person, дата)] новые ДР, [Review]). Заявки — по дате подачи. ДР ставится
    автоматически, только если ФИ подходит одному человеку, у него нет другой ДР, город не
    противоречит и заявитель сам указал старты на Siberman; иначе — «проверить»."""
    updates, reviews = [], []
    order = sorted(applicants, key=lambda x: (x.submitted_at or datetime.datetime.min, x.tranid))
    for a in order:
        cands = _applicant_candidates(reg, a)
        if not cands:
            continue
        if len(cands) > 1:
            if sum(1 for c in cands if c.birthdate == a.birthdate) != 1:
                reviews.append(Review("applicant_ambiguous", others=tuple(cands), detail=a.tranid))
            continue
        c = cands[0]
        if c.birthdate == a.birthdate:
            continue
        if c.birthdate is not None:
            reviews.append(Review("bd_conflict", person=c, detail=a.tranid))
            continue
        if a.city and c.city and norm_city(a.city) != norm_city(c.city):
            reviews.append(Review("applicant_city_mismatch", person=c, detail=a.tranid))
            continue
        if not a.claimed_starts:              # не указал стартов на Siberman — может быть тёзкой
            reviews.append(Review("applicant_unconfirmed", person=c, detail=a.tranid))
            continue
        c.birthdate = a.birthdate
        updates.append((c, a.birthdate))
    return updates, reviews
