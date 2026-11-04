"""Привязка карточки спортсмена (clients.id) к кабинету-почте («Это я») по подтверждённой ДР
(спецификация docs/superpowers/specs/2026-11-03-athlete-cards-history-design.md).

Привязка действует, пока карточка существует и её ДР совпадает с подтверждённой: проверка — лениво,
в claimed_cards(). Заявление/снятие пишутся в журнал dq_actions. Карточка и её история принадлежат человеку,
чьи ФИ и ДР (с поправкой на опечатки) совпадают с карточкой — same_person(): строка «переданного слота»
(другой человек на карточке) права заявить не даёт, в историю и в рассылку не попадает. Пул — autocommit: атомарность
нескольких запросов — через start_transaction(). claim() сериализует запросы по карточке блокировкой
строки clients (FOR UPDATE); UNIQUE (client_id) — страховка. Письма claim() не шлёт: роутер ставит
notify_claimed() в BackgroundTasks."""

import html
import json
import logging
from datetime import date
from enum import Enum

from mysql.connector import errorcode
from mysql.connector.errors import IntegrityError

from src.analytics.dq_checks import compatible_bd, fio_close, fio_key, real_bd
from src.core.mailer import mask_email, send_mail
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
    OTHER_PERSON = "other_person"


def same_person(card: dict, row: dict) -> bool:
    """Строка (заявка/результат) принадлежит владельцу карточки: ДР совместимы (dq_checks.compatible_bd: заглушка,
    опечатка, день↔месяц) и ФИ близки (dq_checks.fio_close). Если у одной из ДР нет настоящего значения (заглушка/пусто),
    ДР человека не подтверждает — тогда ФИ должны совпасть точно или быть переставлены (без нечёткого fio_close:
    «Иванов Евгений» и «Иванова Евгения» — разные люди). card/row — dict с surname, name, birthday (date|None)."""
    def iso(d):
        return d.isoformat() if d else ""
    a, b = iso(card["birthday"]), iso(row["birthday"])
    ka, kb = fio_key(card), fio_key(row)
    close = fio_close(ka, kb) if real_bd(a) and real_bd(b) else ka in (kb, kb[::-1])
    return close and compatible_bd(a, b)


def log_action(cur, action: str, client_id: int, details: dict, user: str) -> None:
    cur.execute("INSERT INTO dq_actions (action, finding_key, details, done_by) VALUES (%s, %s, %s, %s)",
                (action, f"client:{client_id}", json.dumps(details, ensure_ascii=False), user))


def unclaim_row(conn, claim_id: int, email: str, client_id: int, reason: str, user: str,
                in_tx: bool = False, table: str = "athlete_claims", action: str = "athlete_unclaim") -> bool:
    """Удаляет привязку (table — athlete_claims или athlete_reps) и пишет журнал action одной транзакцией
    (in_tx — внутри уже открытой транзакции вызывающего, commit/rollback за ним). False — строку уже
    сняли (параллельный запрос)."""
    cur = conn.cursor()
    if not in_tx:
        conn.start_transaction()
    try:
        cur.execute(f"DELETE FROM {table} WHERE id = %s", (claim_id,))
        removed = cur.rowcount == 1
        if removed:
            log_action(cur, action, client_id, {"email": email, "reason": reason}, user)
        if not in_tx:
            conn.commit()
        return removed
    except Exception:
        if not in_tx:
            conn.rollback()
        raise
    finally:
        cur.close()


