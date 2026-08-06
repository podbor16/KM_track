"""
Сервисный слой: ParseResult → БД.
Вызывается из admin-роута после подтверждения превью.
"""
import logging
from typing import Optional

from src.siberman.db import (
    get_siberman_connection, get_checkpoints, clear_race_year,
    upsert_participant, upsert_checkpoint_time, upsert_transition,
    upsert_stage_total, upsert_overall_result, write_best_record,
)
from src.siberman.parser import ParseResult

log = logging.getLogger(__name__)

# Дистанции этапов (км)
STAGE_DISTANCES_KM: dict[str, float] = {
    "swim":      10.0,
    "bike_day1": 145.0,
    "bike_day2": 276.0,
    "run":       84.0,
}
# Последний seq для каждого этапа (из seed)
STAGE_MAX_SEQ: dict[str, int] = {
    "swim": 7, "bike_day1": 6, "bike_day2": 8, "run": 12,
}
BIKE_STAGES = {"bike_day1", "bike_day2"}
BIKE_DAY2_BASE_START_S = 8 * 3600  # 08:00:00 (Красноярск) — старт лидера по рангу вело-1

# Заплыв — 4 круга по 2,5 км с буем-разворотом на середине каждого круга
# (7 КТ: 3 разворота + 4 круга). Только "круговые" seq входят в счётчик
# кругов — "разворот"-КТ не считаются отдельным кругом. Для бега seq уже
# 1:1 совпадает с номером круга — отдельная константа не нужна.
SWIM_LAP_SEQS: dict[int, int] = {2: 1, 4: 2, 6: 3, 7: 4}


def format_seconds(s: Optional[int]) -> str:
    if s is None:
        return "—"
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}"


def format_pace(s: Optional[int]) -> str:
    if s is None:
        return "—"
    return f"{s // 60}:{s % 60:02d}"


def compute_split_times(cumulative: list[Optional[int]]) -> list[Optional[int]]:
    """Вычислить сплиты из накопленных времён.

    Если в середине встречается None — все последующие сплиты тоже None.
    """
    splits: list[Optional[int]] = []
    prev: Optional[int] = None
    gap_seen = False
    for c in cumulative:
        if gap_seen or c is None:
            splits.append(None)
            if c is None:
                gap_seen = True
        elif prev is None:
            splits.append(c)
        else:
            splits.append(c - prev)
        if c is not None:
            prev = c
    return splits


def _last_cp(cp_times: dict, stage: str) -> Optional[int]:
    """Последний не-None cumulative для этапа."""
    for seq in range(STAGE_MAX_SEQ[stage], 0, -1):
        v = cp_times.get((stage, seq))
        if v is not None:
            return v
    return None


def compute_stage_totals(cp_times: dict) -> dict[str, Optional[int]]:
    """
    Вычислить итоговое чистое время по каждому этапу.

    swim     — последний чекпоинт плавания (накоп. с нуля).
    bike_day1 — последний cp bike_day1 (накоп. от старта гонки) минус swim:
                включает T1, т.к. отдельной колонки T1 нет.
    bike_day2 — последний cp bike_day2 (уже elapsed относительно
                расчётного старта участника — см. convert_bike_times_to_elapsed).
    run       — последний cp run (накоп. от старта 3-го дня).
    """
    swim = _last_cp(cp_times, "swim")
    bike1_abs = _last_cp(cp_times, "bike_day1")
    bike1 = (bike1_abs - swim) if bike1_abs is not None and swim is not None else None
    bike2 = _last_cp(cp_times, "bike_day2")
    run   = _last_cp(cp_times, "run")
    return {"swim": swim, "bike_day1": bike1, "bike_day2": bike2, "run": run}


def _finished_stage(cp_times: dict, stage: str) -> bool:
    """Дошёл ли участник до ПОСЛЕДНЕЙ КТ этапа (а не просто до какой-то)."""
    return cp_times.get((stage, STAGE_MAX_SEQ[stage])) is not None


