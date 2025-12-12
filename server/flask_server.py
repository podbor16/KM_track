# server/flask_server.py
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import requests
import json
from datetime import datetime
import os
import time
import threading
import logging
import random
import math  # ОБЯЗАТЕЛЬНО: Нужен для расчетов координат

# Импорт парсера. Убедитесь, что файл называется ParsingRaceInMap.py
# Если ваш файл называется ParcingRaceInMap.py (с ошибкой), измените импорт ниже:
from ParsingRaceInMap import CopernicoParser

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

app = Flask(__name__, static_folder=os.path.join(BASE_DIR, 'server', 'static'))
CORS(app)

# --- ГЛОБАЛЬНЫЕ НАСТРОЙКИ СИМУЛЯЦИИ ---
# Изменяйте эту переменную, чтобы ускорить или замедлить всех бегунов
MANUAL_SPEED_KMH = 15.0       # Скорость в км/ч (поставьте 50.0 для быстрого теста)
USE_MANUAL_SPEED = True       # True = все бегут с заданной скоростью. False = случайная скорость.

# Настройки геометрии трассы
ONE_WAY_LENGTH_KM = 1.75      # Длина отрисованной линии (в одну сторону)
TOTAL_RACE_KM = 7.0           # Полная дистанция забега (4 плеча по 1.75)
# ----------------------------------------

# Путь к файлу с данными
RACE_DATA_FILE = os.path.join(BASE_DIR, "race_data.json")

# Конфигурация кеширования
cache_data = None
cache_time = None
CACHE_DURATION = 2  # Обновлять позиции каждые 2 секунды (интерполяция)
LAST_COPERNICO_REQUEST = 0
REQUEST_MIN_INTERVAL = 2

# OSM конфигурация
OSM_WAY_ID = 181589417
osm_route_data = None
ROUTE_CACHE_DURATION = 3600
last_route_fetch_time = 0

# Выбранные участники
selected_runners = set()
MAX_SELECTED_RUNNERS = 5
# Блокировка потоков
cache_lock = threading.Lock()


# --- КЛАСС ДЛЯ РАСЧЕТА МАРШРУТА ---
class RouteCalculator:
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

    def get_shuttle_position(self, total_distance_run):
        """
        Преобразует пробежавшее расстояние (напр. 2.5 км)
        в координату на линии 1.75 км с учетом направления (туда или обратно).
        """
        # Ограничиваем дистанцию
        total_distance_run = max(0, min(total_distance_run, TOTAL_RACE_KM))
        
        # Определяем, на каком мы отрезке (плече)
        # 0: 0 -> 1.75 (Вперед)
        # 1: 1.75 -> 3.5 (Назад)
        # 2: 3.5 -> 5.25 (Вперед)
        # 3: 5.25 -> 7.0 (Назад)
        leg_index = int(total_distance_run // ONE_WAY_LENGTH_KM)
        
        # Дистанция внутри текущего плеча
        dist_in_leg = total_distance_run % ONE_WAY_LENGTH_KM
        
        # Обработка граничного случая (ровно на повороте)
        if dist_in_leg == 0 and total_distance_run > 0 and total_distance_run < TOTAL_RACE_KM:
             # Не меняем индекс, math обработает корректно, но для логики:
             pass

        # Вычисляем позицию на ГЕОМЕТРИИ линии (от 0 до 1.75)
        if leg_index % 2 == 0:
            # Четный круг (0, 2...) - бежим ВПЕРЕД
            geometry_dist = dist_in_leg
        else:
            # Нечетный круг (1, 3...) - бежим НАЗАД (инверсия)
            geometry_dist = ONE_WAY_LENGTH_KM - dist_in_leg

        # Защита от выхода за пределы геометрии
        geometry_dist = max(0, min(geometry_dist, self.total_path_length))
        
        return self._interpolate_coords(geometry_dist)

    def _interpolate_coords(self, target_dist):
        """Находит координату [lat, lon] на линии для заданной дистанции"""
        if not self.path_coords:
            return [0, 0]

        current_dist = 0
        for i, seg_len in enumerate(self.segment_lengths):
            if current_dist + seg_len >= target_dist:
                # Точка внутри этого сегмента
                remaining = target_dist - current_dist
                ratio = remaining / seg_len if seg_len > 0 else 0
                
                p1 = self.path_coords[i]
                p2 = self.path_coords[i+1]
                
                lat = p1[0] + (p2[0] - p1[0]) * ratio
                lon = p1[1] + (p2[1] - p1[1]) * ratio
                return [lat, lon]
            
            current_dist += seg_len
            
        return self.path_coords[-1] # Если конец пути

# Глобальный экземпляр калькулятора
route_calc = RouteCalculator()


# --- ОБРАБОТКА OSM ---
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
            if element['type'] == 'way' and element['id'] == OSM_WAY_ID:
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
        [56.031108, 92.951328]   # Разворот (примерно)
    ]