def sweep(conn, where: str, params: tuple, in_tx: bool = False, table: str = "athlete_claims",
          action: str = "athlete_unclaim") -> tuple[list[int], list[int]]:
    """Проверяет привязки (table: athlete_claims или athlete_reps) по условию `where` (по алиасу ac): недействительные снимает.
    -> (client_id действующих, client_id снятых) в порядке заявления."""
    cur = conn.cursor(dictionary=True)
    cur.execute(f"""SELECT ac.id, ac.email, ac.client_id, ac.birthday, c.id AS card, c.birthday AS card_birthday
                    FROM {table} ac LEFT JOIN clients c ON c.id = ac.client_id
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
        if unclaim_row(conn, r["id"], r["email"], r["client_id"], reason, "system", in_tx, table, action):
            dropped.append(r["client_id"])
    return valid, dropped


def claimed_cards(email: str) -> tuple[list[int], list[int]]:
    """(действующие client_id аккаунта, client_id снятых сейчас привязок). Снимает недействительные:
    карточки нет (card_deleted) или clients.birthday <> athlete_claims.birthday (birthday_changed) —
    DELETE + журнал dq_actions (athlete_unclaim, details={"email", "reason"}, done_by='system')."""
    conn = _conn()
    try:
        return sweep(conn, "ac.email = %s", (normalize_email(email),))
    finally:
        conn.close()


def claim(email: str, client_id: int, birthday: date) -> ClaimResult:
    """Заявить карточку: проверки — спецификация «Заявление карточки», п. 1–6 и «Доработки» (OTHER_PERSON:
    вторая карточка аккаунта — только с той же ДР). Нет заявки этого человека (same_person) на почте — ValueError. Всё — в одной транзакции под блокировкой строки карточки (параллельные запросы по
    ней идут по очереди, лимит попыток не обойти); устаревшая привязка снимается в ней же. Попытка пишется
    только при MISMATCH. Писем не шлёт: при OK вызывающий ставит notify_claimed() в фон."""
    return in_transaction(_claim, normalize_email(email), client_id, birthday)


def in_transaction(fn, *args):
    """fn(conn, *args) в одной транзакции отдельного соединения пула (autocommit там выключается start_transaction)."""
    conn = _conn()
    try:
        conn.start_transaction()
        try:
            result = fn(conn, *args)
            conn.commit()
            return result
        except BaseException:
            conn.rollback()
            raise
    finally:
        conn.close()


def require_own_lead(cur, email: str, client_id: int, card: dict) -> None:
    """Среди заявок почты есть заявка самого владельца карточки (same_person), иначе ValueError."""
    cur.execute("""SELECT surname, name, birthday FROM leads
                   WHERE client_id = %s AND (LOWER(email) = %s OR LOWER(ma_email) = %s)""",
                (client_id, email, email))
    if not any(same_person(card, lead) for lead in cur.fetchall()):
        raise ValueError(f"карточки {client_id} нет среди заявок почты аккаунта")


def attempts_exceeded(cur, email: str, client_id: int) -> bool:
    """Лимит неверных ДР на (аккаунт, карточку) за сутки — общий для «Это я» и «Я представитель»."""
    cur.execute("""SELECT COUNT(*) AS n FROM athlete_claim_attempts
                   WHERE email = %s AND client_id = %s AND created_at > NOW() - INTERVAL 1 DAY""",
                (email, client_id))
    return cur.fetchone()["n"] >= CLAIM_ATTEMPTS_PER_DAY


def record_attempt(cur, email: str, client_id: int) -> None:
    cur.execute("DELETE FROM athlete_claim_attempts WHERE created_at < NOW() - INTERVAL 1 DAY")
    cur.execute("INSERT INTO athlete_claim_attempts (email, client_id) VALUES (%s, %s)", (email, client_id))


def _claim(conn, email: str, client_id: int, birthday: date) -> ClaimResult:
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute("SELECT surname, name, birthday FROM clients WHERE id = %s FOR UPDATE", (client_id,))
        card = cur.fetchone()
        if card is None:
            raise ValueError(f"карточки {client_id} нет")
        require_own_lead(cur, email, client_id, card)

        sweep(conn, "ac.client_id = %s", (client_id,), in_tx=True)   # устаревшая чужая привязка не должна мешать
        cur.execute("SELECT email FROM athlete_claims WHERE client_id = %s", (client_id,))
        owner = cur.fetchone()
        if owner is not None:
            return ClaimResult.ALREADY_MINE if owner["email"] == email else ClaimResult.TAKEN

        if card["birthday"] in NO_BIRTHDAY:
            return ClaimResult.NO_BIRTHDAY

        cur.execute("""SELECT DISTINCT ac.birthday FROM athlete_claims ac
                       JOIN clients c ON c.id = ac.client_id AND c.birthday = ac.birthday WHERE ac.email = %s""", (email,))
        mine = {r["birthday"] for r in cur.fetchall()}
        if mine and card["birthday"] not in mine:    # один человек — одна ДР; до лимита и до сверки ДР
            return ClaimResult.OTHER_PERSON

        if attempts_exceeded(cur, email, client_id):
            return ClaimResult.LIMIT

        if card["birthday"] != birthday:
            record_attempt(cur, email, client_id)
            return ClaimResult.MISMATCH

        try:
            cur.execute("INSERT INTO athlete_claims (email, client_id, birthday) VALUES (%s, %s, %s)",
                        (email, client_id, birthday))
        except IntegrityError as e:   # страховка UNIQUE; под блокировкой карточки сюда попадать не должны
            if e.errno != errorcode.ER_DUP_ENTRY:
                raise
            cur.execute("SELECT email FROM athlete_claims WHERE client_id = %s", (client_id,))
            owner = cur.fetchone()
            return ClaimResult.ALREADY_MINE if owner and owner["email"] == email else ClaimResult.TAKEN
        log_action(cur, "athlete_claim", client_id, {"email": email}, email)
        return ClaimResult.OK
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
            unclaim_row(conn, row["id"], email, client_id, "user", email)
    finally:
        conn.close()


def notify_recipients(client_id: int, account_email: str) -> list[str]:
    """Различные непустые leads.email/ma_email заявок самого владельца карточки (same_person; заявки переданного
    слота — не его) в lower/strip, без почты аккаунта, не больше NOTIFY_MAX."""
    account_email = normalize_email(account_email)
    conn = _conn()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT surname, name, birthday FROM clients WHERE id = %s", (client_id,))
        card = cur.fetchone()
        if card is None:
            cur.close()
            return []
        cur.execute("SELECT surname, name, birthday, email, ma_email FROM leads WHERE client_id = %s", (client_id,))
        rows = [r for r in cur.fetchall() if same_person(card, r)]
        cur.close()
    finally:
        conn.close()
    found = {(m or "").strip().lower() for r in rows for m in (r["email"], r["ma_email"])} - {""}
    return sorted(found - {account_email})[:NOTIFY_MAX]


def send_notice(client_id: int, account_email: str, subject: str, text_for) -> None:
    """Письмо остальным адресам карточки. Отправка синхронная — вызывать из BackgroundTasks. text_for(fio, маска
    почты аккаунта) -> текст. Ничего не бросает: ошибки БД и SMTP только в лог."""
    account_email = normalize_email(account_email)
    try:
        conn = _conn()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT surname, name FROM clients WHERE id = %s", (client_id,))
            card = cur.fetchone()
            cur.close()
        finally:
            conn.close()
        if card is None:
            return
        recipients = notify_recipients(client_id, account_email)
    except Exception:
        logger.exception("Уведомление по карточке %s: не удалось получить адресатов", client_id)
        return
    text = text_for(f"{card['surname']} {card['name']}".strip(), mask_email(account_email))
    body = html.escape(text.strip())
    page = f'<div style="font-family:Arial,sans-serif;font-size:15px;color:#333;max-width:480px"><p>{body}</p></div>'
    for to in recipients:
        try:
            send_mail(to, subject, text, page)
        except Exception:
            logger.exception("Уведомление по карточке %s: письмо не отправлено", client_id)


def notify_claimed(client_id: int, account_email: str) -> None:
    """Письмо остальным адресам карточки о привязке (send_notice)."""
    send_notice(client_id, account_email, "Вашу историю забегов привязали к личному кабинету",
                lambda fio, masked: (f"Историю забегов {fio} на сайте результатов Красмарафона привязали к почте "
                                     f"{masked}. Если это не вы — напишите нам на {SUPPORT_EMAIL}\n"))


# M в «N/M»: финишировавшие (Finished и есть время) в событии и в той же категории (пустая = «без категории»);
# подзапросы идут по индексу results.event_id (EXPLAIN: ref idx_event/uq_results_event_start, ~10^3 строк на событие)
_RESULTS_SQL = """
    SELECT r.id, r.client_id, r.surname, r.name, r.birthday, r.event_id, r.start_number, e.event_name, e.event_year,
           e.event_date, e.event_distance, r.race_status, r.time_clear_finish, r.time_gun_finish,
           r.category, r.rank_absolute, r.rank_absolute_clean, r.rank_category, r.rank_category_clean,
           (SELECT COUNT(*) FROM results f WHERE f.event_id = r.event_id AND f.race_status = 'Finished'
               AND COALESCE(f.time_clear_finish, f.time_gun_finish) IS NOT NULL) AS finishers_total,
           (SELECT COUNT(*) FROM results f WHERE f.event_id = r.event_id AND f.race_status = 'Finished'
               AND COALESCE(f.time_clear_finish, f.time_gun_finish) IS NOT NULL
               AND COALESCE(NULLIF(TRIM(f.category), ''), '') = COALESCE(NULLIF(TRIM(r.category), ''), '')
           ) AS finishers_category
    FROM results r LEFT JOIN events e ON e.id = r.event_id
    WHERE r.client_id IN ({ph}) ORDER BY r.id"""

_LEADS_SQL = """
    SELECT l.id, l.client_id, l.surname, l.name, l.birthday, l.event_id, l.start_number, l.refund, l.event_name,
           l.event_year, e.event_date, e.event_distance, l.created_at, l.order_id, l.amount, l.promocode, l.discount,
           l.products, l.email, l.ma_email
    FROM leads l LEFT JOIN events e ON e.id = l.event_id
    WHERE l.client_id IN ({ph}) AND l.is_duplicate = 0 ORDER BY l.id"""


def history_rows(client_ids) -> tuple[list[dict], list[dict]]:
    """(результаты, заявки) карточек для athlete_history.build_history — только строки самого владельца карточки
    (same_person: строка переданного слота, ФИ другого человека, не показывается; опечатки — показываются). Заявки
    без дублей; события — LEFT JOIN; флаг «Без ПД» не учитывается (человек смотрит свои данные)."""
    ids = [int(i) for i in client_ids]
    if not ids:
        return [], []
    ph = ",".join(["%s"] * len(ids))
    conn = _conn()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(f"SELECT id, surname, name, birthday FROM clients WHERE id IN ({ph})", ids)
        cards = {c["id"]: c for c in cur.fetchall()}
        cur.execute(_RESULTS_SQL.format(ph=ph), ids)
        results = [r for r in cur.fetchall() if r["client_id"] in cards and same_person(cards[r["client_id"]], r)]
        cur.execute(_LEADS_SQL.format(ph=ph), ids)
        leads = [r for r in cur.fetchall() if r["client_id"] in cards and same_person(cards[r["client_id"]], r)]
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
