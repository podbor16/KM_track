"""
Сборка live-JSON топ-10 участников по контрольным точкам для трансляции
Жары (5 км/21.1 км). Источник данных — таблица results, которую в реальном
времени населяет load_race_results.py --continuous (см. RaceLoader.
_maybe_write_broadcast_json() в load_race_results.py — точка вызова).

"Официальное" время/место на отметке = чистое время (time_clear_kt*,
rank_absolute_kt*/rank_sex_kt*) — на уровне промежуточных КТ в БД вообще
нет gun-time варианта, только на старте/финише. Для финиша сознательно
берутся _clean-поля (rank_absolute_clean/rank_sex_clean/
finish_pace_avg_clean), а не обычные rank_absolute/rank_sex — Жара в этом
сезоне награждает по чистому времени (см. коммит 9b1d549).

Полная схема JSON и обоснования решений — в
docs/superpowers/specs/2026-08-18-zhara-live-top10-broadcast-json-design.md.
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

PARTICIPANT_PHOTO_PLACEHOLDER_URL = (
    "https://results.krasmarafon.ru/static/images/krasmarafon/participant-placeholder.png"
)

_TOP_N = 10


def _td_to_seconds(value) -> Optional[float]:
    """MySQL TIME-поля (mysql-connector) приходят как datetime.timedelta,
    не строки — в отличие от load_race_results.py, который сам форматирует
    время в строки ПЕРЕД записью в БД. Здесь мы читаем уже сохранённые
    значения заново через отдельный SELECT, получая сырой driver-тип."""
    if value is None:
        return None
    if isinstance(value, timedelta):
        return value.total_seconds()
    return None


def _seconds_to_hms(seconds: float) -> str:
    total = int(round(seconds))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _seconds_to_pace_str(seconds: float) -> str:
    total = int(round(seconds))
    m, s = divmod(total, 60)
    return f"{m}:{s:02d}"


def _format_gap(seconds: float) -> str:
    """+ММ:СС (+ЧЧ:ММ:СС если ≥ часа), "Лидер" у первого места (0 или
    отрицательное — защита от погрешности округления при сравнении лидера
    с самим собой)."""
    if seconds <= 0:
        return "Лидер"
    total = int(round(seconds))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h > 0:
        return f"+{h:02d}:{m:02d}:{s:02d}"
    return f"+{m:02d}:{s:02d}"


def _forecast_finish_seconds(
    time_clear_seconds: float, pace_avg_seconds_per_km: Optional[float], remaining_km: float,
) -> Optional[float]:
    """Прогноз финишного времени (elapsed/чистое, БЕЗ астрономического
    времени) — линейная экстраполяция среднего темпа с начала гонки
    (тот же темп, что уже даёт pace_avg_kt* в БД) на оставшуюся дистанцию.
    None, если темп неизвестен — отсутствие прогноза, не "прогноз
    совпадает с текущим временем"."""
    if pace_avg_seconds_per_km is None:
        return None
    return time_clear_seconds + remaining_km * pace_avg_seconds_per_km


def _sex_code(sex_ru: str) -> str:
    return "M" if sex_ru == "Мужчина" else "F"


def _format_distance_label(distance_km: float) -> str:
    return f"{distance_km:g} км"


