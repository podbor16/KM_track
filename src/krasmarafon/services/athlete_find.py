"""«Найти себя» (Б3, docs/superpowers/specs/2026-11-04-athlete-b3-design.md): поиск своей карточки по ФИ + ДР + стартовому
номеру с любого забега. Доказательство, что человек знает карточку, — номер. Лимит — FIND_PER_DAY поисков в сутки на аккаунт
(athlete_find_attempts; не смешивается с лимитом неверных ДР). Заявление найденной карточки — athlete_claims.claim(...,
via_find=True) по токену находки: подписанный (HMAC SECRET_KEY) client_id + почта + срок TOKEN_TTL_SEC, чтобы заявить
можно было только найденную этим аккаунтом карточку."""

import hmac
import time
from datetime import date
from typing import Optional

from src.krasmarafon.services.athlete_auth import _conn, _hmac, normalize_email
from src.krasmarafon.services.athlete_claims import NO_BIRTHDAY, advisory_lock, history_rows

FIND_PER_DAY = 5
TOKEN_TTL_SEC = 15 * 60


class FindLimit(Exception):
    """Больше FIND_PER_DAY поисков за сутки с этого аккаунта."""


def find_card(email: str, surname: str, name: str, birthday: date, bib) -> Optional[dict]:
    """Ровно одна карточка с такими ФИ (регистр и ё/е — по коллации БД) и ДР (не заглушка), у которой есть строка с этим
    номером (results.start_number или leads.start_number): {"client_id", "title", "since", "starts"}; иначе None
    (не нашли / несколько — не различается). Каждый вызов — попытка; сверх лимита — FindLimit."""
    email = normalize_email(email)
    surname, name = (surname or "").strip(), (name or "").strip()
    conn = _conn()
    try:
        cur = conn.cursor(dictionary=True)
        with advisory_lock(cur, f"find:{email}"):
            cur.execute("DELETE FROM athlete_find_attempts WHERE created_at < NOW() - INTERVAL 1 DAY")
            cur.execute("""SELECT COUNT(*) AS n FROM athlete_find_attempts
                           WHERE email = %s AND created_at > NOW() - INTERVAL 1 DAY""", (email,))
            if cur.fetchone()["n"] >= FIND_PER_DAY:
                raise FindLimit()
            cur.execute("INSERT INTO athlete_find_attempts (email) VALUES (%s)", (email,))
        try:
            bib = int(str(bib).strip())
        except ValueError:
            return None
        if not surname or not name or not birthday or birthday in NO_BIRTHDAY or bib < 0:
            return None
        cur.execute("""SELECT c.id, c.surname, c.name FROM clients c
                       WHERE c.surname = %s AND c.name = %s AND c.birthday = %s
                         AND (EXISTS (SELECT 1 FROM results r WHERE r.client_id = c.id AND r.start_number = %s)
                              OR EXISTS (SELECT 1 FROM leads l WHERE l.client_id = c.id AND l.start_number = %s))
                       LIMIT 2""", (surname, name, birthday, bib, bib))
        rows = cur.fetchall()
        cur.close()
    finally:
        conn.close()
    if len(rows) != 1:
        return None
    card = rows[0]
    results, leads = history_rows([card["id"]])
    years = [r["event_year"] for r in results + leads if r.get("event_year")]
    return {"client_id": card["id"], "title": f"{card['surname']} {card['name']}".strip(),
            "since": min(years) if years else None, "starts": len(results)}


def _sign(email: str, client_id: int, exp: int) -> str:
    return _hmac(f"find:{email}:{client_id}:{exp}")


def make_token(email: str, client_id: int) -> str:
    """Токен находки "client_id.exp.подпись" для POST /me/find/claim."""
    email = normalize_email(email)
    exp = int(time.time()) + TOKEN_TTL_SEC
    return f"{int(client_id)}.{exp}.{_sign(email, int(client_id), exp)}"


def read_token(email: str, token) -> Optional[int]:
    """client_id из токена, если подпись верна, он выдан этой почте и не просрочен; иначе None."""
    try:
        cid, exp, sig = str(token).split(".")
        cid, exp = int(cid), int(exp)
    except ValueError:
        return None
    if exp < time.time() or not hmac.compare_digest(sig, _sign(normalize_email(email), cid, exp)):
        return None
    return cid
