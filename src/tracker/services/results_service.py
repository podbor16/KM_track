"""
Сервис для получения и расчёта результатов события.
Содержит бизнес-логику эндпоинта /api/event-results.
"""

import logging
import threading
import time
from typing import Optional
from datetime import datetime, date, timezone

from src.config.event_loader import EventConfig, get_event_by_name
from src.tracker.models.analytics import RaceResultsResponse

logger = logging.getLogger(__name__)

# Кэш исторических данных (прошлый год)
_hist_cache: dict = {}
_hist_cache_ts: dict = {}
HIST_CACHE_TTL = 600

# Кэш категорийных темпов (исторические данные — не меняются)
_cat_speeds_cache: dict = {}
_cat_speeds_cache_ts: dict = {}
CAT_SPEEDS_TTL = 600

# Кэш финального ответа build_event_results (включает Python-обработку 1000+ участников)
_response_cache: dict = {}
_response_cache_ts: dict = {}
RESPONSE_CACHE_TTL = 5     # секунд до первого перестроения (live-режим: данные КТ должны быть свежими)
STALE_TTL = 30             # секунд до принудительного синхронного перестроения

# Singleflight: один поток пересчитывает при холодном кеше, остальные ждут
_build_locks: dict = {}
_build_locks_meta = threading.Lock()

# Фоновые перестроения: не запускать второй поток пока первый ещё работает
_rebuild_in_progress: set = set()
_rebuild_progress_lock = threading.Lock()


def _get_cached_category_speeds(ev_name, ev_distance, ev_year) -> dict:
    from src.analytics.db_connection_optimized import get_category_avg_paces
    key = f"{ev_name}|{ev_distance}|{ev_year}"
    _now = time.time()
    if key in _cat_speeds_cache and (_now - _cat_speeds_cache_ts.get(key, 0)) < CAT_SPEEDS_TTL:
        return _cat_speeds_cache[key]
    result = get_category_avg_paces(ev_name, ev_distance, ev_year) if ev_name else {}
    _cat_speeds_cache[key] = result
    _cat_speeds_cache_ts[key] = _now
    return result


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


