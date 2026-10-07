#!/usr/bin/env python3
"""
Импорт результатов прошедшего старта из выгрузки Copernico в xlsx
(2026-09-26, первым — Х Трейл 2025, 10 км). Нужны трекеру следующего года:
личный темп и средний темп категорий (results_service — исторический кеш).

Колонки: Bib, Surname, Name, Date of Birth (дд/мм/гггг), Status, Start,
[Gender (Male/Female) — иначе пол из категории], [Category], время финиша. Колонок финиша в выгрузках бывает
несколько с одинаковым названием («Finish» — чистое / официальное / темп): время
определяется по содержимому (чч:мм:сс, темп «3'14"/km» отбрасывается), чистое —
колонка со словом «чист», иначе меньшая из двух; чистое > официального хоть у
одного — ошибка. Колонка финиша одна — это официальное время, чистого нет (NULL, места
по чистому не считаются; решение пользователя 2026-10-06). Гандикап (Снежная семёрка): Start — задержка волны, официальное —
от первого выстрела (порядок прихода = места).
Промежуточные отметки (2026-10-06): колонки с километражем в названии («2,5», «4,5»,
«2,5km») или заданные --checkpoints «razv1=1.75,razv2=5.25» → time_clear_kt1…7 и темп
(как загрузчик Copernico: время / км отметки), дистанции — в events.checkpoint_distances.
--checkpoints-only — дописать отметки в уже загруженные результаты (по номеру), финиш не трогать.
Протоколы «по группам» (Жара 2025): строки-заголовки групп пропускаются, Start
необязателен, категории «Мужчины 1986−1990 г. р.» / «Мальчики 2014 г.р.» → краткий
вид как в 2026 («М35-39» — возраст в год старта). Элита (src/analytics/elite.py) —
в Bib «Элита» или фамилия (именной номер, Жара 2025): служебный номер как у замыкающих
в загрузчике (максимальный номер + 1000…), на сайте «Элита», диплом — по этому номеру.
Числовой номер вне основных диапазонов Жары 21,1 км («Присвоить номера») — тоже элита.
Места считаются заново: абсолютное/пол/категория по времени выстрела и по
чистому времени. client_id подставляет trg_results_before_insert.

  python scripts/import_results_xlsx.py --event-id 95 --xlsx …            # dry-run
  python scripts/import_results_xlsx.py --event-id 95 --xlsx … --apply
"""

import argparse
import collections
import datetime
import difflib
import json
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent.parent))

import openpyxl

from scripts.import_boom_historical import get_connection
from src.analytics.elite import distance_label, is_elite, is_pacer, main_ranges
from src.common.categories import age_category, canonical_category
from src.common.names import normalize_person_name, normalize_sex

SENTINEL = "1900-01-01"
SEX = {"Male": "Мужчина", "Female": "Женщина"}
SERVICE_NUMBER_OFFSET = 1000                         # как SWEEPER_NUMBER_OFFSET в load_race_results.py
_GROUP = re.compile(r"^\s*(мужчины|юноши|мальчики|женщины|девушки|девочки)\W*(\d{4})(?:\s*[-−–]\s*(\d{4}))?", re.I)
# статусы протоколов (англ./рус./исп. выгрузки Copernico) → как в остальных результатах БД
STATUS = {"Disqualified": "DSQ", "Финишировал": "Finished", "Не стартовал": "Not started",
          "Не финишировал": "DNF", "Дисквалификация": "DSQ", "Сошел": "Withdrawn", "Сошёл": "Withdrawn",
          "Finalizado": "Finished", "Sin salida": "Not started", "Retirado": "Withdrawn", "Descalificado": "DSQ"}
_GROUP_HEADER = re.compile(r"^\s*(мужчины|юноши|мальчики|женщины|девушки|девочки)", re.I)
_PACER_GROUP = re.compile(r"пейс|pacer", re.I)                  # «Пейсмейкеры» (Жара 2024)


def _secs(v):
    if isinstance(v, datetime.time):
        return v.hour * 3600 + v.minute * 60 + v.second
    if isinstance(v, datetime.timedelta):
        return int(v.total_seconds())
    try:
        h, m, s = (int(x) for x in str(v).strip().split(":"))
        return h * 3600 + m * 60 + s
    except (TypeError, ValueError):
        return None


