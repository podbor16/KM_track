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
