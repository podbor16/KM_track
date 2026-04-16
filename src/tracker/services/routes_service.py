"""
Сервис маршрутов — загрузка из GPX файлов
"""

import os
import xml.etree.ElementTree as ET
import logging
from typing import List, Tuple

from src.config import settings

logger = logging.getLogger(__name__)

# Маппинг: event_name (ключ из settings.EVENTS_CONFIG) → путь к GPX файлу
GPX_FILES = {
    'night_run': os.path.join('static', 'map', '2026', 'night_run.gpx'),
    'snow7':     os.path.join('static', 'map', '2026', 'snow7.gpx'),
    'rosneft':   os.path.join('static', 'map', '2026', 'rosneft.gpx'),
}

# Кэш загруженных маршрутов (event_name → список координат)
_gpx_route_cache: dict = {}

# Глобальный экземпляр калькулятора маршрута
route_calc: 'RouteCalculator'


class RouteCalculator:
    """Рассчитывает позицию на маршруте по пройденной дистанции"""

    def __init__(self):
        self.path_coords: List = []
        self.segment_lengths: List[float] = []
        self.total_path_length: float = 0.0

    def set_path(self, coords):
        self.path_coords = coords
        self._calculate_segment_lengths()

    def _calculate_segment_lengths(self):
        self.segment_lengths = []
        self.total_path_length = 0.0

        if len(self.path_coords) < 2:
            return

        for i in range(len(self.path_coords) - 1):
            lat1, lon1 = self.path_coords[i]
            lat2, lon2 = self.path_coords[i + 1]
            distance = ((lat2 - lat1) ** 2 + (lon2 - lon1) ** 2) ** 0.5
            self.segment_lengths.append(distance)
            self.total_path_length += distance

    def get_position_on_loop(self, distance_km):
        """Позиция на кольцевом маршруте"""
        if not self.path_coords or not self.total_path_length:
            return None
        ratio = min(max(distance_km / self.total_path_length, 0), 1)
        point_index = min(int(ratio * (len(self.path_coords) - 1)), len(self.path_coords) - 1)
        coords = self.path_coords[point_index]
        return list(coords) if coords else None

    def get_shuttle_position(self, distance_km, one_way_length_km, total_distance_km):
        """Позиция на челночном маршруте (туда-обратно)"""
        if not self.path_coords or not one_way_length_km:
            return None
        if distance_km <= one_way_length_km:
            ratio = distance_km / one_way_length_km
        else:
            remaining = distance_km - one_way_length_km
            ratio = max(1.0 - (remaining / one_way_length_km), 0)
        point_index = min(max(int(ratio * (len(self.path_coords) - 1)), 0), len(self.path_coords) - 1)
        coords = self.path_coords[point_index]
        return list(coords) if coords else None

    def calculate_distance(self, lat, lon):
        """Расстояние до ближайшей точки маршрута"""
        if not self.path_coords:
            return 0
        min_distance = float('inf')
        closest_distance = 0
        for i, (route_lat, route_lon) in enumerate(self.path_coords):
            distance = ((lat - route_lat) ** 2 + (lon - route_lon) ** 2) ** 0.5
            if distance < min_distance:
                min_distance = distance
                closest_distance = sum(self.segment_lengths[:i]) if i > 0 else 0
        return closest_distance


route_calc = RouteCalculator()


def load_route_from_gpx(event_name: str) -> List[Tuple[float, float]]:
    """
    Загружает координаты маршрута из GPX файла.
    Результат кэшируется на весь срок работы приложения.
    """
    if event_name in _gpx_route_cache:
        return _gpx_route_cache[event_name]

    gpx_relative = GPX_FILES.get(event_name)
    if not gpx_relative:
        logger.warning(f"⚠️ GPX файл для '{event_name}' не задан в GPX_FILES")
        return []

    gpx_path = os.path.join(settings.BASE_DIR, gpx_relative)
    if not os.path.exists(gpx_path):
        logger.warning(f"⚠️ GPX файл не найден: {gpx_path}")
        return []

    try:
        tree = ET.parse(gpx_path)
        root = tree.getroot()

        # Пробуем с namespace GPX 1.1, затем без него
        coords = []
        ns = {'gpx': 'http://www.topografix.com/GPX/1/1'}
        for trkpt in root.findall('.//gpx:trkpt', ns):
            coords.append((float(trkpt.get('lat')), float(trkpt.get('lon'))))

        if not coords:
            for trkpt in root.findall('.//{*}trkpt'):
                coords.append((float(trkpt.get('lat')), float(trkpt.get('lon'))))

        if coords:
            _gpx_route_cache[event_name] = coords
            logger.info(f"✅ GPX '{event_name}': загружено {len(coords)} точек")
        else:
            logger.warning(f"⚠️ GPX '{gpx_path}' не содержит точек трека")

        return coords

    except Exception as e:
        logger.error(f"❌ Ошибка чтения GPX '{gpx_path}': {e}")
        return []


def get_route_calculator() -> RouteCalculator:
    """Получить глобальный экземпляр калькулятора маршрута"""
    return route_calc
