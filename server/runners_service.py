# server/runners_service.py
import json
import logging
import os
from datetime import datetime
from config import (
    RACE_DATA_FILE, USE_MANUAL_SPEED, MANUAL_SPEED_KMH,
    EVENTS_CONFIG, CURRENT_EVENT
)
from ParsingRaceInMap import CopernicoParser
from models import RaceConfig
from routes_service import get_route_calculator

logger = logging.getLogger(__name__)

# Инициализация
race_config = RaceConfig()
copernico_parser = CopernicoParser(race_config)

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
            runner = copernico_parser.parse_runner_data(item)
            if runner:
                if 'speed' not in runner:
                    runner['speed'] = 10.0
                if 'last_update' not in runner:
                    runner['last_update'] = current_time_iso
                if 'current_distance' not in runner:
                    runner['current_distance'] = 0.0
                
                runners.append(runner)
        except Exception:
            pass
    return runners


def update_runner_positions(runners, event_name=CURRENT_EVENT):
    """Обновляет позиции и дистанции участников"""
    current_time = datetime.now()
    event_config = EVENTS_CONFIG.get(event_name, EVENTS_CONFIG[CURRENT_EVENT])
    route_calc = get_route_calculator()

    # Инициализация маршрута если еще нет
    if not route_calc.path_coords:
        from routes_service import fetch_route_from_osm
        fetch_route_from_osm(event_name)

    is_loop = event_name == 'rosneft'

    for runner in runners:
        if 'last_update' not in runner:
            runner['last_update'] = current_time.isoformat()

        status = runner.get('status', '').lower()
        is_active = status in ['started', 'running']
        runner_distance = runner.get('race_distance', event_config.get('total_race_km', 5.0))

        # Если финишировал
        if status == 'finished':
            runner['current_distance'] = runner_distance
            if is_loop:
                coords = route_calc.get_position_on_loop(runner_distance)
            else:
                coords = route_calc.get_shuttle_position(runner_distance)

            if coords:
                runner['position'] = {'lat': coords[0], 'lng': coords[1]}
            continue

        # Активные бегуны
        if is_active:
            try:
                last_update_dt = datetime.fromisoformat(runner['last_update'])
            except:
                last_update_dt = current_time
            
            time_diff_hours = (current_time - last_update_dt).total_seconds() / 3600.0

            # Определяем скорость
            if USE_MANUAL_SPEED:
                speed = MANUAL_SPEED_KMH
            else:
                speed = runner.get('speed', 10.0)

            # Считаем новую дистанцию
            dist_increment = speed * time_diff_hours
            current_dist = float(runner.get('current_distance', 0.0))
            new_dist = current_dist + dist_increment
            
            if new_dist >= runner_distance:
                new_dist = runner_distance
                runner['status'] = 'finished'
            
            runner['current_distance'] = new_dist
            runner['speed'] = speed

            # Вычисляем координаты
            if is_loop:
                lat_lon = route_calc.get_position_on_loop(new_dist)
            else:
                lat_lon = route_calc.get_shuttle_position(new_dist)

            if lat_lon:
                runner['position'] = {
                    'lat': lat_lon[0],
                    'lng': lat_lon[1]
                }

        runner['last_update'] = current_time.isoformat()

    return runners
