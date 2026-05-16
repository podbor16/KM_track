"""
Сервис управления участниками гонки
"""

import logging
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def _time_field_to_datetime(race_date: date, t) -> Optional[datetime]:
    """
    Конвертирует поле TIME из mysql-connector (timedelta) в datetime.
    mysql-connector возвращает TIME-колонки как datetime.timedelta.
    """
    if t is None:
        return None
    if isinstance(t, timedelta):
        return datetime.combine(race_date, datetime.min.time()) + t
    if isinstance(t, datetime):
        return t
    try:
        return datetime.combine(race_date, t)
    except Exception:
        return None


def _timedelta_to_hours(td) -> float:
    """Конвертирует timedelta в часы. Возвращает 0.0 если не timedelta."""
    if isinstance(td, timedelta):
        return td.total_seconds() / 3600.0
    return 0.0


def _kmh_to_pace_str(kmh: float) -> str:
    """10.0 км/ч → '6:00'. Возвращает '6:00' при ошибке."""
    if kmh <= 0:
        return "6:00"
    secs_per_km = 3600.0 / kmh
    minutes = int(secs_per_km // 60)
    seconds = int(secs_per_km % 60)
    return f"{minutes}:{seconds:02d}"


def calculate_live_position(
    result: Dict,
    checkpoint_distances: List[float],
    race_date: date,
    category_speeds: Dict[str, float],
    hist_speed: Optional[float] = None,
    gun_start_dt: Optional[datetime] = None,
) -> Tuple[float, float, str]:
    """
    Рассчитывает текущую скорость, дистанцию и темп участника в live-режиме.

    Логика:
    - Финишировал: speed=0, dist=total
    - До первой КТ (time_clear_kt1 IS NULL):
        speed = среднее по категории (из category_speeds)
        dist  = speed * elapsed_since_start, ограничена checkpoint_distances[1]
    - После КТn (time_clear_ktN NOT NULL):
        speed = checkpoint_distances[N] / time_clear_ktN_in_hours  (фактическая скорость)
        dist  = checkpoint_distances[N] + speed * elapsed_since_ktN
        pace  = time_clear_ktN_seconds / checkpoint_distances[N]  в формате "м:сс"

    Args:
        result:               строка из таблицы results (dict)
        checkpoint_distances: [0.0, kt1_km, kt2_km, ..., finish_km]
        race_date:            дата проведения забега (datetime.date)
        category_speeds:      {category: avg_speed_kmh}

    Returns:
        Кортеж (speed_kmh, current_distance_km, pace_str)
    """
    DEFAULT_SPEED = 10.0
    DEFAULT_PACE = "6:00"

    now = datetime.now()
    total_distance = checkpoint_distances[-1] if checkpoint_distances else 5.0

    # --- Финишировал ---
    if result.get('time_clear_finish'):
        finish_pace = result.get('finish_pace_avg_clean') or result.get('finish_pace_avg') or DEFAULT_PACE
        if isinstance(finish_pace, timedelta):
            _s = int(finish_pace.total_seconds())
            finish_pace = f"{_s // 60}:{_s % 60:02d}"
        return 0.0, total_distance, str(finish_pace) if finish_pace else DEFAULT_PACE

    # --- Не стартовал (нет времени старта) ---
    start_td = result.get('time_clear_start')
    if gun_start_dt is not None:
        # Используем точное UTC-время выстрела + задержку старта участника
        delay = start_td if isinstance(start_td, timedelta) else timedelta(0)
        start_dt = gun_start_dt + delay
    else:
        start_dt = _time_field_to_datetime(race_date, start_td)
    if start_dt is None:
        return DEFAULT_SPEED, 0.0, DEFAULT_PACE

    # --- Определяем последнюю пройденную КТ ---
    kt_keys = ['kt1', 'kt2', 'kt3', 'kt4', 'kt5', 'kt6', 'kt7']
    last_kt_idx = 0
    last_kt_td = None

    for i, kt in enumerate(kt_keys):
        kt_time = result.get(f'time_clear_{kt}')
        cp_idx = i + 1
        if kt_time is not None and cp_idx < len(checkpoint_distances):
            last_kt_idx = cp_idx
            last_kt_td = kt_time

    # --- До первой КТ: исторический или категорийный темп ---
    if last_kt_idx == 0:
        if hist_speed and hist_speed > 0:
            speed_kmh = hist_speed
        else:
            category = (result.get('category') or '').strip()
            speed_kmh = category_speeds.get(category, DEFAULT_SPEED)
            if speed_kmh <= 0:
                speed_kmh = DEFAULT_SPEED

        elapsed_hours = max(0.0, (now - start_dt).total_seconds() / 3600.0)
        # Без кэпа на КТ: маркер движется непрерывно по маршруту.
        # Телепорт на КТ произойдёт когда фактическое время КТ появится в БД.
        current_distance = min(speed_kmh * elapsed_hours, total_distance)
        return speed_kmh, current_distance, _kmh_to_pace_str(speed_kmh)

    # --- После КТN: скорость по последнему участку (при ≥2 КТ) или кумулятивная ---
    kt_dist = checkpoint_distances[last_kt_idx]
    kt_hours = _timedelta_to_hours(last_kt_td)

    if last_kt_idx >= 2:
        # Темп последнего участка от фактической предыдущей КТ с данными
        prev_kt_td = None
        prev_kt_dist = 0.0
        for _pi in range(last_kt_idx - 1, 0, -1):
            _candidate = result.get(f'time_clear_kt{_pi}')
            if isinstance(_candidate, timedelta):
                prev_kt_td = _candidate
                prev_kt_dist = checkpoint_distances[_pi] if _pi < len(checkpoint_distances) else 0.0
                break
        if isinstance(prev_kt_td, timedelta):
            seg_dist = kt_dist - prev_kt_dist
            seg_h = _timedelta_to_hours(last_kt_td) - _timedelta_to_hours(prev_kt_td)
            if seg_dist > 0 and seg_h > 0:
                speed_kmh = seg_dist / seg_h
                seg_secs = (last_kt_td - prev_kt_td).total_seconds()
                secs_per_km = seg_secs / seg_dist
            else:
                speed_kmh = kt_dist / kt_hours if kt_hours > 0 and kt_dist > 0 else DEFAULT_SPEED
                kt_sec = last_kt_td.total_seconds() if isinstance(last_kt_td, timedelta) else 0
                secs_per_km = kt_sec / kt_dist if kt_dist > 0 else 360
        else:
            speed_kmh = kt_dist / kt_hours if kt_hours > 0 and kt_dist > 0 else DEFAULT_SPEED
            kt_sec = last_kt_td.total_seconds() if isinstance(last_kt_td, timedelta) else 0
            secs_per_km = kt_sec / kt_dist if kt_dist > 0 else 360
    else:
        # Первая КТ: кумулятив = интервал
        if kt_hours > 0 and kt_dist > 0:
            speed_kmh = kt_dist / kt_hours
            kt_sec = last_kt_td.total_seconds() if isinstance(last_kt_td, timedelta) else 0
            secs_per_km = kt_sec / kt_dist if kt_dist > 0 else 360
        else:
            speed_kmh = DEFAULT_SPEED
            secs_per_km = 360

    mins = int(secs_per_km // 60)
    secs = int(secs_per_km % 60)
    pace_str = f"{mins}:{secs:02d}"

    # JS анимирует от last_kt_unix_ms: distKm = kt_dist + speed × (now − last_kt_unix_ms)
    # Возвращаем позицию AT checkpoint — экстраполяцию делает клиент
    current_distance = kt_dist
    return speed_kmh, current_distance, pace_str
