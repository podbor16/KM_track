"""Обращения кабинета (Б3, docs/superpowers/specs/2026-11-04-athlete-b3-design.md): dispute — «это моя карточка»
(заявлена другим аккаунтом), wrong_row — «это не мой забег» (строка истории), not_found — «не могу найти себя».
Оператор админки решает: transfer (только dispute), attach (только not_found), reject, close. Создание и решение пишутся
в журнал dq_actions (athlete_request / athlete_request_resolve). Письма сервис не шлёт: resolve() возвращает данные,
роутер ставит notify_resolved() в BackgroundTasks."""

import html
import json
import logging
from typing import Optional

from mysql.connector import errorcode
from mysql.connector.errors import IntegrityError

from src.core.mailer import send_mail
from src.krasmarafon.services import athlete_find
from src.krasmarafon.services.athlete_auth import _conn, normalize_email
from src.krasmarafon.services.athlete_claims import (
    NO_BIRTHDAY, SUPPORT_EMAIL, advisory_lock, in_transaction, log_action, same_person, sweep, unclaim_row)

logger = logging.getLogger(__name__)

KINDS = ("dispute", "wrong_row", "not_found")
ACTIONS = ("transfer", "attach", "reject", "close")
MAX_OPEN = 3
MAX_TEXT = 1000
ROW_TABLES = ("results", "leads")

DECISIONS = {
    "transfer": "Карточка привязана к вашему кабинету",
    "attach": "Карточка привязана к вашему кабинету",
    "reject": "Обращение отклонено",
    "close": "Обращение закрыто",
}


class RequestError(ValueError):
    """Обращение или решение отклонено. code: bad_kind, too_long, forbidden, limit (create); bad_action, closed,
    not_found, no_card, taken, no_birthday (resolve)."""

    def __init__(self, code: str, message: str = ""):
        super().__init__(message or code)
        self.code = code


def _text(value, code: str = "too_long") -> Optional[str]:
    value = (value or "").strip()
    if len(value) > MAX_TEXT:
        raise RequestError(code, f"длина больше {MAX_TEXT}")
    return value or None


def _log(cur, action: str, request_id: int, client_id: Optional[int], details: dict, user: str) -> None:
    """Журнал по карточке (client:ID), а без карточки — по обращению (request:ID)."""
    if client_id is not None:
        log_action(cur, action, client_id, details, user)
    else:
        cur.execute("INSERT INTO dq_actions (action, finding_key, details, done_by) VALUES (%s, %s, %s, %s)",
                    (action, f"request:{request_id}", json.dumps(details, ensure_ascii=False), user))


def create(email: str, kind: str, client_id: Optional[int] = None, row: Optional[tuple] = None,
           payload: Optional[dict] = None, comment: str = "", find_token: Optional[str] = None) -> int:
    """Создать обращение -> id (при совпадении с открытым обращением того же аккаунта — id существующего). Права:
    dispute(client_id) — карточка заявлена другим аккаунтом, и у заявителя есть своя заявка на почте или токен находки
    (find_token от athlete_find.make_token) на эту карточку; wrong_row(row=("results"|"leads", id)) — строка из
    истории своей или подопечной карточки; not_found(payload) — без проверок. RequestError: bad_kind, too_long,
    forbidden, limit (≥ MAX_OPEN открытых)."""
    return in_transaction(_create, normalize_email(email), kind, client_id, row, payload, comment, find_token)


def _owns_card(cur, email: str, client_id: int) -> bool:
    for table in ("athlete_claims", "athlete_reps"):
        cur.execute(f"""SELECT 1 FROM {table} t JOIN clients c ON c.id = t.client_id AND c.birthday = t.birthday
                        WHERE t.email = %s AND t.client_id = %s""", (email, client_id))
        if cur.fetchone():
            return True
    return False


def _check_dispute(cur, email: str, client_id, find_token) -> int:
    cur.execute("SELECT id, surname, name, birthday FROM clients WHERE id = %s", (client_id,))
    card = cur.fetchone()
    if card is None:
        raise RequestError("forbidden", "нет такой карточки")
    cur.execute("""SELECT t.email FROM athlete_claims t JOIN clients c ON c.id = t.client_id AND c.birthday = t.birthday
                   WHERE t.client_id = %s""", (client_id,))
    owner = cur.fetchone()
    if owner is None or owner["email"] == email:
        raise RequestError("forbidden", "карточка не заявлена другим аккаунтом")
    cur.execute("""SELECT surname, name, birthday FROM leads
                   WHERE client_id = %s AND (LOWER(email) = %s OR LOWER(ma_email) = %s)""", (client_id, email, email))
    if any(same_person(card, lead) for lead in cur.fetchall()):
        return client_id
    if athlete_find.read_token(email, find_token) == client_id:
        return client_id
    raise RequestError("forbidden", "нет заявки на почте и находки")