def _birthday(v):
    if isinstance(v, datetime.datetime):
        return v.date().isoformat()
    try:
        return datetime.datetime.strptime(str(v).strip(), "%d/%m/%Y").date().isoformat()
    except ValueError:
        return SENTINEL


def _hms(s):
    return None if s is None else f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def finish_columns(h, rows):
    """-> (чистое | None, официальное) — индексы колонок времени финиша (см. docstring модуля)."""
    low = [x.lower().replace('"', "").replace("«", "").replace("»", "") for x in h]
    cand = [k for k, x in enumerate(low) if x.startswith(("finish", "финиш", "результат")) or "чист" in x]
    timed = [k for k in cand if (vals := [r[k] for r in rows if len(r) > k and r[k] not in (None, "")])
             and sum(_secs(v) is not None for v in vals) >= 0.9 * len(vals)]
    if not timed or len(timed) > 2:
        raise ValueError(f"не удалось определить колонки финиша: {[h[k] for k in cand]}")
    if len(timed) == 1:
        return None, timed[0]
    a, b = timed
    named = [k for k in timed if "чист" in low[k]]
    if named:
        clean = named[0]
    else:
        pairs = [(_secs(r[a]), _secs(r[b])) for r in rows if _secs(r[a]) and _secs(r[b])]
        clean = a if sum(x for x, _ in pairs) <= sum(y for _, y in pairs) else b
    gun = b if clean == a else a
    bad = sum(1 for r in rows if _secs(r[clean]) and _secs(r[gun]) and _secs(r[clean]) > _secs(r[gun]))
    if bad:
        raise ValueError(f"чистое время больше официального у {bad} строк: «{h[clean]}» / «{h[gun]}»")
    return clean, gun


HEADER_ALIASES = {"номер": "Bib", "фамилия": "Surname", "имя": "Name",      # протоколы с русскими/англ.
                  "дата рождения": "Date of Birth", "статус": "Status",      # заголовками в любом регистре
                  "bib": "Bib", "dorsal": "Bib", "surname": "Surname", "name": "Name",
                  "date of birth": "Date of Birth", "birthdate": "Date of Birth", "status": "Status",
                  "gender": "Gender", "category": "Category", "start": "Start", "старт": "Start",
                  "год рождения": "Birth Year"}
_LETTER_BIB = re.compile(r"^(\d+)[а-яa-z]$", re.I)


def _number(bib):
    """«1859» и «1859а» (буква — пометка организатора) → номер; текст («Элита», «Замыкающий») → None."""
    if bib.isdigit():
        return int(bib)
    m = _LETTER_BIB.match(bib)
    return int(m.group(1)) if m else None


_KIDS = {"мальчики": "Мальчики", "девочки": "Девочки"}


def group_sex(category) -> str:
    """Пол по названию группы протокола («Девочки 2016 г.р.» → «Женщина»); иначе ''."""
    m = _GROUP.match(category or "")
    if not m:
        return ""
    return "Мужчина" if m.group(1).lower() in ("мужчины", "юноши", "мальчики") else "Женщина"


def short_category(category, year):
    """«Мужчины 1986−1990 г. р.» → «М35-39» (возраст в год старта). Детский забег — как в
    результатах 2026 (Copernico): «Мальчики 2014 г.р.» (решение 2026-10-06). Остальное — как есть."""
    m = _GROUP.match(category or "")
    if not m:
        return category
    if m.group(1).lower() in _KIDS:
        return f"{_KIDS[m.group(1).lower()]} {m.group(2)} г.р."
    sex = "М" if m.group(1).lower() in ("мужчины", "юноши", "мальчики") else "Ж"
    y1, y2 = int(m.group(2)), int(m.group(3) or m.group(2))
    young, old = year - max(y1, y2), year - min(y1, y2)
    if "старше" in category.lower():                    # «Женщины 1960 г.р. и старше» → «Ж65+»
        return f"{sex}{old}+"
    return f"{sex}{young}" if young == old else f"{sex}{young}-{old}"


_KM_HEADER = re.compile(r"^(\d+(?:[.,]\d+)?)\s*(?:km|км)?$", re.I)
MAX_CHECKPOINTS = 7


