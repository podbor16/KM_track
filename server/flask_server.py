# server/flask_server.py
from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
import requests
import json
from datetime import datetime, timedelta
import os
import time
import threading
import logging
import math

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Получаем абсолютный путь к корневой папке проекта
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

app = Flask(__name__,
            static_folder=BASE_DIR,
            static_url_path='')
CORS(app)

# Конфигурация Copernico API
COPERNICO_API_URL = "https://public-api.copernico.cloud/api/races/--2025-70363/preset/podbor250718@gmail.com:::Снежная 7 трекер/7%20km"
# COPERNICO_API_URL = "https://api.copernico.cloud/api/v2/races/---2025-89449/7km"  # Альтернативный URL

# Конфигурация кеширования
cache_data = None
cache_time = None
CACHE_DURATION = 10  # секунд
LAST_COPERNICO_REQUEST = 0
REQUEST_MIN_INTERVAL = 2  # минимальный интервал между запросами к Copernico в секундах

# Структура маршрута для Снежной семерки (7 км, 2 круга по 3.5 км)
RACE_CONFIG = {
    'total_distance': 7.0,  # общая дистанция в км
    'lap_distance': 3.5,  # дистанция одного круга в км
    'event_name': 'Снежная семерка',
    'checkpoints': [
        {'id': 'start', 'distance': 0.0, 'name': 'Старт', 'coord': [56.028855, 92.946101]},
        {'id': 'turn1', 'distance': 1.75, 'name': '1.75 км (разворот)', 'coord': [56.02996, 92.949893]},
        {'id': 'lap_end', 'distance': 3.5, 'name': '3.5 км (конец 1 круга)', 'coord': [56.0295, 92.947]},
        {'id': 'turn2', 'distance': 5.25, 'name': '5.25 км (разворот)', 'coord': [56.02996, 92.949893]},
        {'id': 'finish', 'distance': 7.0, 'name': 'Финиш', 'coord': [56.028855, 92.946101]}
    ],
    'segments': [
        {'from': 'start', 'to': 'turn1', 'distance': 1.75, 'direction': 'forward'},
        {'from': 'turn1', 'to': 'lap_end', 'distance': 1.75, 'direction': 'backward'},
        {'from': 'lap_end', 'to': 'turn2', 'distance': 1.75, 'direction': 'forward'},
        {'from': 'turn2', 'to': 'finish', 'distance': 1.75, 'direction': 'backward'}
    ]
}

# Блокировка для потокобезопасного доступа к кешу
cache_lock = threading.Lock()


def fetch_copernico_data():
    """Получение данных из Copernico API"""
    global LAST_COPERNICO_REQUEST

    try:
        # Проверка интервала между запросами
        current_time = time.time()
        time_since_last_request = current_time - LAST_COPERNICO_REQUEST

        if time_since_last_request < REQUEST_MIN_INTERVAL:
            wait_time = REQUEST_MIN_INTERVAL - time_since_last_request
            logger.info(f"⏳ Ожидание {wait_time:.1f} сек перед следующим запросом к Copernico")
            time.sleep(wait_time)

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'application/json'
        }

        logger.info(f"🌐 Запрос данных из Copernico API: {COPERNICO_API_URL}")
        response = requests.get(COPERNICO_API_URL, headers=headers, timeout=15)
        response.raise_for_status()

        # Проверяем, что это действительно JSON
        content_type = response.headers.get('content-type', '')
        if 'application/json' not in content_type.lower():
            logger.warning(f"⚠️ Ответ не JSON: {content_type}")
            logger.debug(f"📄 Ответ (первые 500 символов): {response.text[:500]}")
            return []

        LAST_COPERNICO_REQUEST = time.time()
        data = response.json()
        logger.info(
            f"✅ Успешно получены данные из Copernico, количество участников: {len(data) if isinstance(data, list) else 'неизвестно'}")

        return data

    except Exception as e:
        logger.error(f"❌ Ошибка при получении данных из Copernico: {e}")
        return []


