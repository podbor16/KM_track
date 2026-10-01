#!/usr/bin/env python3
"""
Чистка карточек клиентов (2026-09-26, решения пользователя по аудиту):

1. ФИО в полях: невидимые символы, лишние пробелы, латиница-двойники и
   посторонние символы; регистр «Иванов»; отчество и инициалы убираются;
   ФИО целиком в одном/обоих полях и имя/фамилия местами — раскладываются по
   полям; латиница -> кириллица, если это русское ФИ (имя узнаётся по
   частотным именам с учётом пола), иностранные ФИ остаются латиницей.
2. Склейка дублей (все категории аудита D1–D8): те же ФИ+ДР, ФИ переставлены,
   ДР-заглушка, ДР отличается на цифру/день↔месяц, разные ДР при общем
   email/телефоне, опечатка в букве фамилии/имени, -а в фамилии; одно слово
   вместо ФИ — карточка с тем же словом, той же ДР и общим контактом.
   Выживает карточка с наибольшим числом результатов, затем заявок; ФИО и ДР
   группы — взвешенное большинство (вес — результаты и заявки), -а в фамилии —
   по полу. Заявки и результаты остальных карточек переносятся к ней.
3. ФИО и ДР в leads/results затронутых карточек приводятся к карточке.
   Флаги заявок (is_duplicate, is_new) не пересчитываются: is_duplicate=1
   убрал бы обе заявки из выгрузки стартового списка.

  python scripts/clean_clients.py --report /tmp/review.xlsx                              # dry-run

После проверки отчёта пользователем:
  python scripts/clean_clients.py --make-decisions review.xlsx --orig report.xlsx --out decisions.json   # без БД
  python scripts/clean_clients.py --decisions decisions.json [--apply --backup /root/backups/x.json]
"""

import argparse
import collections
import itertools
import json
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.analytics.client_merge import apply, recompute_aggregates  # noqa: E402,F401
from src.common.names import (_CYR, SENTINELS, Names, _near_bd, canonical_fio, lev, norm,  # noqa: E402,F401
                                 title, tokens, translit)

# ---------------------------------------------------------------- дубли

def _phone(v):
    d = re.sub(r"\D", "", v or "")
    return d[-10:] if len(d) >= 10 else ""


def _email(v):
    v = (v or "").strip().lower()
    return "" if v in ("", "example@mail.ru") else v


def _lev1(a, b):
    return a != b and lev(a, b, 1) == 1




def find_groups(cards):
    """cards: {id: {s, n, bd, contacts, ...}} с каноническими s/n.
    -> [(set(id), {категории})] — группы из ≥2 карточек."""
    parent = {i: i for i in cards}
    cats = collections.defaultdict(set)

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b, cat):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra
        cats[(min(a, b), max(a, b))].add(cat)

    by_fi, by_nb, by_sb, by_word = (collections.defaultdict(list) for _ in range(4))
    for i, c in cards.items():
        fi = (norm(c["s"]), norm(c["n"]))
        if not fi[0] or not fi[1]:                    # ФИО не разобрано — только правило «одно слово»
            continue
        by_fi[fi].append(i)
        if c["bd"] not in SENTINELS:
            by_nb[(fi[1], c["bd"])].append(i)
            by_sb[(fi[0], c["bd"])].append(i)
    for fi, ids in by_fi.items():
        for a, b in itertools.combinations(ids, 2):
            ca, cb = cards[a], cards[b]
            shared = ca["contacts"] & cb["contacts"]
            if ca["bd"] == cb["bd"]:
                union(a, b, "D1 те же ФИ и ДР")
            elif ca["bd"] in SENTINELS or cb["bd"] in SENTINELS:
                real = {cards[x]["bd"] for x in ids if cards[x]["bd"] not in SENTINELS}
                if shared or len(real) == 1:
                    union(a, b, "D3a/D4 ДР-заглушка")
            elif shared:
                union(a, b, "D3b разные ДР, общий контакт")
            elif _near_bd(ca["bd"], cb["bd"]):
                union(a, b, "D5 ДР отличается на цифру")
        swapped = (fi[1], fi[0])
        if swapped != fi:
            for a in ids:
                for b in by_fi.get(swapped, []):
                    if cards[a]["bd"] == cards[b]["bd"]:
                        union(a, b, "D2 ФИ переставлены")
    for group_by, cat_a, cat_b in ((by_nb, "D6 опечатка в фамилии", "D6b -а в фамилии"), (by_sb, "D7 опечатка в имени", None)):
        for (_, _), ids in group_by.items():
            for a, b in itertools.combinations(ids, 2):
                x, y = ((norm(cards[a]["s"]), norm(cards[b]["s"])) if cat_b else (norm(cards[a]["n"]), norm(cards[b]["n"])))
                if _lev1(x, y):
                    union(a, b, cat_b if cat_b and (x + "а" == y or y + "а" == x) else cat_a)
    # одно слово вместо ФИ: карточка с этим словом в фамилии или имени, той же ДР и общим контактом
    for i, c in cards.items():
        if c.get("one_word"):
            w = norm(c["s"] or c["n"])
            for j, d in cards.items():
                if j != i and d["bd"] == c["bd"] and c["contacts"] & d["contacts"] and \
                        w in (norm(d["s"]), norm(d["n"])) and not d.get("one_word"):
                    union(i, j, "L одно слово вместо ФИ")
    groups = collections.defaultdict(set)
    for i in cards:
        groups[find(i)].add(i)
    out = []
    for ids in groups.values():
        if len(ids) > 1:
            gc = set()
            for a, b in itertools.combinations(sorted(ids), 2):
                gc |= cats.get((a, b), set())
            out.append((ids, gc))
    return out


