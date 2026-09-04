from typing import Optional
from src.duathlon222.db import get_duathlon_connection

# Дистанции этапов целиком — из stage_fields (финиш), не из кругов.
STAGE_KM = {"run1": 10.0, "bike": 170.0, "run2": 42.0}

# Шаг между соседними отметками (км) — уточнено живым fetch Copernico
# 2026-09-04 (реальные отметки трассы, не номинальные 2.5/4.04/3.5): Бег-1 и
# Бег-2 включают середины кругов (вдвое больше точек прогресса, по решению
# пользователя), поэтому их фактический шаг вдвое меньше "длины круга".
LAP_KM = {"run1": 1.25, "bike": 4.04, "run2": 1.757}
# Бег-2: 25 отметок, не 24 — первая (лап 1) отдельное реальное поле
# Copernico "times.official_20" (20 м от старта, короткий "пролог", ТА ЖЕ
# структура, что у Вело), найдено пользователем 2026-09-04; раньше это поле
# не читалось из Copernico вовсе, а следующая отметка ("1777") ошибочно
# считалась первой — см. STAGE_LAP_OFFSET ниже.
LAP_COUNT = {"run1": 8, "bike": 42, "run2": 25}

# Смещение отметок от чистого "n*LAP_KM" — сверено с точными именами полей
# Copernico (config/copernico/duathlon_222_2026.yaml:stage_lap_fields), не
# подогнано на глаз. Формула одна и та же для Вело/Бег-2: distance(n) =
# n*LAP_KM + OFFSET, где OFFSET = "реальная дистанция первой отметки" -
# LAP_KM (т.е. distance(1) даёт ровно эту первую отметку, а не полный шаг).
#   Вело: первая отметка (мачта) — 3.4 км, не полные 4.04 км.
#     OFFSET = 3.4-4.04. distance(42) = 169.04 (последняя реальная
#     отметка — "b169,04"; сам финиш вело, 170 км, отдельное поле
#     "b170-start_T2" — 0.96 км между последней отметкой и финишем это
#     не баг, так реально измерена трасса).
#   Бег-2: первая отметка — 20 м (0.02 км), "пролог" ещё короче велового.
#     OFFSET = 0.02-1.757. distance(25) = 42.188 (последняя реальная
#     отметка — "42188" метров; сам финиш бег-2 — отдельное поле
#     ":::finish:::", отдельно от списка кругов, как и везде).
#   Бег-1: отметки 1-7 точно "n*1.25", 8-я (последняя, "9,98 km") на 20 м
#     короче чистых 10 км — тем не менее финиш бег-1 отдельным полем
#     "10 km" (не "9,98"), подтверждено пользователем 2026-09-04 ДЛЯ
#     ЦЕЛЕЙ ОПРЕДЕЛЕНИЯ run1_s (stage_fields), не для формулы отметок —
#     здесь оставляем OFFSET=0 (даёт ровно 10.0 на n=8), т.к. отдельного
#     поля "8-й отметки" в сумме с финишем как у Вело/Бег-2 тут нет.
STAGE_LAP_OFFSET = {"run1": 0.0, "bike": 3.4 - 4.04, "run2": 0.02 - 1.757}

# Отметки, которые не ложатся на равномерную формулу "n*LAP_KM+OFFSET" вовсе
# (не смещение всей последовательности, а ЕДИНИЧНОЕ отклонение одной
# конкретной отметки) — сверено с точным именем поля Copernico. Сейчас
# единственный случай: последняя (8-я) отметка Бег-1 — реальное поле
# "9,98 km", а не ровно 10.0 (как дала бы формула n*1.25) — официальный
# финиш Бег-1 (10 км) при этом ОТДЕЛЬНОЕ поле stage_fields.run1, та же
# структура "финиш ≠ последняя отметка", что у Вело/Бег-2. Показывается
# пользователю как есть, 9.98 (округление до 2 знаков, не до 1 — иначе
# 9.98 слилось бы визуально с финишем 10.0, что и вызывало путаницу до
# 2026-09-04), поэтому в карточке участника у Бег-1 теперь тоже появляется
# отдельная строка "10.0/10.0 км · Финиш" (см. duathlon_participant.html),
# как у Вело/Бег-2.
IRREGULAR_LAP_KM: dict[tuple[str, int], float] = {("run1", 8): 9.98}


