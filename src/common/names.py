"""
Правила для ФИО и ДР участников: нормализация, сравнение, разбор полей.

Общие для чистки карточек (scripts/clean_clients.py), проверок привязки к
карточкам (src/analytics/data_quality.py) и нормализации на входе
(normalize_person_name — вебхук Tilda, импорт заявок, лоадер Copernico).
"""

import collections
import re

SENTINELS = {"1900-01-01", "1905-01-01"}

# ---------------------------------------------------------------- текст ФИО

_INVISIBLE = re.compile("[​-‏⁠﻿­̀́]")
_HOMOGLYPH = str.maketrans("aAeEoOpPcCxXyYkKmMtTHBh", "аАеЕоОрРсСхХуУкКмМтТНВһ")
_TO_LATIN = str.maketrans("аАеЕоОрРсСхХуУкКмМтТНВ", "aAeEoOpPcCxXyYkKmMtTHB")
_CYR = re.compile(r"[а-яё]", re.I)
_LAT = re.compile(r"[a-z]", re.I)
_PATR_FEMALE = re.compile(r"(вна|ична)$", re.I)     # фамилий с такими окончаниями почти нет
_PATR_MALE = re.compile(r"вич$", re.I)               # «Валисевич», «Богданкевич» — фамилии

_TRANSLIT = [
    ("shch", "щ"), ("sch", "щ"), ("iia", "ия"), ("zh", "ж"), ("kh", "х"), ("ts", "ц"), ("tz", "ц"),
    ("ch", "ч"), ("sh", "ш"), ("yu", "ю"), ("iu", "ю"), ("ju", "ю"), ("ya", "я"), ("ja", "я"),
    ("ia", "ия"), ("yo", "ё"), ("jo", "ё"), ("ye", "е"), ("je", "е"), ("ii", "ий"), ("iy", "ий"),
    ("yi", "ый"), ("ey", "ей"), ("ay", "ай"), ("oy", "ой"), ("uy", "уй"), ("ph", "ф"), ("x", "кс"),
    ("a", "а"), ("b", "б"), ("v", "в"), ("w", "в"), ("g", "г"), ("d", "д"), ("e", "е"), ("z", "з"),
    ("i", "и"), ("j", "й"), ("k", "к"), ("l", "л"), ("m", "м"), ("n", "н"), ("o", "о"), ("p", "п"),
    ("r", "р"), ("s", "с"), ("t", "т"), ("u", "у"), ("f", "ф"), ("h", "х"), ("c", "к"), ("q", "к"),
]


def norm(s):
    """Ключ сравнения: без регистра, ё=е, без лишних пробелов (как collation БД)."""
    return re.sub(r"\s+", " ", (s or "").strip().lower().replace("ё", "е"))


def translit(word):
    w, out, i = word.lower(), [], 0
    while i < len(w):
        if w[i] in "aeou" and w[i + 1:i + 2] == "y" and w[i + 2:i + 3] in tuple("aeiou"):
            out.append(dict(zip("aeou", "аеоу"))[w[i]])   # «Troyakova» -> «Троякова»
            i += 1
            continue
        if w[i] == "y" and not w.startswith(("ya", "yu", "yo", "ye", "yi"), i):
            # конечная y после согласной — «ий» (Dmitry), иначе «ы»
            out.append("ий" if i == len(w) - 1 and i and w[i - 1] not in "aeiou" else "ы")
            i += 1
            continue
        for lat, cyr in _TRANSLIT:
            if w.startswith(lat, i):
                out.append(cyr)
                i += len(lat)
                break
        else:
            out.append(w[i])
            i += 1
    return "".join(out)


def title(word):
    """«ИВАНОВ»/«иванов» -> «Иванов» (по частям через дефис); «МакКой» не трогаем."""
    if not (word.isupper() or word.islower() or word[:1].islower()):
        return word
    return "-".join(p[:1].upper() + p[1:].lower() for p in word.split("-"))


def lev(a, b, limit=2):
    """Расстояние Дамерау (перестановка соседних букв — одна правка: «Adnrei»)."""
    if abs(len(a) - len(b)) > limit:
        return limit + 1
    d = [[i + j if not i * j else 0 for j in range(len(b) + 1)] for i in range(len(a) + 1)]
    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + (a[i - 1] != b[j - 1]))
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                d[i][j] = min(d[i][j], d[i - 2][j - 2] + 1)
    return d[-1][-1]