def compute_overall(stage_totals: dict[str, Optional[int]]) -> Optional[int]:
    """Общее чистое время = сумма всех этапов (None если хоть один этап DNF)."""
    vals = [stage_totals.get(s) for s in ("swim", "bike_day1", "bike_day2", "run")]
    if any(v is None for v in vals):
        return None
    return sum(vals)  # type: ignore[arg-type]


def convert_bike_times_to_elapsed(result: ParseResult, race_start_s: int) -> dict[str, int]:
    """
    Переводит RAW астрономическое время вело (секунды от полуночи, как
    внесли судьи) в elapsed, мутируя result.checkpoint_times in place.
    Плавание и бег не трогает — они уже elapsed.

    1. bike_day1 → elapsed относительно race_start_s (старт дня 1, задаётся
       в админке при загрузке) — одинаково для personal и relay.
    2. Считает bike_day1 total (включая T1) для каждого "райдера"
       (personal bib ИЛИ relay "{bib}:bike") = последний cp bike_day1 минус
       swim_total (для relay swim_total — из записи "{bib}:swim" команды).
    3. Ранжирует всех райдеров по bike_day1 total одним общим зачётом
       (без разделения по полу/формату) через rank_by().
    4. Вычисляет расчётный старт вело-2 по рангу:
         ранг 1-5: BIKE_DAY2_BASE_START_S + (ранг-1)*180
         ранг 6+:  BIKE_DAY2_BASE_START_S + 4*180 + (ранг-5)*60
       (см. knowledge/decisions/2026-07-09-siberman-live-v2-tasks.md)
    5. bike_day2 → elapsed относительно ИНДИВИДУАЛЬНОГО старта райдера.

    Райдеры без вычисленного bike_day1 total (DNF/DNS на вело-1) не
    попадают в ранжирование и не получают старт вело-2.

    Возвращает {rider_key: start_day2_s} — используется для отображения
    расчётного старта в админке и на публичной странице результатов.
    """
    for cp_times in result.checkpoint_times.values():
        for key in list(cp_times.keys()):
            if key[0] == "bike_day1" and cp_times[key] is not None:
                cp_times[key] = (cp_times[key] - race_start_s) % 86400

    rider_bike1_total: dict[str, int] = {}
    for p in result.participants:
        if p["format"] == "individual":
            rider_key = p["bib"]
            swim_cp = bike_cp = result.checkpoint_times.get(rider_key, {})
        elif p["format"] == "relay" and p.get("relay_stage") == "bike":
            rider_key = f"{p['bib']}:bike"
            swim_cp = result.checkpoint_times.get(f"{p['bib']}:swim", {})
            bike_cp = result.checkpoint_times.get(rider_key, {})
        else:
            continue

        swim_total = _last_cp(swim_cp, "swim")
        bike1_abs = _last_cp(bike_cp, "bike_day1")
        # _finished_stage — а не просто "есть хоть одна КТ вело-1": до
        # фикса рейдер, дошедший только до первой КТ (3 км), уже получал
        # расчётный старт дня 2 и попадал в стартовый лист, хотя вело-1
        # ещё в процессе у всех — стартовый лист должен появляться только
        # после того, как кто-то РЕАЛЬНО финишировал вело-1 (найдено
        # пользователем 2026-08-04 на живом тестовом прогоне).
        if swim_total is not None and bike1_abs is not None and _finished_stage(bike_cp, "bike_day1"):
            rider_bike1_total[rider_key] = bike1_abs - swim_total

    ranks = rank_by(rider_bike1_total)

    def _start_offset(rank: int) -> int:
        if rank <= 5:
            return (rank - 1) * 180
        return 4 * 180 + (rank - 5) * 60

    start_day2: dict[str, int] = {
        rider_key: BIKE_DAY2_BASE_START_S + _start_offset(rank)
        for rider_key, rank in ranks.items() if rank is not None
    }

    for rider_key, start_s in start_day2.items():
        cp_times = result.checkpoint_times.get(rider_key, {})
        for key in list(cp_times.keys()):
            if key[0] == "bike_day2" and cp_times[key] is not None:
                cp_times[key] = (cp_times[key] - start_s) % 86400

    return start_day2


