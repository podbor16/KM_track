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


def _lap_ranks_from_rows(rows: list[dict]) -> dict[tuple[int, str, int], dict]:
    """Место и отставание от лидера на КАЖДОМ (этап, круг) — среди тех, кто
    уже дошёл ровно до этого круга (не экстраполяция). Отдельно абсолютное и
    по полу — тот же принцип, что колонки "Место (абсолют)"/"Место (пол)" в
    карточке участника Siberman.

    rows: [{"participant_id", "stage", "lap_number", "cumulative_s", "gender"}, ...]
    Возвращает {(participant_id, stage, lap_number): {"rank_abs","gap_abs","rank_gender","gap_gender"}}
    """
    groups: dict[tuple[str, int], list[dict]] = {}
    for row in rows:
        groups.setdefault((row["stage"], row["lap_number"]), []).append(row)

    def _assign(items: list[dict]) -> dict[int, tuple[int, int]]:
        items = sorted(items, key=lambda r: r["cumulative_s"])
        if not items:
            return {}
        leader_s = items[0]["cumulative_s"]
        return {r["participant_id"]: (i + 1, r["cumulative_s"] - leader_s) for i, r in enumerate(items)}

    result: dict[tuple[int, str, int], dict] = {}
    for (stage, lap_number), items in groups.items():
        for pid, (rank_abs, gap_abs) in _assign(items).items():
            result[(pid, stage, lap_number)] = {
                "rank_abs": rank_abs, "gap_abs": gap_abs,
                "rank_gender": None, "gap_gender": None,
            }
        for gender in ("M", "F"):
            g_items = [r for r in items if r["gender"] == gender]
            for pid, (rank_g, gap_g) in _assign(g_items).items():
                result[(pid, stage, lap_number)]["rank_gender"] = rank_g
                result[(pid, stage, lap_number)]["gap_gender"] = gap_g
    return result


def _build_stage_laps(
    stage_code: str, lap_rows: list[dict], stage_start_s: Optional[int],
    ranks: dict[tuple[int, str, int], dict], participant_id: int,
) -> list[dict]:
    """Круги одного этапа участника: сплит (от предыдущего круга/старта
    этапа), скорость круга, место+отставание (абсолют/пол) на этом круге."""
    laps = []
    prev_cum = stage_start_s
    for lr in lap_rows:
        cum = lr["cumulative_s"]
        split = (cum - prev_cum) if prev_cum is not None else None
        speed_kmh = round(LAP_KM[stage_code] / (split / 3600.0), 2) if split and split > 0 else None
        r = ranks.get((participant_id, stage_code, lr["lap_number"]), {})
        laps.append({
            "lap_number": lr["lap_number"],
            "cumulative_s": cum,
            "split_s": split,
            "speed_kmh": speed_kmh,
            "rank_abs": r.get("rank_abs"),
            "gap_abs": r.get("gap_abs"),
            "rank_gender": r.get("rank_gender"),
            "gap_gender": r.get("gap_gender"),
        })
        prev_cum = cum
    return laps


def get_participant(event_id: int, start_number: int) -> Optional[dict]:
    """Данные для карточки участника: этапы + круги внутри каждого этапа
    (сплиты, места, отставания), общее место (абсолют/пол) — переиспользует
    get_standings(), не дублирует сортировку/прогресс-логику."""
    conn = get_duathlon_connection()
    if not conn:
        return None
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT id, start_number, surname, name, gender, status, run1_s, bike_s, run2_s "
            "FROM participants WHERE event_id=%s AND start_number=%s",
            (event_id, start_number),
        )
        row = cursor.fetchone()
        if not row:
            return None

        run1_time, bike_time, run2_time = _stage_times(row["run1_s"], row["bike_s"], row["run2_s"])
        current_stage, current_stage_start_s = _current_stage(row["run1_s"], row["bike_s"], row["run2_s"])

        cursor.execute(
            "SELECT stage, lap_number, cumulative_s FROM checkpoints "
            "WHERE participant_id=%s ORDER BY stage, lap_number",
            (row["id"],),
        )
        by_stage: dict[str, list] = {}
        for lr in cursor.fetchall():
            by_stage.setdefault(lr["stage"], []).append(lr)

        cursor.execute("""
            SELECT c.participant_id, c.stage, c.lap_number, c.cumulative_s, p.gender
            FROM checkpoints c JOIN participants p ON p.id = c.participant_id
            WHERE p.event_id = %s
        """, (event_id,))
        ranks = _lap_ranks_from_rows(cursor.fetchall())

        lap_number, lap_cumulative_s = None, None
        current_laps = by_stage.get(current_stage, [])
        if current_laps:
            lap_number, lap_cumulative_s = current_laps[-1]["lap_number"], current_laps[-1]["cumulative_s"]
        forecast_s = None
        if current_stage != "finished" and row["status"] not in ("dnf", "dsq"):
            forecast_s = _forecast_stage_finish(current_stage, lap_number, lap_cumulative_s, current_stage_start_s)

        stage_starts = {"run1": 0, "bike": row["run1_s"], "run2": row["bike_s"]}
        stages_out = {
            stage_code: {
                "distance_km": STAGE_KM[stage_code],
                "lap_km": LAP_KM[stage_code],
                "lap_count": LAP_COUNT[stage_code],
                "laps": _build_stage_laps(
                    stage_code, by_stage.get(stage_code, []),
                    stage_starts[stage_code], ranks, row["id"],
                ),
            }
            for stage_code in ("run1", "bike", "run2")
        }

        abs_standings = get_standings(event_id)
        gender_standings = get_standings(event_id, row["gender"])
        rank_abs = next((s["rank"] for s in abs_standings if s["id"] == row["id"]), None)
        rank_gender = next((s["rank"] for s in gender_standings if s["id"] == row["id"]), None)

        return {
            "id": row["id"],
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
            "rank_abs": rank_abs,
            "rank_gender": rank_gender,
            "stages": stages_out,
        }
    finally:
        cursor.close()
        conn.close()


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
