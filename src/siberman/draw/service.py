"""
Жеребьёвка Siberman: снимки состояния (админка/публика), операции записи, кэш, фиды vMix.

Каждая запись — в транзакции под блокировкой строки draw_config года (SELECT … FOR UPDATE):
операции года идут строго по очереди, двойной клик не создаст дубль. Каждая запись
увеличивает draw_config.version; публичный снимок пересобирается при смене версии,
а сама версия читается из БД не чаще раза в CACHE_TTL_S на воркер.
"""
import csv
import datetime
import io
import logging
import threading
import time

import mysql.connector

from src.siberman.db import get_siberman_connection
from src.siberman.draw import db as ddb
from src.siberman.draw.importer import import_report, parse_applicants
from src.siberman.draw.logic import (
    CATEGORIES, CATEGORY_LABELS, ROUND_LABELS, build_lists, category_of, check_pick,
    in_round_pool, placement, round_counters,
)
from src.siberman.draw.payments import PAYMENT_ICONS, auto_invite_allowed, next_invitee
from src.siberman.draw.simulation import win_probabilities


log = logging.getLogger(__name__)


class DrawError(Exception):
    """Ошибка, которую оператор видит как есть."""


class DrawUnavailable(DrawError):
    """БД недоступна: роутер отвечает 503 (а не 409), vMix/страница повторят запрос."""


CACHE_TTL_S = 1.0
# 2000 прогонов: на VPS (3 ядра EPYC) ~0,9 с вместо ~2,2 с при 5000 — пересчёт идёт в каждом
# из 3 воркеров и под GIL тормозит их ответы; погрешность ±1 п.п. (замер 2026-10-14).
SIMS = 2000
FEEDS = ("men", "women", "relay", "wildcard", "last")
FEED_COLUMNS = {
    "men": ("num", "name", "city", "section", "status"),
    "women": ("num", "name", "city", "section", "status"),
    "relay": ("num", "name", "city", "section", "status"),
    "wildcard": ("num", "name", "city", "category"),
    "last": ("name", "city", "category", "num", "round"),
}
SECTION_LABELS = {"winner": "Победитель", "waitlist": "Лист ожидания", None: ""}
AQUARIUM_GROUPS = {"relay": ("Эстафеты", "blue"), "repeat": ("Повторные", "black"),
                   "novice": ("Новички", "black"), "individual": ("Личники", "black")}

_cache: dict[int, tuple[int, float, dict]] = {}
_probs: dict[int, tuple[int, dict | None]] = {}
_probs_running: set[int] = set()
_lock = threading.Lock()
_year_locks: dict[int, threading.Lock] = {}


def clear_cache() -> None:
    with _lock:
        _cache.clear()
        _probs.clear()


def _connect():
    conn = get_siberman_connection()
    if conn is None:
        raise DrawUnavailable("БД недоступна")
    return conn


def _year_lock(year: int) -> threading.Lock:
    with _lock:
        return _year_locks.setdefault(year, threading.Lock())


def _empty_config() -> dict:
    cfg = {f: None for f in ddb.CONFIG_INT_FIELDS}
    return {**cfg, "current_round": 0, "version": 0, "auto_invite_until": None, "imported_at": None}


def _snapshot(conn, year: int, create: bool = True) -> dict:
    """create=False — путь публичного чтения: без INSERT, для года без строки — пустое состояние."""
    if create:
        config = ddb.load_config(conn, year)
    else:
        config = ddb.get_config(conn, year)
        if config is None:
            return {"year": year, "config": _empty_config(), "applicants": [], "picks": [],
                    "lists": build_lists({}, [], _empty_config())}
    apps = ddb.load_applicants(conn, year)
    picks = ddb.load_picks(conn, year)
    lists = build_lists({a["id"]: a for a in apps}, picks, config)
    return {"year": year, "config": config, "applicants": apps, "picks": picks, "lists": lists}


def _applicant(snap: dict, applicant_id: int) -> dict:
    a = next((x for x in snap["applicants"] if x["id"] == applicant_id), None)
    if a is None:
        raise DrawError("нет такой заявки")
    return a