def _query_checkpoint_rows(
    connection, event_id: int, time_col: str, rank_abs_col: str,
    rank_sex_col: str, pace_col: str, sex_filter: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Столбцы (time_col/rank_abs_col/...) — не пользовательский ввод, один
    из фиксированного набора имён вида time_clear_kt1..kt6/time_clear_finish,
    которые формирует только generate_top10_json() ниже — параметризовать
    их через placeholder нельзя (это имена колонок, не значения)."""
    cur = connection.cursor(dictionary=True)
    try:
        params: List[Any] = [event_id]
        sex_clause = ""
        if sex_filter:
            sex_clause = "AND r.sex = %s"
            params.append(sex_filter)
        query = (
            f"SELECT r.start_number, r.surname, r.name, r.sex, c.city, "
            f"       r.{rank_abs_col} AS rank_absolute, r.{rank_sex_col} AS rank_sex, "
            f"       r.{time_col} AS time_clear, r.{pace_col} AS pace_avg "
            f"FROM results r "
            f"LEFT JOIN clients c ON c.id = r.client_id "
            f"WHERE r.event_id = %s AND r.{time_col} IS NOT NULL {sex_clause} "
            # Сортировка по TIME-колонке, а НЕ по rank_absolute_kt*/rank_sex_kt*:
            # в реальной схеме БД rank_absolute_kt6/kt7 — VARCHAR(50), не INT,
            # сортировка по ним лексикографическая ("10" < "2") и даёт неверный
            # порядок. Сортировка по time_col корректна всегда.
            f"ORDER BY r.{time_col} ASC "
            f"LIMIT {_TOP_N}"
        )
        cur.execute(query, params)
        rows = cur.fetchall()
    finally:
        cur.close()
    return rows


def _build_checkpoint(
    connection, event_id: int, code: str, label: str, time_col: str,
    rank_abs_col: str, rank_sex_col: str, pace_col: str,
    photo_map: Dict[int, str], remaining_km: Optional[float] = None,
) -> Dict[str, Any]:
    abs_rows = _query_checkpoint_rows(connection, event_id, time_col, rank_abs_col, rank_sex_col, pace_col)
    male_rows = _query_checkpoint_rows(connection, event_id, time_col, rank_abs_col, rank_sex_col, pace_col, sex_filter="Мужчина")
    female_rows = _query_checkpoint_rows(connection, event_id, time_col, rank_abs_col, rank_sex_col, pace_col, sex_filter="Женщина")

    leader_abs_s = _td_to_seconds(abs_rows[0]["time_clear"]) if abs_rows else None
    leader_male_s = _td_to_seconds(male_rows[0]["time_clear"]) if male_rows else None
    leader_female_s = _td_to_seconds(female_rows[0]["time_clear"]) if female_rows else None

    def build_list(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        result = []
        for rec in rows:
            seconds = _td_to_seconds(rec["time_clear"])
            leader_sex_s = leader_male_s if rec["sex"] == "Мужчина" else leader_female_s
            pace_seconds = _td_to_seconds(rec["pace_avg"])
            entry = {
                "start_number": rec["start_number"],
                "surname": rec["surname"],
                "name": rec["name"],
                "sex": _sex_code(rec["sex"]),
                "city": rec.get("city") or "",
                "rank_absolute": int(rec["rank_absolute"]) if rec["rank_absolute"] is not None else None,
                "rank_sex": int(rec["rank_sex"]) if rec["rank_sex"] is not None else None,
                "time": _seconds_to_hms(seconds),
                "pace": _seconds_to_pace_str(pace_seconds) if pace_seconds is not None else None,
                "gap_absolute": _format_gap(seconds - leader_abs_s) if leader_abs_s is not None else "Лидер",
                "gap_sex": _format_gap(seconds - leader_sex_s) if leader_sex_s is not None else "Лидер",
                "photo_url": photo_map.get(rec["start_number"], PARTICIPANT_PHOTO_PLACEHOLDER_URL),
            }
            if remaining_km is not None:
                forecast_seconds = _forecast_finish_seconds(seconds, pace_seconds, remaining_km)
                if forecast_seconds is not None:
                    entry["forecast_finish_time"] = _seconds_to_hms(forecast_seconds)
            result.append(entry)
        return result

    return {
        "code": code,
        "label": label,
        "top10_absolute": build_list(abs_rows),
        "top10_male": build_list(male_rows),
        "top10_female": build_list(female_rows),
    }


def _load_photo_map(connection, event_id: int) -> Dict[int, str]:
    cur = connection.cursor(dictionary=True)
    try:
        cur.execute(
            "SELECT start_number, photo_url FROM participant_photos WHERE event_id = %s",
            (event_id,),
        )
        rows = cur.fetchall()
    finally:
        cur.close()
    return {r["start_number"]: r["photo_url"] for r in rows}


def generate_top10_json(connection, event_id: int, output_path: str) -> None:
    """Собирает live-топ-10 по всем отметкам события event_id и атомарно
    перезаписывает JSON-файл по пути output_path (полностью пишет во
    временный файл, затем os.replace() — читающая сторона никогда не видит
    файл в момент записи наполовину)."""
    cur = connection.cursor(dictionary=True)
    try:
        cur.execute(
            "SELECT event_name, event_distance, event_year, checkpoint_distances "
            "FROM events WHERE id = %s",
            (event_id,),
        )
        event = cur.fetchone()
    finally:
        cur.close()
    if not event:
        raise ValueError(f"event_id={event_id} не найден в events")

    checkpoint_distances = (
        json.loads(event["checkpoint_distances"]) if event["checkpoint_distances"] else []
    )
    num_kt = max(0, len(checkpoint_distances) - 2)

    photo_map = _load_photo_map(connection, event_id)

    checkpoints = []
    for i in range(1, num_kt + 1):
        checkpoints.append(_build_checkpoint(
            connection, event_id,
            code=f"kt{i}", label=f"КТ{i} ({checkpoint_distances[i]} км)",
            time_col=f"time_clear_kt{i}", rank_abs_col=f"rank_absolute_kt{i}",
            rank_sex_col=f"rank_sex_kt{i}", pace_col=f"pace_avg_kt{i}",
            photo_map=photo_map,
            remaining_km=float(event["event_distance"]) - checkpoint_distances[i],
        ))

    checkpoints.append(_build_checkpoint(
        connection, event_id,
        code="finish", label="Финиш",
        time_col="time_clear_finish", rank_abs_col="rank_absolute_clean",
        rank_sex_col="rank_sex_clean", pace_col="finish_pace_avg_clean",
        photo_map=photo_map,
    ))

    data = {
        "event_name": event["event_name"],
        "event_year": event["event_year"],
        "distance": _format_distance_label(float(event["event_distance"])),
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "checkpoints": checkpoints,
    }

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    tmp_path = output_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, output_path)
