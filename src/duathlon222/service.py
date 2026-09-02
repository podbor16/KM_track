from typing import Optional
from src.duathlon222.db import get_duathlon_connection

# Дистанции и круги этапов — фиксированы для этой гонки, см. config/events/duathlon_222.yaml
STAGE_KM = {"run1": 10.0, "bike": 170.0, "run2": 42.0}
LAP_KM = {"run1": 2.5, "bike": 4.04, "run2": 3.5}
LAP_COUNT = {"run1": 4, "bike": 42, "run2": 12}


def _stage_times(run1_s, bike_s, run2_s):
    """Время каждого этапа отдельно — вычитание соседних кумулятивных отметок
    от общего массового старта. None — этап ещё не пройден."""
    run1_time = run1_s
    bike_time = bike_s - run1_s if (bike_s is not None and run1_s is not None) else None
    run2_time = run2_s - bike_s if (run2_s is not None and bike_s is not None) else None
    return run1_time, bike_time, run2_time


def _speed_kmh(stage_code: str, stage_time_s) -> Optional[float]:
    if not stage_time_s or stage_time_s <= 0:
        return None
    return round(STAGE_KM[stage_code] / (stage_time_s / 3600.0), 2)


def _current_stage(run1_s, bike_s, run2_s):
    """Какой этап сейчас в процессе (или завершён) + с какой кумулятивной
    отметки (сек от общего старта) он начался — для тикающих часов на
    фронтенде. run1 — дефолт и для «ещё не стартовал»: отдельного сигнала
    старта Copernico не даёт, отличить не от чего."""
    if run2_s is not None:
        return "finished", None
    if bike_s is not None:
        return "run2", bike_s
    if run1_s is not None:
        return "bike", run1_s
    return "run1", 0


def _forecast_stage_finish(stage: str, last_lap_number, last_lap_cumulative_s, stage_start_s) -> Optional[int]:
    """Прогноз момента финиша ТЕКУЩЕГО (незавершённого) этапа — экстраполяция
    по средней скорости уже пройденных кругов ЭТОГО этапа (тот же принцип,
    что forecastTime() в Siberman: elapsed * target/пройдено). Возвращает
    кумулятивные секунды от общего старта гонки, или None, если данных о
    кругах ещё нет (первый круг ещё не пройден)."""
    if last_lap_number is None or last_lap_cumulative_s is None or not last_lap_number:
        return None
    dist_so_far_km = last_lap_number * LAP_KM[stage]
    elapsed_in_stage_s = last_lap_cumulative_s - stage_start_s
    if dist_so_far_km <= 0 or elapsed_in_stage_s <= 0:
        return None
    forecast_in_stage_s = elapsed_in_stage_s * (STAGE_KM[stage] / dist_so_far_km)
    return round(stage_start_s + forecast_in_stage_s)


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

        # Последний пройденный круг каждого (участник, этап) — одним запросом
        # на всё событие, агрегируем в Python (объём данных мал: до ~100
        # участников x 58 кругов максимум за всю гонку).
        cursor.execute("""
            SELECT c.participant_id, c.stage, c.lap_number, c.cumulative_s
            FROM checkpoints c
            JOIN participants p ON p.id = c.participant_id
            WHERE p.event_id = %s
        """, (event_id,))
        last_lap: dict[tuple[int, str], tuple[int, int]] = {}
        for lap_row in cursor.fetchall():
            key = (lap_row["participant_id"], lap_row["stage"])
            if key not in last_lap or lap_row["lap_number"] > last_lap[key][0]:
                last_lap[key] = (lap_row["lap_number"], lap_row["cumulative_s"])

        result = []
        for i, row in enumerate(rows):
            run1_time, bike_time, run2_time = _stage_times(row["run1_s"], row["bike_s"], row["run2_s"])
            current_stage, current_stage_start_s = _current_stage(
                row["run1_s"], row["bike_s"], row["run2_s"]
            )
            lap_number, lap_cumulative_s = last_lap.get((row["id"], current_stage), (None, None))
            forecast_s = None
            if current_stage != "finished" and row["status"] not in ("dnf", "dsq"):
                forecast_s = _forecast_stage_finish(
                    current_stage, lap_number, lap_cumulative_s, current_stage_start_s
                )
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
                "run1_speed_kmh": _speed_kmh("run1", run1_time),
                "bike_speed_kmh": _speed_kmh("bike", bike_time),
                "run2_speed_kmh": _speed_kmh("run2", run2_time),
                "total_s": row["run2_s"],
                "current_stage": current_stage,
                "current_stage_start_s": current_stage_start_s,
                "current_stage_lap": lap_number,
                "current_stage_lap_total": LAP_COUNT.get(current_stage),
                "forecast_stage_finish_s": forecast_s,
            })
        return result
    finally:
        cursor.close()
        conn.close()