def _active_pick(snap: dict, pick_id: int) -> dict:
    p = next((x for x in snap["picks"] if x["id"] == pick_id), None)
    if p is None or p["cancelled_at"] is not None:
        raise DrawError("запись не найдена или уже отменена")
    return p


def _fio(a: dict) -> str:
    return f"{a['surname']} {a['name']}".strip()


def _write(year: int, op):
    """op(conn, snap) в транзакции под блокировкой строки года; version += 1."""
    conn = _connect()
    try:
        ddb.ensure_config(conn, year)
        conn.start_transaction()
        ddb.lock_config(conn, year)
        result = op(conn, _snapshot(conn, year))
        ddb.bump_version(conn, year)
        conn.commit()
        return result
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ── Записи ──────────────────────────────────────────────────────────────────

def pick(year: int, applicant_id: int, user: str = "") -> dict:
    def op(conn, snap):
        a = _applicant(snap, applicant_id)
        rnd = snap["config"]["current_round"]
        reason = check_pick(a, rnd, snap["lists"], snap["config"], {x["id"]: x for x in snap["applicants"]})
        if reason:
            raise DrawError(f"{_fio(a)}: {reason}")
        category = category_of(a)
        pick_id = ddb.insert_pick(conn, year, a["id"], rnd, category)
        return {"pick_id": pick_id, "category": category, "position": len(snap["lists"][category]) + 1}
    return _write(year, op)


def _reset_payment(conn, year: int, snap: dict, applicant_id: int, user: str) -> None:
    """Вытесненный/отменённый участник больше не в списке — его статус оплаты не должен висеть."""
    a = next((x for x in snap["applicants"] if x["id"] == applicant_id), None)
    if a and a["payment_status"] != "none":
        ddb.update_payment_status(conn, applicant_id, "none")
        ddb.audit(conn, year, applicant_id, "payment", a["payment_status"], "none", None, user)


def cancel(year: int, pick_id: int, user: str = "") -> dict:
    def op(conn, snap):
        p = _active_pick(snap, pick_id)
        ddb.cancel_pick(conn, pick_id)
        ddb.audit(conn, year, p["applicant_id"], "cancel_pick", str(pick_id), "", None, user)
        _reset_payment(conn, year, snap, p["applicant_id"], user)
        return {"ok": True}
    return _write(year, op)


def replace(year: int, pick_id: int, applicant_id: int, user: str = "") -> dict:
    """Исправить: другой участник на то же место (тот же зачёт, раунд исходной записи)."""
    def op(conn, snap):
        p = _active_pick(snap, pick_id)
        a = _applicant(snap, applicant_id)
        if category_of(a) != p["category"]:
            raise DrawError(f"{_fio(a)}: другой зачёт — используйте «Отменить»")
        reason = check_pick(a, p["round"], snap["lists"])
        if reason:
            raise DrawError(f"{_fio(a)}: {reason}")
        new_id = ddb.insert_pick(conn, year, a["id"], p["round"], p["category"], position_key=p["position_key"])
        ddb.cancel_pick(conn, pick_id, replaced_by=new_id)
        ddb.audit(conn, year, a["id"], "replace_pick", str(p["applicant_id"]), str(a["id"]), p["applicant_id"], user)
        _reset_payment(conn, year, snap, p["applicant_id"], user)
        return {"pick_id": new_id}
    return _write(year, op)


def set_round(year: int, rnd: int, user: str = "") -> dict:
    if rnd not in ROUND_LABELS:
        raise DrawError("нет такого раунда")

    def op(conn, snap):
        ddb.set_round(conn, year, rnd)
        return {"round": rnd}
    return _write(year, op)


def save_config(year: int, values: dict, user: str = "") -> dict:
    clean = {}
    for k in ddb.CONFIG_INT_FIELDS:
        if k not in values:
            continue
        v = values[k]
        if v is not None and (not isinstance(v, int) or isinstance(v, bool) or not 0 <= v <= 1000):
            raise DrawError(f"{k}: нужно целое число от 0 до 1000")
        clean[k] = v
    if "auto_invite_until" in values:
        clean["auto_invite_until"] = values["auto_invite_until"]

    def op(conn, snap):
        ddb.save_config(conn, year, clean)
        return {"ok": True}
    return _write(year, op)


