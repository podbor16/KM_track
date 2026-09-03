from typing import Optional
from src.duathlon222.db import get_duathlon_connection

# Дистанции и круги этапов — фиксированы для этой гонки, см. config/events/duathlon_222.yaml
STAGE_KM = {"run1": 10.0, "bike": 170.0, "run2": 42.0}
LAP_KM = {"run1": 2.5, "bike": 4.04, "run2": 3.5}
LAP_COUNT = {"run1": 4, "bike": 42, "run2": 12}


def _stage_times(run1_s, t1_s, bike_s, t2_s, run2_s):
    """ЧИСТОЕ время каждого этапа — вычитание соседних кумулятивных отметок
    МИНУС время в транзитной зоне между ними (Т1/Т2 считаются в общее время
    гонки, но не в время самого этапа). Если длительность транзита ещё
    неизвестна (t1_s/t2_s пока None — поля Copernico не подтверждены/не
    настали) — считаем 0, т.е. отдаём сырую разницу как временный фоллбэк, не
    пустую ячейку; как только появятся реальные Т1/Т2, число само уточнится."""
    run1_time = run1_s
    bike_time = bike_s - run1_s - (t1_s or 0) if (bike_s is not None and run1_s is not None) else None
    run2_time = run2_s - bike_s - (t2_s or 0) if (run2_s is not None and bike_s is not None) else None
    return run1_time, bike_time, run2_time


def _speed_kmh(stage_code: str, stage_time_s) -> Optional[float]:
    if not stage_time_s or stage_time_s <= 0:
        return None
    return round(STAGE_KM[stage_code] / (stage_time_s / 3600.0), 2)


def _current_stage(run1_s, t1_s, bike_s, t2_s, run2_s):
    """Какой этап сейчас в процессе (или завершён) + с какой кумулятивной
    отметки (сек от общего старта) он начался — для тикающих часов и
    прогноза на фронтенде. Старт следующего этапа = финиш предыдущего +
    транзит (Т1/Т2), а не сразу финиш предыдущего — иначе прогноз/таймер
    включали бы транзитную зону как будто участник уже крутит педали.
    run1 — дефолт и для «ещё не стартовал»: отдельного сигнала старта
    Copernico не даёт, отличить не от чего."""
    if run2_s is not None:
        return "finished", None
    if bike_s is not None:
        return "run2", bike_s + (t2_s or 0)
    if run1_s is not None:
        return "bike", run1_s + (t1_s or 0)
    return "run1", 0


_STAGE_ORDER = ("run1", "bike", "run2")


def _distance_covered_km(current_stage: str, current_stage_lap) -> float:
    """Суммарная дистанция, пройденная участником по ВСЕЙ гонке (км) — общий
    критерий живого места: кто прошёл больше километров, тот выше, даже если
    оба ещё внутри одного и того же незавершённого этапа (напр. один прошёл
    2 круга бег-1, другой — 3, оба ещё не финишировали этап целиком)."""
    if current_stage == "finished":
        return sum(STAGE_KM.values())
    completed_km = 0.0
    for stage_code in _STAGE_ORDER:
        if stage_code == current_stage:
            break
        completed_km += STAGE_KM[stage_code]
    return completed_km + (current_stage_lap or 0) * LAP_KM[current_stage]


def _display_status(raw_status: str, distance_km: float) -> str:
    """rawStatus (dnf/dsq/finished) — как есть с Copernico, определяет
    сортировку/дименг, не подменяется. Для промежуточного 'active' (Copernico
    для этой гонки не различает "ещё не стартовал"/"на дистанции" — оба
    приходят как 'notstarted'/'active') статус ВЫВОДИТСЯ из факта реального
    прогресса (пройдено >0 км), а не берётся из БД буквально — тот же принцип,
    что rawStatus vs slice-status в Siberman."""
    if raw_status in ("dnf", "dsq", "finished"):
        return raw_status
    return "active" if distance_km > 0 else "notstarted"


def _forecast_stage_finish(stage: str, last_lap_number, last_lap_cumulative_s, stage_start_s) -> Optional[int]:
    """Прогноз момента финиша ТЕКУЩЕГО (незавершённого) этапа — экстраполяция
    по средней скорости уже пройденных кругов ЭТОГО этапа, на ЧИСТЫХ данных
    (stage_start_s уже учитывает Т1/Т2 — см. _current_stage, транзит не
    попадает в темп экстраполяции). Тот же принцип, что forecastTime() в
    Siberman: elapsed * target/пройдено. Возвращает кумулятивные секунды от
    общего старта гонки, или None, если данных о кругах ещё нет (первый круг
    ещё не пройден)."""
    if last_lap_number is None or last_lap_cumulative_s is None or not last_lap_number:
        return None
    dist_so_far_km = last_lap_number * LAP_KM[stage]
    elapsed_in_stage_s = last_lap_cumulative_s - stage_start_s
    if dist_so_far_km <= 0 or elapsed_in_stage_s <= 0:
        return None
    forecast_in_stage_s = elapsed_in_stage_s * (STAGE_KM[stage] / dist_so_far_km)
    return round(stage_start_s + forecast_in_stage_s)