def parse_runner_data(raw_runner):
    """Парсинг данных одного спортсмена из формата Copernico"""
    try:
        # Извлекаем базовые данные
        runner_id = raw_runner.get('Id') or raw_runner.get('id') or raw_runner.get('dorsal') or 0
        dorsal = raw_runner.get('dorsal') or runner_id
        name = raw_runner.get('Name') or raw_runner.get('name', '')
        surname = raw_runner.get('Surname') or raw_runner.get('surname', '')
        full_name = raw_runner.get('Full name') or raw_runner.get('full_name') or f"{surname} {name}".strip()

        if not full_name:
            full_name = f"Участник {dorsal}"

        category = raw_runner.get('Category') or raw_runner.get('category', 'Не указана')
        gender = raw_runner.get('Gender') or raw_runner.get('gender', 'unknown')
        status = raw_runner.get('Status') or raw_runner.get('status', 'started')
        status = 'finished' if status.lower() in ['finished', 'финишировал'] else 'started'

        # Извлекаем данные о контрольных точках
        checkpoints = []
        checkpoint_mapping = {
            'start': {
                'official': 'Start.toficial',
                'real': 'Start.treal',
                'pos': 'Start.pos',
                'distance': 0.0,
                'name': 'Старт'
            },
            'turn1': {
                'official': '1.75km.toficial',
                'real': '1.75km.treal',
                'pos': '1.75km.pos',
                'distance': 1.75,
                'name': '1.75 км'
            },
            'lap_end': {
                'official': '3.5km.toficial',
                'real': '3.5km.treal',
                'pos': '3.5km.pos',
                'distance': 3.5,
                'name': '3.5 км'
            },
            'turn2': {
                'official': '5.25km.toficial',
                'real': '5.25km.treal',
                'pos': '5.25km.pos',
                'distance': 5.25,
                'name': '5.25 км'
            },
            'finish': {
                'official': 'Finish.toficial',
                'real': 'Finish.treal',
                'pos': 'Finish.pos',
                'distance': 7.0,
                'name': 'Финиш'
            }
        }

        for cp_id, cp_info in checkpoint_mapping.items():
            cp_time_official = raw_runner.get(cp_info['official'])
            cp_time_real = raw_runner.get(cp_info['real'])
            cp_pos = raw_runner.get(cp_info['pos'])

            checkpoint = {
                'id': cp_id,
                'name': cp_info['name'],
                'distance': cp_info['distance'],
                'passed': False,
                'time': None,
                'timestamp': None,
                'position': cp_pos if cp_pos and cp_pos != '-' else None
            }

            # Проверяем, прошел ли спортсмен эту точку
            if cp_time_official and cp_time_official != '-' and cp_time_official.strip():
                try:
                    # Формат времени: "ЧЧ:ММ:СС" или "ММ:СС"
                    time_parts = cp_time_official.split(':')
                    if len(time_parts) == 2:  # ММ:СС
                        minutes, seconds = map(int, time_parts)
                        total_seconds = minutes * 60 + seconds
                    elif len(time_parts) == 3:  # ЧЧ:ММ:СС
                        hours, minutes, seconds = map(int, time_parts)
                        total_seconds = hours * 3600 + minutes * 60 + seconds
                    else:
                        total_seconds = 0

                    # Время в миллисекундах с начала дня
                    start_time = datetime.strptime("10:00:00", "%H:%M:%S")
                    checkpoint_time = start_time + timedelta(seconds=total_seconds)
                    checkpoint['time'] = int(checkpoint_time.timestamp() * 1000)
                    checkpoint['timestamp'] = checkpoint_time.isoformat()
                    checkpoint['passed'] = True
                except (ValueError, TypeError) as e:
                    logger.debug(f"⚠️ Ошибка парсинга времени для точки {cp_id}: {e}")

            checkpoints.append(checkpoint)

        # Рассчитываем текущую дистанцию и позицию
        current_distance = 0.0
        for cp in reversed(checkpoints):
            if cp['passed']:
                current_distance = cp['distance']
                break

        # Определяем текущий сегмент
        current_segment = None
        for segment in RACE_CONFIG['segments']:
            start_cp = next(cp for cp in RACE_CONFIG['checkpoints'] if cp['id'] == segment['from'])
            end_cp = next(cp for cp in RACE_CONFIG['checkpoints'] if cp['id'] == segment['to'])

            if start_cp['distance'] <= current_distance <= end_cp['distance']:
                current_segment = segment
                break

        # Рассчитываем прогресс на текущем сегменте
        segment_progress = 0.0
        if current_segment:
            start_cp = next(cp for cp in RACE_CONFIG['checkpoints'] if cp['id'] == current_segment['from'])
            end_cp = next(cp for cp in RACE_CONFIG['checkpoints'] if cp['id'] == current_segment['to'])

            if end_cp['distance'] > start_cp['distance']:
                segment_progress = (current_distance - start_cp['distance']) / (
                            end_cp['distance'] - start_cp['distance'])
            else:
                segment_progress = (start_cp['distance'] - current_distance) / (
                            start_cp['distance'] - end_cp['distance'])

        # Рассчитываем позицию на карте
        position = calculate_position_by_distance(current_distance)

        # Получаем темп из данных Copernico
        finish_avg_pace = raw_runner.get('Finish.avg') or raw_runner.get('avg_pace')
        pace = 6.0  # Темп по умолчанию 6:00 мин/км
        if finish_avg_pace and finish_avg_pace != '-':
            try:
                # Формат: "ММ'СС""/Км"
                pace_parts = finish_avg_pace.replace('"', '').replace("'", ":").split(':')
                if len(pace_parts) >= 2:
                    minutes = int(pace_parts[0])
                    seconds = int(pace_parts[1])
                    pace = minutes + seconds / 60
            except (ValueError, TypeError) as e:
                logger.debug(f"⚠️ Ошибка парсинга темпа: {e}")

        # Формируем объект спортсмена
        runner = {
            'id': runner_id,
            'dorsal': dorsal,
            'name': name,
            'surname': surname,
            'full_name': full_name,
            'category': category,
            'gender': gender,
            'status': status,
            'pace': round(pace, 2),
            'current_distance': round(current_distance, 2),
            'checkpoints': checkpoints,
            'last_update': datetime.now().isoformat(),
            'position': {
                'lat': position[0],
                'lng': position[1]
            }
        }

        return runner

    except Exception as e:
        logger.error(f"⚠️ Ошибка обработки спортсмена: {type(e).__name__}: {e}")
        return None