def compute_metrics(stage: str, total_s: Optional[int]) -> tuple[Optional[int], Optional[float]]:
    """Вернуть (avg_pace_s/км, avg_speed_kmh). Для вело — скорость, для остальных — темп."""
    if not total_s:
        return None, None
    dist = STAGE_DISTANCES_KM[stage]
    if stage in BIKE_STAGES:
        return None, round(dist / (total_s / 3600), 2)
    return round(total_s / dist), None


def rank_by(pid_to_val: dict[int, Optional[int]]) -> dict[int, Optional[int]]:
    """
    Стандартное спортивное ранжирование (1,1,3 при ничьей).
    None → None (DNF/DNS не получают места).
    """
    finite = sorted((v, pid) for pid, v in pid_to_val.items() if v is not None)
    ranks: dict[int, Optional[int]] = {}
    rank = 1
    for i, (val, pid) in enumerate(finite):
        if i > 0 and val == finite[i - 1][0]:
            ranks[pid] = ranks[finite[i - 1][1]]
        else:
            ranks[pid] = rank
        rank += 1
    for pid, v in pid_to_val.items():
        if v is None:
            ranks[pid] = None
    return ranks


def build_preview(result: ParseResult) -> dict:
    return {
        "race_year":         result.race_year,
        "participant_count": len(result.participants),
        "participants": [
            {
                "bib":      p["bib"],
                "name":     f"{p['surname']} {p['name']}",
                "gender":   {"M": "М", "F": "Ж"}.get(p["gender"], p["gender"]),
                "format":   p["format"],
                "status":   p["status"],
                "cp_count": sum(
                    1 for v in result.checkpoint_times.get(
                        p.get("_cp_key", p["bib"]), {}
                    ).values() if v is not None
                ),
            }
            for p in result.participants
        ],
        "errors": result.errors,
    }


def build_bike_day2_starts(result: ParseResult, starts: dict[str, int]) -> list[dict]:
    """Список расчётных стартов вело-2 для отображения (админка + результаты),
    отсортирован по времени старта."""
    rows = []
    for p in result.participants:
        if p["format"] == "individual":
            rider_key = p["bib"]
            label = f"{p['surname']} {p['name']}"
        elif p["format"] == "relay" and p.get("relay_stage") == "bike":
            rider_key = f"{p['bib']}:bike"
            label = p["relay_team_name"]
        else:
            continue
        start_s = starts.get(rider_key)
        if start_s is None:
            continue
        rows.append({
            "bib": p["bib"], "name": label,
            "start_s": start_s, "start": format_seconds(start_s),
        })
    rows.sort(key=lambda r: r["start_s"])
    return rows


