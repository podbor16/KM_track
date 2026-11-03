"""
Склейка карточек клиентов: перенос заявок и результатов, итоговые ФИО/ДР,
восстановление контактов, пересчёт счётчиков. Бэкап затронутых строк — в JSON.
"""

import collections
import json
from pathlib import Path

from mysql.connector.errors import ProgrammingError

from src.analytics.db_results import recompute_duplicates


def log_action(cur, action, key, details, user):
    """Запись журнала dq_actions -> её id (по нему действие отменяется)."""
    cur.execute("INSERT INTO dq_actions (action, finding_key, details, done_by) VALUES (%s, %s, %s, %s)",
                (action, key or "", json.dumps(details, ensure_ascii=False, default=str), user or ""))
    return cur.lastrowid


def move_athlete_claims(cur, merged_into, user):
    """Привязки кабинета (athlete_claims) удаляемых карточек -> на итоговую, если её никто не заявил; иначе
    привязка удаляемой снимается (журнал athlete_unclaim). Совпадение ДР проверит claimed_cards().
    Таблицы ещё нет (миграция не применена) — ничего не делаем.
    -> [{client_id, email, moved_to | dropped[, stale]}]; stale — у снятой привязки ДР уже не совпадала с карточкой
    (при отмене не возвращается: подтверждённой ДР, которую можно восстановить, нет)."""
    if not merged_into:
        return []
    ids = sorted(set(merged_into) | set(merged_into.values()))
    try:
        cur.execute("SELECT a.id, a.email, a.client_id, a.birthday = c.birthday FROM athlete_claims a "
                    f"LEFT JOIN clients c ON c.id = a.client_id WHERE a.client_id IN ({','.join(['%s'] * len(ids))}) "
                    "ORDER BY a.created_at, a.id", ids)
        claims = cur.fetchall()
    except ProgrammingError as e:
        if e.errno != 1146:
            raise
        return []
    taken = {cid for _, _, cid, _ in claims if cid not in merged_into}
    moved = []
    for claim_id, email, cid, valid in claims:
        if cid not in merged_into:
            continue
        target = merged_into[cid]
        if target in taken:
            cur.execute("DELETE FROM athlete_claims WHERE id = %s", (claim_id,))
            log_action(cur, "athlete_unclaim", f"client:{cid}", {"email": email, "reason": "merged"}, user)
            moved.append({"client_id": cid, "email": email, "dropped": True, **({} if valid else {"stale": True})})
        else:
            cur.execute("UPDATE athlete_claims SET client_id = %s WHERE id = %s", (target, claim_id))
            taken.add(target)
            moved.append({"client_id": cid, "email": email, "moved_to": target})
    return moved


