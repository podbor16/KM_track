"""
Сервисный слой: ParseResult → БД.
Вызывается из admin-роута после подтверждения превью.
"""
import logging
from typing import Optional

from src.siberman.db import (
    get_siberman_connection, get_checkpoints, clear_race_year,
    upsert_participant, upsert_checkpoint_time, upsert_transition,
)
from src.siberman.parser import ParseResult

log = logging.getLogger(__name__)


def format_seconds(s: Optional[int]) -> str:
    if s is None:
        return "—"
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}"


def format_pace(s: Optional[int]) -> str:
    """s — секунды на км."""
    if s is None:
        return "—"
    return f"{s // 60}:{s % 60:02d}"


def compute_split_times(cumulative: list[Optional[int]]) -> list[Optional[int]]:
    """Вычислить сплиты из накопленных времён.

    Если в середине встречается None — все последующие сплиты тоже None
    (пропущенный чекпоинт делает дальнейшие сплиты бессмысленными).
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


def build_preview(result: ParseResult) -> dict:
    """Сформировать preview для отображения в admin UI перед сохранением."""
    return {
        "race_year":         result.race_year,
        "participant_count": len(result.participants),
        "participants": [
            {
                "bib":      p["bib"],
                "name":     f"{p['surname']} {p['name']}",
                "gender":   p["gender"],
                "format":   p["format"],
                "status":   p["status"],
                "cp_count": len(result.checkpoint_times.get(p["bib"], {})),
            }
            for p in result.participants
        ],
        "errors": result.errors,
    }


def apply_to_db(result: ParseResult) -> dict:
    """
    Записать ParseResult в БД:
    1. Удалить все данные за год
    2. Upsert участников
    3. Upsert checkpoint_times
    4. Upsert transitions
    Возвращает summary dict.
    """
    conn = get_siberman_connection()
    if conn is None:
        return {"ok": False, "error": "DB connection failed"}

    try:
        checkpoints = get_checkpoints(conn, result.race_year)
        cp_id_map: dict[tuple[str, int], int] = {
            (row["stage"], row["seq"]): row["id"]
            for row in checkpoints
        }

        clear_race_year(conn, result.race_year)

        inserted_parts = 0
        inserted_times = 0

        for p in result.participants:
            pid = upsert_participant(conn, p)
            inserted_parts += 1

            bib = p["bib"]

            # Гандикап
            handicap = result.handicaps.get(bib)
            if handicap is not None:
                cur = conn.cursor()
                cur.execute(
                    "UPDATE participants SET bike_day2_handicap_s=%s WHERE id=%s",
                    (handicap, pid)
                )

            # Чекпоинты
            cp_times = result.checkpoint_times.get(bib, {})
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

            # Транзитные зоны
            for zone, dur in result.transitions.get(bib, {}).items():
                upsert_transition(conn, pid, zone, dur)

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
