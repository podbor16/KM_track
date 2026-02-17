"""
Сервис управления участниками гонки
Перенесён из tracker/server/runners_service.py с обновленными импортами
"""

import json
import logging
import os
import re
from datetime import datetime

from src.config import settings
from src.tracker.parsers.ParsingRaceInMap import CopernicoParser

logger = logging.getLogger(__name__)

# RaceConfig и RouteCalculator используются для типизации
class RaceConfig:
    """Конфигурация гонки"""
    pass


class RouteCalculator:
    """Калькулятор маршрута"""
    pass

# Инициализация
race_config = RaceConfig()
copernico_parser = CopernicoParser(race_config)


def get_route_calculator():
    """Получить калькулятор маршрута"""
    from src.tracker.services.routes_service import get_route_calculator as _get_rc
    return _get_rc()


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
        if not os.path.exists(settings.RACE_DATA_FILE):
            logger.error(f"❌ Файл НЕ НАЙДЕН: {settings.RACE_DATA_FILE}")
            return []

        with open(settings.RACE_DATA_FILE, 'r', encoding='utf-8') as f:
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


def update_runner_positions(runners, event_name=None):
    """Обновляет позиции и дистанции участников"""
    if event_name is None:
        event_name = settings.CURRENT_EVENT
        
    current_time = datetime.now()
    event_config = settings.EVENTS_CONFIG.get(event_name, settings.EVENTS_CONFIG[settings.CURRENT_EVENT])
    route_calc = get_route_calculator()

    if not route_calc.path_coords:
        from src.tracker.services.routes_service import fetch_route_from_osm
        fetch_route_from_osm(event_name)

    is_loop = event_name == 'rosneft'
    total_race_distance = event_config.get('total_race_km', 7.0)
    one_way_length = event_config.get('one_way_length_km', settings.ONE_WAY_LENGTH_KM)

    for runner in runners:
        status = runner.get('status', '').lower()

        if status == 'finished':
            runner['current_distance'] = total_race_distance
            if is_loop:
                coords = route_calc.get_position_on_loop(total_race_distance)
            else:
                coords = route_calc.get_shuttle_position(total_race_distance, one_way_length, total_race_distance)
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
            
            if is_loop:
                lat_lon = route_calc.get_position_on_loop(new_dist)
            else:
                lat_lon = route_calc.get_shuttle_position(new_dist, one_way_length, total_race_distance)
            if lat_lon:
                runner['position'] = {'lat': lat_lon[0], 'lng': lat_lon[1]}

        runner['last_update'] = current_time.isoformat()

    return runners