def checkpoint_columns(h, overrides):
    """{индекс колонки: км} — отметки по названию («2,5», «4,5km») и из --checkpoints."""
    cols = {}
    for k, name in enumerate(h):
        low = name.strip().lower()
        if low in overrides:
            cols[k] = overrides[low]
        elif (m := _KM_HEADER.match(low)):
            cols[k] = float(m.group(1).replace(",", "."))
    return cols


def parse(path, year, overrides=None):
    ws = openpyxl.load_workbook(path, read_only=True, data_only=True).active
    rows = list(ws.iter_rows(values_only=True))
    # строка заголовков — первая с «Фамилия»/«Surname» (у протоколов Жары 2024 сверху шапка)
    head = next(k for k, r in enumerate(rows[:20])
                if r and any(str(v or "").strip().lower() in ("фамилия", "surname") for v in r))
    h = [HEADER_ALIASES.get(str(x or "").strip().lower(), str(x or "").strip()) for x in rows[head]]
    rows = rows[head:]
    i = {k: h.index(k) for k in ("Surname", "Name", "Status")}
    bib_i = h.index("Bib") if "Bib" in h else None                  # Женская 2024 — без номеров
    bd_i = h.index("Date of Birth") if "Date of Birth" in h else None
    by_i = h.index("Birth Year") if "Birth Year" in h else None      # Жара 2024 — только год
    start_i = h.index("Start") if "Start" in h else None
    sex_i = h.index("Gender") if "Gender" in h else None
    i["clean"], i["Finish"] = finish_columns(h, rows[1:])
    cat_i = h.index("Category") if "Category" in h else None
    cp_cols = checkpoint_columns(h, overrides or {})
    out = []
    group = ""                                       # текущий заголовок группы протокола «по группам»
    pacers = False                                   # группа «Пейсмейкеры»: без категории, пол — из заявки
    for r in rows[1:]:
        if not r or not r[i["Surname"]]:                               # пусто / заголовок группы
            if r and r[0] and _GROUP_HEADER.match(str(r[0])):
                group, pacers = str(r[0]).strip(), False
            elif r and r[0] and _PACER_GROUP.search(str(r[0])):
                group, pacers = "", True
            continue
        bib = str(r[bib_i] or "").strip() if bib_i is not None else ""
        raw_category = (str(r[cat_i] or "").strip() if cat_i is not None else "") or group
        category = canonical_category(short_category(raw_category, year))
        sex = SEX.get(str(r[sex_i] or "").strip(), "") if sex_i is not None else ""
        if not sex:                                                     # нет Gender — пол из группы/категории
            sex = group_sex(raw_category)
        if not sex and category[:1].upper() in ("М", "Ж"):
            sex = "Мужчина" if category[:1].upper() == "М" else "Женщина"
        status = STATUS.get(str(r[i["Status"]] or "").strip(), str(r[i["Status"]] or "").strip())
        clean = _secs(r[i["clean"]]) if i["clean"] is not None else None
        gun = _secs(r[i["Finish"]])
        finished = status == "Finished" and gun
        out.append({
            "surname": normalize_person_name(str(r[i["Surname"]])), "name": normalize_person_name(str(r[i["Name"]] or "")),
            "birthday": _birthday(r[bd_i]) if bd_i is not None else SENTINEL,
            "birth_year": int(r[by_i]) if by_i is not None and str(r[by_i] or "").strip().isdigit() else None,
            "sex": sex,
            "bib": bib, "start_number": _number(bib),
            "category": category,
            "race_status": status, "start": _secs(r[start_i]) if start_i is not None else None,
            "gun": gun if finished else None, "clean": clean if finished else None,
            "kt": {km: t for k, km in cp_cols.items() if (t := _secs(r[k]))},
            "pacer_group": pacers,
        })
    return out


def rank(rows):
    fin = [r for r in rows if r["gun"]]
    for field, suffix in (("gun", ""), ("clean", "_clean")):
        order = sorted((r for r in fin if r[field]), key=lambda r: (r[field], r["start_number"]))
        by_sex, by_cat = collections.Counter(), collections.Counter()
        for n, r in enumerate(order, 1):
            by_sex[r["sex"]] += 1
            by_cat[r["category"]] += 1
            r["rank_absolute" + suffix], r["rank_sex" + suffix], r["rank_category" + suffix] = n, by_sex[r["sex"]], by_cat[r["category"]]


