from typing import Optional
from src.triatleta.db import get_tri_connection


def calculate_gap(
    participant_laps: int,
    participant_elapsed_ms: int,
    leader_laps: int,
    leader_elapsed_ms: int,
) -> str:
    """Отставание от лидера."""
    if participant_laps == leader_laps and participant_elapsed_ms == leader_elapsed_ms:
        return "—"
    if participant_laps < leader_laps:
        diff = leader_laps - participant_laps
        if diff == 1:
            return "−1 круг"
        elif 2 <= diff <= 4:
            return f"−{diff} круга"
        else:
            return f"−{diff} кругов"
    delta_ms = participant_elapsed_ms - leader_elapsed_ms
    total_sec = delta_ms // 1000
    h = total_sec // 3600
    m = (total_sec % 3600) // 60
    s = total_sec % 60
    return f"+{h:02d}:{m:02d}:{s:02d}"


def get_standings(event_id: int, category: Optional[str] = None) -> list[dict]:
    """Таблица результатов: больше кругов → меньше времени."""
    conn = get_tri_connection()
    if not conn:
        return []
    try:
        cursor = conn.cursor(dictionary=True)
        cat_filter = "AND p.category = %s" if category else ""
        params = [event_id, category] if category else [event_id]
        cursor.execute(f"""
            SELECT
                p.id,
                p.start_number,
                p.surname,
                p.name,
                p.gender,
                p.category,
                p.team_name,
                COUNT(l.id) AS laps_completed,
                ROUND(COUNT(l.id) * 4.040, 3) AS total_km,
                COALESCE(MAX(l.cumulative_ms), 0) AS elapsed_ms,
                CASE
                    WHEN MAX(l.cumulative_ms) > 0
                    THEN ROUND(COUNT(l.id) * 4.040 / (MAX(l.cumulative_ms) / 3600000.0), 2)
                    ELSE 0.0
                END AS avg_speed_kmh
            FROM participants p
            LEFT JOIN laps l ON l.participant_id = p.id
            WHERE p.event_id = %s {cat_filter}
            GROUP BY p.id
            ORDER BY laps_completed DESC, elapsed_ms ASC
        """, params)
        rows = cursor.fetchall()
        if not rows:
            return []
        leader = rows[0]
        result = []
        for i, row in enumerate(rows):
            row["rank"] = i + 1
            row["gap"] = calculate_gap(
                row["laps_completed"], row["elapsed_ms"],
                leader["laps_completed"], leader["elapsed_ms"],
            )
            row["elapsed_ms"] = int(row["elapsed_ms"])
            result.append(row)
        return result
    finally:
        cursor.close()
        conn.close()


def get_all_laps(event_id: int) -> list[dict]:
    """Все круги события для сплитов по часам."""
    conn = get_tri_connection()
    if not conn:
        return []
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT l.participant_id, l.lap_number, l.cumulative_ms, l.lap_ms,
                   p.surname, p.name, p.start_number
            FROM laps l
            JOIN participants p ON p.id = l.participant_id
            WHERE l.event_id = %s
            ORDER BY l.participant_id, l.lap_number
        """, (event_id,))
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()