def _lap_distance_km(stage_code: str, lap_number: Optional[int]) -> float:
    """Кумулятивная дистанция (км) НА данной отметке этапа — не просто
    lap_number*LAP_KM: Вело стартует с более коротким "прологом" (см.
    STAGE_LAP_OFFSET), у Бег-1 последняя отметка — единичное отклонение (см.
    IRREGULAR_LAP_KM). 0.0, если отметка ещё не пройдена (lap_number=None)."""
    if not lap_number:
        return 0.0
    irregular = IRREGULAR_LAP_KM.get((stage_code, lap_number))
    if irregular is not None:
        return irregular
    return lap_number * LAP_KM[stage_code] + STAGE_LAP_OFFSET[stage_code]


def _lap_split_distance_km(stage_code: str, lap_number: int) -> float:
    """Дистанция ИМЕННО этой отметки (не кумулятивно от старта этапа) — для
    скорости/темпа сплита. Разница соседних кумулятивных дистанций — общая
    формула, корректно учитывает и "пролог" (первая отметка короче — сплит от
    старта этапа, т.е. от 0), и единичные отклонения (IRREGULAR_LAP_KM) любой
    отметки, не только первой."""
    if lap_number <= 1:
        return _lap_distance_km(stage_code, 1)
    return _lap_distance_km(stage_code, lap_number) - _lap_distance_km(stage_code, lap_number - 1)


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


def _speed_kmh_for_distance(distance_km: float, elapsed_s) -> Optional[float]:
    """Скорость км/ч для произвольной пройденной дистанции/времени — обобщение
    _speed_kmh() на частичный прогресс (не только завершённый этап целиком),
    нужно для _speed_kmh() ниже и для рангов внутри незавершённого этапа
    (get_stage_standings)."""
    if not elapsed_s or elapsed_s <= 0 or not distance_km:
        return None
    return round(distance_km / (elapsed_s / 3600.0), 2)


def _speed_kmh(stage_code: str, stage_time_s) -> Optional[float]:
    return _speed_kmh_for_distance(STAGE_KM[stage_code], stage_time_s)


_STAGE_ORDER = ("run1", "bike", "run2")
# Дистанция гонки, пройденная ДО начала этого этапа — для заголовка поста
# ("X из 222 км") и общей позиции.
_STAGE_KM_BEFORE = {"run1": 0.0, "bike": STAGE_KM["run1"], "run2": STAGE_KM["run1"] + STAGE_KM["bike"]}


def _stage_start_s(
    stage_code, run1_s, t1_s, bike_s, t2_s, bike_start_s=None, run2_start_s=None,
) -> Optional[int]:
    """Кумулятивная отметка (сек от общего старта), с которой НАЧАЛСЯ этот
    этап — финиш предыдущего + транзит (Т1/Т2), а не сразу финиш предыдущего,
    иначе сплит/темп/прогноз включали бы транзитную зону, будто участник уже
    на трассе следующего этапа. None, если предыдущий этап ещё не завершён
    (стартовая отметка этого этапа неизвестна).

    bike_start_s/run2_start_s — СЫРЫЕ поля Copernico (bike0/
    finish_T2-start_R2, см. миграцию 004), точный момент входа на этап;
    ПРЕДПОЧИТАЮТСЯ реконструкции run1_s+t1_s/bike_s+t2_s — та реконструкция
    теряет до 1-2с из-за раздельного округления run1_s и t1_s каждого до
    целых секунд (найдено пользователем 2026-09-04). Опциональны (None) —
    для обратной совместимости со строками, где эти колонки ещё не
    заполнены (например, тестовые участники, вписанные вручную SQL)."""
    if stage_code == "run1":
        return 0
    if stage_code == "bike":
        if bike_start_s is not None:
            return bike_start_s
        return (run1_s + (t1_s or 0)) if run1_s is not None else None
    if stage_code == "run2":
        if run2_start_s is not None:
            return run2_start_s
        return (bike_s + (t2_s or 0)) if bike_s is not None else None
    return None