def resolve_group(ids, cards, names):
    """-> (выжившая id, фамилия, имя, ДР) группы."""
    w = {i: 10 * cards[i]["nr"] + cards[i]["nl"] + 1 for i in ids}
    survivor = max(ids, key=lambda i: (cards[i]["nr"], cards[i]["nl"], cards[i]["bd"] not in SENTINELS, -i))

    def vote(field, ok=lambda v: True):
        tally = collections.Counter()
        for i in ids:
            v = cards[i][field]
            if v and ok(v):
                tally[v] += w[i]
        return tally.most_common(1)[0][0] if tally else cards[survivor][field]

    cyr = lambda v: bool(_CYR.search(v))
    has_cyr = any(cyr(cards[i]["n"]) for i in ids)
    name = vote("n", lambda v: (cyr(v) or not has_cyr) and (names.is_first(v) or not any(names.is_first(cards[i]["n"]) for i in ids)))
    surname = vote("s", lambda v: (cyr(v) or not has_cyr) and len(v) > 1)
    # -а в фамилии — по полу группы
    sexes = collections.Counter(cards[i]["sex"] for i in ids if cards[i]["sex"])
    sex = sexes.most_common(1)[0][0] if sexes else ""
    variants = {cards[i]["s"] for i in ids}
    base = surname[:-1] if surname.endswith("а") and surname[:-1] in variants else surname
    if base + "а" in variants or base != surname:
        surname = base + "а" if sex == "Ж" else base
    bd = vote("bd", lambda v: v not in SENTINELS)
    return survivor, surname, name, bd


# ---------------------------------------------------------------- БД