def apply(conn, cards, final, merged_into, backup, drop_leads=(), user="script", claims_out=None):
    """drop_leads — карточки, чьи заявки удаляются (решение пользователя); карточка
    удаляется, если у неё не осталось ни заявок, ни результатов. Привязки кабинета склеенных карточек
    переносятся в той же транзакции (user — для журнала; claims_out — список, куда кладётся перенос)."""
    cur = conn.cursor(dictionary=True)
    touched = sorted(set(final) | set(merged_into))
    ph = lambda ids: ",".join(str(int(i)) for i in ids)
    snap = {}
    if drop_leads:
        cur.execute(f"SELECT * FROM leads WHERE client_id IN ({ph(drop_leads)})")
        snap["dropped_leads"] = cur.fetchall()
        cur.execute(f"SELECT * FROM clients WHERE id IN ({ph(drop_leads)})")
        snap["dropped_clients"] = cur.fetchall()
    for chunk in (touched[i:i + 2000] for i in range(0, len(touched), 2000)):
        cur.execute(f"SELECT * FROM clients WHERE id IN ({ph(chunk)})")
        snap.setdefault("clients", []).extend(cur.fetchall())
        cur.execute(f"SELECT id, client_id, surname, name, birthday FROM leads WHERE client_id IN ({ph(chunk)})")
        snap.setdefault("leads", []).extend(cur.fetchall())
        cur.execute(f"SELECT id, client_id, surname, name, birthday FROM results WHERE client_id IN ({ph(chunk)})")
        snap.setdefault("results", []).extend(cur.fetchall())
    Path(backup).write_text(json.dumps(snap, default=str, ensure_ascii=False), encoding="utf-8")

    by_survivor = collections.defaultdict(list)
    for i, s in merged_into.items():
        by_survivor[s].append(i)
    # пул — autocommit: без явной транзакции откат при ошибке был бы пустым
    if not conn.in_transaction:
        conn.start_transaction()
    try:
        plain = conn.cursor()
        moved_claims = move_athlete_claims(plain, merged_into, user)
        plain.close()
        if claims_out is not None:
            claims_out.extend(moved_claims)
        for s, others in by_survivor.items():
            cur.execute(f"UPDATE leads SET client_id = %s WHERE client_id IN ({ph(others)})", (s,))
            cur.execute(f"UPDATE results SET client_id = %s WHERE client_id IN ({ph(others)})", (s,))
        merged = sorted(merged_into)
        for chunk in (merged[i:i + 1000] for i in range(0, len(merged), 1000)):
            cur.execute(f"DELETE FROM clients WHERE id IN ({ph(chunk)})")
        # два шага, чтобы не упереться в uk_client при взаимных переименованиях
        ids = sorted(final)
        for chunk in (ids[i:i + 1000] for i in range(0, len(ids), 1000)):
            cur.execute(f"UPDATE clients SET surname = CONCAT('~', id) WHERE id IN ({ph(chunk)})")
        for i, (s, n, bd) in final.items():
            cur.execute("UPDATE clients SET surname = %s, name = %s, birthday = %s WHERE id = %s", (s, n, bd, i))
            cur.execute("UPDATE leads SET surname = %s, name = %s, birthday = %s WHERE client_id = %s", (s, n, bd, i))
            cur.execute("UPDATE results SET surname = %s, name = %s, birthday = %s WHERE client_id = %s", (s, n, bd, i))
        # trg_leads_after_update переписывает phone/email карточки данными каждой
        # обновлённой заявки — возвращаем: переименованным — как было, склеенным —
        # из самой свежей заявки с непустым значением (как при вставке заявки)
        before = {c["id"]: c for c in snap.get("clients", [])}
        for i in ids:
            if i in by_survivor:
                cur.execute("""
                    UPDATE clients c SET
                      c.phone = COALESCE((SELECT l.phone FROM leads l WHERE l.client_id = c.id AND l.phone <> ''
                                          ORDER BY l.created_at DESC, l.id DESC LIMIT 1), c.phone),
                      c.email = COALESCE((SELECT l.email FROM leads l WHERE l.client_id = c.id AND l.email <> ''
                                          ORDER BY l.created_at DESC, l.id DESC LIMIT 1), c.email)
                    WHERE c.id = %s""", (i,))
            elif i in before:
                cur.execute("UPDATE clients SET phone = %s, email = %s WHERE id = %s",
                            (before[i]["phone"], before[i]["email"], i))
        for chunk in (ids[i:i + 1000] for i in range(0, len(ids), 1000)):
            recompute_aggregates(cur, chunk)
        # заявки склеенных карточек на одну дистанцию — теперь одна основная, остальные дубли
        recompute_duplicates(cur, ids)
        if drop_leads:
            cur.execute(f"DELETE FROM leads WHERE client_id IN ({ph(drop_leads)})")
            cur.execute(f"""DELETE c FROM clients c WHERE c.id IN ({ph(drop_leads)})
                            AND NOT EXISTS (SELECT 1 FROM leads l WHERE l.client_id = c.id)
                            AND NOT EXISTS (SELECT 1 FROM results r WHERE r.client_id = c.id)""")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return len(snap.get("leads", [])), len(snap.get("results", []))


def recompute_aggregates(cur, ids):
    """Счётчики карточки — из фактических заявок и результатов."""
    ph = ",".join(str(int(i)) for i in ids)
    cur.execute(f"""
        UPDATE clients c
        LEFT JOIN (SELECT client_id, COUNT(*) n, COALESCE(SUM(amount), 0) s, MAX(id) mx,
                          MIN(created_at) mn, MAX(created_at) md
                   FROM leads WHERE client_id IN ({ph}) GROUP BY client_id) l ON l.client_id = c.id
        LEFT JOIN (SELECT client_id, MAX(id) r FROM results WHERE client_id IN ({ph}) GROUP BY client_id) r
               ON r.client_id = c.id
        SET c.count_leads = COALESCE(l.n, 0), c.total_amount = COALESCE(l.s, 0), c.last_lead_id = l.mx,
            c.first_lead_date = l.mn, c.last_lead_date = l.md, c.last_result_id = r.r
        WHERE c.id IN ({ph})""")
    cur.execute(f"""
        UPDATE clients c
        JOIN leads l ON l.id = (SELECT x.id FROM leads x WHERE x.client_id = c.id ORDER BY x.created_at, x.id LIMIT 1)
        SET c.first_event_id = l.event_id, c.first_event_name = l.event_name
        WHERE c.id IN ({ph})""")
