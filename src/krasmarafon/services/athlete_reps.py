"""Представители карточки (Б2, docs/superpowers/specs/2026-11-04-athlete-reps-design.md): аккаунт получает доступ к
истории другого человека (ребёнка, родителя, подопечного), подтвердив ДР его карточки. Правила — по образцу
привязки «Это я» (athlete_claims): право — заявка этого человека на почте аккаунта (same_person), лимит неверных ДР
общий (athlete_claim_attempts), доступ действует, пока карточка существует и её ДР равна подтверждённой, снятие и
получение пишутся в журнал dq_actions (athlete_rep / athlete_unrep). У карточки может быть несколько представителей.
Письма become_rep() не шлёт: роутер ставит notify_rep() в BackgroundTasks."""

from datetime import date
from enum import Enum

from mysql.connector import errorcode
from mysql.connector.errors import IntegrityError

from src.core.mailer import mask_email
from src.krasmarafon.services.athlete_auth import _conn, normalize_email
from src.krasmarafon.services.athlete_claims import (
    NO_BIRTHDAY, SUPPORT_EMAIL, attempts_exceeded, in_transaction, log_action, record_attempt, require_own_lead,
    send_notice, sweep, unclaim_row)

_TABLE, _UNREP = "athlete_reps", "athlete_unrep"


class RepResult(str, Enum):
    OK = "ok"
    ALREADY = "already"
    OWN = "own"
    NO_BIRTHDAY = "no_birthday"
    LIMIT = "limit"
    MISMATCH = "mismatch"


def _sweep_reps(conn, where: str, params: tuple, in_tx: bool = False) -> tuple[list[int], list[int]]:
    return sweep(conn, where, params, in_tx, table=_TABLE, action=_UNREP)


def rep_cards(email: str) -> tuple[list[int], list[int]]:
    """(действующие client_id доступов аккаунта, client_id снятых сейчас). Снимает недействительные: карточки нет
    (card_deleted) или clients.birthday <> athlete_reps.birthday (birthday_changed) — DELETE + журнал athlete_unrep
    (done_by='system')."""
    conn = _conn()
    try:
        return _sweep_reps(conn, "ac.email = %s", (normalize_email(email),))
    finally:
        conn.close()


def become_rep(email: str, client_id: int, birthday: date) -> RepResult:
    """Стать представителем карточки. Нет заявки этого человека на почте (или нет карточки) — ValueError. Всё — в одной
    транзакции под блокировкой строки карточки (лимит попыток не обойти параллельными запросами). Попытка пишется
    только при MISMATCH. Писем не шлёт: при OK вызывающий ставит notify_rep() в фон."""
    return in_transaction(_become_rep, normalize_email(email), client_id, birthday)


def _become_rep(conn, email: str, client_id: int, birthday: date) -> RepResult:
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute("SELECT surname, name, birthday FROM clients WHERE id = %s FOR UPDATE", (client_id,))
        card = cur.fetchone()
        if card is None:
            raise ValueError(f"карточки {client_id} нет")
        require_own_lead(cur, email, client_id, card)

        _sweep_reps(conn, "ac.client_id = %s", (client_id,), in_tx=True)      # устаревший доступ не должен мешать
        cur.execute("""SELECT 1 FROM athlete_claims ac JOIN clients c ON c.id = ac.client_id AND c.birthday = ac.birthday
                       WHERE ac.client_id = %s AND ac.email = %s""", (client_id, email))
        if cur.fetchone():
            return RepResult.OWN
        cur.execute("SELECT 1 FROM athlete_reps WHERE client_id = %s AND email = %s", (client_id, email))
        if cur.fetchone():
            return RepResult.ALREADY
        if card["birthday"] in NO_BIRTHDAY:
            return RepResult.NO_BIRTHDAY
        if attempts_exceeded(cur, email, client_id):
            return RepResult.LIMIT
        if card["birthday"] != birthday:
            record_attempt(cur, email, client_id)
            return RepResult.MISMATCH

        try:
            cur.execute("INSERT INTO athlete_reps (email, client_id, birthday) VALUES (%s, %s, %s)",
                        (email, client_id, birthday))
        except IntegrityError as e:   # страховка UNIQUE; под блокировкой карточки сюда попадать не должны
            if e.errno != errorcode.ER_DUP_ENTRY:
                raise
            return RepResult.ALREADY
        log_action(cur, "athlete_rep", client_id, {"email": email}, email)
        return RepResult.OK
    finally:
        cur.close()


def _remove(conn, rep_id: int, email: str, client_id: int, reason: str, user: str) -> bool:
    return unclaim_row(conn, rep_id, email, client_id, reason, user, table=_TABLE, action=_UNREP)


def remove_rep(email: str, client_id: int) -> None:
    """Отказаться от доступа (чужой не трогает); журнал athlete_unrep, reason='user'."""
    email = normalize_email(email)
    conn = _conn()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT id FROM athlete_reps WHERE email = %s AND client_id = %s", (email, client_id))
        row = cur.fetchone()
        cur.close()
        if row:
            _remove(conn, row["id"], email, client_id, "user", email)
    finally:
        conn.close()


def reps_of(owner_email: str) -> list[dict]:
    """Действующие представители действующих привязок владельца: [{"id", "client_id", "email_masked", "created_at"}]
    в порядке получения доступа. Только чтение."""
    conn = _conn()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("""SELECT r.id, r.client_id, r.email, r.created_at
                       FROM athlete_reps r
                       JOIN athlete_claims ac ON ac.client_id = r.client_id AND ac.email = %s
                       JOIN clients c ON c.id = r.client_id AND c.birthday = ac.birthday AND c.birthday = r.birthday
                       ORDER BY r.created_at, r.id""", (normalize_email(owner_email),))
        rows = cur.fetchall()
        cur.close()
    finally:
        conn.close()
    return [{"id": r["id"], "client_id": r["client_id"], "email_masked": mask_email(r["email"]),
             "created_at": r["created_at"]} for r in rows]


def remove_rep_by_owner(owner_email: str, rep_id: int) -> bool:
    """Владелец убирает представителя со своей (действующей) привязки; журнал athlete_unrep, reason='owner_removed',
    done_by — почта владельца. False — доступа нет или он не к карточке владельца."""
    owner_email = normalize_email(owner_email)
    conn = _conn()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("""SELECT r.id, r.email, r.client_id FROM athlete_reps r
                       JOIN athlete_claims ac ON ac.client_id = r.client_id AND ac.email = %s
                       JOIN clients c ON c.id = r.client_id AND c.birthday = ac.birthday
                       WHERE r.id = %s""", (owner_email, int(rep_id)))
        row = cur.fetchone()
        cur.close()
        return bool(row) and _remove(conn, row["id"], row["email"], row["client_id"], "owner_removed", owner_email)
    finally:
        conn.close()


def notify_rep(client_id: int, account_email: str) -> None:
    """Письмо остальным адресам карточки о новом представителе (athlete_claims.send_notice: в фоне, ошибки — в лог)."""
    send_notice(client_id, account_email, "Аккаунт получил доступ к истории ваших забегов",
                lambda fio, masked: (f"Доступ к истории забегов {fio} на сайте результатов Красмарафона получил "
                                     f"аккаунт {masked}. Если вы не знаете этого человека — напишите нам на "
                                     f"{SUPPORT_EMAIL}\n"))