def _recompute_records(conn, race_year: int, pid_to_participant: dict, pid_totals: dict,
                        pid_meta: dict, pid_cp_times: dict, relay_by_bib: dict) -> None:
    """Пересчитывает рекорды Siberman (siberman_records) ЖИВЬЁМ на каждый
    apply. Кандидатом на рекорд КОНКРЕТНОЙ колонки становится любой, кто
    реально финишировал именно ЭТОТ сегмент (не обязательно всю гонку) и
    сейчас НЕ dnf/dsq — рекорд должен быть виден в live-режиме, а не
    только после финиша всей гонки; если участник позже получает dnf, на
    следующем apply он выпадает из кандидатов и рекорд автоматически
    "откатывается" к следующему подходящему (или к историческому
    baseline) — решение 2026-08-05, второй раунд, после первоначального
    "только полный финишер". 'overall' — колонка-исключение: требует
    финиша ВСЕЙ гонки (не просто сегмента) и недоступна эстафете (личное
    достижение одного человека, не сумма троих). 'male'/'female' считает
    и эстафетчиков (у них есть реальный личный пол на этапе),
    '..._individual' — только личный зачёт. Полный пересчёт (не
    инкрементальное сравнение "побил — не побил") делает откат возможным
    без доп. состояния — см. write_best_record() в db.py.

    `pid_to_participant` — участник по participant_id (минимум surname/
    name/relay_team_name), общий источник и для Excel-пути (apply_to_db),
    и для live-обновлений Copernico (copernico_run.py) — см.
    recompute_totals_ranks_records()."""

    def bike_total_for(pid: int) -> Optional[int]:
        t = pid_totals.get(pid, {})
        b1, b2 = t.get("bike_day1"), t.get("bike_day2")
        return b1 + b2 if b1 is not None and b2 is not None else None

    def gender_cats(gender: str, individual: bool) -> list[str]:
        base = "male" if gender == "M" else "female" if gender == "F" else None
        if base is None:
            return []
        return [base, f"{base}_individual"] if individual else [base]

    # candidates[(column_key, category)] = [(value, holder_name, holder_team), ...]
    candidates: dict[tuple[str, str], list[tuple[int, str, Optional[str]]]] = {}

    def add(column_key: str, category: str, value: Optional[int], name: str, team: Optional[str]) -> None:
        if value is None:
            return
        candidates.setdefault((column_key, category), []).append((value, name, team))

    def add_stage(column_key: str, value: Optional[int], name: str, team: Optional[str],
                  gender: str, individual: bool) -> None:
        add(column_key, "absolute", value, name, team)
        for cat in gender_cats(gender, individual):
            add(column_key, cat, value, name, team)

    # --- Личники — по каждой колонке своя проверка ФИНИША СЕГМЕНТА, не всей гонки ---
    for pid, meta in pid_meta.items():
        if meta["format"] != "individual" or meta["status"] != "active":
            continue
        p = pid_to_participant.get(pid)
        if p is None:
            continue
        name = f"{p['surname']} {p['name']}"
        totals = pid_totals[pid]
        cp_times = pid_cp_times.get(pid, {})

        if all(_finished_stage(cp_times, s) for s in ("swim", "bike_day1", "bike_day2", "run")):
            add("overall", "absolute", totals["overall"], name, None)
            for cat in gender_cats(p["gender"], individual=True):
                if cat.endswith("_individual"):
                    add("overall", cat, totals["overall"], name, None)

        if _finished_stage(cp_times, "swim"):
            add_stage("swim", totals.get("swim"), name, None, p["gender"], True)
        if _finished_stage(cp_times, "bike_day1") and _finished_stage(cp_times, "bike_day2"):
            add_stage("bike_total", bike_total_for(pid), name, None, p["gender"], True)
        if _finished_stage(cp_times, "run"):
            add_stage("run", totals.get("run"), name, None, p["gender"], True)

    # --- Эстафеты — по каждой роли свой участник, свой статус, свой финиш сегмента ---
    for bib, roles in relay_by_bib.items():
        swim_pid, bike_pid, run_pid = roles.get("swim"), roles.get("bike"), roles.get("run")
        team_p = (pid_to_participant.get(swim_pid) or pid_to_participant.get(bike_pid)
                  or pid_to_participant.get(run_pid))
        team_name = team_p.get("relay_team_name") if team_p else None

        if swim_pid and pid_meta.get(swim_pid, {}).get("status") == "active" \
                and _finished_stage(pid_cp_times.get(swim_pid, {}), "swim"):
            p = pid_to_participant.get(swim_pid)
            if p:
                add_stage("swim", pid_totals[swim_pid].get("swim"),
                          f"{p['surname']} {p['name']}", team_name, p["gender"], False)
        if bike_pid and pid_meta.get(bike_pid, {}).get("status") == "active" \
                and _finished_stage(pid_cp_times.get(bike_pid, {}), "bike_day1") \
                and _finished_stage(pid_cp_times.get(bike_pid, {}), "bike_day2"):
            p = pid_to_participant.get(bike_pid)
            if p:
                add_stage("bike_total", bike_total_for(bike_pid),
                          f"{p['surname']} {p['name']}", team_name, p["gender"], False)
        if run_pid and pid_meta.get(run_pid, {}).get("status") == "active" \
                and _finished_stage(pid_cp_times.get(run_pid, {}), "run"):
            p = pid_to_participant.get(run_pid)
            if p:
                add_stage("run", pid_totals[run_pid].get("run"),
                          f"{p['surname']} {p['name']}", team_name, p["gender"], False)
        # Эстафета не участвует в column_key='overall'.

    for (column_key, category), items in candidates.items():
        write_best_record(conn, column_key, category, items, race_year)