def _name_key(text):
    return str(text or "").strip().lower().replace("ё", "е")


def fill_from_leads(cur, event_id, rows):
    """--from-leads (решение 2026-10-06): номера нет в протоколе (Женская 2024) — номер из заявки
    того же забега; только год рождения (Жара 2024) — полная дата из заявки с тем же ФИО и годом.
    ДР по ФИО (Жара 2024 — в заявках нет номеров): ФИО+год → фамилия+год+похожее имя («Макским»,
    «Ира») → ФИО без года (пейсеры); ФИ и пол — из заявки.
    ДР по номеру: заявка с тем же номером и той же фамилией или годом рождения —
    её ДР (если год сходится), ФИ и пол (у пейсеров пола в протоколе нет); иначе по ФИО и году.
    Номер ищется по ступеням: ФИО+ДР → фамилия+ДР → имя+ДР → фамилия+имя → фамилия (уменьшительные
    имена «Юлька», опечатки в фамилии «Жиленковв» и в ДР) — среди заявок, чей номер ещё не занят, и только однозначно с обеих
    сторон; ФИ строки берутся из заявки — иначе trg_results_before_insert не свяжет результат с
    карточкой заявки и заведёт новую. Не нашлось — ДР «01.01.год», номер служебный.
    -> {что сделано: число}, [не найдено], [найдено не по ФИО+ДР — на проверку]."""
    cur.execute("SELECT surname, name, birthday, start_number, sex FROM leads WHERE event_id = %s", (event_id,))
    fetched = cur.fetchall()
    leads = [(_name_key(s), _name_key(n), bd, bib, s, n) for s, n, bd, bib, _ in fetched]
    by_name = collections.defaultdict(list)
    for surname, name, bd, bib, *_ in leads:
        by_name[(surname, name)].append((bd, bib))
    by_bib = collections.defaultdict(list)
    for s_orig, n_orig, bd, bib, sex in fetched:
        if bib:
            by_bib[int(bib)].append((s_orig, n_orig, bd, sex))
    done, missing, loose = collections.Counter(), [], []
    for r in rows:
        if r["birthday"] != SENTINEL or not r["start_number"]:
            continue
        cands = [c for c in by_bib.get(r["start_number"], [])
                 if _name_key(c[0]) == _name_key(r["surname"]) or (c[2] and c[2].year == r.get("birth_year"))]
        if len(cands) != 1:
            continue
        surname, name, bd, sex = cands[0]
        if bd and bd.year > 1900 and (not r.get("birth_year") or bd.year == r["birth_year"]):
            r["birthday"] = str(bd)
            done["ДР из заявки (по номеру)"] += 1
        if (_name_key(surname), _name_key(name)) != (_name_key(r["surname"]), _name_key(r["name"])):
            loose.append(f"№{r['start_number']} {r['surname']} {r['name']} → заявка {surname} {name}")
            r["surname"], r["name"] = surname, name
        if not r.get("sex") and sex:
            r["sex"] = normalize_sex(sex)
            done["пол из заявки"] += 1
    # ДР по ФИО — ступени, каждая заявка один раз и однозначно с обеих сторон
    by_surname = collections.defaultdict(list)
    for k, (surname, *_rest) in enumerate(leads):
        by_surname[surname].append(k)
    year_ok = lambda r, bd: r.get("birth_year") and bd and bd.year == r["birth_year"]
    similar = lambda a, b: a == b or difflib.SequenceMatcher(None, a, b).ratio() >= 0.6
    bd_stages = (("ФИО+год", lambda r, l: l[1] == _name_key(r["name"]) and year_ok(r, l[2])),
                 ("фамилия+год+похожее имя", lambda r, l: year_ok(r, l[2]) and similar(l[1], _name_key(r["name"]))),
                 ("ФИО без года", lambda r, l: not r.get("birth_year") and l[1] == _name_key(r["name"])))
    pending = [r for r in rows if r["birthday"] == SENTINEL]
    taken = set()
    for label, ok in bd_stages:
        hits = {id(r): [k for k in by_surname.get(_name_key(r["surname"]), []) if k not in taken and ok(r, leads[k])]
                for r in pending}
        # строки одного человека (те же ФИО и год, результат не больше чем у одной — перерегистрация
        # под другим номером, Жара 2024) делят заявку
        per_lead = collections.defaultdict(list)
        for r in pending:
            for k in hits[id(r)]:
                per_lead[k].append(r)
        person = lambda r: (_name_key(r["surname"]), _name_key(r["name"]), r.get("birth_year"))
        same_person = lambda rs: len({person(x) for x in rs}) == 1 and sum(x["race_status"] == "Finished" for x in rs) <= 1
        for r in list(pending):
            ks = hits[id(r)]
            if len(ks) != 1 or not same_person(per_lead[ks[0]]):
                continue
            k = ks[0]
            _s, _n, bd, _bib, surname, name = leads[k]
            sex = fetched[k][4]
            if r is per_lead[k][-1]:
                taken.add(k)
            pending.remove(r)
            if bd and bd.year > 1900:
                r["birthday"] = str(bd)
            done["ДР из заявки" + ("" if label == "ФИО+год" else f" ({label})")] += 1
            if (_s, _n) != (_name_key(r["surname"]), _name_key(r["name"])):
                loose.append(f"{r['surname']} {r['name']} {r.get('birth_year') or ''} → заявка {surname} {name} {bd}")
                r["surname"], r["name"] = surname, name
            if not r.get("sex") and sex:
                r["sex"] = normalize_sex(sex)
                done["пол из заявки"] += 1
    for r in pending:
        if r.get("birth_year"):
            r["birthday"] = f"{r['birth_year']}-01-01"
        missing.append(f"{r['surname']} {r['name']} {r.get('birth_year') or 'без года'} {r['race_status']}"
                       f" — {'несколько заявок' if by_name.get((_name_key(r['surname']), _name_key(r['name']))) else 'нет заявки'}")

    used = {r["start_number"] for r in rows if r["start_number"]}
    pending = [r for r in rows if r["start_number"] is None and not r["bib"]]
    stages = (("ФИО+ДР", lambda s, n, bd: (s, n, bd)), ("фамилия+ДР", lambda s, n, bd: (s, bd)),
              ("имя+ДР", lambda s, n, bd: (n, bd)), ("фамилия+имя", lambda s, n, bd: (s, n)), ("фамилия", lambda s, n, bd: (s,)))
    for label, key in stages:
        free = collections.defaultdict(list)
        for surname, name, bd, bib, orig_surname, orig_name in leads:
            if bib and int(bib) not in used:
                free[key(surname, name, str(bd))].append((orig_surname, orig_name, bd, int(bib)))
        row_key = lambda r: key(_name_key(r["surname"]), _name_key(r["name"]), r["birthday"])
        rows_per_key = collections.Counter(row_key(r) for r in pending)
        for r in list(pending):
            cands = free.get(row_key(r), [])
            if len(cands) != 1 or rows_per_key[row_key(r)] != 1:
                continue
            surname, name, bd, bib = cands[0]
            r["start_number"] = bib
            used.add(bib)
            pending.remove(r)
            done["номер из заявки" + ("" if label == "ФИО+ДР" else f" ({label})")] += 1
            if label != "ФИО+ДР":
                loose.append(f"{r['surname']} {r['name']} {r['birthday']} → №{bib}: заявка {surname} {name} {bd}")
                r["surname"], r["name"] = surname, name
    missing += [f"{r['surname']} {r['name']} {r['birthday']} {r['race_status']} — нет заявки" for r in pending]
    return done, missing, loose