def import_applicants(year: int, file_bytes: bytes, dry_run: bool = True, user: str = "") -> dict:
    apps, errors = parse_applicants(file_bytes)
    report = import_report(apps)
    if dry_run or errors:
        return {"report": report, "errors": errors, "written": False}

    def op(conn, snap):
        if snap["picks"]:
            raise DrawError("жеребьёвка уже началась — загрузка таблицы запрещена (сначала «Очистить журнал»)")
        ddb.replace_applicants(conn, year, apps)
        return {"report": report, "errors": [], "written": True}
    return _write(year, op)


def reset(year: int, confirm: str, user: str = "") -> dict:
    if confirm != str(year):
        raise DrawError(f"для очистки введите {year}")

    def op(conn, snap):
        ddb.reset_draw(conn, year)
        return {"ok": True}
    return _write(year, op)


def set_payment(year: int, applicant_id: int, status: str, comment: str = "", user: str = "",
                today: datetime.date | None = None) -> dict:
    if status not in PAYMENT_ICONS:
        raise DrawError("нет такого статуса оплаты")
    today = today or datetime.date.today()

    def op(conn, snap):
        a = _applicant(snap, applicant_id)
        placed = placement(snap["lists"], a["id"])
        if placed is None:
            raise DrawError(f"{_fio(a)}: ещё не вытянут")
        old, old_comment = a["payment_status"], a["payment_comment"] or ""
        ddb.update_payment(conn, a["id"], status, comment)
        if old != status:
            ddb.audit(conn, year, a["id"], "payment", old, status, None, user)
        elif old_comment != comment[:500]:
            ddb.audit(conn, year, a["id"], "payment_comment", old_comment[:200], comment[:200], None, user)
        result = {"auto_invited": None, "waitlist_empty": False, "suggest_revert": None, "already_invited": None}
        if status == "unpaid" and old != "unpaid" and auto_invite_allowed(snap["config"]["auto_invite_until"], today):
            rows = snap["lists"][placed[0]]
            for r in rows:
                if r["applicant_id"] == a["id"]:
                    r["payment_status"] = status
            prev_id = ddb.last_auto_invite(conn, year, a["id"])
            prev = next((x for x in snap["applicants"] if x["id"] == prev_id), None)
            nxt = next_invitee(rows)
            if prev and prev["payment_status"] == "pending":
                # цепочка ❌→✅→❌: приглашённый в прошлый раз ещё ждёт — второго не зовём
                result["already_invited"] = {"applicant_id": prev["id"], "surname": prev["surname"],
                                             "name": prev["name"]}
            elif nxt is None:
                result["waitlist_empty"] = True
            else:
                ddb.update_payment_status(conn, nxt["applicant_id"], "pending")
                ddb.audit(conn, year, nxt["applicant_id"], "auto_invite", "none", "pending", a["id"], user)
                result["auto_invited"] = {"applicant_id": nxt["applicant_id"], "surname": nxt["surname"],
                                          "name": nxt["name"], "category": placed[0], "position": nxt["position"]}
        if old == "unpaid" and status != "unpaid":
            invited_id = ddb.last_auto_invite(conn, year, a["id"])
            invited = next((x for x in snap["applicants"] if x["id"] == invited_id), None)
            if invited and invited["payment_status"] == "pending":
                result["suggest_revert"] = {"applicant_id": invited["id"], "surname": invited["surname"],
                                            "name": invited["name"]}
        return result
    return _write(year, op)


# ── Чтение: админка ─────────────────────────────────────────────────────────

