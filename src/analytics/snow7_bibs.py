"""Ручное назначение стартовых номеров на 7 км «Снежной семёрки»."""

import json

from src.analytics.bibs import SNOW7_EVENT, load_leads, main_lead_per_person
from src.analytics.db_results import invalidate_start_list_cache, recompute_duplicates

DISTANCE = "7 км"


class AssignmentConflict(ValueError):
    """Назначение конфликтует с текущим стартовым списком."""


def _main_7km(entries):
    return [row for row in main_lead_per_person(entries) if row["event_distance"] == DISTANCE]


def overview(conn, event_year):
    rows = _main_7km(load_leads(conn, SNOW7_EVENT, event_year))
    entries = []
    for row in sorted(rows, key=lambda row: (row["surname"] or "", row["name"] or "", row["id"])):
        entries.append({
            "id": row["id"],
            "surname": row["surname"],
            "name": row["name"],
            "sex": row["sex"],
            "birth_year": row["birthday"].year if row["birthday"] else None,
            "start_number": row["start_number"],
        })
    return {"entries": entries}


def assign(conn, event_year, lead_id, start_number, user):
    cur = conn.cursor(dictionary=True)
    try:
        conn.start_transaction()
        entries = load_leads(conn, SNOW7_EVENT, event_year, for_update=True)
        row = next((item for item in _main_7km(entries) if item["id"] == lead_id), None)
        if row is None:
            raise AssignmentConflict("Назначение доступно для действующей основной заявки на 7 км.")
        previous_number = row["start_number"] or None
        if start_number != previous_number:
            if start_number is not None and any(item["start_number"] == start_number for item in entries):
                raise AssignmentConflict(f"Номер {start_number} уже назначен на этом мероприятии.")
            client_id = row["client_id"]
            cur.execute("SELECT phone, email FROM clients WHERE id = %s FOR UPDATE", (client_id,))
            contacts = cur.fetchone()
            cur.execute("UPDATE leads SET start_number = %s WHERE id = %s", (start_number, lead_id))
            recompute_duplicates(cur, [client_id])
            # Сохраняем контакты карточки при обновлении заявки через триггер.
            if contacts:
                cur.execute(
                    "UPDATE clients SET phone = %s, email = %s WHERE id = %s",
                    (contacts["phone"], contacts["email"], client_id),
                )
            cur.execute(
                "INSERT INTO dq_actions (action, finding_key, details, done_by) VALUES (%s, %s, %s, %s)",
                ("assign_bib", f"lead:{lead_id}", json.dumps({"before": previous_number, "after": start_number}), user),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
    if start_number != previous_number:
        invalidate_start_list_cache()
    return {"start_number": start_number}
