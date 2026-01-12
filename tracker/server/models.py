# server/models.py
import math
import logging
from config import ONE_WAY_LENGTH_KM, TOTAL_RACE_KM

logger = logging.getLogger(__name__)


class RouteCalculator:
    """Класс для расчета маршрута и позиции бегуна"""
    
    def __init__(self):
        self.path_coords = []      # Координаты линии (OSM)
        self.segment_lengths = []  # Длины каждого кусочка дороги
        self.total_path_length = 0 # Общая длина линии

    def set_path(self, coords):
        """Загружает геометрию маршрута и считает длины сегментов"""
        self.path_coords = coords
        self.segment_lengths = []
        self.total_path_length = 0
        
        if not coords or len(coords) < 2:
            return

        for i in range(len(coords) - 1):
            p1 = coords[i]
            p2 = coords[i+1]
            dist = self._haversine_distance(p1, p2)
            self.segment_lengths.append(dist)
            self.total_path_length += dist
            
        logger.info(f"📏 Геометрия маршрута загружена. Длина линии: {self.total_path_length:.3f} км")

    def _haversine_distance(self, p1, p2):
        """Расстояние между двумя точками (lat, lon) в км"""
        R = 6371  # Радиус Земли
        dlat = math.radians(p2[0] - p1[0])
        dlon = math.radians(p2[1] - p1[1])
        a = math.sin(dlat/2) * math.sin(dlat/2) + \
            math.cos(math.radians(p1[0])) * math.cos(math.radians(p2[0])) * \
            math.sin(dlon/2) * math.sin(dlon/2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        return R * c

    def get_position_on_loop(self, total_distance_run, laps=1):
        """
        Для кольцевых маршрутов (Роснефть): бегун движется по кругу
        total_distance_run - сколько км пробежал
        laps - количество кругов в дистанции
        """
        if not self.path_coords or self.total_path_length == 0:
            return None

        distance_on_current_lap = total_distance_run % self.total_path_length
        return self._interpolate_coords(distance_on_current_lap)

    def get_shuttle_position(self, total_distance_run):
        """
        Преобразует пробежавшее расстояние в координату на линии с учетом направления.
        Для челночных маршрутов (Снежная семерка)
        """
        total_distance_run = max(0, min(total_distance_run, TOTAL_RACE_KM))
        
        # Определяем, на каком мы отрезке (плече)
        leg_index = int(total_distance_run // ONE_WAY_LENGTH_KM)
        dist_in_leg = total_distance_run % ONE_WAY_LENGTH_KM
        
        # Вычисляем позицию на геометрии линии
        if leg_index % 2 == 0:
            geometry_dist = dist_in_leg  # Четный: вперед
        else:
            geometry_dist = ONE_WAY_LENGTH_KM - dist_in_leg  # Нечетный: назад

        geometry_dist = max(0, min(geometry_dist, self.total_path_length))
        return self._interpolate_coords(geometry_dist)

    def _interpolate_coords(self, target_dist):
        """Находит координату [lat, lon] на линии для заданной дистанции"""
        if not self.path_coords:
            return [0, 0]

        current_dist = 0
        for i, seg_len in enumerate(self.segment_lengths):
            if current_dist + seg_len >= target_dist:
                remaining = target_dist - current_dist
                ratio = remaining / seg_len if seg_len > 0 else 0
                
                p1 = self.path_coords[i]
                p2 = self.path_coords[i+1]
                
                lat = p1[0] + (p2[0] - p1[0]) * ratio
                lon = p1[1] + (p2[1] - p1[1]) * ratio
                return [lat, lon]
            
            current_dist += seg_len
            
        return self.path_coords[-1]


class RaceConfig:
    """Конфигурация забега"""
    
    def __init__(self):
        self.total_distance = TOTAL_RACE_KM
        self.lap_distance = 3.5
        self.event_name = "Снежная семерка"
        self.checkpoints = [
            {'id': 'start', 'distance': 0.0, 'name': 'Старт', 'coord': [56.028855, 92.946101]},
            {'id': 'turn1', 'distance': 1.75, 'name': 'Разворот', 'coord': [56.031108, 92.951328]},
            {'id': 'finish', 'distance': 7.0, 'name': 'Финиш', 'coord': [56.028855, 92.946101]}
        ]