def _check_row(cur, email: str, row) -> tuple[str, int, int]:
    try:
        table, row_id = row
        row_id = int(row_id)
    except (TypeError, ValueError):
        raise RequestError("forbidden", "строка не указана")
    if table not in ROW_TABLES:
        raise RequestError("forbidden", "неизвестная таблица")
    cur.execute(f"SELECT client_id, surname, name, birthday FROM {table} WHERE id = %s", (row_id,))
    data = cur.fetchone()
    if data is None or data["client_id"] is None or not _owns_card(cur, email, data["client_id"]):
        raise RequestError("forbidden", "строка не из вашей истории")
    cur.execute("SELECT surname, name, birthday FROM clients WHERE id = %s", (data["client_id"],))
    if not same_person(cur.fetchone(), data):
        raise RequestError("forbidden", "строка не из вашей истории")
    return table, row_id, data["client_id"]


def _create(conn, email: str, kind: str, client_id, row, payload, comment, find_token) -> int:
    if kind not in KINDS:
        raise RequestError("bad_kind", kind)
    comment = _text(comment)
    cur = conn.cursor(dictionary=True)
    try:
        with advisory_lock(cur, f"request:{email}"):
            row_table = row_id = None
            data = dict(payload) if payload else None
            if kind == "dispute":
                client_id = _check_dispute(cur, email, client_id, find_token)
                if athlete_find.read_token(email, find_token) == client_id:
                    data = {**(data or {}), "via": "find"}
            elif kind == "wrong_row":
                row_table, row_id, client_id = _check_row(cur, email, row)
            else:
                client_id = None
            payload_json = json.dumps(data, ensure_ascii=False, sort_keys=True) if data else None

            cur.execute("""SELECT id FROM athlete_requests
                           WHERE email = %s AND kind = %s AND status = 'new' AND client_id <=> %s
                             AND row_table <=> %s AND row_id <=> %s
                             AND (kind <> 'not_found' OR payload <=> CAST(%s AS JSON)) LIMIT 1""",
                        (email, kind, client_id, row_table, row_id, payload_json))
            same = cur.fetchone()
            if same:
                return same["id"]
            cur.execute("SELECT COUNT(*) AS n FROM athlete_requests WHERE email = %s AND status = 'new'", (email,))
            if cur.fetchone()["n"] >= MAX_OPEN:
                raise RequestError("limit", f"открытых обращений: {MAX_OPEN}")
            cur.execute("""INSERT INTO athlete_requests (email, kind, client_id, row_table, row_id, payload, comment)
                           VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                        (email, kind, client_id, row_table, row_id, payload_json, comment))
            rid = cur.lastrowid
            _log(cur, "athlete_request", rid, client_id,
                 {"request_id": rid, "kind": kind, "email": email, "row": [row_table, row_id] if row_table else None},
                 email)
            return rid
    finally:
        cur.close()


_LIST_SQL = """SELECT r.id, r.email, r.kind, r.client_id, r.row_table, r.row_id, r.payload, r.comment, r.status,
                      r.resolution, r.answer, r.resolved_by, r.resolved_at, r.created_at,
                      TRIM(CONCAT(c.surname, ' ', c.name)) AS card
               FROM athlete_requests r LEFT JOIN clients c ON c.id = r.client_id
               WHERE r.status {cond} ORDER BY r.created_at {order}, r.id {order}"""


def list_requests(status: str = "new") -> list[dict]:
    """Обращения для админки: "new" — открытые (старые первыми), иначе — рассмотренные (новые первыми).
    card — ФИ карточки или None, payload — dict или None."""
    cond, order = ("= 'new'", "ASC") if status == "new" else ("<> 'new'", "DESC")
    conn = _conn()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(_LIST_SQL.format(cond=cond, order=order))
        rows = cur.fetchall()
        cur.close()
    finally:
        conn.close()
    for r in rows:
        r["payload"] = json.loads(r["payload"]) if r["payload"] else None
        r["card"] = r["card"] or None
    return rows


def count_new() -> int:
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM athlete_requests WHERE status = 'new'")
        n = cur.fetchone()[0]
        cur.close()
        return n
    finally:
        conn.close()


def resolve(request_id: int, action: str, operator: str, answer: str = "", client_id: Optional[int] = None) -> dict:
    """Решить открытое обращение (одна транзакция). transfer — только dispute: привязка переходит заявителю (ДР привязки —
    ДР карточки), представители остаются; attach — только not_found: заявителю привязывается свободная карточка client_id,
    оператором выбранная; reject / close — любое. answer — ответ оператора (≤ MAX_TEXT). RequestError: bad_action,
    too_long, not_found, closed, no_card, taken, no_birthday. -> данные для notify_resolved: {"id", "email", "kind",
    "action", "answer", "client_id", "fio", "former_owner"}."""
    if action not in ACTIONS:
        raise RequestError("bad_action", action)
    answer = _text(answer)
    return in_transaction(_resolve, int(request_id), action, operator, answer, client_id)


def _grant(conn, cur, email: str, card: dict, via: str, operator: str) -> None:
    """Привязка «Это я» заявителю по решению оператора; свой доступ представителя на этой карточке больше не нужен."""
    try:
        cur.execute("INSERT INTO athlete_claims (email, client_id, birthday) VALUES (%s, %s, %s)",
                    (email, card["id"], card["birthday"]))
    except IntegrityError as e:
        if e.errno != errorcode.ER_DUP_ENTRY:
            raise
        raise RequestError("taken", "карточку уже заявили")
    log_action(cur, "athlete_claim", card["id"], {"email": email, "via": via, "by": operator}, operator)
    cur.execute("SELECT id FROM athlete_reps WHERE email = %s AND client_id = %s", (email, card["id"]))
    rep = cur.fetchone()
    if rep:
        unclaim_row(conn, rep["id"], email, card["id"], "claimed", operator, in_tx=True,
                    table="athlete_reps", action="athlete_unrep")


def _resolve(conn, request_id: int, action: str, operator: str, answer, client_id) -> dict:
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute("SELECT * FROM athlete_requests WHERE id = %s FOR UPDATE", (request_id,))
        req = cur.fetchone()
        if req is None:
            raise RequestError("not_found", "обращения нет")
        if req["status"] != "new":
            raise RequestError("closed", "обращение уже рассмотрено")
        if (action == "transfer" and req["kind"] != "dispute") or (action == "attach" and req["kind"] != "not_found"):
            raise RequestError("bad_action", f"{action} не для {req['kind']}")

        card_id, former = req["client_id"], None
        if action in ("transfer", "attach"):
            card_id = req["client_id"] if action == "transfer" else client_id
            card = None
            if card_id:
                cur.execute("SELECT id, surname, name, birthday FROM clients WHERE id = %s FOR UPDATE", (card_id,))
                card = cur.fetchone()
            if card is None:
                raise RequestError("no_card", "карточки нет")
            if card["birthday"] in NO_BIRTHDAY:
                raise RequestError("no_birthday", "у карточки нет ДР")
            sweep(conn, "ac.client_id = %s", (card_id,), in_tx=True)     # устаревшая привязка не считается владельцем
            cur.execute("SELECT id, email FROM athlete_claims WHERE client_id = %s", (card_id,))
            owner = cur.fetchone()
            if owner and owner["email"] != req["email"]:
                if action == "attach":
                    raise RequestError("taken", "карточку уже заявили")
                unclaim_row(conn, owner["id"], owner["email"], card_id, "dispute", operator, in_tx=True)
                former = owner["email"]
            if not owner or owner["email"] != req["email"]:
                _grant(conn, cur, req["email"], card, "dispute" if action == "transfer" else "attach", operator)

        cur.execute("""UPDATE athlete_requests SET status = 'resolved', resolution = %s, answer = %s, resolved_by = %s,
                       resolved_at = NOW(), client_id = %s WHERE id = %s""",
                    (action, answer, operator, card_id, request_id))
        _log(cur, "athlete_request_resolve", request_id, card_id,
             {"request_id": request_id, "email": req["email"], "kind": req["kind"], "action": action,
              "answer": answer}, operator)
        fio = None
        if card_id:
            cur.execute("SELECT surname, name FROM clients WHERE id = %s", (card_id,))
            c = cur.fetchone()
            fio = f"{c['surname']} {c['name']}".strip() if c else None
        return {"id": request_id, "email": req["email"], "kind": req["kind"], "action": action, "answer": answer,
                "client_id": card_id, "fio": fio, "former_owner": former}
    finally:
        cur.close()


def _send(to: str, subject: str, text: str) -> None:
    page = f'<div style="font-family:Arial,sans-serif;font-size:15px;color:#333;max-width:480px">' \
           f'<p>{html.escape(text.strip()).replace(chr(10), "<br>")}</p></div>'
    try:
        send_mail(to, subject, text, page)
    except Exception:
        logger.exception("Обращение: письмо не отправлено")


def notify_resolved(info: dict) -> None:
    """Письма о решении (resolve() -> info): заявителю — всегда, прежнему владельцу — при transfer. Отправка синхронная —
    вызывать из BackgroundTasks; ничего не бросает, ошибки SMTP — в лог."""
    text = DECISIONS[info["action"]] + "."
    if info.get("answer"):
        text += f"\n\nОтвет организаторов: {info['answer']}"
    _send(info["email"], "Ваше обращение рассмотрено", text + "\n")
    if info.get("former_owner"):
        _send(info["former_owner"], "Карточку передали другому аккаунту",
              f"Карточка {info['fio']} передана другому аккаунту по решению организаторов. Если это ошибка — "
              f"ответьте на это письмо или напишите на {SUPPORT_EMAIL}\n")
