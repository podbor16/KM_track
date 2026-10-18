"""
Реестр людей Siberman: синхронизация после каждой загрузки результатов, импорт заявок Тильды,
ручные решения админки (слить, перенести выступления, ДР, статус «проверить»), журнал с отменой,
карточки и поиск. Все записи — под MySQL GET_LOCK (живой цикл Copernico и админка не
пересекаются) и в одной транзакции. Спецификация hall §3.
"""
import contextlib
import datetime
import json
import logging
from typing import Optional

from src.siberman.db import get_siberman_connection
from src.siberman.persons import db as pdb
from src.siberman.persons.applicants import parse_applicants_csv
from src.siberman.persons.linking import Registry, attach_birthdates, link_participants, natkey, plain_key

log = logging.getLogger(__name__)

LOCK_NAME = "siberman_persons"
REVIEW_STATUSES = ("open", "resolved", "deferred")
REVIEW_TITLES = {
    "namesake_candidate": "Одинаковые ФИ — тот же человек или тёзка?",
    "bib_name_change": "Тот же личный номер, другое ФИ",
    "format_switch": "Эстафета и личный зачёт связаны по совпадению ФИ",
    "bd_conflict": "В заявке другая дата рождения",
    "applicant_ambiguous": "Заявка подходит нескольким тёзкам",
    "applicant_city_mismatch": "Заявка с тем же ФИ, но из другого города",
    "applicant_unconfirmed": "Заявка с тем же ФИ без стартов на Siberman — это он?",
    "gender_mismatch": "Те же ФИ, другой пол — тот же человек?",
    "bib_gender_mismatch": "Личный номер у человека другого пола",
    "relinked": "ФИ в протоколе изменилось — выступление ушло к другому человеку",
    "manual_name_changed": "Ручная привязка, а ФИ в протоколе теперь другое",
}
APPLICANT_KINDS = ("bd_conflict", "applicant_ambiguous", "applicant_city_mismatch", "applicant_unconfirmed")


class PersonsError(Exception):
    """Ошибка, которую админ видит как есть."""


class PersonsUnavailable(PersonsError):
    """БД недоступна — роутер отвечает 503."""


class PersonsBusy(PersonsError):
    """Реестр занят (перезапись протокола или другая синхронизация)."""


@contextlib.contextmanager
def _connection():
    conn = get_siberman_connection()
    if conn is None:
        raise PersonsUnavailable("БД недоступна")
    try:
        yield conn
    finally:
        conn.close()


@contextlib.contextmanager
def _locked_tx(conn, wait_s: int = 10):
    cur = conn.cursor(buffered=True)
    cur.execute("SELECT GET_LOCK(%s, %s)", (LOCK_NAME, wait_s))
    if cur.fetchone()[0] != 1:
        raise PersonsBusy("Реестр занят другой операцией — повторите через несколько секунд")
    try:
        conn.start_transaction()
        try:
            yield
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
    finally:
        cur.execute("SELECT RELEASE_LOCK(%s)", (LOCK_NAME,))
        cur.fetchall()


def _fio(row: Optional[dict]) -> str:
    return f"{row['surname']} {row['name']}".strip() if row else "—"


# ── синхронизация ────────────────────────────────────────────────────────────

def sync(conn, wait_s: int = 10) -> dict:
    """Привязать новые выступления, записать ДР из заявок, убрать устаревшие автопривязки и людей
    без выступлений. Идемпотентна: повторный запуск ничего не меняет."""
    with _locked_tx(conn, wait_s):
        reg = Registry(pdb.load_persons(conn))
        rows = pdb.load_participant_rows(conn)
        names = {natkey(r): plain_key(r["surname"], r["name"]) for r in rows}
        new_links, reviews = link_participants(reg, rows, pdb.load_links(conn))
        for p in reg.new:
            p.id = pdb.insert_person(conn, {"surname": p.surname, "name": p.name, "gender": p.gender,
                                            "bib_individual": p.bib_individual, "city": p.city})
        for p in reg.bib_assigned:
            pdb.update_person(conn, p.id, {"bib_individual": p.bib_individual})
        pdb.set_links(conn, [(k, p.id, names[k]) for k, p in new_links.items()], manual=False)
        pdb.delete_links(conn, reg.dropped)
        bd_updates, bd_reviews = attach_birthdates(reg, pdb.load_applicants(conn))
        for p, bd in bd_updates:
            pdb.update_person(conn, p.id, {"birthdate": bd})
        added = pdb.add_reviews(conn, reviews + bd_reviews)
        stale_links, orphans = pdb.delete_stale(conn)
        pdb.refresh_display(conn, {p.id for p in new_links.values()} | {p.id for p in reg.bib_assigned})
    return {"linked": len(new_links), "new_persons": len(reg.new), "birthdates": len(bd_updates),
            "reviews": added, "dropped": len(reg.dropped), "stale_links": stale_links, "orphans": orphans}


