from typing import Optional
from src.duathlon222.db import get_duathlon_connection


def _stage_times(run1_s, bike_s, run2_s):
    """Время каждого этапа отдельно — вычитание соседних кумулятивных отметок
    от общего массового старта. None — этап ещё не пройден."""
    run1_time = run1_s
    bike_time = bike_s - run1_s if (bike_s is not None and run1_s is not None) else None
    run2_time = run2_s - bike_s if (run2_s is not None and bike_s is not None) else None
    return run1_time, bike_time, run2_time


def get_standings(event_id: int, gender: Optional[str] = None) -> list[dict]:
    """Таблица результатов: по прогрессу (сколько этапов пройдено), затем по
    времени внутри той же стадии прогресса. DNF/DSQ — всегда внизу, независимо
    от того, насколько быстрым было их частичное время (rawStatus, не выводить
    из наличия времени на этапе)."""
    conn = get_duathlon_connection()
    if not conn:
        return []
    try:
        cursor = conn.cursor(dictionary=True)
        gender_filter = "AND gender = %s" if gender else ""
        params = [event_id, gender] if gender else [event_id]
        cursor.execute(f"""
            SELECT id, start_number, surname, name, gender, status, run1_s, bike_s, run2_s,
                   (status IN ('dnf','dsq')) AS is_out,
                   CASE WHEN run2_s IS NOT NULL THEN 3
                        WHEN bike_s IS NOT NULL THEN 2
                        WHEN run1_s IS NOT NULL THEN 1
                        ELSE 0 END AS progress,
                   COALESCE(run2_s, bike_s, run1_s, 999999999) AS sort_time
            FROM participants
            WHERE event_id = %s {gender_filter}
            ORDER BY is_out ASC, progress DESC, sort_time ASC, start_number ASC
        """, params)
        rows = cursor.fetchall()
        result = []
        for i, row in enumerate(rows):
            run1_time, bike_time, run2_time = _stage_times(row["run1_s"], row["bike_s"], row["run2_s"])
            result.append({
                "id": row["id"],
                "rank": i + 1,
                "start_number": row["start_number"],
                "surname": row["surname"],
                "name": row["name"],
                "gender": row["gender"],
                "status": row["status"],
                "run1_s": run1_time,
                "bike_s": bike_time,
                "run2_s": run2_time,
                "total_s": row["run2_s"],
            })
        return result
    finally:
        cursor.close()
        conn.close()
