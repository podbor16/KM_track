"""Привязка карточки спортсмена (clients.id) к кабинету-почте («Это я») по подтверждённой ДР
(спецификация docs/superpowers/specs/2026-11-03-athlete-cards-history-design.md).

Привязка действует, пока карточка существует и её ДР совпадает с подтверждённой: проверка — лениво,
в claimed_cards(). Заявление/снятие пишутся в журнал dq_actions. Пул — autocommit: атомарность
нескольких запросов — через start_transaction(); гонку двух аккаунтов решает UNIQUE (client_id)."""

import html
import json
import logging
from datetime import date
from enum import Enum

from mysql.connector.errors import IntegrityError

from src.core.mailer import send_mail
from src.krasmarafon.services.athlete_auth import _conn, normalize_email

logger = logging.getLogger(__name__)

CLAIM_ATTEMPTS_PER_DAY = 5
NOTIFY_MAX = 10
NO_BIRTHDAY = (None, date(1900, 1, 1))
SUPPORT_EMAIL = "1@krasmarafon.ru"


class ClaimResult(str, Enum):
    OK = "ok"
    ALREADY_MINE = "already_mine"
    TAKEN = "taken"
    NO_BIRTHDAY = "no_birthday"
    LIMIT = "limit"
    MISMATCH = "mismatch"


def _log(cur, action: str, client_id: int, details: dict, user: str) -> None:
    cur.execute("INSERT INTO dq_actions (action, finding_key, details, done_by) VALUES (%s, %s, %s, %s)",
                (action, f"client:{client_id}", json.dumps(details, ensure_ascii=False), user))


def _unclaim_row(conn, claim_id: int, email: str, client_id: int, reason: str, user: str) -> bool:
    """Удаляет привязку и пишет журнал одной транзакцией. False — привязку уже сняли (параллельный запрос)."""
    cur = conn.cursor()
    conn.start_transaction()
    try:
        cur.execute("DELETE FROM athlete_claims WHERE id = %s", (claim_id,))
        removed = cur.rowcount == 1
        if removed:
            _log(cur, "athlete_unclaim", client_id, {"email": email, "reason": reason}, user)
        conn.commit()
        return removed
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()


def _sweep(conn, where: str, params: tuple) -> tuple[list[int], list[int]]:
    """Проверяет привязки по условию `where` (по алиасу ac): недействительные снимает.
    -> (client_id действующих, client_id снятых) в порядке заявления."""
    cur = conn.cursor(dictionary=True)
    cur.execute(f"""SELECT ac.id, ac.email, ac.client_id, ac.birthday, c.id AS card, c.birthday AS card_birthday
                    FROM athlete_claims ac LEFT JOIN clients c ON c.id = ac.client_id
                    WHERE {where} ORDER BY ac.created_at, ac.id""", params)
    rows = cur.fetchall()
    cur.close()
    valid, dropped = [], []
    for r in rows:
        if r["card"] is None:
            reason = "card_deleted"
        elif r["card_birthday"] != r["birthday"]:
            reason = "birthday_changed"
        else:
            valid.append(r["client_id"])
            continue
        if _unclaim_row(conn, r["id"], r["email"], r["client_id"], reason, "system"):
            dropped.append(r["client_id"])
    return valid, dropped


def claimed_cards(email: str) -> tuple[list[int], list[int]]:
    """(действующие client_id аккаунта, client_id снятых сейчас привязок). Снимает недействительные:
    карточки нет (card_deleted) или clients.birthday <> athlete_claims.birthday (birthday_changed) —
    DELETE + журнал dq_actions (athlete_unclaim, details={"email", "reason"}, done_by='system')."""
    conn = _conn()
    try:
        return _sweep(conn, "ac.email = %s", (normalize_email(email),))
    finally:
        conn.close()


def claim(email: str, client_id: int, birthday: date) -> ClaimResult:
    """Заявить карточку: проверки — спецификация «Заявление карточки», п. 1–6. Карточки нет среди заявок
    почты — ValueError. Попытка пишется только при MISMATCH. При OK — журнал и уведомление адресатам
    карточки (ошибки отправки не мешают)."""
    email = normalize_email(email)
    conn = _conn()
    try:
        result, card = _claim(conn, email, client_id, birthday)
    finally:
        conn.close()
    if result == ClaimResult.OK:
        _notify(card, client_id, email)
    return result


