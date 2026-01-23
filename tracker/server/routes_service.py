# server/routes_service.py
import os
import json
import time
import requests
import logging
import urllib3
from config import (
    BASE_DIR, EVENTS_CONFIG, ROUTE_CACHE_DURATION,
    ONE_WAY_LENGTH_KM
)
from models import RouteCalculator

logger = logging.getLogger(__name__)

# Кеш маршрутов
osm_route_data = {}
last_route_fetch_time = {}
route_calc = RouteCalculator()


def process_osm_route_data(data):
    """Обработка данных маршрута из OSM"""
    try:
        nodes = {}
        for element in data['elements']:
            if element['type'] == 'node':
                nodes[element['id']] = {
                    'lat': element['lat'],
                    'lon': element['lon']
                }

        way_nodes = []
        for element in data['elements']:
            if element['type'] == 'way':
                way_nodes = element['nodes']
                break

        if not way_nodes:
            logger.warning("⚠️ Не найдены узлы для маршрута в данных OSM")
            return None

        route_coords = []
        for node_id in way_nodes:
            if node_id in nodes:
                route_coords.append([
                    nodes[node_id]['lat'],
                    nodes[node_id]['lon']
                ])

        if len(route_coords) < 2:
            logger.warning("⚠️ Недостаточно точек для построения маршрута")
            return None

        logger.info(f"✅ Обработан маршрут с {len(route_coords)} точками")
        return route_coords

    except Exception as e:
        logger.error(f"❌ Ошибка при обработке данных маршрута: {type(e).__name__}: {e}")
        return None


def get_fallback_route():
    """Резервный маршрут на случай ошибки загрузки из OSM"""
    logger.info("🛡️ Используем резервный маршрут")
    return [
        [56.028855, 92.946101],  # Старт
        [56.02996, 92.949893],   # Середина
        [56.031108, 92.951328]   # Разворот
    ]


def load_route_from_json(event_name):
    """Загрузка маршрута из JSON файла (для Роснефть и других)"""
    try:
        json_file = os.path.join(BASE_DIR, f"{event_name}_route.json")
        if os.path.exists(json_file):
            logger.info(f"📂 Загрузка маршрута из {json_file}")
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('coordinates', [])
        return None
    except Exception as e:
        logger.error(f"❌ Ошибка при загрузке маршрута из JSON: {e}")
        return None


def fetch_route_from_osm(event_name='snow7'):
    """Получение данных маршрута из OpenStreetMap или JSON"""
    global osm_route_data, last_route_fetch_time

    current_time = time.time()
    
    # Проверяем кеш для данного мероприятия
    if event_name in osm_route_data and event_name in last_route_fetch_time:
        if (current_time - last_route_fetch_time[event_name]) < ROUTE_CACHE_DURATION:
            return osm_route_data[event_name]

    # Сначала пробуем загрузить из JSON (для Роснефть)
    if event_name == 'rosneft':
        json_route = load_route_from_json(event_name)
        if json_route:
            logger.info(f"✅ Маршрут {event_name} загружен из JSON ({len(json_route)} точек)")
            osm_route_data[event_name] = json_route
            last_route_fetch_time[event_name] = current_time
            return json_route

    # Если JSON нет, загружаем из OSM
    event_config = EVENTS_CONFIG.get(event_name, EVENTS_CONFIG['snow7'])
    way_id = event_config['osm_way_id']

    try:
        logger.info(f"🌍 Запрос маршрута из OpenStreetMap (Way ID: {way_id})")
        url = f"https://overpass-api.de/api/interpreter?data=[out:json];way({way_id});(._;>;);out;"
        headers = {'User-Agent': 'KrasmarathonTracker/1.0'}
        # Try with SSL verification first, fallback to unverified if needed
        try:
            response = requests.get(url, headers=headers, timeout=15, verify=True)
        except requests.exceptions.SSLError as ssl_error:
            logger.warning(f"⚠️ SSL ошибка при подключении к OSM: {ssl_error}. Пробуем без проверки сертификата...")
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            response = requests.get(url, headers=headers, timeout=15, verify=False)
        response.raise_for_status()

        data = response.json()
        processed_route = process_osm_route_data(data)

        if processed_route:
            osm_route_data[event_name] = processed_route
            last_route_fetch_time[event_name] = current_time
            return processed_route
        else:
            return None

    except requests.exceptions.RequestException as req_error:
        logger.error(f"❌ Ошибка при запросе маршрута из OSM: {req_error}")
        return get_fallback_route()
    except Exception as e:
        logger.error(f"❌ Ошибка при загрузке маршрута из OSM: {e}")
        return get_fallback_route()


def get_route_calculator():
    """Получить глобальный экземпляр калькулятора маршрута"""
    return route_calc