def tokens(field):
    s = _INVISIBLE.sub("", field or "").replace(" ", " ").replace("ë", "ё").replace("Ë", "Ё")
    s = re.sub(r"\s*-\s*", "-", s)                     # «Петров- Дельверс»
    s = re.sub(r"[^\w\s\-'’]|[\d_]", " ", s)          # «Салимжанов.», «✅», «Ксения69_»
    out = []
    for t in s.split():
        t = t.strip("-'’")
        if _CYR.search(t) and _LAT.search(t):
            if len(_LAT.findall(t)) > len(_CYR.findall(t)):  # «Моrotskiy» — латиница с кириллическими М, о
                t = translit(t.translate(_TO_LATIN))
            else:                                            # «Нинa», «ЛаZученко», «Светланd»
                t = "".join(ch if not _LAT.match(ch) else
                            ch.translate(_HOMOGLYPH) if ch.translate(_HOMOGLYPH) != ch else translit(ch)
                            for ch in t)
        if t:
            out.append(t)
    return out


class Names:
    """Частотные имена (с полом) и фамилии — по заявкам и результатам."""

    def __init__(self, rows):
        name_f, surn_f = collections.Counter(), collections.Counter()
        sex = collections.defaultdict(collections.Counter)
        for s, n, x in rows:
            for t in tokens(n)[:1]:
                name_f[norm(t)] += 1
                sex[norm(t)][(x or "")[:1].upper()] += 1
            for t in tokens(s)[:1]:
                surn_f[norm(t)] += 1
        self.first = {n: k for n, k in name_f.items() if k >= 5 and surn_f[n] < k / 3 and _CYR.search(n)}
        self.sex = {n: sex[n].most_common(1)[0][0] for n in self.first}

    def is_first(self, t):
        return norm(t) in self.first

    def match_first(self, lat, sex="", exact=False):
        """Латинское имя -> частотное русское имя (или None). Точное совпадение
        транслита (в т.ч. с «ь»: Igor -> Игорь, Olga -> Ольга) — без учёта пола;
        близкое — только того же пола («Petra» не «Петр»)."""
        c = translit(lat)
        for v in [c] + [c[:i] + "ь" + c[i:] for i in range(1, len(c) + 1)]:
            if v in self.first:
                return v
        if exact:
            return None
        limit = 0 if len(c) <= 4 else 1 if len(c) == 5 else 2
        best = None
        for n, k in self.first.items():
            d = lev(n, c, limit) if limit else 1
            if d > limit or (sex and self.sex[n] in "МЖ" and self.sex[n] != sex[:1].upper()):
                continue
            if best is None or (d, -k) < best[0]:
                best = ((d, -k), n)
        return best[1] if best else None


