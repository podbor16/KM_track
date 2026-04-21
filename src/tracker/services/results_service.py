"""
Сервис для получения и расчёта результатов события.
Содержит бизнес-логику эндпоинта /api/event-results.
"""

import logging
import time
from typing import Optional
from datetime import datetime, date, timezone

from src.config.event_loader import EventConfig, get_event_by_name
from src.tracker.models.analytics import RaceResultsResponse

logger = logging.getLogger(__name__)

# Кэш исторических данных (прошлый год)
_hist_cache: dict = {}
_hist_cache_ts: dict = {}
HIST_CACHE_TTL = 600  # 10 минут — пересоздаём кэш если данные устарели


def _kt_pace(kt_time_td, checkpoint_distances: list, kt_idx: int) -> Optional[str]:
    """On-the-fly расчёт темпа КТ если pace_avg_ktN = NULL в БД."""
    from datetime import timedelta
    if not isinstance(kt_time_td, timedelta):
        return None
    if kt_idx >= len(checkpoint_distances) or checkpoint_distances[kt_idx] <= 0:
        return None
    secs = kt_time_td.total_seconds()
    secs_per_km = secs / checkpoint_distances[kt_idx]
    m, s = int(secs_per_km // 60), int(secs_per_km % 60)
    return f"{m}:{s:02d}"


def build_event_results(
    event_id: Optional[int],
    event_name: Optional[str],
    year: Optional[int],
    events: dict[str, EventConfig],
) -> RaceResultsResponse:
    """
    Возвращает результаты события из БД с live-позициями и историческим кешем.

    Args:
        event_id: ID события в БД (приоритет над event_name)
        event_name: Название события (используется если event_id не задан)
        year: Год события
        events: Словарь EventConfig из settings.EVENTS

    Returns:
        RaceResultsResponse — полный список участников с live-данными
    """
    import json as _json
    from datetime import timedelta as _td
    from src.analytics.db_connection_optimized import (
        get_race_results_by_event_id,
        get_race_results_by_event_id_and_year,
        get_event_info_by_id,
        get_event_info,
        get_category_avg_paces,
        get_prev_year_results,
    )
    from src.tracker.services.runners_service import calculate_live_position
    from src.tracker.services.pace_calculator import parse_pace_to_kmh
    from fastapi import HTTPException

    server_time_unix = int(time.time() * 1000)
    current_year = datetime.now().year

    # --- Загрузка результатов из БД ---
    if event_id:
        logger.info(f"Загрузка результатов для event_id={event_id}")
        results_data = get_race_results_by_event_id(event_id)
    elif event_name and year:
        logger.info(f"Загрузка результатов для {event_name} {year}")
        results_data = get_race_results_by_event_id_and_year(event_name, year)
    else:
        raise HTTPException(status_code=400, detail="Укажите event_id или event_name + year")

    # --- Данные события для live-расчётов ---
    if event_id:
        ev_info = get_event_info_by_id(event_id) or {}
    else:
        ev_info = get_event_info(event_name, year or current_year) or {}

    race_date = ev_info.get('event_date') or date.today()
    ev_name = ev_info.get('event_name', event_name or '')
    ev_distance = ev_info.get('event_distance')
    ev_year = ev_info.get('event_year', current_year)

    # --- gun_start_dt из gun_time_utc в БД ---
    gun_start_dt = None
    race_gun_unix_ms = None
    _gun_utc = ev_info.get('gun_time_utc')
    if _gun_utc:
        try:
            _gun_aware = datetime.fromisoformat(_gun_utc.replace('Z', '+00:00'))
            race_gun_unix_ms = int(_gun_aware.timestamp() * 1000)
            gun_start_dt = _gun_aware.astimezone().replace(tzinfo=None)
        except Exception as _ge:
            logger.debug(f"gun_time_utc parse failed: {_ge}")

    # Контрольные точки: из БД или расчётные
    raw_cp = ev_info.get('checkpoint_distances')
    if raw_cp:
        checkpoint_distances = (
            [float(x) for x in raw_cp]
            if isinstance(raw_cp, list)
            else [float(x) for x in _json.loads(raw_cp)]
        )
    else:
        # Пробуем взять из YAML
        event_cfg_match = get_event_by_name(events, ev_name)
        if event_cfg_match:
            tracked = event_cfg_match.get_tracked()
            if tracked and tracked.checkpoint_distances:
                checkpoint_distances = tracked.checkpoint_distances
            else:
                total_km = float(ev_distance) if ev_distance else 5.0
                checkpoint_distances = [0.0, total_km]
        else:
            total_km = float(ev_distance) if ev_distance else 5.0
            checkpoint_distances = [0.0, total_km]

    category_speeds = get_category_avg_paces(ev_name, ev_distance, ev_year) if ev_name else {}

    # --- Исторический кеш (предыдущий год) ---
    cache_key = f"{ev_name}|{ev_distance}|{ev_year}"
    _now_ts = time.time()
    _cache_stale = (_now_ts - _hist_cache_ts.get(cache_key, 0)) > HIST_CACHE_TTL
    if cache_key not in _hist_cache or not _hist_cache[cache_key].get('populated') or _cache_stale:
        prev_year = (ev_year or current_year) - 1
        prev_rows = get_prev_year_results(ev_name, str(ev_distance) if ev_distance is not None else '', prev_year) if ev_name else []
        personal: dict = {}
        cat_raw: dict = {}
        for row in prev_rows:
            bday = row.get('birthday')
            bday_str = bday.isoformat() if hasattr(bday, 'isoformat') else str(bday or '')
            key = f"{(row.get('surname') or '').strip()}|{(row.get('name') or '').strip()}|{bday_str}".upper()
            pace_val = row.get('finish_pace_avg_clean')
            if isinstance(pace_val, _td):
                _s = int(pace_val.total_seconds())
                pace_val = f"{_s // 60}:{_s % 60:02d}"
            spd = parse_pace_to_kmh(str(pace_val) if pace_val else '')
            if spd > 0:
                personal[key] = spd
            cat = (row.get('category') or '').strip().split(' (')[0].strip()
            if cat and spd > 0:
                cat_raw.setdefault(cat, []).append(spd)
        _hist_cache[cache_key] = {
            'personal': personal,
            'category_avg': {c: sum(v) / len(v) for c, v in cat_raw.items()},
            'prev_year': prev_year,
            'populated': bool(prev_rows),
        }
        if prev_rows:
            _hist_cache_ts[cache_key] = _now_ts
        logger.info(
            f"Исторические данные загружены: {len(personal)} личных, "
            f"{len(cat_raw)} категорий за {prev_year} год"
        )
    hist_data = _hist_cache[cache_key]

    # --- Формирование результатов ---
    results = []
    _debug_count = 0
    for runner in results_data:
        bday = runner.get('birthday')
        bday_str = bday.isoformat() if hasattr(bday, 'isoformat') else str(bday or '')
        runner_key = f"{(runner.get('surname') or '').strip()}|{(runner.get('name') or '').strip()}|{bday_str}".upper()

        cat_norm = (runner.get('category') or '').strip().split(' (')[0].strip()
        if runner_key in hist_data['personal']:
            r_hist_speed = hist_data['personal'][runner_key]
            r_hist_source = 'personal'
        elif cat_norm in hist_data['category_avg']:
            r_hist_speed = hist_data['category_avg'][cat_norm]
            r_hist_source = 'category'
        else:
            r_hist_speed = None
            r_hist_source = None

        try:
            speed_kmh, current_dist, pace_str = calculate_live_position(
                runner, checkpoint_distances, race_date, category_speeds,
                hist_speed=r_hist_speed,
                gun_start_dt=gun_start_dt,
            )
        except Exception as _e:
            logger.warning(f"calculate_live_position error for runner {runner.get('id')}: {_e}")
            speed_kmh, current_dist, pace_str = 10.0, 0.0, "6:00"

        if runner.get('time_clear_finish') or runner.get('time_clear_kt1'):
            pace_source = ''
        else:
            pace_source = r_hist_source or ''
            if _debug_count < 20 and runner.get('race_status') == 'Running':
                logger.info(
                    f"[DEBUG] #{runner.get('start_number')} {runner.get('surname')} {runner.get('name')}: "
                    f"cat='{cat_norm}' "
                    f"hist={f'{r_hist_speed:.2f}' if r_hist_speed else 'None'} ({r_hist_source}), "
                    f"speed={speed_kmh:.2f}, pace={pace_str}"
                )
                _debug_count += 1

        results.append({
            'id': runner.get('id') or runner.get('client_id'),
            'start_number': runner.get('start_number'),
            'surname': runner.get('surname', ''),
            'name': runner.get('name', ''),
            'full_name': f"{runner.get('surname', '')} {runner.get('name', '')}".strip(),
            'sex': runner.get('sex'),
            'category': runner.get('category'),
            'birthday': runner.get('birthday'),
            'race_status': runner.get('race_status'),
            'status': runner.get('race_status'),
            'rank_absolute': runner.get('rank_absolute'),
            'rank_sex': runner.get('rank_sex'),
            'rank_category': runner.get('rank_category'),
            'rank_absolute_clean': runner.get('rank_absolute_clean'),
            'rank_sex_clean': runner.get('rank_sex_clean'),
            'rank_category_clean': runner.get('rank_category_clean'),
            'time_gun_finish': runner.get('time_gun_finish'),
            'time_clear_finish': runner.get('time_clear_finish'),
            'finish_pace_avg': runner.get('finish_pace_avg'),
            'distance': runner.get('distance', runner.get('distance_from_event', '5 км')),
            'event': runner.get('distance', runner.get('distance_from_event', '5 км')),
            'checkpoints': {
                'kt1': {'time': runner.get('time_clear_kt1'), 'pace': runner.get('pace_avg_kt1') or _kt_pace(runner.get('time_clear_kt1'), checkpoint_distances, 1)},
                'kt2': {'time': runner.get('time_clear_kt2'), 'pace': runner.get('pace_avg_kt2') or _kt_pace(runner.get('time_clear_kt2'), checkpoint_distances, 2)},
                'kt3': {'time': runner.get('time_clear_kt3'), 'pace': runner.get('pace_avg_kt3') or _kt_pace(runner.get('time_clear_kt3'), checkpoint_distances, 3)},
                'kt4': {'time': runner.get('time_clear_kt4'), 'pace': runner.get('pace_avg_kt4') or _kt_pace(runner.get('time_clear_kt4'), checkpoint_distances, 4)},
                'kt5': {'time': runner.get('time_clear_kt5'), 'pace': runner.get('pace_avg_kt5') or _kt_pace(runner.get('time_clear_kt5'), checkpoint_distances, 5)},
            },
            'speed': round(speed_kmh, 2),
            'current_distance': round(current_dist, 3),
            'current_pace': pace_str,
            'pace_source': pace_source,
            'prev_year': hist_data['prev_year'],
            'time_clear_start_s': (
                int(runner.get('time_clear_start').total_seconds())
                if isinstance(runner.get('time_clear_start'), _td) else None
            ),
        })

    # --- YAML fallback для race_gun_unix_ms если в БД нет gun_time_utc ---
    if race_gun_unix_ms is None:
        event_cfg_match = get_event_by_name(events, ev_name)
        if event_cfg_match and event_cfg_match.gun_time and race_date:
            try:
                _rd = race_date if isinstance(race_date, date) else date.today()
                _gun_dt = datetime.combine(
                    _rd, datetime.strptime(event_cfg_match.gun_time, '%H:%M:%S').time()
                )
                race_gun_unix_ms = int(_gun_dt.timestamp() * 1000)
            except Exception as _ge:
                logger.debug(f"gun_time YAML parse failed: {_ge}")

    return RaceResultsResponse(
        event=ev_name or f"event_{event_id}",
        total_results=len(results_data),
        results=results,
        timestamp=datetime.now().isoformat(),
        server_time_unix=server_time_unix,
        race_gun_unix_ms=race_gun_unix_ms,
    )
