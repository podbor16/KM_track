"""«Найти себя» (Б3, docs/superpowers/specs/2026-11-04-athlete-b3-design.md): поиск своей карточки по ФИ + ДР + стартовому
номеру с любого забега. Доказательство, что человек знает карточку, — номер. Лимит — FIND_PER_DAY поисков в сутки на аккаунт
(athlete_find_attempts; не смешивается с лимитом неверных ДР). Заявление найденной карточки — athlete_claims.claim(...,
via_find=True) по токену находки: подписанный (HMAC SECRET_KEY) client_id + почта + срок TOKEN_TTL_SEC, чтобы заявить
можно было только найденную этим аккаунтом карточку."""

import hmac
from contextlib import nullcontext
import time
from datetime import date
from typing import Optional

from src.krasmarafon.services.athlete_auth import _conn, _hmac, normalize_email
from src.krasmarafon.services.athlete_claims import NO_BIRTHDAY, advisory_lock, history_rows, same_person

FIND_PER_DAY = 5
FIND_PER_FIO_DAY = 10      # общий лимит на пару «фамилия + имя» со всех аккаунтов
TOKEN_TTL_SEC = 15 * 60


class FindLimit(Exception):
    """Больше FIND_PER_DAY поисков за сутки с этого аккаунта или FIND_PER_FIO_DAY по одной паре «фамилия + имя»."""


def _fio_key(surname: str, name: str) -> Optional[str]:
    """Пара «фамилия + имя» без регистра, ё и лишних пробелов; None, если одной из частей нет."""
    parts = [" ".join(p.lower().replace("ё", "е").split()) for p in (surname, name)]
    return " ".join(parts) if all(parts) else None


def find_card(email: str, surname: str, name: str, birthday: date, bib) -> Optional[dict]:
    """Ровно одна карточка с такими ФИ (регистр и ё/е — по коллации БД) и ДР (не заглушка), у которой есть строка с этим
    номером (results.start_number или leads.start_number без дубля; только собственные строки владельца, как в истории): {"client_id", "title", "since", "starts"}; иначе None
    (не нашли / несколько — не различается). Каждый вызов — попытка; сверх лимита — FindLimit."""
    email = normalize_email(email)
    surname, name = (surname or "").strip(), (name or "").strip()
    conn = _conn()
    try:
        cur = conn.cursor(dictionary=True)
        fio = _fio_key(surname, name)
        with advisory_lock(cur, f"find:{email}"):
            cur.execute("DELETE FROM athlete_find_attempts WHERE created_at < NOW() - INTERVAL 1 DAY")
            cur.execute("""SELECT COUNT(*) AS n FROM athlete_find_attempts
                           WHERE email = %s AND created_at > NOW() - INTERVAL 1 DAY""", (email,))
            if cur.fetchone()["n"] >= FIND_PER_DAY:
                raise FindLimit()
            with advisory_lock(cur, f"find-fio:{fio}") if fio else nullcontext():
                if fio:
                    cur.execute("""SELECT COUNT(*) AS n FROM athlete_find_attempts
                                   WHERE fio = %s AND created_at > NOW() - INTERVAL 1 DAY""", (fio,))
                    if cur.fetchone()["n"] >= FIND_PER_FIO_DAY:
                        raise FindLimit()
                cur.execute("INSERT INTO athlete_find_attempts (email, fio) VALUES (%s, %s)", (email, fio))
        try:
            bib = int(str(bib).strip())
        except ValueError:
            return None
        if not surname or not name or not birthday or birthday in NO_BIRTHDAY or bib < 0:
            return None
        cur.execute("""SELECT c.id, c.surname, c.name, c.birthday FROM clients c
                       WHERE c.surname = %s AND c.name = %s AND c.birthday = %s LIMIT 10""", (surname, name, birthday))
        rows = [c for c in cur.fetchall() if _has_own_bib(cur, c, bib)]
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


def _has_own_bib(cur, card: dict, bib: int) -> bool:
    """Номер есть у собственной строки владельца карточки (same_person): результат или заявка без дубля (как в истории)."""
    cur.execute("""SELECT surname, name, birthday FROM results WHERE client_id = %s AND start_number = %s
                   UNION ALL
                   SELECT surname, name, birthday FROM leads
                   WHERE client_id = %s AND start_number = %s AND is_duplicate = 0""", (card["id"], bib, card["id"], bib))
    return any(same_person(card, row) for row in cur.fetchall())


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