def _claim(conn, email: str, client_id: int, birthday: date) -> tuple[ClaimResult, dict]:
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute("""SELECT c.surname, c.name, c.birthday FROM clients c WHERE c.id = %s AND EXISTS (
                         SELECT 1 FROM leads WHERE client_id = c.id AND (LOWER(email) = %s OR LOWER(ma_email) = %s))""",
                    (client_id, email, email))
        card = cur.fetchone()
        if card is None:
            raise ValueError(f"карточки {client_id} нет среди заявок почты аккаунта")

        _sweep(conn, "ac.client_id = %s", (client_id,))   # устаревшая чужая привязка не должна мешать
        cur.execute("SELECT email FROM athlete_claims WHERE client_id = %s", (client_id,))
        owner = cur.fetchone()
        if owner is not None:
            return (ClaimResult.ALREADY_MINE if owner["email"] == email else ClaimResult.TAKEN), card

        if card["birthday"] in NO_BIRTHDAY:
            return ClaimResult.NO_BIRTHDAY, card

        cur.execute("""SELECT COUNT(*) AS n FROM athlete_claim_attempts
                       WHERE email = %s AND client_id = %s AND created_at > NOW() - INTERVAL 1 DAY""",
                    (email, client_id))
        if cur.fetchone()["n"] >= CLAIM_ATTEMPTS_PER_DAY:
            return ClaimResult.LIMIT, card

        if card["birthday"] != birthday:
            cur.execute("INSERT INTO athlete_claim_attempts (email, client_id) VALUES (%s, %s)", (email, client_id))
            return ClaimResult.MISMATCH, card

        conn.start_transaction()
        try:
            cur.execute("INSERT INTO athlete_claims (email, client_id, birthday) VALUES (%s, %s, %s)",
                        (email, client_id, birthday))
            _log(cur, "athlete_claim", client_id, {"email": email}, email)
            conn.commit()
        except IntegrityError:        # параллельно карточку заявил другой аккаунт (или эта же почта из второй вкладки)
            conn.rollback()
            cur.execute("SELECT email FROM athlete_claims WHERE client_id = %s", (client_id,))
            owner = cur.fetchone()
            return (ClaimResult.ALREADY_MINE if owner and owner["email"] == email else ClaimResult.TAKEN), card
        except Exception:
            conn.rollback()
            raise
        return ClaimResult.OK, card
    finally:
        cur.close()


def unclaim(email: str, client_id: int) -> None:
    """Снять привязку этого аккаунта (чужую не трогает); журнал athlete_unclaim, reason='user'."""
    email = normalize_email(email)
    conn = _conn()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT id FROM athlete_claims WHERE email = %s AND client_id = %s", (email, client_id))
        row = cur.fetchone()
        cur.close()
        if row:
            _unclaim_row(conn, row["id"], email, client_id, "user", email)
    finally:
        conn.close()


def notify_recipients(client_id: int, account_email: str) -> list[str]:
    """Различные непустые leads.email/ma_email карточки (lower, strip), без почты аккаунта, не больше NOTIFY_MAX."""
    account_email = normalize_email(account_email)
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("""SELECT LOWER(TRIM(email)) FROM leads WHERE client_id = %s
                       UNION SELECT LOWER(TRIM(ma_email)) FROM leads WHERE client_id = %s""", (client_id, client_id))
        found = {r[0] for r in cur.fetchall() if r[0]}
        cur.close()
    finally:
        conn.close()
    return sorted(found - {account_email})[:NOTIFY_MAX]


def mask_email(email: str) -> str:
    """petr@mail.ru -> p***@mail.ru"""
    local, at, domain = (email or "").partition("@")
    return f"{local[:1]}***{at}{domain}"


