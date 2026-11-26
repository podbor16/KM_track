"""Ручные назначения на 7 км «Снежной семёрки» 2026."""

import json

from src.analytics.bibs import SNOW7_2026, main_lead_per_person
from src.analytics.db_results import invalidate_start_list_cache, recompute_duplicates

DISTANCE = "7 км"
# Время по Красноярску и возрастные диапазоны стартовых волн из таблицы Tilda.
WAVES = (
    ("11:00:00", "Ж 70+, М 75+"),
    ("11:06:02", "Ж 65–69, М 70–74"),
    ("11:06:32", "Ж 60–64"),
    ("11:07:45", "Ж 55–59, М 65–69"),
    ("11:09:50", "Ж 50–54, М 60–64"),
    ("11:10:28", "Ж 45–49"),
    ("11:11:30", "Ж 40–44"),
    ("11:12:17", "Ж 12–39"),
    ("11:12:40", "М 55–59"),
    ("11:14:07", "М 50–54"),
    ("11:14:39", "М 45–49"),
    ("11:15:20", "М 40–44"),
    ("11:15:45", "М 12–39"),
)


class AssignmentConflict(ValueError):
    """Назначение конфликтует с текущим стартовым списком."""


def _load_entries(cur, *, for_update=False):
    lock = " FOR UPDATE" if for_update else ""
    cur.execute(
        """SELECT id, client_id, event_id, event_distance, dup_main, created_at,
                  start_number, start_wave, surname, name, sex, YEAR(birthday) AS birth_year
           FROM leads WHERE event_name = %s AND event_year = %s AND refund = 0
           ORDER BY id""" + lock,
        SNOW7_2026,
    )
    return cur.fetchall()


def _main_7km(entries):
    return [row for row in main_lead_per_person(entries) if row["event_distance"] == DISTANCE]


def overview(conn):
    cur = conn.cursor(dictionary=True)
    try:
        rows = _main_7km(_load_entries(cur))
    finally:
        cur.close()
    fields = ("id", "surname", "name", "sex", "birth_year", "start_number", "start_wave")
    return {
        "waves": [{"id": i, "time": time, "groups": groups}
                  for i, (time, groups) in enumerate(WAVES, start=1)],
        "entries": [{field: row[field] for field in fields}
                    for row in sorted(rows, key=lambda row: (row["surname"] or "", row["name"] or "", row["id"]))],
    }


def assign(conn, lead_id, start_number, start_wave, user):
    cur = conn.cursor(dictionary=True)
    try:
        conn.start_transaction()
        entries = _load_entries(cur, for_update=True)
        row = next((item for item in _main_7km(entries) if item["id"] == lead_id), None)
        if row is None:
            raise AssignmentConflict("Назначение доступно для действующей основной заявки на 7 км.")
        previous = {"start_number": row["start_number"] or None, "start_wave": row["start_wave"]}
        assignment = {"start_number": start_number, "start_wave": start_wave}
        if start_number != previous["start_number"] and start_number is not None and any(
            item["start_number"] == start_number and item["id"] != lead_id for item in entries
        ):
            raise AssignmentConflict(f"Номер {start_number} уже назначен на этом мероприятии.")
        if previous != assignment:
            client_id = row["client_id"]
            cur.execute("SELECT phone, email FROM clients WHERE id = %s FOR UPDATE", (client_id,))
            contacts = cur.fetchone()
            cur.execute(
                "UPDATE leads SET start_number = %s, start_wave = %s WHERE id = %s",
                (start_number, start_wave, lead_id),
            )
            if start_number != previous["start_number"]:
                recompute_duplicates(cur, [client_id])
            # Триггер обновления заявки может перезаписать контакты карточки.
            if contacts:
                cur.execute(
                    "UPDATE clients SET phone = %s, email = %s WHERE id = %s",
                    (contacts["phone"], contacts["email"], client_id),
                )
            cur.execute(
                "INSERT INTO dq_actions (action, finding_key, details, done_by) VALUES (%s, %s, %s, %s)",
                ("snow7_start", f"lead:{lead_id}", json.dumps({"before": previous, "after": assignment}), user),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
    if start_number != previous["start_number"]:
        invalidate_start_list_cache()
    return assignment