def load(conn):
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT c.id, c.surname, c.name, c.birthday, c.email, c.phone,
               (SELECT COUNT(*) FROM leads l WHERE l.client_id = c.id) nl,
               (SELECT COUNT(*) FROM results r WHERE r.client_id = c.id) nr
        FROM clients c WHERE c.id <> 0""")
    clients = cur.fetchall()
    cur.execute("SELECT client_id, surname, name, sex, email, phone FROM leads")
    leads = cur.fetchall()
    cur.execute("SELECT client_id, surname, name, sex FROM results")
    results = cur.fetchall()
    cur.close()
    return clients, leads, results


def build_cards(clients, leads, results, names):
    sex = collections.defaultdict(collections.Counter)
    contacts = collections.defaultdict(set)
    for r in leads:
        sex[r["client_id"]][(r["sex"] or "")[:1].upper()] += 1
        contacts[r["client_id"]] |= {x for x in (_email(r["email"]), _phone(r["phone"])) if x}
    for r in results:
        sex[r["client_id"]][(r["sex"] or "")[:1].upper()] += 1
    cards = {}
    for c in clients:
        x = sex[c["id"]]
        x.pop("", None)
        sx = x.most_common(1)[0][0] if x else ""
        s, n, notes = canonical_fio(c["surname"], c["name"], names, sx)
        cards[c["id"]] = {
            "id": c["id"], "s0": c["surname"], "n0": c["name"], "s": s, "n": n, "notes": notes,
            "bd": str(c["birthday"]), "sex": sx, "nl": c["nl"], "nr": c["nr"],
            "contacts": contacts[c["id"]] | {x for x in (_email(c["email"]), _phone(c["phone"])) if x},
            "one_word": "одно слово в обоих полях" in notes or not s or not n,
        }
    return cards


def plan_changes(cards, names):
    groups = find_groups(cards)
    final, merged_into, group_info = {}, {}, []
    for gi, (ids, cats) in enumerate(sorted(groups, key=lambda g: min(g[0])), 1):
        survivor, s, n, bd = resolve_group(ids, cards, names)
        final[survivor] = (s, n, bd)
        for i in ids:
            if i != survivor:
                merged_into[i] = survivor
        group_info.append((gi, sorted(ids, key=lambda i: (i != survivor, i)), cats, survivor, (s, n, bd)))
    for i, c in cards.items():
        if i not in final and i not in merged_into and not c["one_word"] and (c["s"], c["n"]) != (c["s0"], c["n0"]):
            final[i] = (c["s"], c["n"], c["bd"])
    # уникальность (фамилия, имя, ДР) после изменений — как uk_client
    keys = collections.Counter()
    for i, c in cards.items():
        if i in merged_into:
            continue
        s, n, bd = final.get(i, (c["s0"], c["n0"], c["bd"]))
        keys[(norm(s), norm(n), bd)] += 1
    clash = [k for k, v in keys.items() if v > 1]
    return final, merged_into, group_info, clash




# ---------------------------------------------------------------- решения пользователя

_GROUP_SHEETS = ("Склейка", "Склейка ДР ±15 лет")
_RED = "FFFF0000"


def _fix_letters(v):
    """«Михалëва» — латинская ë -> ё."""
    return str(v or "").strip().replace("ë", "ё").replace("Ë", "Ё")


def make_decisions(user_path, orig_path):
    """Проверенный пользователем xlsx + исходный отчёт -> решения по id карточек:
    groups — [{id выжившей: фамилия, имя, ДР, члены}], renames — {id: (фамилия, имя)},
    exclude — «Не решено» + строки, выделенные красным (их не трогаем).
    Правило группы: строки «Выживает: да» — отдельные карточки со своими
    «Станет …»; остальные строки — к выжившей с той же «Станет ДР» (или к
    единственной). Правка имени на листе «Латиница»/«ФИО» важнее «Станет»
    группы, если строку выжившей в листе склейки не правили."""
    import openpyxl
    u = openpyxl.load_workbook(user_path)
    o = openpyxl.load_workbook(orig_path, read_only=True)
    vals = lambda wb, s: [r for r in wb[s].iter_rows(min_row=2, values_only=True) if any(v not in (None, "") for v in r)]
    errors, exclude = [], set()
    for ws in u.worksheets:                                   # красные строки
        id_col = 2 if ws.title in _GROUP_SHEETS else 0
        for r in ws.iter_rows(min_row=2):
            if any(c.fill is not None and c.fill.fill_type == "solid" and c.fill.fgColor.type == "rgb"
                   and c.fill.fgColor.rgb == _RED for c in r) and r[id_col].value:
                exclude.add(int(r[id_col].value))
    exclude |= {int(r[0]) for r in vals(u, "Не решено")}

    same = lambda a, b: [str(x or "") for x in a] == [str(x or "") for x in b]
    orig_g = {(r[0], r[2]): r for r in vals(o, "Склейка")}
    final_g, edited_g = dict(orig_g), set()
    for s in _GROUP_SHEETS:
        for r in vals(u, s):
            k = (r[0], r[2])
            if k in orig_g and not same(r, orig_g[k]):
                if k in edited_g and not same(r, final_g[k]):
                    errors.append(f"группа {k[0]}, id {k[1]}: разные правки на листах склейки")
                final_g[k] = r
                edited_g.add(k)
    ov, ov_orig = {}, {}
    for s in ("Латиница", "ФИО"):
        ov.update({int(r[0]): (_fix_letters(r[3]), _fix_letters(r[4])) for r in vals(u, s)})
        ov_orig.update({int(r[0]): (_fix_letters(r[3]), _fix_letters(r[4])) for r in vals(o, s)})
    ov_edited = {i for i, v in ov.items() if ov_orig.get(i) != v}

    by_group = collections.defaultdict(list)
    for (g, i), r in final_g.items():
        by_group[g].append(r)
    groups, grouped = [], set()
    for g, rs in sorted(by_group.items()):
        rs = [r for r in rs if int(r[2]) not in exclude]
        surv = [r for r in rs if str(r[3] or "").strip().lower() == "да"]
        if len(rs) < 2 and not surv:
            continue
        if all(not r[7] and not r[8] for r in rs):             # ФИО не разобрано — как «Не решено»
            exclude |= {int(r[2]) for r in rs}
            continue
        if not surv:
            errors.append(f"группа {g}: нет выжившей карточки")
            continue
        subs = {int(r[2]): {"s": _fix_letters(r[7]), "n": _fix_letters(r[8]), "bd": str(r[9])[:10], "members": [int(r[2])],
                            "edited": (g, r[2]) in edited_g} for r in surv}
        for r in rs:
            if r in surv:
                continue
            to = [i for i, x in subs.items() if x["bd"] == str(r[9])[:10]] if len(subs) > 1 else list(subs)
            if len(to) != 1:
                errors.append(f"группа {g}, id {r[2]}: непонятно, к какой карточке присоединить")
                continue
            subs[to[0]]["members"].append(int(r[2]))
        for sid, x in subs.items():
            edits = {ov[m] for m in x["members"] if m in ov_edited}
            if edits and not x["edited"]:
                if len(edits) > 1:
                    errors.append(f"группа {g}: разные правки ФИО у карточек {x['members']}")
                else:
                    x["s"], x["n"] = edits.pop()
            if not x["s"] or not x["n"]:
                errors.append(f"группа {g}, id {sid}: пустые фамилия или имя")
            groups.append({"survivor": sid, "surname": x["s"], "name": x["n"], "birthday": x["bd"], "members": x["members"]})
            grouped |= set(x["members"])
    renames = {i: v for i, v in ov.items() if i not in grouped and i not in exclude and v[0] and v[1]}
    return {"groups": groups, "renames": renames, "exclude": sorted(exclude), "errors": errors}


def plan_from_decisions(cards, dec):
    """Решения -> (final, merged_into, пропущено: id, которых уже нет в БД)."""
    final, merged_into, missing = {}, {}, []
    for g in dec["groups"]:
        ids = [i for i in g["members"] if i in cards]
        missing += [i for i in g["members"] if i not in cards]
        if g["survivor"] not in cards:
            continue
        for i in ids:
            if i != g["survivor"]:
                merged_into[i] = g["survivor"]
        final[g["survivor"]] = (g["surname"], g["name"], g["birthday"])
    for i, (s, n) in dec["renames"].items():
        i = int(i)
        if i not in cards:
            missing.append(i)
        elif (s, n) != (cards[i]["s0"], cards[i]["n0"]):
            final[i] = (s, n, cards[i]["bd"])
    for i in list(final):                                      # без изменений — не трогаем
        s, n, bd = final[i]
        if (s, n, bd) == (cards[i]["s0"], cards[i]["n0"], cards[i]["bd"]) and i not in merged_into.values():
            del final[i]
    # после правок ФИО+ДР совпали с другой карточкой — это тот же человек: склеиваем
    # (выживает карточка с большим числом результатов, затем заявок, с учётом склеенных в неё)
    weight = collections.Counter()
    for i, c in cards.items():
        weight[merged_into.get(i, i)] += 1000 * c["nr"] + c["nl"]
    by_key = collections.defaultdict(list)
    for i, c in cards.items():
        if i not in merged_into:
            s, n, bd = final.get(i, (c["s0"], c["n0"], c["bd"]))
            by_key[(norm(s), norm(n), bd)].append(i)
    auto = []
    for k, ids in by_key.items():
        if len(ids) < 2:
            continue
        surv = max(ids, key=lambda i: (weight[i], -i))
        values = final.get(surv) or next(final[i] for i in ids if i in final)
        for o in ids:
            if o == surv:
                continue
            for m, t in list(merged_into.items()):
                if t == o:
                    merged_into[m] = surv
            merged_into[o] = surv
            final.pop(o, None)
        final[surv] = values
        auto.append((surv, sorted(ids)))
    return final, merged_into, missing, auto


# ---------------------------------------------------------------- отчёт

def write_report(path, cards, final, merged_into, group_info, clash):
    import openpyxl
    from openpyxl.styles import Font, PatternFill
    wb = openpyxl.Workbook()
    ws0 = wb.active
    ws0.title = "Сводка"
    fill = [PatternFill("solid", fgColor="FFFFFF"), PatternFill("solid", fgColor="EEF3FB")]
    head = ["id", "Было фамилия", "Было имя", "Станет фамилия", "Станет имя", "ДР", "Пол", "Заявок", "Результатов", "Что сделано"]

    def sheet(title_, rows, widths):
        ws = wb.create_sheet(title_)
        ws.append(rows[0])
        for c in ws[1]:
            c.font = Font(bold=True)
        for r in rows[1:]:
            ws.append(r)
        for i, wd in enumerate(widths):
            ws.column_dimensions[openpyxl.utils.get_column_letter(i + 1)].width = wd
        ws.freeze_panes = "B2"
        ws.auto_filter.ref = ws.dimensions
        return ws

    solo = [i for i in final if i not in {g[3] for g in group_info}]
    lat = [i for i, c in cards.items() if any(n.startswith(("латиница", "иностранное")) for n in c["notes"])]
    fio = [i for i in solo if i not in lat]
    row = lambda i: [i, cards[i]["s0"], cards[i]["n0"], cards[i]["s"], cards[i]["n"], cards[i]["bd"], cards[i]["sex"],
                     cards[i]["nl"], cards[i]["nr"], ", ".join(cards[i]["notes"])]
    widths = [8, 24, 20, 24, 20, 11, 6, 8, 11, 40]
    sheet("Латиница", [head] + [row(i) for i in sorted(lat)], widths)
    sheet("ФИО", [head] + [row(i) for i in sorted(fio)], widths)
    ghead = ["Группа", "Что совпало", "id", "Выживает", "Было фамилия", "Было имя", "Было ДР", "Станет фамилия",
             "Станет имя", "Станет ДР", "Пол", "Заявок", "Результатов"]
    grows, gap = [ghead], [ghead]
    for gi, ids, cats, survivor, (s, n, bd) in group_info:
        years = [int(cards[i]["bd"][:4]) for i in ids if cards[i]["bd"] not in SENTINELS]
        for i in ids:
            r = [gi, "; ".join(sorted(cats)), i, "да" if i == survivor else "", cards[i]["s0"], cards[i]["n0"],
                 cards[i]["bd"], s, n, bd, cards[i]["sex"], cards[i]["nl"], cards[i]["nr"]]
            grows.append(r)
            if years and max(years) - min(years) >= 15:
                gap.append(r)
    gw = [7, 30, 8, 9, 22, 18, 11, 22, 18, 11, 6, 8, 11]
    for name_, rows in (("Склейка", grows), ("Склейка ДР ±15 лет", gap)):
        ws = sheet(name_, rows, gw)
        for k, r in enumerate(ws.iter_rows(min_row=2), 1):
            for c in r:
                c.fill = fill[(r[0].value or 0) % 2]
    unresolved = [i for i, c in cards.items() if c["one_word"] and i not in merged_into and i not in final]
    sheet("Не решено", [head] + [row(i) for i in sorted(unresolved)], widths)
    ws0.append(["Показатель", "Значение"])
    for k, v in (("Карточек всего", len(cards)), ("Групп склейки", len(group_info)),
                 ("Карточек удалится (склеены)", len(merged_into)),
                 ("Карточек после чистки", len(cards) - len(merged_into)),
                 ("Исправлено ФИО без склейки", len(fio)), ("Латиница (перевод/оставлено)", len(lat)),
                 ("Групп с разницей ДР ≥ 15 лет (родитель/ребёнок?)", len({r[0] for r in gap[1:]})),
                 ("Не решено", len(unresolved)), ("Совпадений ФИО+ДР после чистки (должно быть 0)", len(clash))):
        ws0.append([k, v])
    ws0.column_dimensions["A"].width = 55
    ws0.column_dimensions["B"].width = 12
    ws0.append([])
    ws0.append(["Листы «Латиница» и «ФИО»: правьте колонки «Станет фамилия/имя» — при применении берутся из файла."])
    wb.save(path)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--report", help="xlsx было/станет (расчёт по правилам)")
    ap.add_argument("--make-decisions", metavar="XLSX", help="проверенный пользователем отчёт -> --out json (без БД)")
    ap.add_argument("--orig", help="исходный отчёт (для --make-decisions)")
    ap.add_argument("--out", help="json решений (для --make-decisions)")
    ap.add_argument("--decisions", help="json решений: применять их, а не расчёт")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--backup")
    args = ap.parse_args()

    if args.make_decisions:
        dec = make_decisions(args.make_decisions, args.orig)
        Path(args.out).write_text(json.dumps(dec, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"Групп: {len(dec['groups'])} (карточек в них {sum(len(g['members']) for g in dec['groups'])}), "
              f"переименований: {len(dec['renames'])}, исключено: {len(dec['exclude'])}, ошибок: {len(dec['errors'])}")
        for e in dec["errors"]:
            print("  !", e)
        return 1 if dec["errors"] else 0

    from scripts.import_boom_historical import get_connection
    conn = get_connection()
    try:
        clients, leads, results = load(conn)
        names = Names([(r["surname"], r["name"], r["sex"]) for r in leads + results])
        cards = build_cards(clients, leads, results, names)
        if args.decisions:
            dec = json.loads(Path(args.decisions).read_text(encoding="utf-8"))
            if dec["errors"]:
                print("В решениях есть ошибки — не применяю.")
                return 1
            final, merged_into, missing, auto = plan_from_decisions(cards, dec)
            clash = []
            print(f"По решениям: удалится карточек {len(merged_into)}, изменится ФИО/ДР {len(final)}, "
                  f"уже нет в БД {len(missing)}, исключено {len(dec['exclude'])}, "
                  f"склеено по совпадению после правок {len(auto)}")
            print(f"Заявки удаляются у карточек: {dec.get('drop_leads', [])} "
                  f"(заявок {sum(cards[i]['nl'] for i in dec.get('drop_leads', []) if i in cards)})")
            for surv, ids in auto:
                print(f"  совпали {ids} -> {surv} «{final[surv][0]} {final[surv][1]}» {final[surv][2]}")
        else:
            final, merged_into, group_info, clash = plan_changes(cards, names)
            write_report(args.report, cards, final, merged_into, group_info, clash)
            print(f"Карточек: {len(cards)}, групп склейки: {len(group_info)}, удалится карточек: {len(merged_into)}, "
                  f"изменится ФИО/ДР: {len(final)}, совпадений после чистки: {len(clash)}")
            print(f"Отчёт: {args.report}")
        if not args.apply:
            print("\ndry-run. Повтори с --apply --backup <путь>.")
            return 0
        if not args.backup or clash:
            print("Нужен --backup." if not args.backup else "Совпадения ФИО+ДР после чистки — не применяю.")
            return 1
        drop = [i for i in (dec.get("drop_leads", []) if args.decisions else []) if i in cards]
        nl, nr = apply(conn, cards, final, merged_into, args.backup, drop)
        print(f"Применено: склеено карточек {len(merged_into)}, изменено {len(final)}; заявок затронуто {nl}, "
              f"результатов {nr}. Бэкап: {args.backup}")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
