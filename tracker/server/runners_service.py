# server/runners_service.py
import json
import logging
import os
import re
from datetime import datetime
from config import (
    RACE_DATA_FILE, USE_MANUAL_SPEED, MANUAL_SPEED_KMH,
    EVENTS_CONFIG, CURRENT_EVENT, CACHE_DURATION
)
from ParsingRaceInMap import CopernicoParser
from models import RaceConfig, RouteCalculator
from routes_service import get_route_calculator

logger = logging.getLogger(__name__)

# Инициализация
race_config = RaceConfig()
copernico_parser = CopernicoParser(race_config)


def parse_pace_to_speed(pace_str):
    """
    Преобразует строку темпа (например, '7'22"/Km') в скорость в км/ч.
    """
    if not pace_str or pace_str.lower() == 'null':
        return 10.0
    
    match = re.search(r"(\d+)'(\d+)", pace_str)
    if match:
        minutes = int(match.group(1))
        seconds = int(match.group(2))
        total_seconds_per_km = minutes * 60 + seconds
        if total_seconds_per_km == 0:
            return 10.0
        
        hours_per_km = total_seconds_per_km / 3600.0
        speed_kmh = 1.0 / hours_per_km
        return speed_kmh
    else:
        return 10.0


def fetch_copernico_data():
    """Загружает данные участников из файла"""
    try:
        if not os.path.exists(RACE_DATA_FILE):
            logger.error(f"❌ Файл НЕ НАЙДЕН: {RACE_DATA_FILE}")
            return []

        with open(RACE_DATA_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)

        raw_data = data.get("data", [])
        if not isinstance(raw_data, list):
            return []

        logger.info(f"✅ Загружено {len(raw_data)} записей из файла")
        return raw_data
    except Exception as e:
        logger.error(f"❌ Ошибка чтения файла: {e}")
        return []


def transform_copernico_data(raw_data):
    """Преобразует сырые данные в структуру участников"""
    runners = []
    current_time_iso = datetime.now().isoformat()

    for item in raw_data:
        try:
            runner = {
                'id': item.get('dorsal', ''),
                'name': f"{item.get('name', '')} {item.get('surname', '')}",
                'full_name': f"{item.get('name', '')} {item.get('surname', '')}",
                'dorsal': item.get('dorsal', ''),
                'category': item.get('category', ''),
                'status': item.get('status', 'notstarted').lower(),
                'start_time': item.get('startRawTime', None),
                'finish_time': item.get('times.official_:::finish:::', None),
                'rankings_full': item.get('rankings_:::full-1:::', None),
                'gender_ranking': item.get('rankings.gen_:::full-1:::', None),
                'category_ranking': item.get('rankings.cat_:::full-1:::', None),
                'current_distance': 0.0,
                'position': {'lat': 0, 'lng': 0},
                'last_update': current_time_iso,
                'speed': 10.0  # Устанавливаем базовую скорость
            }
            
            # Обновляем скорость на основе данных, если они есть
            interval_average = item.get('intervalaverages_:::full-1:::')
            if interval_average:
                runner['speed'] = parse_pace_to_speed(interval_average)
            
            runners.append(runner)
        except Exception as e:
            logger.error(f"Ошибка при обработке данных участника: {e}")
            continue
    return runners


def update_runner_positions(runners, event_name=CURRENT_EVENT):
    """Обновляет позиции и дистанции участников"""
    current_time = datetime.now()
    event_config = EVENTS_CONFIG.get(event_name, EVENTS_CONFIG[CURRENT_EVENT])
    route_calc = get_route_calculator()

    if not route_calc.path_coords:
        from routes_service import fetch_route_from_osm
        fetch_route_from_osm(event_name)

    is_loop = event_name == 'rosneft'
    total_race_distance = event_config.get('total_race_km', 7.0)

    for runner in runners:
        status = runner.get('status', '').lower()

        if status == 'finished':
            runner['current_distance'] = total_race_distance
            coords = route_calc.get_position_on_loop(total_race_distance) if is_loop else route_calc.get_shuttle_position(total_race_distance)
            if coords:
                runner['position'] = {'lat': coords[0], 'lng': coords[1]}
            continue

        if status in ['started', 'running']:
            try:
                last_update_dt = datetime.fromisoformat(runner['last_update'])
            except (ValueError, TypeError):
                last_update_dt = current_time

            time_diff_hours = (current_time - last_update_dt).total_seconds() / 3600.0
            
            # Используем скорость, которая уже установлена в transform_copernico_data
            speed = runner.get('speed', 10.0)

            dist_increment = speed * time_diff_hours
            new_dist = float(runner.get('current_distance', 0.0)) + dist_increment
            
            if new_dist >= total_race_distance:
                new_dist = total_race_distance
                runner['status'] = 'finished'
            
            runner['current_distance'] = new_dist
            
            lat_lon = route_calc.get_position_on_loop(new_dist) if is_loop else route_calc.get_shuttle_position(new_dist)
            if lat_lon:
                runner['position'] = {'lat': lat_lon[0], 'lng': lat_lon[1]}

        runner['last_update'] = current_time.isoformat()

    return runners