def sync_now() -> dict:
    with _connection() as conn:
        return sync(conn)


_last_fingerprint = None   # отпечаток протокола после последней успешной синхронизации (на воркер)
_last_error = None


def auto_sync():
    """Синхронизация после загрузки результатов — только если протокол изменился с прошлого раза
    (вставки, удаления, правки ФИ) и реестр не занят. Ошибки — в лог (предупреждение один раз на воркер,
    например пока миграция 014 не применена). → результат sync или None."""
    global _last_fingerprint, _last_error
    conn = get_siberman_connection()
    if conn is None:
        return None
    try:
        fp = pdb.protocol_fingerprint(conn)
        if fp == _last_fingerprint:
            return None
        result = sync(conn, wait_s=0)
        _last_fingerprint = fp
        _last_error = None
        log.info("[persons] sync: %s", result)
        return result
    except PersonsBusy:
        return None   # идёт перезапись протокола или другая синхронизация — следующий цикл доделает
    except Exception as e:
        msg = str(e)
        (log.debug if msg == _last_error else log.warning)(f"[persons] sync пропущен: {msg}")
        _last_error = msg
        return None
    finally:
        conn.close()


def sync_safe() -> None:
    """Хвост каждой загрузки результатов (recompute_totals_ranks_records); в тестах подменяется no-op."""
    auto_sync()


@contextlib.contextmanager
def protocol_rewrite(conn):
    """Держать реестр, пока строки года удаляются и вставляются заново (загрузка Excel): синхронизация
    из другого воркера не увидит полупустой протокол и не удалит привязки и людей. Лок не взят за
    30 с — загрузка всё равно идёт (результаты гонки важнее), просто без защиты."""
    cur = conn.cursor(buffered=True)
    cur.execute("SELECT GET_LOCK(%s, 30)", (LOCK_NAME,))
    got = cur.fetchone()[0] == 1
    if not got:
        log.warning("[persons] лок реестра не получен за 30 с — перезапись года без защиты реестра")
    try:
        yield
    finally:
        if got:
            try:
                cur.execute("SELECT RELEASE_LOCK(%s)", (LOCK_NAME,))
                cur.fetchall()
            except Exception as e:
                log.warning(f"[persons] RELEASE_LOCK: {e}")


def import_applicants(data: bytes) -> dict:
    """CSV заявок Тильды → siberman_applicants, затем синхронизация (ДР людям)."""
    try:
        apps, stats = parse_applicants_csv(data)
    except ValueError as e:
        raise PersonsError(str(e)) from None
    with _connection() as conn:
        with _locked_tx(conn):
            pdb.upsert_applicants(conn, apps)
        return {**stats, "sync": sync(conn)}


# ── журнал-снимки ────────────────────────────────────────────────────────────

def _plain(row: Optional[dict]) -> Optional[dict]:
    if row is None:
        return None
    return {k: (v.isoformat() if isinstance(v, (datetime.date, datetime.datetime)) else v) for k, v in row.items()}


def _snapshot(conn, person_ids, keys: list, review_ids=()) -> dict:
    person_ids = sorted({int(i) for i in person_ids if i is not None})
    persons = pdb.get_persons(conn, person_ids)
    links = pdb.links_for_keys(conn, keys)
    return {"persons": {str(i): _plain(persons.get(i)) for i in person_ids},
            "links": [[k[0], k[1], k[2], links.get(tuple(k))] for k in keys],
            "reviews": [_plain(r) for r in pdb.reviews_state(conn, person_ids, review_ids)]}


def _record(conn, action: str, summary: str, snap: dict, user: str) -> int:
    scope = ({f"p:{i}" for i in snap["persons"]} | {f"k:{y}/{b}/{s}" for y, b, s, _ in snap["links"]}
             | {f"r:{r['id']}" for r in snap.get("reviews", [])})
    return pdb.add_audit(conn, action, summary, snap, scope, user)