def admin_state(year: int) -> dict:
    conn = _connect()
    try:
        snap = _snapshot(conn, year)
    finally:
        conn.close()
    cfg, rnd = snap["config"], snap["config"]["current_round"]
    by_id = {a["id"]: a for a in snap["applicants"]}
    positions = {r["pick_id"]: r["position"] for rows in snap["lists"].values() for r in rows}
    for a in snap["applicants"]:
        placed = placement(snap["lists"], a["id"])
        a["placed"] = {"category": placed[0], "position": placed[1]} if placed else None
        a["in_round"] = in_round_pool(a, rnd)
        a["category"] = category_of(a)
        a["block"] = check_pick(a, rnd, snap["lists"], cfg, by_id)
    journal = [{
        "pick_id": p["id"], "applicant_id": p["applicant_id"],
        "surname": by_id[p["applicant_id"]]["surname"], "name": by_id[p["applicant_id"]]["name"],
        "round": p["round"], "category": p["category"], "created_at": p["created_at"],
        "cancelled_at": p["cancelled_at"], "replaced_by": p["replaced_by"], "position": positions.get(p["id"]),
    } for p in sorted(snap["picks"], key=lambda p: p["id"], reverse=True)]
    return {"year": year, "config": cfg, "round_labels": ROUND_LABELS, "category_labels": CATEGORY_LABELS,
            "applicants": snap["applicants"], "lists": snap["lists"], "journal": journal,
            "counters": round_counters(snap["applicants"], snap["lists"], rnd)}


def applicant_summary(year: int, applicant_id: int) -> dict:
    conn = _connect()
    try:
        snap = _snapshot(conn, year)
        a = _applicant(snap, applicant_id)
        history = ddb.siberman_history(conn, a["surname"], a["name"])
        audit = ddb.load_audit(conn, year, applicant_id)
    finally:
        conn.close()
    placed = placement(snap["lists"], applicant_id)
    where = None
    if placed:
        row = next(r for r in snap["lists"][placed[0]] if r["applicant_id"] == applicant_id)
        where = {"category": placed[0], "position": placed[1], "round": row["round"], "created_at": row["created_at"]}
    return {"applicant": a, "history": history, "placement": where, "audit": audit}


# ── Чтение: публика (кэш) ───────────────────────────────────────────────────

def _fresh(hit, now: float) -> bool:
    return bool(hit) and now - hit[1] < CACHE_TTL_S


def _store(year: int, version: int, snap: dict) -> None:
    """Не затираем более новую версию более старой (запись из соседнего потока/воркера)."""
    with _lock:
        cur = _cache.get(year)
        if cur is None or cur[0] <= version:
            _cache[year] = (version, time.monotonic(), snap)


def _cached_snapshot(year: int) -> dict:
    hit = _cache.get(year)
    if _fresh(hit, time.monotonic()):
        return hit[2]
    with _year_lock(year):  # single-flight: на промах кэша — один запрос в БД на воркер
        hit = _cache.get(year)
        if _fresh(hit, time.monotonic()):
            return hit[2]
        try:
            conn = _connect()
            try:
                if hit and hit[0] == ddb.get_version(conn, year):
                    snap = hit[2]
                else:
                    snap = _snapshot(conn, year, create=False)
                    snap["version"] = snap["config"]["version"]
            finally:
                conn.close()
        except (DrawError, mysql.connector.Error) as e:
            if hit:
                log.warning("draw %s: БД недоступна, отдаём прошлый снимок: %s", year, e)
                _store(year, hit[0], hit[2])  # отметка времени — не долбим БД чаще CACHE_TTL_S
                return hit[2]
            if isinstance(e, DrawError):
                raise
            raise DrawUnavailable("БД недоступна") from e
        _store(year, snap["version"], snap)
    _ensure_probabilities(snap)
    return snap


def _ensure_probabilities(snap: dict) -> None:
    """Пересчёт вероятностей в фоне при смене версии; публика видит последний готовый."""
    year, version = snap["year"], snap["version"]
    with _lock:
        done = _probs.get(year)
        if (done and done[0] == version) or year in _probs_running:
            return
        _probs_running.add(year)

    def run():
        try:
            probs = win_probabilities(snap["applicants"], snap["lists"], snap["config"],
                                      snap["config"]["current_round"], sims=SIMS)
        except Exception:
            log.exception("draw %s: расчёт вероятностей упал (версия %s)", year, version)
            probs = None  # (version, None): не перезапускаем каждую секунду
        with _lock:
            done = _probs.get(year)
            if done is None or done[0] <= version:
                _probs[year] = (version, probs)
            _probs_running.discard(year)

    threading.Thread(target=run, daemon=True).start()