def fetch_route_from_osm():
    """Получение данных маршрута из OpenStreetMap"""
    global osm_route_data, last_route_fetch_time

    current_time = time.time()
    if osm_route_data and (current_time - last_route_fetch_time) < ROUTE_CACHE_DURATION:
        return osm_route_data

    try:
        logger.info(f"🌍 Запрос маршрута из OpenStreetMap (Way ID: {OSM_WAY_ID})")
        url = f"https://overpass-api.de/api/interpreter?data=[out:json];way({OSM_WAY_ID});(._;>;);out;"

        headers = {'User-Agent': 'KrasmarathonTracker/1.0'}
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()

        data = response.json()
        processed_route = process_osm_route_data(data)

        if processed_route:
            osm_route_data = processed_route
            last_route_fetch_time = current_time
            
            # ВАЖНО: Загружаем данные в калькулятор
            route_calc.set_path(processed_route)
            
            return processed_route
        else:
            return None

    except Exception as e:
        logger.error(f"❌ Ошибка при загрузке маршрута из OSM: {e}")
        fallback = get_fallback_route()
        # ВАЖНО: Загружаем резервный маршрут в калькулятор
        route_calc.set_path(fallback)
        return fallback


@app.route('/api/route')
def get_route():
    """Получение данных маршрута"""
    try:
        route_data = fetch_route_from_osm()
        if route_data:
            return jsonify({
                'coordinates': route_data,
                'distance': TOTAL_RACE_KM,
                'way_id': OSM_WAY_ID
            })
        else:
            return jsonify({
                'coordinates': get_fallback_route(),
                'distance': TOTAL_RACE_KM,
                'fallback': True
            }), 503
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# --- КОНФИГУРАЦИЯ ЗАБЕГА ---
class RaceConfig:
    def __init__(self):
        self.total_distance = TOTAL_RACE_KM
        self.lap_distance = 3.5
        self.event_name = "Снежная семерка"
        # Чекпоинты (для справки, но движение теперь считает route_calc)
        self.checkpoints = [
            {'id': 'start', 'distance': 0.0, 'name': 'Старт', 'coord': [56.028855, 92.946101]},
            {'id': 'turn1', 'distance': 1.75, 'name': 'Разворот', 'coord': [56.031108, 92.951328]},
            {'id': 'finish', 'distance': 7.0, 'name': 'Финиш', 'coord': [56.028855, 92.946101]}
        ]

race_config = RaceConfig()
copernico_parser = CopernicoParser(race_config)


# --- РАБОТА С ДАННЫМИ УЧАСТНИКОВ ---
def fetch_copernico_data():
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
    runners = []
    current_time_iso = datetime.now().isoformat()

    for item in raw_data:
        try:
            runner = copernico_parser.parse_runner_data(item)
            if runner:
                # Инициализация для симуляции
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


def update_runner_positions(runners):
    """Обновляет позиции участников (ЧЕЛНОЧНЫЙ БЕГ)"""
    current_time = datetime.now()
    
    # Инициализация маршрута если еще нет
    if not route_calc.path_coords:
        fetch_route_from_osm() # Это загрузит данные в route_calc

    for runner in runners:
        if 'last_update' not in runner:
            runner['last_update'] = current_time.isoformat()

        status = runner.get('status', '').lower()
        
        # Активен, если статус started или running
        is_active = status in ['started', 'running']
        
        # Если финишировал - ставим на финиш
        if status == 'finished':
            runner['current_distance'] = TOTAL_RACE_KM
            coords = route_calc.get_shuttle_position(TOTAL_RACE_KM)
            runner['position'] = {'lat': coords[0], 'lng': coords[1]}
            continue

        if is_active:
            # 1. Время с последнего обновления
            try:
                last_update_dt = datetime.fromisoformat(runner['last_update'])
            except:
                last_update_dt = current_time
            
            time_diff_hours = (current_time - last_update_dt).total_seconds() / 3600.0

            # 2. Скорость (Ручная или Индивидуальная)
            if USE_MANUAL_SPEED:
                speed = MANUAL_SPEED_KMH
            else:
                speed = runner.get('speed', 10.0)

            # 3. Новая дистанция
            dist_increment = speed * time_diff_hours
            current_dist = float(runner.get('current_distance', 0.0))
            new_dist = current_dist + dist_increment
            
            # Проверка финиша
            if new_dist >= TOTAL_RACE_KM:
                new_dist = TOTAL_RACE_KM
                runner['status'] = 'finished'
            
            runner['current_distance'] = new_dist
            runner['speed'] = speed
            
            # 4. ВЫЧИСЛЕНИЕ КООРДИНАТ (ТУДА-ОБРАТНО)
            lat_lon = route_calc.get_shuttle_position(new_dist)
            
            runner['position'] = {
                'lat': lat_lon[0],
                'lng': lat_lon[1]
            }

        runner['last_update'] = current_time.isoformat()

    return runners