def _notify(card: dict, client_id: int, account_email: str) -> None:
    fio = f"{card['surname']} {card['name']}".strip()
    subject = "Вашу историю забегов привязали к личному кабинету"
    text = (f"Историю забегов {fio} на сайте результатов Красмарафона привязали к почте "
            f"{mask_email(account_email)}. Если это не вы — напишите нам на {SUPPORT_EMAIL}\n")
    body = html.escape(text.strip())
    page = f'<div style="font-family:Arial,sans-serif;font-size:15px;color:#333;max-width:480px"><p>{body}</p></div>'
    try:
        recipients = notify_recipients(client_id, account_email)
    except Exception:
        logger.exception("Уведомление о привязке карточки %s: не удалось получить адресатов", client_id)
        return
    for to in recipients:
        try:
            send_mail(to, subject, text, page)
        except Exception:
            logger.exception("Уведомление о привязке карточки %s: письмо не отправлено", client_id)


_RESULTS_SQL = """
    SELECT r.id, r.client_id, r.surname, r.event_id, r.start_number, e.event_name, e.event_year, e.event_date,
           e.event_distance, r.race_status, r.time_clear_finish, r.time_gun_finish,
           r.rank_category, r.rank_category_clean
    FROM results r LEFT JOIN events e ON e.id = r.event_id
    WHERE r.client_id IN ({ph}) ORDER BY r.id"""

_LEADS_SQL = """
    SELECT l.id, l.client_id, l.event_id, l.start_number, l.refund, l.event_name, l.event_year,
           e.event_date, e.event_distance
    FROM leads l LEFT JOIN events e ON e.id = l.event_id
    WHERE l.client_id IN ({ph}) AND l.is_duplicate = 0 ORDER BY l.id"""


def history_rows(client_ids) -> tuple[list[dict], list[dict]]:
    """(результаты, заявки) карточек для athlete_history.build_history. Заявки без дублей; события — LEFT JOIN;
    флаг «Без ПД» не учитывается (человек смотрит свои данные)."""
    ids = [int(i) for i in client_ids]
    if not ids:
        return [], []
    ph = ",".join(["%s"] * len(ids))
    conn = _conn()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(_RESULTS_SQL.format(ph=ph), ids)
        results = cur.fetchall()
        cur.execute(_LEADS_SQL.format(ph=ph), ids)
        leads = cur.fetchall()
        cur.close()
        return results, leads
    finally:
        conn.close()


def history_title(client_ids) -> str:
    """ФИ самой новой по времени заявления карточки из списка (clients.surname name); пусто — если нет."""
    ids = [int(i) for i in client_ids]
    if not ids:
        return ""
    conn = _conn()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(f"""SELECT c.surname, c.name FROM athlete_claims ac JOIN clients c ON c.id = ac.client_id
                        WHERE ac.client_id IN ({",".join(["%s"] * len(ids))})
                        ORDER BY ac.created_at DESC, ac.id DESC LIMIT 1""", ids)
        row = cur.fetchone()
        cur.close()
        return f"{row['surname']} {row['name']}".strip() if row else ""
    finally:
        conn.close()


def duplicate_accounts() -> list[dict]:
    """Для админки: аккаунты с ≥ 2 действующими привязками (ДР карточки = подтверждённой):
    [{"email", "cards": [{"id", "surname", "name", "birthday"}]}]. Только чтение."""
    conn = _conn()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("""SELECT ac.email, c.id, c.surname, c.name, c.birthday
                       FROM athlete_claims ac JOIN clients c ON c.id = ac.client_id AND c.birthday = ac.birthday
                       WHERE ac.email IN (SELECT a2.email FROM athlete_claims a2
                                          JOIN clients c2 ON c2.id = a2.client_id AND c2.birthday = a2.birthday
                                          GROUP BY a2.email HAVING COUNT(*) >= 2)
                       ORDER BY ac.email, ac.created_at, ac.id""")
        rows = cur.fetchall()
        cur.close()
    finally:
        conn.close()
    out: dict = {}
    for r in rows:
        out.setdefault(r["email"], {"email": r["email"], "cards": []})["cards"].append(
            {"id": r["id"], "surname": r["surname"], "name": r["name"], "birthday": r["birthday"]})
    return list(out.values())