def canonical_fio(surname, name, names, sex=""):
    """-> (фамилия, имя, заметки). Пустая строка — поле определить не удалось."""
    ts, tn = tokens(surname), tokens(name)
    if norm(surname) == norm(name):
        if len(ts) < 2:                                 # «Олеся» «Олеся» — второго слова нет
            w = title(ts[0]) if ts else ""
            return w, w, ["одно слово в обоих полях"]
        tn = []                                         # ФИО целиком в обоих полях
    notes = []
    # инициалы: «С.», «К.», «ЕП»
    initial = lambda t: len(t) == 1 or (len(t) == 2 and t.isupper())
    if any(initial(t) for t in ts + tn):
        notes.append("инициал убран")
    ts, tn = [t for t in ts if not initial(t)], [t for t in tn if not initial(t)]
    # латиница: русское ФИ -> кириллица (транслит), иностранное остаётся
    words = [("s", t) for t in ts] + [("n", t) for t in tn]
    if any(not _CYR.search(t) for _, t in words):
        cyr = [t for _, t in words if _CYR.search(t)]
        if any(names.is_first(t) for t in cyr) and any(not names.is_first(t) for t in cyr):
            words = [x for x in words if _CYR.search(x[1])]          # «Прусаков … Prusakov Vladimir»
            notes.append("латинский дубль ФИО убран")
        else:
            # имя ищем сначала в поле имени; в поле фамилии — только если в поле имени его нет
            fm = {}
            for field in ("n", "s"):
                if field == "s" and (any(names.is_first(t) for f, t in words if f == "n" and _CYR.search(t))
                                     or any(fm.values())):
                    break
                for f, t in words:
                    if f == field and not _CYR.search(t):
                        fm[t] = names.match_first(t, sex, exact=field == "s")   # «Slawson» — не «Самсон»
            if cyr or any(fm.values()):
                words = [(f, t if _CYR.search(t) else fm.get(t) or title(translit(t))) for f, t in words]
                notes.append("латиница -> кириллица")
            else:                                    # иностранное ФИ — как есть, только регистр
                return " ".join(title(t) for t in ts), " ".join(title(t) for t in tn), notes + ["иностранное ФИ"]

    ts, tn = [t for f, t in words if f == "s"], [t for f, t in words if f == "n"]

    # отчество: -вна/-ична — всегда; -вич — сразу после имени и если есть другая фамилия
    # («Наталия Валисевич», «Богданкевич Ратибор» — фамилии)
    other_surname = lambda x: any(u != x and not names.is_first(u) and not _PATR_MALE.search(u)
                                  and not _PATR_FEMALE.search(u) for u in ts + tn)
    kept = []
    for field in (ts, tn):
        out = []
        for k, t in enumerate(field):
            male = _PATR_MALE.search(t) and k > 0 and names.is_first(field[k - 1]) and other_surname(t)
            if len(t) > 5 and not names.is_first(t) and (_PATR_FEMALE.search(t) or male):
                notes.append("отчество убрано")
            else:
                out.append(t)
        kept.append(out)
    ts, tn = kept
    words = [("s", t) for t in ts] + [("n", t) for t in tn]

    # имя: частотное имя из поля имени, иначе из поля фамилии, иначе поле имени
    firsts = [x for x in words if names.is_first(x[1])]
    pick = (next((x for x in firsts if x[0] == "n"), None) or (firsts[0] if firsts else None)
            or next((x for x in words if x[0] == "n"), None))
    if pick and not names.is_first(pick[1]) and len([f for f, _ in words if f == "n"]) > 1:
        return "", "", notes + ["не удалось разобрать имя"]     # «Алмазная Крошка»
    new_name = title(pick[1]) if pick else ""
    if "-" in new_name:                                          # «Есения-Принцесса» -> «Есения»
        parts = new_name.split("-")
        if any(names.is_first(p) for p in parts) and not all(names.is_first(p) for p in parts):
            new_name = "-".join(p for p in parts if names.is_first(p))
    left = [x for x in words if x is not pick]
    # фамилия: не-имена, сначала из поля фамилии; лишние имена (родителя) отбрасываются
    cand = [x for x in left if not names.is_first(x[1])] or left
    parts = [t for f, t in cand if f == "s"] or [t for f, t in cand]
    if pick and pick[0] == "s" and cand and all(f == "n" for f, _ in cand):
        notes.append("имя и фамилия переставлены")
    uniq = []
    for t in parts:
        if norm(t) not in {norm(u) for u in uniq} and (not pick or norm(t) != norm(pick[1])):
            uniq.append(t)
    if len(words) > 2 or len(uniq) + (1 if pick else 0) < len(words):
        notes.append("лишние слова убраны")
    if not uniq:
        notes.append("нет фамилии")
    return " ".join(title(t) for t in uniq), new_name, notes


def _near_bd(a, b):
    if a in SENTINELS or b in SENTINELS or a == b:
        return False
    (ya, ma, da), (yb, mb, db) = a.split("-"), b.split("-")
    return (ya, ma, da) == (yb, db, mb) or sum(x != y for x, y in zip(a, b)) == 1


def normalize_person_name(value):
    """Фамилия или имя на входе (заявка, протокол хронометража) — только надёжные правки,
    без словарей и перестановок полей (это делают проверки качества данных):
    невидимые символы и NBSP, цифры и знаки, латиница-двойник в кириллическом слове
    («Нинa»), ё/ë -> е (как триггеры БД), регистр каждой части через дефис
    («капустин-богданов» -> «Капустин-Богданов», «COQUET» -> «Coquet»)."""
    if not value or not isinstance(value, str):
        return value
    words = []
    for t in tokens(value):
        t = t.replace("ё", "е").replace("Ё", "Е")
        words.append("-".join(p[:1].upper() + p[1:].lower() for p in t.split("-")))
    return " ".join(words)


def normalize_event_name(value):
    """Название события: латинские буквы-двойники в кириллическом слове -> кириллица.
    «Cнежная семерка» (латинская C в товаре Tilda) заводила отдельное событие-двойник
    рядом с «Снежная семерка» (2026-10-05: 25 заявок на 2 км ушли «мимо» Снежной)."""
    if not value or not isinstance(value, str):
        return value
    return " ".join(w.translate(_HOMOGLYPH) if _CYR.search(w) and _LAT.search(w) else w for w in value.split())


_SEX_FEMALE = ("ж", "female", "f")
_SEX_MALE = ("м", "male", "m")


def normalize_sex(value) -> str:
    """«жен», «Ж», «женский», «Female» → «Женщина»; «муж», «М», «мужской» → «Мужчина» —
    канон заявок и результатов (бейдж пола на сайте; 2026-10-06). Пусто/непонятно — как есть."""
    raw = str(value or "").strip()
    low = raw.lower()
    if low.startswith(_SEX_FEMALE) or low in ("female", "f"):
        return "Женщина"
    if low.startswith(_SEX_MALE) or low in ("male", "m"):
        return "Мужчина"
    return raw