def calculate_distance_between_points(point1, point2):
    """Рассчитывает расстояние между двумя точками в км (упрощенно)"""
    # Используем упрощенную формулу для небольших расстояний
    lat1, lon1 = point1
    lat2, lon2 = point2

    # Приблизительное расстояние в км (1 градус широты ≈ 111 км)
    lat_distance = (lat2 - lat1) * 111
    lon_distance = (lon2 - lon1) * 111 * math.cos(math.radians((lat1 + lat2) / 2))

    return math.sqrt(lat_distance ** 2 + lon_distance ** 2)


def find_segment_by_distance(distance):
    """Находит сегмент маршрута по пройденной дистанции"""
    for segment in RACE_CONFIG['segments']:
        start_point = next(cp for cp in RACE_CONFIG['checkpoints'] if cp['id'] == segment['from'])
        end_point = next(cp for cp in RACE_CONFIG['checkpoints'] if cp['id'] == segment['to'])

        if start_point['distance'] <= distance <= end_point['distance']:
            return {
                'segment': segment,
                'start_point': start_point,
                'end_point': end_point,
                'segment_progress': (distance - start_point['distance']) / segment['distance']
            }

    # Если дистанция больше общей длины, возвращаем последний сегмент
    last_segment = RACE_CONFIG['segments'][-1]
    last_start = next(cp for cp in RACE_CONFIG['checkpoints'] if cp['id'] == last_segment['from'])
    last_end = next(cp for cp in RACE_CONFIG['checkpoints'] if cp['id'] == last_segment['to'])

    return {
        'segment': last_segment,
        'start_point': last_start,
        'end_point': last_end,
        'segment_progress': 1.0
    }


def calculate_position_by_distance(distance):
    """Рассчитывает координаты по пройденной дистанции"""
    segment_info = find_segment_by_distance(distance)

    if segment_info['segment_progress'] >= 1.0:
        return segment_info['end_point']['coord']

    start_coord = segment_info['start_point']['coord']
    end_coord = segment_info['end_point']['coord']
    progress = segment_info['segment_progress']

    # Линейная интерполяция между точками
    lat = start_coord[0] + (end_coord[0] - start_coord[0]) * progress
    lng = start_coord[1] + (end_coord[1] - start_coord[1]) * progress

    return [lat, lng]


def transform_copernico_data(raw_data):
    """Трансформация данных из Copernico в наш формат"""
    runners = []

    if not isinstance(raw_data, list):
        logger.warning(f"⚠️ Неожиданный формат данных из Copernico: {type(raw_data)}")
        return runners

    logger.info(f"🔄 Обработка {len(raw_data)} спортсменов из Copernico")

    for i, item in enumerate(raw_data):
        try:
            runner = parse_runner_data(item)
            if runner:
                runners.append(runner)
        except Exception as e:
            logger.error(f"⚠️ Ошибка обработки спортсмена {i}: {type(e).__name__}: {e}")
            logger.debug(f"   Данные спортсмена: {item}")

    logger.info(f"✅ Успешно обработано {len(runners)} спортсменов")
    return runners