def _restore(conn, snap: dict) -> None:
    """Вернуть людей и привязки к снимку «до»: сначала освободить личные номера (уникальность),
    затем люди, привязки, удалить созданных действием, вернуть номера."""
    persons = {int(k): v for k, v in snap["persons"].items()}
    now = pdb.get_persons(conn, persons)
    for pid in now:
        pdb.update_person(conn, pid, {"bib_individual": None})
    for pid, row in persons.items():
        if row is None:
            continue
        fields = {k: row[k] for k in ("surname", "name", "gender", "birthdate", "city", "country")}
        if pid in now:
            pdb.update_person(conn, pid, fields)
        else:
            pdb.insert_person(conn, {**fields, "id": pid})
    pdb.delete_links(conn, [(y, b, s) for y, b, s, link in snap["links"] if link is None])
    for y, b, s, link in snap["links"]:
        if link is not None:
            pdb.set_links(conn, [((y, b, s), link["person_id"], link["name_key"])], manual=bool(link["manual"]))
    pdb.restore_reviews(conn, snap.get("reviews", []))
    for pid, row in persons.items():
        if row is None and pid in now:
            pdb.delete_person(conn, pid)
    for pid, row in persons.items():
        if row and row["bib_individual"]:
            pdb.update_person(conn, pid, {"bib_individual": row["bib_individual"]})


def undo(audit_id: int, user: str) -> dict:
    with _connection() as conn, _locked_tx(conn):
        a = pdb.get_audit(conn, audit_id)
        if not a:
            raise PersonsError("Действие не найдено")
        if a["undone_at"]:
            raise PersonsError("Действие уже отменено")
        later = pdb.later_conflicts(conn, audit_id, set(filter(None, a["scope"].split(","))))
        if later:
            raise PersonsError("Сначала отмените более поздние действия по этим людям: "
                               + ", ".join(f"#{i}" for i in later))
        payload = a["payload"]
        _restore(conn, json.loads(payload) if isinstance(payload, (str, bytes, bytearray)) else payload)
        pdb.mark_undone(conn, audit_id, user)
    return {"ok": True}


# ── ручные решения ───────────────────────────────────────────────────────────

def merge(source_id: int, target_id: int, user: str, review_id: Optional[int] = None) -> dict:
    """Все выступления source → target, source удаляется (тот же человек под разными ФИ)."""
    if int(source_id) == int(target_id):
        raise PersonsError("Это один и тот же человек")
    with _connection() as conn, _locked_tx(conn):
        persons = pdb.get_persons(conn, [source_id, target_id])
        src, dst = persons.get(int(source_id)), persons.get(int(target_id))
        if not src or not dst:
            raise PersonsError("Человек не найден — обновите страницу")
        if src["bib_individual"] and dst["bib_individual"]:
            raise PersonsError(f"У обоих свой личный номер (№{src['bib_individual']} и №{dst['bib_individual']}) — "
                               "по правилам Siberman это разные люди")
        snap = _snapshot(conn, [source_id, target_id], pdb.links_of_person(conn, source_id), [review_id])
        pdb.move_links(conn, source_id, target_id)
        pdb.move_reviews(conn, source_id, target_id)
        pdb.delete_person(conn, source_id)
        pdb.update_person(conn, target_id, {"bib_individual": dst["bib_individual"] or src["bib_individual"],
                                            "birthdate": dst["birthdate"] or src["birthdate"]})
        pdb.refresh_display(conn, [target_id])
        if review_id is not None:
            pdb.set_review_status(conn, review_id, "resolved", user)
        audit_id = _record(conn, "merge", f"Слиты: {_fio(src)} (id {source_id}) → {_fio(dst)} (id {target_id})",
                           snap, user)
    return {"ok": True, "person_id": int(target_id), "audit_id": audit_id}