def _segment_pace(curr_td, prev_td, curr_dist: float, prev_dist: float) -> Optional[str]:
    """Интервальный темп на участке prev→curr (не кумулятивный)."""
    from datetime import timedelta
    if not isinstance(curr_td, timedelta):
        return None
    seg_dist = curr_dist - prev_dist
    if seg_dist <= 0:
        return None
    prev_secs = prev_td.total_seconds() if isinstance(prev_td, timedelta) else 0.0
    seg_time = curr_td.total_seconds() - prev_secs
    if seg_time <= 0:
        return None
    secs_per_km = seg_time / seg_dist
    m, s = int(secs_per_km // 60), int(secs_per_km % 60)
    return f"{m}:{s:02d}"


def _calc_last_kt_unix_ms(runner: dict, gun_start_dt) -> Optional[int]:
    """Unix ms реального времени когда участник прошёл последнюю КТ с данными."""
    from datetime import timedelta
    if gun_start_dt is None:
        return None
    for kt in reversed(['kt1', 'kt2', 'kt3', 'kt4', 'kt5', 'kt6', 'kt7']):
        kt_td = runner.get(f'time_clear_{kt}')
        if isinstance(kt_td, timedelta):
            kt_wall = gun_start_dt + kt_td
            return int(kt_wall.timestamp() * 1000)
    return None


def _find_prev_kt_td_and_dist(runner: dict, current_kt_1based_idx: int, checkpoint_distances: list):
    """Найти предыдущую КТ с данными (не обязательно kt{N-1}). Возвращает (timedelta|None, dist_km)."""
    from datetime import timedelta
    for prev_i in range(current_kt_1based_idx - 1, 0, -1):
        td = runner.get(f'time_clear_kt{prev_i}')
        if isinstance(td, timedelta):
            dist = checkpoint_distances[prev_i] if prev_i < len(checkpoint_distances) else 0.0
            return td, dist
    return None, checkpoint_distances[0] if checkpoint_distances else 0.0


def _build_kt_checkpoints(runner: dict, checkpoint_distances: list) -> dict:
    """Строит словарь kt2..kt7 с interval_pace от фактической предыдущей КТ с данными."""
    result = {}
    for n in range(2, 8):
        prev_td, prev_dist = _find_prev_kt_td_and_dist(runner, n, checkpoint_distances)
        curr_dist = checkpoint_distances[n] if n < len(checkpoint_distances) else 0.0
        result[f'kt{n}'] = {
            'time': runner.get(f'time_clear_kt{n}'),
            'pace': runner.get(f'pace_avg_kt{n}') or _kt_pace(runner.get(f'time_clear_kt{n}'), checkpoint_distances, n),
            'interval_pace': _segment_pace(runner.get(f'time_clear_kt{n}'), prev_td, curr_dist, prev_dist),
        }
    return result


def _calc_lap_from_kts(runner: dict, num_laps: int) -> int:
    """
    Круг по наличию KT-времён. Достаточно любой КТ из пары (чётной или нечётной).
    kt2 или kt3 → круг 2; kt4 или kt5 → круг 3; kt6 или kt7 → круг 4.
    """
    if num_laps <= 1:
        return 1
    def has(n):
        return runner.get(f'time_clear_kt{n}') is not None
    if has(6) or has(7):
        return 4
    if has(4) or has(5):
        return 3
    if has(2) or has(3):
        return 2
    return 1


def _do_build(
    event_id: Optional[int],
    event_name: Optional[str],
    year: Optional[int],
    events: dict,
) -> "RaceResultsResponse":
    """Выполняет сборку ответа: DB-запросы + Python-обработка участников. Без кеш-логики."""
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

    _t0 = time.time()
    server_time_unix = int(time.time() * 1000)
    current_year = datetime.now().year

    # --- Загрузка результатов из БД ---
    _t_db = time.time()
    if event_id:
        results_data = get_race_results_by_event_id(event_id)
    elif event_name and year:
        results_data = get_race_results_by_event_id_and_year(event_name, year)
    else:
        raise HTTPException(status_code=400, detail="Укажите event_id или event_name + year")
    _t_db_done = time.time() - _t_db

    # --- Данные события для live-расчётов ---
    _t_ev = time.time()
    if event_id:
        ev_info = get_event_info_by_id(event_id) or {}
    else:
        ev_info = get_event_info(event_name, year or current_year) or {}
    _t_ev_done = time.time() - _t_ev

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

    category_speeds = _get_cached_category_speeds(ev_name, ev_distance, ev_year)

    # Количество кругов из YAML (для цветовой индикации круга на карте)
    num_laps = 1
    _ev_cfg = get_event_by_name(events, ev_name)
    if _ev_cfg:
        _tracked_d = _ev_cfg.get_tracked()
        if _tracked_d:
            num_laps = _tracked_d.route.laps or 1

    # --- Исторический кеш (предыдущий год) ---
    _t_hist = time.time()
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
    _t_hist_done = time.time() - _t_hist

    # --- Формирование результатов ---
    _t_loop = time.time()
    results = []
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
            'finish_pace_avg_gun': runner.get('finish_pace_avg_gun'),
            'finish_pace_avg_clean': runner.get('finish_pace_avg_clean'),
            'distance': runner.get('event_distance') or runner.get('distance') or runner.get('distance_from_event') or '5 км',
            'event': runner.get('distance', runner.get('distance_from_event', '5 км')),
            'checkpoints': {
                'kt1': {
                    'time': runner.get('time_clear_kt1'),
                    'pace': runner.get('pace_avg_kt1') or _kt_pace(runner.get('time_clear_kt1'), checkpoint_distances, 1),
                    'interval_pace': _segment_pace(
                        runner.get('time_clear_kt1'), None,
                        checkpoint_distances[1] if len(checkpoint_distances) > 1 else 0.0,
                        checkpoint_distances[0] if checkpoint_distances else 0.0,
                    ),
                },
                **_build_kt_checkpoints(runner, checkpoint_distances),
            },
            'speed': round(speed_kmh, 2),
            'current_distance': round(current_dist, 3),
            'current_pace': pace_str,
            'pace_source': pace_source,
            'prev_year': hist_data['prev_year'],
            'lap': _calc_lap_from_kts(runner, num_laps),
            'time_clear_start_s': (
                int(runner.get('time_clear_start').total_seconds())
                if isinstance(runner.get('time_clear_start'), _td) else None
            ),
            'last_kt_unix_ms': _calc_last_kt_unix_ms(runner, gun_start_dt),
        })
    _t_loop_done = time.time() - _t_loop

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

    _total = time.time() - _t0
    logger.info(
        f"build_event_results: db={_t_db_done:.2f}s ev={_t_ev_done:.2f}s "
        f"hist={_t_hist_done:.2f}s loop={_t_loop_done:.2f}s total={_total:.2f}s "
        f"runners={len(results)}"
    )

    return RaceResultsResponse(
        event=ev_name or f"event_{event_id}",
        total_results=len(results_data),
        results=results,
        timestamp=datetime.now().isoformat(),
        server_time_unix=server_time_unix,
        race_gun_unix_ms=race_gun_unix_ms,
        total_distance_km=float(checkpoint_distances[-1]) if checkpoint_distances else None,
    )