@app.route('/api/runners', methods=['GET'])
def get_runners():
    global cache_data, cache_time

    try:
        current_time = datetime.now()

        with cache_lock:
            # Если кеш свежий, просто обновляем позиции (интерполяция)
            if cache_data and cache_time and (current_time - cache_time).total_seconds() < CACHE_DURATION:
                cache_data = update_runner_positions(cache_data)
                return jsonify(cache_data)

        # Если кеш устарел, читаем файл заново (симуляция прихода новых данных)
        raw_data = fetch_copernico_data()
        
        if not raw_data:
            # Если файл пуст, но в кеше что-то есть - продолжаем крутить кеш
            if cache_data:
                runners = cache_data
            else:
                return jsonify([])
        else:
            # Новые данные из файла. Нужно сохранить накопленный прогресс!
            new_runners_map = {str(r.get('dorsal')): r for r in transform_copernico_data(raw_data)}
            
            if cache_data:
                for cached_runner in cache_data:
                    rid = str(cached_runner.get('dorsal'))
                    if rid in new_runners_map:
                        # Переносим накопленную дистанцию в новые данные
                        new_runners_map[rid]['current_distance'] = cached_runner.get('current_distance', 0)
                        new_runners_map[rid]['last_update'] = cached_runner.get('last_update')
            
            runners = list(new_runners_map.values())

        # Обновляем позиции
        runners = update_runner_positions(runners)

        with cache_lock:
            cache_data = runners
            cache_time = current_time

        return jsonify(runners)

    except Exception as e:
        logger.error(f"❌ Ошибка в /api/runners: {e}")
        return jsonify([])


@app.route('/api/search-runners', methods=['GET'])
def search_runners():
    global cache_data
    try:
        query = request.args.get('q', '').strip().lower()
        if not query or not cache_data:
            return jsonify([])

        results = []
        for runner in cache_data:
            dorsal = str(runner.get('dorsal', '')).lower()
            surname = str(runner.get('surname', '')).lower()
            
            if dorsal.startswith(query) or surname.startswith(query):
                results.append(runner)

        results.sort(key=lambda x: (x.get('dorsal') != query, x.get('surname')))
        return jsonify(results[:20])
    except Exception:
        return jsonify([])


@app.route('/api/select-runner', methods=['POST'])
def select_runner():
    global selected_runners
    data = request.get_json()
    runner_id = str(data.get('runner_id', '')).strip()
    
    if runner_id:
        if len(selected_runners) < MAX_SELECTED_RUNNERS:
            selected_runners.add(runner_id)
            return jsonify({'success': True, 'selected_ids': list(selected_runners)})
        else:
            return jsonify({'success': False, 'error': 'Limit reached'}), 400
    return jsonify({'success': False}), 400


@app.route('/api/deselect-runner', methods=['POST'])
def deselect_runner():
    global selected_runners
    data = request.get_json()
    runner_id = str(data.get('runner_id', '')).strip()
    if runner_id in selected_runners:
        selected_runners.remove(runner_id)
    return jsonify({'success': True, 'selected_ids': list(selected_runners)})


@app.route('/api/selected-runners', methods=['GET'])
def get_selected_runners():
    global cache_data, selected_runners
    if not cache_data:
        return jsonify([])
    res = [r for r in cache_data if str(r.get('id')) in selected_runners or str(r.get('dorsal')) in selected_runners]
    return jsonify(res)


@app.route('/api/race-config', methods=['GET'])
def get_race_config_api():
    return jsonify({
        'event_name': race_config.event_name,
        'total_distance': race_config.total_distance,
        'checkpoints': race_config.checkpoints
    })


@app.route('/')
def serve_index():
    if os.path.exists(os.path.join(app.static_folder, 'index.html')):
        return send_from_directory(app.static_folder, 'index.html')
    return "index.html not found", 404


if __name__ == '__main__':
    print("🚀 Запуск трекера Снежной семерки")
    print(f"🔧 Режим скорости: {'РУЧНОЙ' if USE_MANUAL_SPEED else 'АВТО'}")
    print(f"⚡ Скорость: {MANUAL_SPEED_KMH} км/ч")
    print("=" * 50)
    # Предварительная загрузка маршрута при старте
    fetch_route_from_osm()
    app.run(host='0.0.0.0', port=5000, debug=True)