def recompute_totals_ranks_records(conn, race_year: int, participants: list[dict],
                                    pid_cp_times: dict[int, dict]) -> None:
    """Пересчитать stage_totals/overall_results/рекорды из уже записанных
    checkpoint_times — общая точка для ОБОИХ источников данных: Excel-путь
    (apply_to_db, полный пересчёт после clear_race_year) и live-обновления
    Copernico (copernico_run.py, точечный upsert без clear_race_year) —
    чтобы не дублировать логику ранжирования между ними.

    `participants` — список словарей минимум с id/bib/gender/format/
    relay_stage/status/surname/name/relay_team_name (для Excel-пути — это
    result.participants + "id"=pid; для Copernico — свежепрочитанные из
    БД участники года). `pid_cp_times` — participant_id → dict
    {(stage,seq): cumulative_s}."""
    pid_totals: dict[int, dict] = {}
    pid_meta:   dict[int, dict] = {}
    pid_to_participant: dict[int, dict] = {}
    for p in participants:
        pid = p["id"]
        cp_times = pid_cp_times.get(pid, {})
        st = compute_stage_totals(cp_times)
        pid_totals[pid] = {**st, "overall": compute_overall(st)}
        pid_meta[pid] = {"gender": p["gender"], "format": p["format"],
                          "relay_stage": p.get("relay_stage", "none"),
                          "status": p.get("status", "active")}
        pid_to_participant[pid] = p

    # Для relay bike-члена: bike_day1 = bike1_abs_finish - swim_total команды
    relay_by_bib: dict[str, dict[str, int]] = {}
    for p in participants:
        if p["format"] == "relay":
            relay_by_bib.setdefault(p["bib"], {})[p.get("relay_stage", "none")] = p["id"]

    for bib, stage_pids in relay_by_bib.items():
        swim_pid = stage_pids.get("swim")
        bike_pid = stage_pids.get("bike")
        if swim_pid and bike_pid:
            swim_total = pid_totals.get(swim_pid, {}).get("swim")
            bike_cp = pid_cp_times.get(bike_pid, {})
            bike1_abs = _last_cp(bike_cp, "bike_day1")
            if bike1_abs is not None and swim_total is not None:
                pid_totals[bike_pid]["bike_day1"] = bike1_abs - swim_total

    indiv_all = [pid for pid, m in pid_meta.items() if m["format"] == "individual"]
    # Ранги только для активных финишёров; DNF/DNS/DSQ → rank=None
    indiv  = [pid for pid in indiv_all if pid_meta[pid].get("status") == "active"]
    male   = [pid for pid in indiv if pid_meta[pid]["gender"] == "M"]
    female = [pid for pid in indiv if pid_meta[pid]["gender"] == "F"]

    for stage in ("swim", "bike_day1", "bike_day2", "run"):
        # Место присваивается только тем, кто реально ДОШЁЛ до финиша
        # этапа (последняя КТ этапа не None).
        finishers = [pid for pid in indiv if _finished_stage(pid_cp_times.get(pid, {}), stage)]
        finishers_m = [pid for pid in finishers if pid in male]
        finishers_f = [pid for pid in finishers if pid in female]
        s_ranks = rank_by({pid: pid_totals[pid][stage] for pid in finishers})
        g_ranks = {
            **rank_by({pid: pid_totals[pid][stage] for pid in finishers_m}),
            **rank_by({pid: pid_totals[pid][stage] for pid in finishers_f}),
        }
        for pid in indiv_all:
            total_s = pid_totals[pid][stage]
            pace, speed = compute_metrics(stage, total_s)
            upsert_stage_total(
                conn, pid, stage, total_s,
                rank_stage=s_ranks.get(pid),   # None для DNF
                rank_gender=g_ranks.get(pid),  # None для DNF
                avg_pace_s=pace,
                avg_speed_kmh=speed,
            )

    # Сохранить stage_totals для relay (без ранжирования)
    relay_pids = [pid for pid, m in pid_meta.items() if m["format"] == "relay"]
    for pid in relay_pids:
        for stage in ("swim", "bike_day1", "bike_day2", "run"):
            total_s = pid_totals[pid].get(stage)
            if total_s is not None:
                pace, speed = compute_metrics(stage, total_s)
                upsert_stage_total(
                    conn, pid, stage, total_s,
                    rank_stage=None, rank_gender=None,
                    avg_pace_s=pace, avg_speed_kmh=speed,
                )

    # Место в абсолютном зачёте — только тем, кто реально финишировал
    # ВСЕ 4 этапа (та же причина, что и для места по этапам).
    race_finishers = [
        pid for pid in indiv
        if all(_finished_stage(pid_cp_times.get(pid, {}), s) for s in ("swim", "bike_day1", "bike_day2", "run"))
    ]
    race_finishers_m = [pid for pid in race_finishers if pid in male]
    race_finishers_f = [pid for pid in race_finishers if pid in female]
    o_ranks = rank_by({pid: pid_totals[pid]["overall"] for pid in race_finishers})
    go_ranks = {
        **rank_by({pid: pid_totals[pid]["overall"] for pid in race_finishers_m}),
        **rank_by({pid: pid_totals[pid]["overall"] for pid in race_finishers_f}),
    }
    for pid in indiv_all:
        upsert_overall_result(
            conn, pid,
            total_s=pid_totals[pid]["overall"],
            rank_overall=o_ranks.get(pid),   # None для DNF
            rank_gender=go_ranks.get(pid),   # None для DNF
            rank_relay=None,
        )

    _recompute_records(conn, race_year, pid_to_participant, pid_totals, pid_meta, pid_cp_times, relay_by_bib)