def _last_row(snap: dict) -> dict | None:
    active = [p for p in snap["picks"] if p["cancelled_at"] is None]
    if not active:
        return None
    last_id = max(p["id"] for p in active)
    for c, rows in snap["lists"].items():
        for r in rows:
            if r["pick_id"] == last_id:
                return {**r, "category": c}
    return None


def _aquarium_group(a: dict, rnd: int) -> str:
    if a["format"] == "relay":
        return "relay"
    return "individual" if rnd >= 4 else a["pool"]


def public_state(year: int) -> dict:
    """Публично: без признака wild card и без необъявленных wild card (их нет нигде)."""
    snap = _cached_snapshot(year)
    cfg, rnd = snap["config"], snap["config"]["current_round"]
    done = _probs.get(year)
    probs = done[1] if done else None
    placed = {r["applicant_id"] for rows in snap["lists"].values() for r in rows}
    people = [a for a in snap["applicants"] if not a["is_wildcard"] and a["id"] not in placed]
    group_keys = ["relay"] + (["individual"] if rnd >= 4 else ["repeat", "novice"])
    groups = []
    for key in group_keys:
        members = [a for a in people if _aquarium_group(a, rnd) == key]
        label, color = AQUARIUM_GROUPS[key]
        groups.append({"key": key, "label": label, "color": color, "people": len(members),
                       "balls": sum(a["chances"] for a in members)})
    order = {k: i for i, k in enumerate(group_keys)}
    people.sort(key=lambda a: (order[_aquarium_group(a, rnd)], -a["chances"], a["surname"], a["name"]))
    last = _last_row(snap)
    return {
        "year": year, "round": rnd, "round_label": ROUND_LABELS[rnd],
        "capacities": {c: cfg[f"capacity_{c}"] for c in CATEGORIES},
        "lists": {c: [{
            "position": r["position"], "surname": r["surname"], "name": r["name"], "city": r["city"],
            "section": r["section"], "status": PAYMENT_ICONS[r["payment_status"]],
            "is_last": last is not None and r["pick_id"] == last["pick_id"],
        } for r in rows] for c, rows in snap["lists"].items()},
        "aquarium": {"groups": groups, "people": [{
            "surname": a["surname"], "name": a["name"], "city": a["city"], "chances": a["chances"],
            "group": _aquarium_group(a, rnd), "probability": None if probs is None else probs.get(a["id"]),
        } for a in people]},
    }


# ── Фиды vMix ───────────────────────────────────────────────────────────────

def feed_rows(year: int, name: str) -> list[dict]:
    snap = _cached_snapshot(year)
    cfg = snap["config"]
    if name in CATEGORIES:
        cap = cfg[f"capacity_{name}"]
        rows = snap["lists"][name]
        out = [{"num": r["position"], "name": _fio(r), "city": r["city"],
                "section": SECTION_LABELS[r["section"]], "status": PAYMENT_ICONS[r["payment_status"]]}
               for r in rows]
        for i in range(len(rows) + 1, (cap or 0) + 1):
            out.append({"num": i, "name": "", "city": "", "section": SECTION_LABELS["winner"], "status": ""})
        return out
    if name == "wildcard":
        wc = sorted(({**r, "category": c} for c, rows in snap["lists"].items() for r in rows if r["is_wildcard"]),
                    key=lambda r: r["position_key"])
        if not wc:
            return [{"num": "", "name": "", "city": "", "category": ""}]
        return [{"num": i, "name": _fio(r), "city": r["city"], "category": CATEGORY_LABELS[r["category"]]}
                for i, r in enumerate(wc, start=1)]
    if name == "last":
        last = _last_row(snap)
        if last is None:  # одна пустая строка: режиссёр настроит колонки Data Source в vMix до эфира
            return [{"name": "", "city": "", "category": "", "num": "", "round": ""}]
        return [{"name": _fio(last), "city": last["city"], "category": CATEGORY_LABELS[last["category"]],
                 "num": last["position"], "round": ROUND_LABELS[last["round"]]}]
    raise DrawError("нет такого фида")


def to_csv(rows: list[dict], columns: tuple) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(columns), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return "\ufeff" + buf.getvalue()