def _background_rebuild(resp_key: str, event_id, event_name, year, events):
    """Фоновое перестроение кеша без блокировки вызывающего потока."""
    try:
        result = _do_build(event_id, event_name, year, events)
        _response_cache[resp_key] = result
        _response_cache_ts[resp_key] = time.time()
        logger.info(f"Background rebuild done: {resp_key}")
    except Exception as e:
        logger.warning(f"Background rebuild error for {resp_key}: {e}")
    finally:
        with _rebuild_progress_lock:
            _rebuild_in_progress.discard(resp_key)


def build_event_results(
    event_id: Optional[int],
    event_name: Optional[str],
    year: Optional[int],
    events: dict,
) -> RaceResultsResponse:
    """
    Возвращает результаты события с live-позициями.

    Стратегия кеша:
    - Свежий (< RESPONSE_CACHE_TTL): мгновенный возврат
    - Устаревший (< STALE_TTL): возврат устаревших данных + фоновое перестроение
    - Холодный (нет данных / > STALE_TTL): синхронное построение с singleflight
    """
    _resp_key = f"{event_id}|{event_name}|{year}"
    _now = time.time()
    _cached = _response_cache.get(_resp_key)
    _age = _now - _response_cache_ts.get(_resp_key, 0)

    # Свежий кеш
    if _cached is not None and _age < RESPONSE_CACHE_TTL:
        return _cached

    # Устаревший, но в пределах STALE_TTL → отдаём сразу + перестраиваем в фоне
    if _cached is not None and _age < STALE_TTL:
        with _rebuild_progress_lock:
            if _resp_key not in _rebuild_in_progress:
                _rebuild_in_progress.add(_resp_key)
                threading.Thread(
                    target=_background_rebuild,
                    args=(_resp_key, event_id, event_name, year, events),
                    daemon=True,
                ).start()
        return _cached

    # Холодный кеш → синхронный билд с singleflight
    with _build_locks_meta:
        if _resp_key not in _build_locks:
            _build_locks[_resp_key] = threading.Lock()
        _key_lock = _build_locks[_resp_key]

    with _key_lock:
        # Двойная проверка: другой поток мог уже построить пока мы ждали
        _now2 = time.time()
        _cached2 = _response_cache.get(_resp_key)
        if _cached2 is not None and (_now2 - _response_cache_ts.get(_resp_key, 0)) < RESPONSE_CACHE_TTL:
            return _cached2

        result = _do_build(event_id, event_name, year, events)
        _response_cache[_resp_key] = result
        _response_cache_ts[_resp_key] = time.time()
        return result