def apply_parse_result_upsert(conn, result: ParseResult) -> dict:
    """То же самое, что делает apply_to_db() ПОСЛЕ clear_race_year() —
    upsert участников/checkpoint_times/transitions без удаления (id
    участников стабилен между вызовами, см. upsert_participant() —
    ON DUPLICATE KEY UPDATE). Используется live-синхронизацией из Google
    Таблицы (google_sheet_sync.py) по тем же причинам, что и Copernico
    (copernico_run.py): полный clear_race_year() коммитится немедленно
    (autocommit=True) — на каждом цикле опроса публичная страница на долю
    секунды показывала бы пустую таблицу. apply_to_db() (ручная Excel-
    загрузка) НЕ тронута — сознательно оставлена с полным пересозданием
    (единственная потеря upsert-режима: участник, полностью УДАЛЁННЫЙ из
    таблицы, не убирается из БД сам собой — принятый компромисс).

    Принимает уже открытое соединение (вызывающий код сам решает,
    коммитить/закрывать) — в отличие от apply_to_db(), которое управляет
    соединением самостоятельно."""
    checkpoints = get_checkpoints(conn, result.race_year)
    cp_id_map: dict[tuple[str, int], int] = {
        (row["stage"], row["seq"]): row["id"] for row in checkpoints
    }

    cp_key_to_pid: dict[str, int] = {}
    upserted_parts = 0
    upserted_times = 0

    for p in result.participants:
        pid = upsert_participant(conn, p)
        cp_key = p.get("_cp_key", p["bib"])
        cp_key_to_pid[cp_key] = pid
        upserted_parts += 1

        handicap = result.handicaps.get(cp_key)
        if handicap is not None:
            cur = conn.cursor()
            cur.execute(
                "UPDATE participants SET bike_day2_handicap_s=%s WHERE id=%s",
                (handicap, pid),
            )

        cp_times = result.checkpoint_times.get(cp_key, {})
        for (stage, seq), cumulative_s in cp_times.items():
            cp_id = cp_id_map.get((stage, seq))
            if cp_id is None:
                log.warning(f"No checkpoint for stage={stage} seq={seq}")
                continue
            prev_cum = cp_times.get((stage, seq - 1))
            split_s: Optional[int] = None
            if cumulative_s is not None and prev_cum is not None:
                split_s = cumulative_s - prev_cum
            elif cumulative_s is not None and seq == 1:
                split_s = cumulative_s
            upsert_checkpoint_time(conn, pid, cp_id, cumulative_s, split_s)
            upserted_times += 1

        for zone, dur in result.transitions.get(cp_key, {}).items():
            upsert_transition(conn, pid, zone, dur)

    participants_meta: list[dict] = []
    pid_cp_times: dict[int, dict] = {}
    for p in result.participants:
        cp_key = p.get("_cp_key", p["bib"])
        pid = cp_key_to_pid[cp_key]
        participants_meta.append({**p, "id": pid})
        pid_cp_times[pid] = result.checkpoint_times.get(cp_key, {})

    recompute_totals_ranks_records(conn, result.race_year, participants_meta, pid_cp_times)

    return {"ok": True, "participants": upserted_parts, "checkpoint_times": upserted_times}


