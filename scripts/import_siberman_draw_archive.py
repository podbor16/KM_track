"""Import verified historical draw results from a private JSON export.

The input is an array of objects with year, source_group, position,
name and payment_outcome. Run migration 021 before this command.
"""

import argparse
import json
from collections import Counter
from pathlib import Path

from src.siberman.db import get_siberman_connection

EXPECTED_COUNTS = {2025: 138, 2026: 252, 2027: 228}
GROUPS = {
    2025: {"wild_card", "round_1", "round_2", "round_3", "round_4"},
    2026: {"men", "women", "relay"},
    2027: {"men", "women", "relay"},
}
OUTCOMES = {"paid", "unpaid", "no_offer"}


def import_rows(conn, rows):
    counts = Counter()
    keys = set()
    for row in rows:
        year = int(row["year"])
        group = row["source_group"]
        position = int(row["position"])
        name = row["name"].strip()
        outcome = row["payment_outcome"]
        key = (year, group, position)
        if (year not in GROUPS or group not in GROUPS[year] or position < 1
                or not name or outcome not in OUTCOMES or key in keys):
            raise ValueError(f"Недопустимая или повторная строка {key}")
        keys.add(key)
        counts[year] += 1
    if counts != EXPECTED_COUNTS:
        raise ValueError(f"Неполный архив: {dict(counts)}")

    conn.start_transaction()
    try:
        with conn.cursor(dictionary=True, buffered=True) as cur:
            cur.execute(
                "SELECT draw_year,source_group,position,participant_name,outcome "
                "FROM siberman_draw_archive_results FOR UPDATE"
            )
            existing = {
                (r["draw_year"], r["source_group"], r["position"]): r
                for r in cur.fetchall()
            }
            for row in rows:
                key = (int(row["year"]), row["source_group"], int(row["position"]))
                prior = existing.get(key)
                if prior:
                    if (prior["participant_name"] != row["name"].strip()
                            or prior["outcome"] != row["payment_outcome"]):
                        raise ValueError(f"Архивная строка изменилась: {key}")
                    continue
                cur.execute(
                    "INSERT INTO siberman_draw_archive_results "
                    "(draw_year,source_group,position,participant_name,outcome) "
                    "VALUES (%s,%s,%s,%s,%s)",
                    (*key, row["name"].strip(), row["payment_outcome"]),
                )
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    return counts


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    source = parser.parse_args().source
    with source.open(encoding="utf-8") as handle:
        archive = json.load(handle)
    connection = get_siberman_connection()
    if connection is None:
        raise SystemExit("База Siberman недоступна")
    try:
        print(dict(import_rows(connection, archive)))
    finally:
        connection.close()
