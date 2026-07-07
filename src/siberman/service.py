"""
Сервисный слой: ParseResult → БД.
Вызывается из admin-роута после подтверждения превью.
"""
import logging
from typing import Optional

from src.siberman.db import (
    get_siberman_connection, get_checkpoints, clear_race_year,
    upsert_participant, upsert_checkpoint_time, upsert_transition,
    upsert_stage_total, upsert_overall_result,
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
    bike_day2 — последний cp bike_day2 (уже чистое время, гандикап вычтен
                организатором / парсером перед записью в БД).
    run       — последний cp run (накоп. от старта 3-го дня).
    """
    swim = _last_cp(cp_times, "swim")
    bike1_abs = _last_cp(cp_times, "bike_day1")
    bike1 = (bike1_abs - swim) if bike1_abs is not None and swim is not None else None
    bike2 = _last_cp(cp_times, "bike_day2")
    run   = _last_cp(cp_times, "run")
    return {"swim": swim, "bike_day1": bike1, "bike_day2": bike2, "run": run}


def compute_overall(stage_totals: dict[str, Optional[int]]) -> Optional[int]:
    """Общее чистое время = сумма всех этапов (None если хоть один этап DNF)."""
    vals = [stage_totals.get(s) for s in ("swim", "bike_day1", "bike_day2", "run")]
    if any(v is None for v in vals):
        return None
    return sum(vals)  # type: ignore[arg-type]


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
                "gender":   "—" if p["format"] == "relay" else p["gender"],
                "format":   p["format"],
                "status":   p["status"],
                "cp_count": sum(
                    1 for v in result.checkpoint_times.get(p["bib"], {}).values()
                    if v is not None
                ),
            }
            for p in result.participants
        ],
        "errors": result.errors,
    }


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

        bib_to_pid: dict[str, int] = {}
        inserted_parts = 0
        inserted_times = 0

        for p in result.participants:
            pid = upsert_participant(conn, p)
            bib_to_pid[p["bib"]] = pid
            inserted_parts += 1

            handicap = result.handicaps.get(p["bib"])
            if handicap is not None:
                cur = conn.cursor()
                cur.execute(
                    "UPDATE participants SET bike_day2_handicap_s=%s WHERE id=%s",
                    (handicap, pid),
                )

            cp_times = result.checkpoint_times.get(p["bib"], {})
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

            for zone, dur in result.transitions.get(p["bib"], {}).items():
                upsert_transition(conn, pid, zone, dur)

        # --- Вычислить тоталы и ранги ---
        pid_totals: dict[int, dict] = {}
        pid_meta:   dict[int, dict] = {}
        for p in result.participants:
            pid = bib_to_pid[p["bib"]]
            cp_times = result.checkpoint_times.get(p["bib"], {})
            st = compute_stage_totals(cp_times)
            pid_totals[pid] = {**st, "overall": compute_overall(st)}
            pid_meta[pid]   = {"gender": p["gender"], "format": p["format"]}

        indiv  = [pid for pid, m in pid_meta.items() if m["format"] == "individual"]
        male   = [pid for pid in indiv if pid_meta[pid]["gender"] == "M"]
        female = [pid for pid in indiv if pid_meta[pid]["gender"] == "F"]

        for stage in ("swim", "bike_day1", "bike_day2", "run"):
            s_ranks = rank_by({pid: pid_totals[pid][stage] for pid in indiv})
            g_ranks = {
                **rank_by({pid: pid_totals[pid][stage] for pid in male}),
                **rank_by({pid: pid_totals[pid][stage] for pid in female}),
            }
            for pid in indiv:
                total_s = pid_totals[pid][stage]
                pace, speed = compute_metrics(stage, total_s)
                upsert_stage_total(
                    conn, pid, stage, total_s,
                    rank_stage=s_ranks[pid],
                    rank_gender=g_ranks.get(pid),
                    avg_pace_s=pace,
                    avg_speed_kmh=speed,
                )

        o_ranks = rank_by({pid: pid_totals[pid]["overall"] for pid in indiv})
        go_ranks = {
            **rank_by({pid: pid_totals[pid]["overall"] for pid in male}),
            **rank_by({pid: pid_totals[pid]["overall"] for pid in female}),
        }
        for pid in indiv:
            upsert_overall_result(
                conn, pid,
                total_s=pid_totals[pid]["overall"],
                rank_overall=o_ranks[pid],
                rank_gender=go_ranks.get(pid),
                rank_relay=None,
            )

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