def apply_to_db(result: ParseResult) -> dict:
    """
    Записать ParseResult в БД:
    1. Удалить все данные за год
    2. Upsert участников + checkpoint_times + transitions
    3. Вычислить stage_totals (итоги, темп/скорость)
    4. Ранжировать и сохранить в stage_totals + overall_results
    """
    conn = get_siberman_connection()
    if conn is None:
        return {"ok": False, "error": "DB connection failed"}

    try:
        checkpoints = get_checkpoints(conn, result.race_year)
        cp_id_map: dict[tuple[str, int], int] = {
            (row["stage"], row["seq"]): row["id"] for row in checkpoints
        }

        clear_race_year(conn, result.race_year)

        # cp_key → participant_id (уникальный ключ для relay: "{bib}:{stage}", для personal: bib)
        cp_key_to_pid: dict[str, int] = {}
        inserted_parts = 0
        inserted_times = 0

        for p in result.participants:
            pid = upsert_participant(conn, p)
            cp_key = p.get("_cp_key", p["bib"])
            cp_key_to_pid[cp_key] = pid
            inserted_parts += 1

            handicap = result.handicaps.get(cp_key)
            if handicap is not None:
                cur = conn.cursor()
                cur.execute(
                    "UPDATE participants SET bike_day2_handicap_s=%s WHERE id=%s",
                    (handicap, pid),
                )

            cp_times = result.checkpoint_times.get(cp_key, {})
            for (stage, seq), cumulative_s in cp_times.items():
                cp_id = cp_id_map.get((stage, seq))
                if cp_id is None:
                    log.warning(f"No checkpoint for stage={stage} seq={seq}")
                    continue
                prev_cum = cp_times.get((stage, seq - 1))
                split_s: Optional[int] = None
                if cumulative_s is not None and prev_cum is not None:
                    split_s = cumulative_s - prev_cum
                elif cumulative_s is not None and seq == 1:
                    split_s = cumulative_s
                upsert_checkpoint_time(conn, pid, cp_id, cumulative_s, split_s)
                inserted_times += 1

            for zone, dur in result.transitions.get(cp_key, {}).items():
                upsert_transition(conn, pid, zone, dur)

        # --- Пересчитать тоталы/ранги/рекорды (общая функция с live-путём Copernico) ---
        participants_meta: list[dict] = []
        pid_cp_times: dict[int, dict] = {}
        for p in result.participants:
            cp_key = p.get("_cp_key", p["bib"])
            pid = cp_key_to_pid[cp_key]
            participants_meta.append({**p, "id": pid})
            pid_cp_times[pid] = result.checkpoint_times.get(cp_key, {})

        recompute_totals_ranks_records(conn, result.race_year, participants_meta, pid_cp_times)

        return {
            "ok":               True,
            "participants":     inserted_parts,
            "checkpoint_times": inserted_times,
        }

    except Exception as e:
        log.error(f"apply_to_db error: {e}")
        return {"ok": False, "error": str(e)}
    finally:
        conn.close()
