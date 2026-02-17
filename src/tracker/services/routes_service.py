"""
Сервис загрузки маршрутов из OpenStreetMap
Перенесён из tracker/server/routes_service.py с обновленными импортами
"""

import os
import json
import time
import requests
import logging
import urllib3

from src.config import settings

logger = logging.getLogger(__name__)


# RouteCalculator: простая реализация для расчета расстояния
class RouteCalculator:
    """Рассчитывает расстояния на маршруте"""
    def __init__(self):
        self.path_coords = []
        self.segment_lengths = []
        self.total_path_length = 0

    def set_path(self, coords):
        """Установить координаты маршрута и пересчитать длины"""
        self.path_coords = coords
        self._calculate_segment_lengths()
    
    def _calculate_segment_lengths(self):
        """Рассчитать длины сегментов между точками"""
        self.segment_lengths = []
        self.total_path_length = 0
        
        if len(self.path_coords) < 2:
            return
        
        for i in range(len(self.path_coords) - 1):
            lat1, lon1 = self.path_coords[i]
            lat2, lon2 = self.path_coords[i + 1]
            
            # Простой расчет расстояния (в градусах)
            distance = ((lat2 - lat1) ** 2 + (lon2 - lon1) ** 2) ** 0.5
            self.segment_lengths.append(distance)
            self.total_path_length += distance

    def get_position_on_loop(self, distance_km):
        """Получить координаты позиции на кольцевом маршруте"""
        if not self.path_coords or not self.total_path_length:
            return None
        
        # Для кольцевого маршрута просто движемся по пути
        # Пересчитываем в процент от общей длины
        ratio = (distance_km / self.total_path_length) if self.total_path_length > 0 else 0
        ratio = min(max(ratio, 0), 1)  # Ограничиваем 0-1
        
        # Находим соответствующую точку на маршруте
        point_index = int(ratio * (len(self.path_coords) - 1))
        point_index = min(point_index, len(self.path_coords) - 1)
        
        coords = self.path_coords[point_index]
        return list(coords) if coords else None

    def get_shuttle_position(self, distance_km, one_way_length_km, total_distance_km):
        """Получить координаты позиции на челночном маршруте (туда-обратно)"""
        if not self.path_coords or not one_way_length_km:
            return None
        
        # Для челночного маршрута:
        # Если distance <= one_way_length: идём туда
        # Если distance > one_way_length: идём обратно
        
        if distance_km <= one_way_length_km:
            # Идём туда
            ratio = distance_km / one_way_length_km
        else:
            # Идём обратно
            remaining = distance_km - one_way_length_km
            ratio = 1.0 - (remaining / one_way_length_km)
            ratio = max(ratio, 0)  # Не может быть меньше 0
        
        # Находим соответствующую точку на маршруте
        point_index = int(ratio * (len(self.path_coords) - 1))
        point_index = min(max(point_index, 0), len(self.path_coords) - 1)
        
        coords = self.path_coords[point_index]
        return list(coords) if coords else None

    def calculate_distance(self, lat, lon):
        """Расчет расстояния до точки на маршруте"""
        if not self.path_coords:
            return 0
        
        # Простой расчет расстояния между двумя точками
        min_distance = float('inf')
        closest_distance = 0
        
        for i, (route_lat, route_lon) in enumerate(self.path_coords):
            # Евклидово расстояние (упрощенно)
            distance = ((lat - route_lat) ** 2 + (lon - route_lon) ** 2) ** 0.5
            if distance < min_distance:
                min_distance = distance
                closest_distance = sum(self.segment_lengths[:i]) if i > 0 else 0
        
        return closest_distance

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
        json_file = os.path.join(settings.BASE_DIR, f"{event_name}_route.json")
        if os.path.exists(json_file):
            logger.info(f"📂 Загрузка маршрута из {json_file}")
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('coordinates', [])
        return None
    except Exception as e:
        logger.error(f"❌ Ошибка при загрузке маршрута из JSON: {e}")
        return None


def fetch_route_from_osm(event_name=None):
    """Получение данных маршрута из OpenStreetMap или JSON"""
    global osm_route_data, last_route_fetch_time

    if event_name is None:
        event_name = settings.CURRENT_EVENT

    current_time = time.time()
    
    # Проверяем кеш для данного мероприятия
    if event_name in osm_route_data and event_name in last_route_fetch_time:
        if (current_time - last_route_fetch_time[event_name]) < settings.ROUTE_CACHE_DURATION:
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
    event_config = settings.EVENTS_CONFIG.get(event_name, {})
    if not event_config:
        logger.warning(f"⚠️ Мероприятие '{event_name}' не найдено в конфигурации")
        return get_fallback_route()
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