def reassign(keys: list, target_id: Optional[int], user: str, review_id: Optional[int] = None) -> dict:
    """Выступления keys → человеку target_id или новому (target_id=None). Личный номер переходит
    вместе со стартами под ним."""
    keys = sorted({(int(k[0]), str(k[1]), str(k[2])) for k in keys})
    if not keys:
        raise PersonsError("Не выбраны выступления")
    with _connection() as conn, _locked_tx(conn):
        rows = pdb.participants_by_keys(conn, keys)
        if len(rows) != len(keys):
            raise PersonsError("Выступление не найдено — обновите страницу")
        before = pdb.links_for_keys(conn, keys)
        old_ids = sorted({v["person_id"] for v in before.values()})
        ind_bibs = sorted({b for _, b, s in keys if s == "none"})
        if len(ind_bibs) > 1:
            raise PersonsError("Выбраны личные старты под разными номерами — переносите по одному номеру")
        bib = ind_bibs[0] if ind_bibs else None
        holder = pdb.person_by_bib(conn, bib) if bib else None
        target = None
        if target_id is not None:
            target = pdb.get_person(conn, target_id)
            if not target:
                raise PersonsError(f"Человек id {target_id} не найден")
            if bib and target["bib_individual"] and target["bib_individual"] != bib:
                raise PersonsError(f"У человека id {target_id} другой личный номер (№{target['bib_individual']})")
        if holder and holder["id"] != target_id:
            rest = [k for k in pdb.links_of_person(conn, holder["id"]) if k[1] == bib and k[2] == "none" and k not in keys]
            if rest:
                raise PersonsError(f"Под №{bib} этот человек выступал и в {', '.join(str(k[0]) for k in rest)} — "
                                   "перенесите все годы с этим номером")
        snap = _snapshot(conn, old_ids + [target_id] + ([holder["id"]] if holder else []), keys, [review_id])
        if holder and holder["id"] != target_id:
            pdb.update_person(conn, holder["id"], {"bib_individual": None})
        last = max(rows, key=lambda r: r["race_year"])
        if target_id is None:
            target_id = pdb.insert_person(conn, {"surname": last["surname"], "name": last["name"],
                                                 "gender": last["gender"] if last["gender"] in ("M", "F") else None,
                                                 "city": last["city"] or "", "country": last["country"] or ""})
            snap["persons"][str(target_id)] = None
        if bib:
            pdb.update_person(conn, target_id, {"bib_individual": bib})
        names = {(int(r["race_year"]), str(r["bib"]), r["relay_stage"]): plain_key(r["surname"], r["name"]) for r in rows}
        pdb.set_links(conn, [(k, target_id, names[k]) for k in keys], manual=True)
        gone = pdb.delete_orphans(conn, old_ids)
        pdb.refresh_display(conn, [i for i in set(old_ids) | {target_id} if i not in gone])
        if review_id is not None:
            pdb.set_review_status(conn, review_id, "resolved", user)
        audit_id = _record(conn, "reassign", f"{len(keys)} выступл. ({_fio(last)}) → id {target_id}", snap, user)
    return {"ok": True, "person_id": int(target_id), "audit_id": audit_id}


def set_birthdate(person_id: int, value: Optional[datetime.date], user: str, review_id: Optional[int] = None) -> dict:
    with _connection() as conn, _locked_tx(conn):
        p = pdb.get_person(conn, person_id)
        if not p:
            raise PersonsError("Человек не найден")
        snap = _snapshot(conn, [person_id], [], [review_id])
        pdb.update_person(conn, person_id, {"birthdate": value})
        if review_id is not None:
            pdb.set_review_status(conn, review_id, "resolved", user)
        audit_id = _record(conn, "birthdate",
                           f"ДР {_fio(p)} (id {person_id}): {p['birthdate'] or '—'} → {value or '—'}", snap, user)
    return {"ok": True, "audit_id": audit_id}


def set_review_status(review_id: int, status: str, user: str) -> dict:
    if status not in REVIEW_STATUSES:
        raise PersonsError(f"Неизвестный статус «{status}»")
    with _connection() as conn, _locked_tx(conn):
        if not pdb.set_review_status(conn, review_id, status, user):
            raise PersonsError("Запись не найдена")
    return {"ok": True}