def drop_protocol_duplicates(rows):
    """Один человек дважды в протоколе (Женская 2024: «финишировала» и «не стартовала») — ФИО, ДР
    и номер (или его отсутствие) совпадают; остаётся строка с результатом. -> (строки, [убранные])."""
    key = lambda r: (_name_key(r["surname"]), _name_key(r["name"]), r["birthday"], r.get("birth_year"), r["start_number"])
    best = {}
    for r in rows:
        if key(r) not in best or (r["race_status"] == "Finished" and best[key(r)]["race_status"] != "Finished"):
            best[key(r)] = r
    return [r for r in rows if best[key(r)] is r], [r for r in rows if best[key(r)] is not r]


def write_checkpoints(cur, event_id, distance_km, rows):
    """Отметки: дистанции → events.checkpoint_distances, время и темп → results по номеру.
    -> (км отметок, обновлено строк)."""
    kms = sorted({km for r in rows for km in r["kt"]})
    if not kms:
        return [], 0
    if len(kms) > MAX_CHECKPOINTS or kms[-1] >= distance_km:
        raise ValueError(f"отметки {kms} не помещаются в {MAX_CHECKPOINTS} КТ до финиша {distance_km} км")
    cur.execute("UPDATE events SET checkpoint_distances = %s WHERE id = %s",
                (json.dumps([0] + kms + [distance_km]), event_id))
    cols = ", ".join(f"time_clear_kt{n} = %s, pace_avg_kt{n} = %s" for n in range(1, MAX_CHECKPOINTS + 1))
    updated = 0
    for r in rows:
        if not r["kt"]:
            continue
        vals = []
        for n in range(MAX_CHECKPOINTS):
            km = kms[n] if n < len(kms) else None
            t = r["kt"].get(km) if km else None
            vals += [_hms(t), _hms(int(t / km)) if t else None]          # темп — как загрузчик (_seconds_to_pace)
        cur.execute(f"UPDATE results SET {cols} WHERE event_id = %s AND start_number = %s",
                    vals + [event_id, r["start_number"]])
        updated += cur.rowcount
    return kms, updated


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--xlsx", required=True, nargs="+", help="один или несколько протоколов одного события (Детский — по годам рождения)")
    ap.add_argument("--event-id", type=int, required=True, help="событие в БД (дистанция берётся из events)")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--checkpoints", default="", help="км отметок для колонок без километража: «razv1=1.75,razv2=5.25»")
    ap.add_argument("--checkpoints-only", action="store_true", help="только дописать отметки в уже загруженные результаты")
    ap.add_argument("--from-leads", action="store_true",
                    help="нет номера / только год рождения — взять из заявок этого забега (по ФИО)")
    ap.add_argument("--sex", help="пол тем, у кого его нет в протоколе (Женская семёрка — «Женщина»)")
    ap.add_argument("--age-categories", action="store_true",
                    help="нет категорий в протоколе — по возрасту в год старта (как Женская 2025)")
    ap.add_argument("--add-missing", action="store_true",
                    help="догрузить строки, которых нет в БД (по номеру), и пересчитать места всех по файлу")
    args = ap.parse_args()
    overrides = {k.strip().lower(): float(v) for k, v in (p.split("=") for p in args.checkpoints.split(",") if p)}

    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT event_name, event_year, event_distance FROM events WHERE id = %s", (args.event_id,))
        ev = cur.fetchone()
        if not ev:
            print(f"Нет события {args.event_id}")
            return 1
        rows = [row for path in args.xlsx for row in parse(path, int(ev[1]), overrides)]
        rows, dropped = drop_protocol_duplicates(rows)
        for r in dropped:
            print(f"Повтор в протоколе убран: {r['surname']} {r['name']} {r['birthday']} {r['race_status']}")
        if args.from_leads:
            done, missing, loose = fill_from_leads(cur, args.event_id, rows)
            print(f"Из заявок: {dict(done)}; не найдено однозначно: {len(missing)}")
            for line in missing:
                print("   ", line)
            print(f"Номер не по ФИО+ДР (проверить): {len(loose)}")
            for line in loose:
                print("   ", line)
        year = int(ev[1])
        for r in rows:
            if args.sex and not r["sex"]:
                r["sex"] = args.sex
            if args.age_categories and not r["category"] and r["sex"] and r["birthday"] != SENTINEL:
                r["category"] = age_category(r["sex"][:1], year - int(r["birthday"][:4]))
        ranges = main_ranges(cur, ev[0], distance_label(ev[2]))
        next_service = max([r["start_number"] for r in rows if r["start_number"]] or [0]) + SERVICE_NUMBER_OFFSET
        for r in rows:
            r["is_elite"] = int(is_elite(r["bib"], ranges, r["surname"]))
            r["is_pacer"] = int(is_pacer(r["bib"]) or r["pacer_group"])
            if r["start_number"] is None:               # именной номер / «Элита» — служебный номер
                r["start_number"], next_service = next_service, next_service + 1
        rank(rows)
        bibs = collections.Counter(r["start_number"] for r in rows)
        dup = [b for b, k in bibs.items() if k > 1]
        print(f"Строк: {len(rows)}, по статусам: {dict(collections.Counter(r['race_status'] for r in rows))}, "
              f"без даты рождения: {sum(r['birthday'] == SENTINEL for r in rows)}, без пола: {sum(not r['sex'] for r in rows)}, "
              f"элита: {sum(r['is_elite'] for r in rows)} (основные диапазоны: {ranges or 'не заданы'}), "
              f"текст вместо номера не-элиты: {[r['bib'] for r in rows if r['bib'] and not r['bib'].isdigit() and not r['is_elite']]}, "
              f"повторы номеров: {dup}")
        print("Категории:", dict(sorted(collections.Counter(r["category"] for r in rows).items())))
        kt_count = collections.Counter(km for r in rows for km in r["kt"])
        print("Отметки (км: участников):", dict(sorted(kt_count.items())) or "нет")
        if dup:
            return 1
        if args.checkpoints_only:
            if not args.apply:
                print("\ndry-run (только отметки). Повтори с --apply.")
                return 0
            kms, updated = write_checkpoints(cur, args.event_id, float(ev[2]), rows)
            conn.commit()
            print(f"Отметки {kms}: обновлено результатов {updated} из {sum(1 for r in rows if r['kt'])}")
            return 0
        cur.execute("SELECT COUNT(*) FROM results WHERE event_id = %s", (args.event_id,))
        existing = cur.fetchone()[0]
        print(f"Событие {args.event_id}: {ev}, результатов в БД: {existing}")
        cur.execute("SELECT start_number FROM results WHERE event_id = %s", (args.event_id,))
        in_db = {r[0] for r in cur.fetchall()}
        if args.add_missing:
            missing = [r for r in rows if r["start_number"] not in in_db]
            print("Догрузить:", [f"№{r['start_number']} {r['surname']} {r['name']} {r['race_status']}" for r in missing])
        if not ev or not ev[2] or (existing and not args.add_missing):
            print("Нет события, нет дистанции или результаты уже есть — не загружаю.")
            return 1
        distance_km = float(ev[2])
        if not args.apply:
            print("\ndry-run. Повтори с --apply.")
            return 0
        pace = lambda s: _hms(round(s / distance_km)) if s else None
        all_rows = rows
        if args.add_missing:                         # вставляем только недостающие, места — всем ниже
            rows = missing
        cur.executemany(
            """INSERT INTO results (surname, name, birthday, client_id, event_id, sex, start_number, category,
                   race_status, time_gun_start, time_gun_finish, time_clear_finish, rank_absolute, rank_sex,
                   rank_category, rank_absolute_clean, rank_sex_clean, rank_category_clean, finish_pace_avg_gun,
                   finish_pace_avg_clean, time_gun_finish_ms, time_clear_finish_ms, is_elite, is_pacer)
               VALUES (%s, %s, %s, 0, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            [(r["surname"], r["name"], r["birthday"], args.event_id, r["sex"], r["start_number"], r["category"],
              r["race_status"], _hms(r["start"]), _hms(r["gun"]), _hms(r["clean"]), r.get("rank_absolute"),
              r.get("rank_sex"), r.get("rank_category"), r.get("rank_absolute_clean"), r.get("rank_sex_clean"),
              r.get("rank_category_clean"), pace(r["gun"]), pace(r["clean"]),
              r["gun"] * 1000 if r["gun"] else None, r["clean"] * 1000 if r["clean"] else None,
              r["is_elite"], r["is_pacer"]) for r in rows])
        if args.add_missing:
            ranks = ("rank_absolute", "rank_sex", "rank_category", "rank_absolute_clean", "rank_sex_clean", "rank_category_clean")
            for r in all_rows:
                cur.execute(f"UPDATE results SET {', '.join(f'{c} = %s' for c in ranks)} WHERE event_id = %s AND start_number = %s",
                            [r.get(c) for c in ranks] + [args.event_id, r["start_number"]])
            rows = all_rows
        kms, updated = write_checkpoints(cur, args.event_id, distance_km, rows)
        conn.commit()
        if kms:
            print(f"Отметки {kms}: записано у {updated}")
        cur.execute("SELECT COUNT(*), SUM(client_id = 0), SUM(race_status = 'Finished') FROM results WHERE event_id = %s",
                    (args.event_id,))
        print("Загружено (всего, без клиента, финишировали):", cur.fetchone())
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