def _forecast_race_finish(current_stage: str, forecast_stage_finish_s: Optional[int]) -> Optional[int]:
    """Прогноз финиша ВСЕЙ ГОНКИ — появляется только на бег-2 (последний
    этап): "префикс" (бег-1 + Т1 + вело + Т2) уже целиком внутри
    stage_start_s этапа бег-2, поэтому прогноз финиша бег-2 И ЕСТЬ прогноз
    финиша гонки — считать заново нечего. На run1/bike нарочно не считаем
    (по решению пользователя, аналогия с Siberman) — предсказывать финиш всей
    гонки по темпу этапа, который не является последним, слишком спекулятивно
    (не учитывает будущий темп ещё не начатых дисциплин)."""
    if current_stage != "run2":
        return None
    return forecast_stage_finish_s


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
            "SELECT id, start_number, surname, name, gender, status, "
            "run1_s, t1_s, bike_s, t2_s, run2_s "
            "FROM participants WHERE event_id=%s AND start_number=%s",
            (event_id, start_number),
        )
        row = cursor.fetchone()
        if not row:
            return None

        run1_time, bike_time, run2_time = _stage_times(
            row["run1_s"], row["t1_s"], row["bike_s"], row["t2_s"], row["run2_s"]
        )
        current_stage, current_stage_start_s = _current_stage(
            row["run1_s"], row["t1_s"], row["bike_s"], row["t2_s"], row["run2_s"]
        )

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
        distance_km = _distance_covered_km(current_stage, lap_number)
        is_out = row["status"] in ("dnf", "dsq")
        forecast_s = None
        if current_stage != "finished" and not is_out:
            forecast_s = _forecast_stage_finish(current_stage, lap_number, lap_cumulative_s, current_stage_start_s)
        forecast_race_s = _forecast_race_finish(current_stage, forecast_s)

        # Старт этапа = финиш предыдущего + транзит (не сразу финиш
        # предыдущего) — иначе сплит 1-го круга включал бы Т1/Т2.
        bike_start = (row["run1_s"] + (row["t1_s"] or 0)) if row["run1_s"] is not None else None
        run2_start = (row["bike_s"] + (row["t2_s"] or 0)) if row["bike_s"] is not None else None
        stage_starts = {"run1": 0, "bike": bike_start, "run2": run2_start}
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
            "status": _display_status(row["status"], distance_km),
            "run1_s": run1_time,
            "t1_s": row["t1_s"],
            "bike_s": bike_time,
            "t2_s": row["t2_s"],
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
            "forecast_race_finish_s": forecast_race_s,
            "rank_abs": rank_abs,
            "rank_gender": rank_gender,
            "stages": stages_out,
        }
    finally:
        cursor.close()
        conn.close()


def _rank_standings_rows(rows: list[dict]) -> list[dict]:
    """Сортировка + место: живой критерий "кто прошёл больше км" (не только
    завершённые этапы целиком — круг внутри незавершённого этапа тоже
    считается), при равной дистанции — кто раньше её достиг. DNF/DSQ — всегда
    в самом низу, независимо от того, как далеко они продвинулись до схода
    (rawStatus). Место НЕ проставляется («—»), пока нет ни одной пройденной
    отметки — 0 км это ещё не участие в зачёте, а "не стартовал".

    rows: список словарей с ключами "_is_out", "_distance_km", "_elapsed_s",
    "start_number" — остальные поля произвольны и просто переносятся."""
    ordered = sorted(
        rows,
        key=lambda r: (r["_is_out"], -r["_distance_km"], r["_elapsed_s"], r["start_number"]),
    )
    rank_counter = 0
    for row in ordered:
        if not row["_is_out"] and row["_distance_km"] > 0:
            rank_counter += 1
            row["rank"] = rank_counter
        else:
            row["rank"] = None
    return ordered


def get_standings(event_id: int, gender: Optional[str] = None) -> list[dict]:
    """Таблица результатов: живое место по факту пройденной дистанции (не
    только по завершённым этапам целиком — см. _rank_standings_rows), статус
    'notstarted'/'active' выводится из наличия прогресса (Copernico для этой
    гонки не различает их отдельным значением)."""
    conn = get_duathlon_connection()
    if not conn:
        return []
    try:
        cursor = conn.cursor(dictionary=True)
        gender_filter = "AND gender = %s" if gender else ""
        params = [event_id, gender] if gender else [event_id]
        cursor.execute(f"""
            SELECT id, start_number, surname, name, gender, status,
                   run1_s, t1_s, bike_s, t2_s, run2_s
            FROM participants
            WHERE event_id = %s {gender_filter}
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

        enriched = []
        for row in rows:
            run1_time, bike_time, run2_time = _stage_times(
                row["run1_s"], row["t1_s"], row["bike_s"], row["t2_s"], row["run2_s"]
            )
            current_stage, current_stage_start_s = _current_stage(
                row["run1_s"], row["t1_s"], row["bike_s"], row["t2_s"], row["run2_s"]
            )
            lap_number, lap_cumulative_s = last_lap.get((row["id"], current_stage), (None, None))
            distance_km = _distance_covered_km(current_stage, lap_number)
            is_out = row["status"] in ("dnf", "dsq")
            forecast_s = None
            if current_stage != "finished" and not is_out:
                forecast_s = _forecast_stage_finish(
                    current_stage, lap_number, lap_cumulative_s, current_stage_start_s
                )
            forecast_race_s = _forecast_race_finish(current_stage, forecast_s)
            enriched.append({
                "id": row["id"],
                "start_number": row["start_number"],
                "surname": row["surname"],
                "name": row["name"],
                "gender": row["gender"],
                "status": _display_status(row["status"], distance_km),
                "run1_s": run1_time,
                "t1_s": row["t1_s"],
                "bike_s": bike_time,
                "t2_s": row["t2_s"],
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
                "forecast_race_finish_s": forecast_race_s,
                "_is_out": is_out,
                "_distance_km": distance_km,
                "_elapsed_s": lap_cumulative_s if lap_cumulative_s is not None else (current_stage_start_s or 0),
            })

        result = _rank_standings_rows(enriched)
        for row in result:
            del row["_is_out"], row["_distance_km"], row["_elapsed_s"]
        return result
    finally:
        cursor.close()
        conn.close()