@app.route('/')
def serve_index():
    """Отдача главной страницы"""
    return send_from_directory(BASE_DIR, 'map.html')


@app.route('/api/runners', methods=['GET'])
def get_runners():
    """Основной endpoint для получения данных участников"""
    global cache_data, cache_time

    try:
        current_time = datetime.now()

        # Проверяем кеш
        with cache_lock:
            if cache_data and cache_time:
                elapsed = (current_time - cache_time).total_seconds()
                if elapsed < CACHE_DURATION:
                    logger.info(f"📦 Используем кешированные данные ({elapsed:.1f} сек)")
                    return jsonify(cache_data)

        # Получаем данные из Copernico
        raw_data = fetch_copernico_data()

        if not raw_data:
            logger.warning("⚠️ Нет данных от Copernico")

            # Если нет данных, но есть кеш - вернем его даже если просрочен
            with cache_lock:
                if cache_data:
                    logger.info("📦 Возвращаем устаревшие кешированные данные")
                    return jsonify(cache_data)

            return jsonify([])

        # Трансформируем данные
        runners = transform_copernico_data(raw_data)

        # Если не удалось получить участников, используем минимальные тестовые данные
        if not runners:
            logger.warning("⚠️ Не удалось преобразовать данные, используем минимальные тестовые данные")
            runners = [{
                'id': 1,
                'dorsal': 1,
                'name': 'Тест',
                'surname': 'Участник',
                'full_name': 'Тест Участник',
                'category': 'Тестовая категория',
                'gender': 'male',
                'status': 'started',
                'pace': 6.0,
                'current_distance': 0.1,
                'checkpoints': [],
                'last_update': current_time.isoformat(),
                'position': {
                    'lat': RACE_CONFIG['checkpoints'][0]['coord'][0],
                    'lng': RACE_CONFIG['checkpoints'][0]['coord'][1]
                }
            }]

        # Сохраняем в кеш
        with cache_lock:
            cache_data = runners
            cache_time = current_time

        logger.info(f"✅ Отправляем {len(runners)} участников")
        return jsonify(runners)

    except Exception as e:
        logger.error(f"❌ Ошибка в /api/runners: {type(e).__name__}: {e}")

        # В случае ошибки вернем пустой список или кеш
        with cache_lock:
            if cache_data:
                logger.info("📦 Возвращаем кешированные данные из-за ошибки")
                return jsonify(cache_data)

        return jsonify({"error": str(e), "message": "Ошибка сервера"}), 500


@app.route('/api/race-config', methods=['GET'])
def get_race_config():
    """Endpoint для получения конфигурации забега"""
    return jsonify({
        'total_distance': RACE_CONFIG['total_distance'],
        'lap_distance': RACE_CONFIG['lap_distance'],
        'event_name': RACE_CONFIG['event_name'],
        'checkpoints': [
            {
                'id': cp['id'],
                'distance': cp['distance'],
                'name': cp['name'],
                'coord': cp['coord']
            } for cp in RACE_CONFIG['checkpoints']
        ],
        'segments': RACE_CONFIG['segments']
    })


@app.route('/api/test', methods=['GET'])
def test_endpoint():
    """Тестовый endpoint для проверки"""
    return jsonify({
        "status": "ok",
        "message": "Сервер работает",
        "timestamp": datetime.now().isoformat(),
        "race_config": {
            'event_name': RACE_CONFIG['event_name'],
            'total_distance': RACE_CONFIG['total_distance'],
            'checkpoints_count': len(RACE_CONFIG['checkpoints'])
        }
    })


if __name__ == '__main__':
    print("🚀 Запуск обновленного сервера для Снежной семерки (7 км, 2 круга)")
    print("=" * 70)
    print(f"🌐 Главная страница: http://localhost:5000/")
    print(f"📡 API участников: http://localhost:5000/api/runners")
    print(f"⚙️ API конфигурации: http://localhost:5000/api/race-config")
    print(f"🧪 Тестовый endpoint: http://localhost:5000/api/test")
    print("=" * 70)
    print(f"📋 Забег: {RACE_CONFIG['event_name']}")
    print(f"📏 Общая длина: {RACE_CONFIG['total_distance']} км (2 круга по {RACE_CONFIG['lap_distance']} км)")
    print(f"🎯 Ключевые точки: Старт → 1.75 км → 3.5 км → 5.25 км → Финиш")
    print("=" * 70)

    app.run(host='0.0.0.0', port=5000, debug=True)