def _current_stage(run1_s, t1_s, bike_s, t2_s, run2_s, bike_start_s=None, run2_start_s=None):
    """Какой этап сейчас в процессе (или завершён) + с какой кумулятивной
    отметки (сек от общего старта) он начался — для тикающих часов и
    прогноза на фронтенде. run1 — дефолт и для «ещё не стартовал»:
    отдельного сигнала старта Copernico не даёт, отличить не от чего."""
    if run2_s is not None:
        return "finished", None
    if bike_s is not None:
        return "run2", _stage_start_s("run2", run1_s, t1_s, bike_s, t2_s, bike_start_s, run2_start_s)
    if run1_s is not None:
        return "bike", _stage_start_s("bike", run1_s, t1_s, bike_s, t2_s, bike_start_s, run2_start_s)
    return "run1", 0


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
    return completed_km + _lap_distance_km(current_stage, current_stage_lap)


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
    dist_so_far_km = _lap_distance_km(stage, last_lap_number)
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
        speed_kmh = _speed_kmh_for_distance(_lap_split_distance_km(stage_code, lr["lap_number"]), split)
        r = ranks.get((participant_id, stage_code, lr["lap_number"]), {})
        laps.append({
            "lap_number": lr["lap_number"],
            "distance_km": round(_lap_distance_km(stage_code, lr["lap_number"]), 2),
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
            "run1_s, t1_s, bike_s, t2_s, run2_s, bike_start_s, run2_start_s "
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
            row["run1_s"], row["t1_s"], row["bike_s"], row["t2_s"], row["run2_s"],
            row["bike_start_s"], row["run2_start_s"],
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

        # "finished" — не настоящий этап в checkpoints (там только run1/
        # bike/run2) — для отметки ФИНИШИРОВАВШЕГО берём последний круг
        # реального последнего этапа (run2), чтобы "Отметка" по-прежнему
        # показывала "42/42 км", а не пустоту (по аналогии с Siberman —
        # там currentStage() у финишировавшего тоже указывает на последний
        # РЕАЛЬНЫЙ этап, не на псевдо-статус).
        mark_stage = "run2" if current_stage == "finished" else current_stage
        lap_number, lap_cumulative_s = None, None
        current_laps = by_stage.get(mark_stage, [])
        if current_laps:
            lap_number, lap_cumulative_s = current_laps[-1]["lap_number"], current_laps[-1]["cumulative_s"]
        distance_km = _distance_covered_km(current_stage, lap_number)
        # Дистанция ИМЕННО этапа отметки (не всей гонки, в отличие от
        # distance_km выше) — для отображения "Отметка N/M км". СЫРАЯ
        # (неокруглённая) версия — отдельно, для темпа/скорости ниже: округление
        # до 1 знака только для показа пользователю НЕ должно влиять на расчёт
        # (иначе, например, отметка "20 м" Бег-2 округляется до 0.0 км и делит
        # на ноль — найдено пользователем 2026-09-04).
        current_stage_distance_km_raw = _lap_distance_km(mark_stage, lap_number) if lap_number else None
        current_stage_distance_km = round(current_stage_distance_km_raw, 2) if lap_number else None
        # Чистое время ТЕКУЩЕГО этапа на последней отметке — ЗАФИКСИРОВАНО
        # (не тикает), нужно и для темпа/скорости ниже, и карточке участника
        # для прогноза ближайшей непройденной отметки (см. duathlon_
        # participant.html:lapTableHtml).
        current_stage_elapsed_s = (
            lap_cumulative_s - current_stage_start_s
            if lap_cumulative_s is not None and current_stage_start_s is not None else None
        )
        current_stage_speed_kmh = None
        if current_stage_distance_km_raw and current_stage_elapsed_s:
            current_stage_speed_kmh = _speed_kmh_for_distance(current_stage_distance_km_raw, current_stage_elapsed_s)
        is_out = row["status"] in ("dnf", "dsq")
        forecast_s = None
        if current_stage != "finished" and not is_out:
            forecast_s = _forecast_stage_finish(current_stage, lap_number, lap_cumulative_s, current_stage_start_s)
        forecast_race_s = _forecast_race_finish(current_stage, forecast_s)

        stage_starts = {
            stage_code: _stage_start_s(
                stage_code, row["run1_s"], row["t1_s"], row["bike_s"], row["t2_s"],
                row["bike_start_s"], row["run2_start_s"],
            )
            for stage_code in _STAGE_ORDER
        }
        stages_out = {
            stage_code: {
                "distance_km": STAGE_KM[stage_code],
                "lap_km": LAP_KM[stage_code],
                "lap_count": LAP_COUNT[stage_code],
                # ВСЕ возможные отметки этапа (1..lap_count) с их дистанцией
                # — независимо от того, дошёл ли до них участник. Карточка
                # показывает их ВСЕ сразу (не только уже пройденные), заполняя
                # постепенно — по аналогии с Siberman (там тот же цикл
                # "1..maxSeq" делает JS, здесь дистанция неравномерна из-за
                # STAGE_LAP_OFFSET у вело, поэтому считаем на бэкенде).
                "marks": [
                    {"lap_number": n, "distance_km": round(_lap_distance_km(stage_code, n), 2)}
                    for n in range(1, LAP_COUNT[stage_code] + 1)
                ],
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
            "current_stage_lap_total": LAP_COUNT.get(mark_stage),
            "current_stage_distance_km": current_stage_distance_km,
            "current_stage_elapsed_s": current_stage_elapsed_s,
            "current_stage_speed_kmh": current_stage_speed_kmh,
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


def _frontier_lap(lap_numbers: list[int]) -> Optional[int]:
    """Самый дальний круг, до которого дошёл хотя бы один участник пула —
    "текущая отметка" для автоматической генерации поста трансляции (тот же
    принцип, что "последняя пройденная отметка" в остальном приложении, но
    для целого ПУЛА, а не одного участника)."""
    return max(lap_numbers) if lap_numbers else None


# Виртуальная "отметка 0" (только Вело/Бег-2) — точный момент ВЫХОДА из
# транзитки (не круг из checkpoints, там её нет вовсе) — сырые поля
# Copernico напрямую (см. миграцию 004/_stage_start_s). Нужна для постов
# трансляции сразу после Т1/Т2, когда до первого настоящего круга ещё
# далеко (запрошено пользователем 2026-09-04).
_TRANSITION_START_COLUMN = {"bike": "bike_start_s", "run2": "run2_start_s"}


def get_available_marks(event_id: int, stage_code: str, gender: Optional[str] = None) -> list[dict]:
    """Список отметок этапа, которые уже кто-то прошёл (для выбора конкретной
    отметки в UI генератора постов — вместо всегда-последней "фронтир"-отметки).
    Возвращает [{"lap_number", "distance_km", "reached_count"}], по возрастанию —
    для Вело/Бег-2 первой (lap_number=0), если применимо, идёт виртуальная
    "отметка 0" (выход из транзитки, см. _TRANSITION_START_COLUMN)."""
    conn = get_duathlon_connection()
    if not conn:
        return []
    try:
        cursor = conn.cursor(dictionary=True)
        marks: list[dict] = []
        start_col = _TRANSITION_START_COLUMN.get(stage_code)
        if start_col:
            gender_filter = "AND gender=%s" if gender else ""
            params = [event_id] + ([gender] if gender else [])
            cursor.execute(
                f"SELECT COUNT(*) AS cnt FROM participants "
                f"WHERE event_id=%s AND {start_col} IS NOT NULL {gender_filter}",
                params,
            )
            reached_count = cursor.fetchone()["cnt"]
            if reached_count:
                marks.append({"lap_number": 0, "distance_km": 0.0, "reached_count": reached_count})

        gender_filter = "AND p.gender=%s" if gender else ""
        params = [event_id, stage_code] + ([gender] if gender else [])
        cursor.execute(f"""
            SELECT c.lap_number, COUNT(*) AS reached_count
            FROM checkpoints c JOIN participants p ON p.id = c.participant_id
            WHERE p.event_id=%s AND c.stage=%s {gender_filter}
            GROUP BY c.lap_number ORDER BY c.lap_number
        """, params)
        marks.extend(
            {
                "lap_number": row["lap_number"],
                "distance_km": round(_lap_distance_km(stage_code, row["lap_number"]), 2),
                "reached_count": row["reached_count"],
            }
            for row in cursor.fetchall()
        )
        return marks
    finally:
        cursor.close()
        conn.close()


def _stage_mark_zero_broadcast(stage_code: str, gender: Optional[str], participants) -> Optional[dict]:
    """Снимок для виртуальной "отметки 0" (выход из транзитки) — не круг из
    checkpoints (там её нет), а прямое чтение bike_start_s/run2_start_s (см.
    _TRANSITION_START_COLUMN/миграция 004). Чистое время этапа на этой точке
    у всех тривиально 0:00 (только что стартовали) — смысл несёт только
    race_elapsed_s (по часам гонки, кто раньше вышел из транзитки)."""
    start_col = _TRANSITION_START_COLUMN.get(stage_code)
    if not start_col:
        return None
    pool = [
        p for p in participants
        if (gender is None or p["gender"] == gender) and p[start_col] is not None
    ]
    if not pool:
        return None
    race_leader = min(p[start_col] for p in pool)
    pool.sort(key=lambda p: p[start_col])
    return {
        "stage": stage_code,
        "lap_mark": 0,
        "stage_km_at_mark": 0.0,
        "stage_total_km": STAGE_KM[stage_code],
        "overall_km": round(_STAGE_KM_BEFORE[stage_code], 1),
        "race_total_km": sum(STAGE_KM.values()),
        "entries": [
            {
                "surname": p["surname"], "name": p["name"],
                "elapsed_s": 0,
                "gap_s": 0,
                "race_elapsed_s": p[start_col],
                "race_gap_s": p[start_col] - race_leader,
                "speed_kmh": None,
            }
            for p in pool
        ],
    }


def get_stage_mark_broadcast(
    event_id: int, stage_code: str, gender: Optional[str] = None, lap_number: Optional[int] = None,
) -> Optional[dict]:
    """Снимок «кто где был на отметке» для поста трансляции (формат Siberman):
    показывает ВСЕХ, у кого есть ЗАПИСЬ именно на этой отметке (исторический
    сплит — не их текущий прогресс, который мог уйти дальше), отсортированных
    по времени восхождения к ней. Время/темп — ЧИСТЫЕ данные этапа (без Т1/Т2,
    stage_start уже их исключает). Если lap_number не передан — берётся САМЫЙ
    ДАЛЬНИЙ круг, до которого дошёл хоть один участник пула (весь пул, если
    gender=None) — прежнее поведение по умолчанию. None, если в пуле ещё
    никто не дошёл ни до одного круга этого этапа (или явно указанной
    отметки, если lap_number передан)."""
    conn = get_duathlon_connection()
    if not conn:
        return None
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT id, surname, name, gender, run1_s, t1_s, bike_s, t2_s,
                   bike_start_s, run2_start_s
            FROM participants WHERE event_id=%s
        """, (event_id,))
        participants = {r["id"]: r for r in cursor.fetchall()}

        if lap_number == 0:
            return _stage_mark_zero_broadcast(stage_code, gender, participants.values())

        gender_filter = "AND p.gender=%s" if gender else ""
        params = [event_id, stage_code] + ([gender] if gender else [])
        cursor.execute(f"""
            SELECT c.participant_id, c.lap_number, c.cumulative_s
            FROM checkpoints c JOIN participants p ON p.id = c.participant_id
            WHERE p.event_id=%s AND c.stage=%s {gender_filter}
        """, params)
        laps = cursor.fetchall()

        frontier = lap_number if lap_number is not None else _frontier_lap([lr["lap_number"] for lr in laps])
        if frontier is None:
            return None

        entries = []
        for lr in laps:
            if lr["lap_number"] != frontier:
                continue
            p = participants.get(lr["participant_id"])
            stage_start = _stage_start_s(
                stage_code, p["run1_s"], p["t1_s"], p["bike_s"], p["t2_s"],
                p["bike_start_s"], p["run2_start_s"],
            )
            if stage_start is None:
                continue
            entries.append({
                "surname": p["surname"], "name": p["name"],
                # Чистое время ЭТАПА (без Т1/Т2/предыдущих этапов) — для
                # поста "по этапу" (кто быстрее ИМЕННО на этом этапе).
                "elapsed_s": lr["cumulative_s"] - stage_start,
                # Кумулятивное время С ОБЩЕГО СТАРТА ГОНКИ (уже включает
                # предыдущие этапы + транзиты) — для поста "по всей гонке".
                # Это РАЗНЫЕ рейтинги для стадий после run1: кто финишировал
                # run1 быстрее, стартует этот этап раньше по часам гонки,
                # даже если сам этап пройдёт медленнее.
                "race_elapsed_s": lr["cumulative_s"],
            })
        if not entries:
            return None
        stage_leader_elapsed = min(e["elapsed_s"] for e in entries)
        race_leader_elapsed = min(e["race_elapsed_s"] for e in entries)
        entries.sort(key=lambda e: e["elapsed_s"])

        # Сырая (неокруглённая) дистанция — для расчёта скорости и суммы с
        # overall_km; округление до 1 знака — только в выводимых полях, не
        # должно искажать сами вычисления (см. get_standings/get_participant,
        # тот же принцип, найдено пользователем 2026-09-04).
        stage_km_at_mark_raw = _lap_distance_km(stage_code, frontier)
        stage_km_at_mark = round(stage_km_at_mark_raw, 2)
        return {
            "stage": stage_code,
            "lap_mark": frontier,
            "stage_km_at_mark": stage_km_at_mark,
            "stage_total_km": STAGE_KM[stage_code],
            "overall_km": round(_STAGE_KM_BEFORE[stage_code] + stage_km_at_mark_raw, 2),
            "race_total_km": sum(STAGE_KM.values()),
            "entries": [
                {
                    "surname": e["surname"], "name": e["name"],
                    "elapsed_s": e["elapsed_s"],
                    "gap_s": e["elapsed_s"] - stage_leader_elapsed,
                    "race_elapsed_s": e["race_elapsed_s"],
                    "race_gap_s": e["race_elapsed_s"] - race_leader_elapsed,
                    "speed_kmh": _speed_kmh_for_distance(stage_km_at_mark_raw, e["elapsed_s"]),
                }
                for e in entries
            ],
        }
    finally:
        cursor.close()
        conn.close()


def _build_checkpoint_series(
    participant_id: int,
    stage_starts: dict[str, Optional[int]],
    laps_by_key: dict[tuple[int, str], list[tuple[int, int]]],
) -> dict[str, list[dict]]:
    """Полная история отметок участника по каждому этапу — для графиков
    «Позиция»/«Темп-скорость» (см. get_standings). elapsed_s — ВСЕГДА от
    старта ГОНКИ (то же значение, что checkpoints.cumulative_s в БД — см.
    load_duathlon_results.py), не от старта этапа: так один и тот же массив
    годится и для живого ранга по гонке целиком, и для сплит-темпа внутри
    этапа (разница cumulative_s между соседними точками не зависит от точки
    отсчёта). lap=0 — виртуальная отметка выхода из транзитки (тот же
    источник, что и _stage_mark_zero_broadcast), добавляется только если
    старт этапа уже известен — даёт точную (не экстраполированную) первую
    точку сплита вместо прежнего трюка "продлить линию плоско до X=0"."""
    result: dict[str, list[dict]] = {}
    for stage_code in _STAGE_ORDER:
        points: list[dict] = []
        start_s = stage_starts.get(stage_code)
        if start_s is not None:
            points.append({"lap": 0, "km": 0.0, "elapsed_s": start_s})
        for lap_number, cumulative_s in laps_by_key.get((participant_id, stage_code), []):
            points.append({
                "lap": lap_number,
                "km": round(_lap_distance_km(stage_code, lap_number), 2),
                "elapsed_s": cumulative_s,
            })
        result[stage_code] = points
    return result


def _global_km(stage_code: str, lap_number: Optional[int]) -> float:
    """Кумулятивная дистанция (км) ОТ СТАРТА ГОНКИ (не этапа) на данной
    отметке — _STAGE_KM_BEFORE[stage] + позиция внутри этапа. Общая ось
    "положения в гонке" для живого отставания в колонке "Итого" (в отличие
    от _distance_covered_km — та берёт CURRENT_STAGE конкретного участника,
    эта считает для ЛЮБОЙ пары (этап, отметка), в т.ч. чужой/прошлой)."""
    return _STAGE_KM_BEFORE[stage_code] + _lap_distance_km(stage_code, lap_number)


def _live_gap_map(entries: list[dict]) -> dict[int, float]:
    """Живое отставание от лидера пула — тот же принцип, что
    computeStageGaps()/bikeCombinedGaps() у Siberman (static/js/
    siberman-common.js): лидер — участник, дальше всех продвинувшийся ПРЯМО
    СЕЙЧАС (по последней достигнутой позиции), не обязательно уже
    завершивший дистанцию целиком. Отставание остальных — разница их
    значения (времени) на своей последней позиции и значением, которое
    ПОКАЗЫВАЛ ЛИДЕР на этой же самой позиции (интерполяция назад по истории
    лидера: последняя его точка с position <= позиции отстающего) —
    отставание "на равной дистанции", а не относительно текущего/финального
    состояния лидера.

    entries: [{"id", "status", "points": [(position, value), ...]}], points
    отсортированы по возрастанию position. DNF/DSQ исключены из пула целиком
    (не могут быть лидером и не получают отставания). Возвращает
    {id: gap_seconds} — только для тех, у кого нашлась интерполируемая
    точка лидера (обычно все, кроме случая "лидер начал позже отстающего",
    структурно невозможного, т.к. лидер по определению дальше)."""
    candidates = [e for e in entries if e["status"] not in ("dnf", "dsq") and e["points"]]
    if not candidates:
        return {}
    leader = min(candidates, key=lambda e: (-e["points"][-1][0], e["points"][-1][1]))
    leader_points = leader["points"]

    def _leader_value_at_or_before(position: float) -> Optional[float]:
        val = None
        for pos, value in leader_points:
            if pos <= position:
                val = value
            else:
                break
        return val

    gaps: dict[int, float] = {}
    for e in candidates:
        own_position, own_value = e["points"][-1]
        if e["id"] == leader["id"]:
            gaps[e["id"]] = 0
            continue
        leader_value = _leader_value_at_or_before(own_position)
        if leader_value is not None:
            gaps[e["id"]] = own_value - leader_value
    return gaps


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
                   run1_s, t1_s, bike_s, t2_s, run2_s, bike_start_s, run2_start_s
            FROM participants
            WHERE event_id = %s {gender_filter}
        """, params)
        rows = cursor.fetchall()

        # Последний пройденный круг каждого (участник, этап) — одним запросом
        # на всё событие, агрегируем в Python (объём данных мал: до ~100
        # участников x 58 кругов максимум за всю гонку). laps_by_key хранит
        # ПОЛНУЮ историю (не только последний круг) — нужна для живого
        # отставания (_live_gap_map ниже интерполирует историю лидера).
        cursor.execute("""
            SELECT c.participant_id, c.stage, c.lap_number, c.cumulative_s
            FROM checkpoints c
            JOIN participants p ON p.id = c.participant_id
            WHERE p.event_id = %s
            ORDER BY c.participant_id, c.stage, c.lap_number
        """, (event_id,))
        last_lap: dict[tuple[int, str], tuple[int, int]] = {}
        laps_by_key: dict[tuple[int, str], list[tuple[int, int]]] = {}
        for lap_row in cursor.fetchall():
            key = (lap_row["participant_id"], lap_row["stage"])
            laps_by_key.setdefault(key, []).append((lap_row["lap_number"], lap_row["cumulative_s"]))
            if key not in last_lap or lap_row["lap_number"] > last_lap[key][0]:
                last_lap[key] = (lap_row["lap_number"], lap_row["cumulative_s"])

        # Живое отставание (см. _live_gap_map) — отдельно по каждому этапу
        # (ось позиции — номер круга, значение — ЧИСТОЕ время этапа без
        # транзита) и по гонке в целом (ось — кумулятивная дистанция от
        # старта гонки через все 3 этапа, значение — сырое cumulative_s, оно
        # уже "глобальное" по построению checkpoints.cumulative_s).
        stage_entries: dict[str, list[dict]] = {sc: [] for sc in _STAGE_ORDER}
        race_entries: list[dict] = []
        for row in rows:
            stage_starts = {
                sc: _stage_start_s(
                    sc, row["run1_s"], row["t1_s"], row["bike_s"], row["t2_s"],
                    row["bike_start_s"], row["run2_start_s"],
                )
                for sc in _STAGE_ORDER
            }
            race_points: list[tuple[float, int]] = []
            for sc in _STAGE_ORDER:
                laps = laps_by_key.get((row["id"], sc))
                if not laps:
                    continue
                race_points.extend((_global_km(sc, ln), cum_s) for ln, cum_s in laps)
                if stage_starts[sc] is not None:
                    stage_entries[sc].append({
                        "id": row["id"], "status": row["status"],
                        "points": [(ln, cum_s - stage_starts[sc]) for ln, cum_s in laps],
                    })
            race_entries.append({"id": row["id"], "status": row["status"], "points": race_points})
        stage_gaps = {sc: _live_gap_map(stage_entries[sc]) for sc in _STAGE_ORDER}
        race_gaps = _live_gap_map(race_entries)

        enriched = []
        for row in rows:
            run1_time, bike_time, run2_time = _stage_times(
                row["run1_s"], row["t1_s"], row["bike_s"], row["t2_s"], row["run2_s"]
            )
            current_stage, current_stage_start_s = _current_stage(
                row["run1_s"], row["t1_s"], row["bike_s"], row["t2_s"], row["run2_s"],
                row["bike_start_s"], row["run2_start_s"],
            )
            # "finished" — не настоящий этап в checkpoints (там только
            # run1/bike/run2) — для отметки финишировавшего берём последний
            # круг реального последнего этапа (run2), чтобы "Отметка"
            # по-прежнему показывала "42/42 км" (см. get_participant).
            mark_stage = "run2" if current_stage == "finished" else current_stage
            lap_number, lap_cumulative_s = last_lap.get((row["id"], mark_stage), (None, None))
            distance_km = _distance_covered_km(current_stage, lap_number)
            # СЫРАЯ (неокруглённая) дистанция — отдельно от округлённой для
            # показа: округление до 1 знака НЕ должно влиять на расчёт темпа/
            # скорости (иначе, например, отметка "20 м" Бег-2 округляется до
            # 0.0 км и делит на ноль — найдено пользователем 2026-09-04).
            current_stage_distance_km_raw = _lap_distance_km(mark_stage, lap_number) if lap_number else None
            current_stage_distance_km = round(current_stage_distance_km_raw, 2) if lap_number else None
            # Чистое время ТЕКУЩЕГО этапа на последней отметке — ЗАФИКСИРОВАНО
            # (не тикает), обновляется на каждую новую отметку (запрошено
            # пользователем 2026-09-04 — убрали живой секундомер по строкам).
            current_stage_elapsed_s = (
                lap_cumulative_s - current_stage_start_s
                if lap_cumulative_s is not None and current_stage_start_s is not None else None
            )
            current_stage_speed_kmh = None
            if current_stage_distance_km_raw and current_stage_elapsed_s:
                current_stage_speed_kmh = _speed_kmh_for_distance(current_stage_distance_km_raw, current_stage_elapsed_s)
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
                "run1_gap_s": stage_gaps["run1"].get(row["id"]),
                "bike_gap_s": stage_gaps["bike"].get(row["id"]),
                "run2_gap_s": stage_gaps["run2"].get(row["id"]),
                "total_s": row["run2_s"],
                # Живое отставание "Итого" — на эквивалентной дистанции (см.
                # _live_gap_map), не только среди уже финишировавших всю
                # гонку целиком (запрошено пользователем 2026-09-04, по
                # аналогии с Siberman).
                "race_gap_s": race_gaps.get(row["id"]),
                "current_stage": current_stage,
                "current_stage_start_s": current_stage_start_s,
                "current_stage_lap": lap_number,
                "current_stage_lap_total": LAP_COUNT.get(mark_stage),
                "current_stage_distance_km": current_stage_distance_km,
                "current_stage_elapsed_s": current_stage_elapsed_s,
                "current_stage_speed_kmh": current_stage_speed_kmh,
                # Итого "так, как есть сейчас" (зафиксировано на последней
                # отметке, не тикает) — пока гонка не завершена целиком
                # (total_s ещё null), это и есть значение колонки "Итого".
                "current_mark_race_elapsed_s": lap_cumulative_s,
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
