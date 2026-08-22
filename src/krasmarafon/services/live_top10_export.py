"""
Сборка live-JSON топ-3 (муж/жен) по контрольным точкам для трансляции
Жары (5 км/21.1 км). Источник данных — таблица results, которую в реальном
времени населяет load_race_results.py --continuous (см. RaceLoader.
_maybe_write_broadcast_json() в load_race_results.py — точка вызова).

Минимальная схема по запросу режиссёра трансляции (2026-08-22): для
каждой отметки — top-3 мужчины и top-3 женщины, поля только "Фамилия Имя"
и время прохождения отметки. Более широкая схема (места, темп, отставание,
фото) была раньше — упрощена по прямому запросу, см. историю коммитов.

"Официальное" время на отметке = чистое время (time_clear_kt*) — на
уровне промежуточных КТ в БД вообще нет gun-time варианта, только на
старте/финише. Для финиша сознательно берётся time_clear_finish — Жара
в этом сезоне награждает по чистому времени (см. коммит 9b1d549).
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

_TOP_N = 3


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


def _seconds_to_time_str(seconds: float) -> str:
    """secs → 'H:MM:SS' (или 'MM:SS', если меньше часа) — единый формат
    времени по всему проекту (см. format_finish_time в diploma_service.py)."""
    total = int(round(seconds))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _format_distance_label(distance_km: float) -> str:
    return f"{distance_km:g} км"


def _query_top3(connection, event_id: int, time_col: str, sex: str) -> List[Dict[str, Any]]:
    """time_col — не пользовательский ввод, один из фиксированного набора
    имён вида time_clear_kt1..kt6/time_clear_finish, которые формирует
    только generate_top10_json() ниже — параметризовать его через
    placeholder нельзя (это имя колонки, не значение)."""
    cur = connection.cursor(dictionary=True)
    try:
        cur.execute(
            f"SELECT surname, name, {time_col} AS time_clear "
            f"FROM results "
            f"WHERE event_id = %s AND sex = %s AND {time_col} IS NOT NULL "
            f"ORDER BY {time_col} ASC "
            f"LIMIT {_TOP_N}",
            (event_id, sex),
        )
        rows = cur.fetchall()
    finally:
        cur.close()
    return rows


def _build_checkpoint(connection, event_id: int, code: str, label: str, time_col: str) -> Dict[str, Any]:
    def build_list(sex: str) -> List[Dict[str, Any]]:
        rows = _query_top3(connection, event_id, time_col, sex)
        return [
            {
                "full_name": f"{rec['surname']} {rec['name']}".strip(),
                "time": _seconds_to_time_str(_td_to_seconds(rec["time_clear"])),
            }
            for rec in rows
        ]

    return {
        "code": code,
        "label": label,
        "top3_male": build_list("Мужчина"),
        "top3_female": build_list("Женщина"),
    }


def generate_top10_json(connection, event_id: int, output_path: str) -> None:
    """Собирает live-топ-3 (муж/жен) по всем отметкам события event_id и
    атомарно перезаписывает JSON-файл по пути output_path (полностью
    пишет во временный файл, затем os.replace() — читающая сторона
    никогда не видит файл в момент записи наполовину)."""
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

    checkpoints = []
    for i in range(1, num_kt + 1):
        checkpoints.append(_build_checkpoint(
            connection, event_id,
            code=f"kt{i}", label=f"КТ{i} ({checkpoint_distances[i]} км)",
            time_col=f"time_clear_kt{i}",
        ))

    checkpoints.append(_build_checkpoint(
        connection, event_id,
        code="finish", label="Финиш",
        time_col="time_clear_finish",
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