def keep_link(review_id: int, user: str) -> dict:
    """«Оставить привязку» по записи о выступлении: привязка становится ручной с текущим ФИ строки
    (подтверждённое написание попадает в ключи человека, следующая смена ФИ снова будет замечена).
    Пишется в журнал — отменяется, как остальные решения."""
    with _connection() as conn, _locked_tx(conn):
        r = pdb.get_review(conn, review_id)
        if not r or not r["race_year"]:
            raise PersonsError("Запись не найдена")
        k = (int(r["race_year"]), str(r["bib"]), r["relay_stage"])
        rows = pdb.participants_by_keys(conn, [k])
        link = pdb.links_for_keys(conn, [k]).get(k)
        if not rows or not link:
            raise PersonsError("Выступление не найдено — обновите страницу")
        snap = _snapshot(conn, [link["person_id"]], [k], [review_id])
        pdb.set_links(conn, [(k, link["person_id"], plain_key(rows[0]["surname"], rows[0]["name"]))], manual=True)
        pdb.set_review_status(conn, review_id, "resolved", user)
        audit_id = _record(conn, "keep_link", f"Привязка оставлена с новым ФИ: {_fio(rows[0])} ({k[0]}, №{k[1]})",
                           snap, user)
    return {"ok": True, "audit_id": audit_id}


# ── чтение для админки ───────────────────────────────────────────────────────

def _start(r: dict) -> dict:
    return {"key": [r["race_year"], str(r["bib"]), r["relay_stage"]], "year": r["race_year"], "bib": str(r["bib"]),
            "format": r["format"], "stage": r["relay_stage"], "team": r.get("relay_team_name") or "",
            "fio": f"{r['surname']} {r['name']}".strip(), "status": r.get("status") or "",
            "city": r.get("city") or "", "overall_s": r.get("total_s"), "manual": r.get("manual", 0)}


def _brief(p: Optional[dict], parts: dict) -> Optional[dict]:
    if p is None:
        return None
    return {"id": p["id"], "fio": _fio(p), "bib": p["bib_individual"],
            "birthdate": p["birthdate"].isoformat() if p["birthdate"] else None,
            "city": p["city"], "starts": [_start(r) for r in parts.get(p["id"], [])]}


def reviews(status: str = "open") -> list:
    if status not in REVIEW_STATUSES:
        raise PersonsError(f"Неизвестный статус «{status}»")
    with _connection() as conn:
        rows = pdb.list_reviews(conn, status)
        ids = set()
        for r in rows:
            ids |= {r["person_id"]} | {int(x) for x in r["other_person_ids"].split(",") if x}
        persons = pdb.get_persons(conn, ids)
        parts = pdb.participations(conn, ids)
        keys = [(r["race_year"], r["bib"], r["relay_stage"]) for r in rows if r["race_year"]]
        prow = {(int(p["race_year"]), str(p["bib"]), p["relay_stage"]): p for p in pdb.participants_by_keys(conn, keys)}
        apps = pdb.get_applicants(conn, [r["detail"] for r in rows if r["kind"] in APPLICANT_KINDS])
    out = []
    for r in rows:
        nk = (int(r["race_year"]), str(r["bib"]), r["relay_stage"]) if r["race_year"] else None
        a = apps.get(r["detail"])
        out.append({
            "id": r["id"], "kind": r["kind"], "title": REVIEW_TITLES.get(r["kind"], r["kind"]),
            "status": r["status"], "created_at": r["created_at"],
            "person": _brief(persons.get(r["person_id"]), parts),
            "others": [_brief(persons.get(int(x)), parts) for x in r["other_person_ids"].split(",") if x],
            "participant": _start(prow[nk]) if nk in prow else None,
            "applicant": {"fio": f"{a['surname']} {a['name']}".strip(), "birthdate": a["birthdate"].isoformat(),
                          "city": a["city"]} if a else None,
        })
    return out


def person_card(person_id: int) -> dict:
    with _connection() as conn:
        p = pdb.get_person(conn, person_id)
        if not p:
            raise PersonsError("Человек не найден")
        parts = pdb.participations(conn, [person_id]).get(int(person_id), [])
        open_reviews = pdb.reviews_for_person(conn, person_id)
    return {"person": {"id": int(person_id), **_plain(p)}, "participations": [_start(r) for r in parts],
            "reviews": open_reviews}


def search(q: str) -> list:
    q = " ".join((q or "").split())
    if len(q) < 2 and not q.isdigit():
        return []
    with _connection() as conn:
        rows = pdb.search_persons(conn, q)
    return [{"id": r["id"], "fio": _fio(r), "bib": r["bib_individual"],
             "birthdate": r["birthdate"].isoformat() if r["birthdate"] else None,
             "city": r["city"], "years": r["years"] or ""} for r in rows]


def journal() -> list:
    with _connection() as conn:
        return pdb.list_audit(conn)
