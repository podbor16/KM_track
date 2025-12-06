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
from copernico_parser import CopernicoParser

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

app = Flask(__name__, static_folder=os.path.join(BASE_DIR, 'server', 'static'))
CORS(app)

# Конфигурация
COPERNICO_API_URL = "https://public-api.copernico.cloud/api/races/--2025-70363/preset/podbor250718@gmail.com:::Снежная 7 трекер/7%20km"

# Конфигурация кеширования
cache_data = None
cache_time = None
CACHE_DURATION = 10
LAST_COPERNICO_REQUEST = 0
REQUEST_MIN_INTERVAL = 2

# OSM конфигурация
OSM_WAY_ID = 181589417
osm_route_data = None

# Выбранные участники
selected_runners = set()
MAX_SELECTED_RUNNERS = 5


# Конфигурация забега
class RaceConfig:
    def __init__(self):
        self.total_distance = 7.0
        self.lap_distance = 3.5
        self.event_name = "Снежная семерка"
        self.checkpoints = [
            {'id': 'start', 'distance': 0.0, 'name': 'Старт', 'coord': [56.028855, 92.946101]},
            {'id': 'turn1', 'distance': 1.75, 'name': '1.75 км (разворот)', 'coord': [56.02996, 92.949893]},
            {'id': 'lap_end', 'distance': 3.5, 'name': '3.5 км (конец 1 круга)', 'coord': [56.0295, 92.947]},
            {'id': 'turn2', 'distance': 5.25, 'name': '5.25 км (разворот)', 'coord': [56.02996, 92.949893]},
            {'id': 'finish', 'distance': 7.0, 'name': 'Финиш', 'coord': [56.028855, 92.946101]}
        ]


race_config = RaceConfig()
copernico_parser = CopernicoParser(race_config)

# Блокировка
cache_lock = threading.Lock()


def fetch_copernico_data():
    """Получение данных из Copernico API"""
    global LAST_COPERNICO_REQUEST

    try:
        current_time = time.time()
        time_since_last_request = current_time - LAST_COPERNICO_REQUEST

        if time_since_last_request < REQUEST_MIN_INTERVAL:
            wait_time = REQUEST_MIN_INTERVAL - time_since_last_request
            logger.info(f"⏳ Ожидание {wait_time:.1f} сек")
            time.sleep(wait_time)

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json'
        }

        logger.info(f"🌐 Запрос данных из Copernico API: {COPERNICO_API_URL}")
        response = requests.get(COPERNICO_API_URL, headers=headers, timeout=15)
        response.raise_for_status()

        LAST_COPERNICO_REQUEST = time.time()
        data = response.json()

        logger.info(
            f"✅ Успешно получены данные, количество участников: {len(data) if isinstance(data, list) else 'неизвестно'}")
        return data

    except Exception as e:
        logger.error(f"❌ Ошибка при получении данных из Copernico: {e}")
        return []


def transform_copernico_data(raw_data):
    """Трансформация данных из Copernico в наш формат"""
    runners = []

    if not isinstance(raw_data, list):
        logger.warning(f"⚠️ Неожиданный формат данных: {type(raw_data)}")
        return runners

    logger.info(f"🔄 Обработка {len(raw_data)} спортсменов")

    for i, item in enumerate(raw_data):
        try:
            runner = copernico_parser.parse_runner_data(item)
            if runner:
                runners.append(runner)
        except Exception as e:
            logger.error(f"⚠️ Ошибка обработки спортсмена {i}: {type(e).__name__}: {e}")

    logger.info(f"✅ Успешно обработано {len(runners)} спортсменов")
    return runners


def generate_test_data():
    """Генерация тестовых данных для разработки"""
    import random
    from datetime import datetime, timedelta

    test_runners = []

    # Используем реальные данные из CSV для имен
    test_names = [
        {"Bib": 212, "Name": "Ирина", "Surname": "Дементьева", "full_name": "Ирина Дементьева", "Category": "Женщины"},
        {"Bib": 592, "Name": "Николай", "Surname": "Бывальцев", "full_name": "Николай Бывальцев",
         "Category": "Мужчины"},
        {"Bib": 2, "Name": "Сергей", "Surname": "Кольга", "full_name": "Сергей Кольга", "Category": "Мужчины"},
        {"Bib": 93, "Name": "Татьяна", "Surname": "Шелкунова", "full_name": "Татьяна Шелкунова", "Category": "Женщины"},
        {"Bib": 349, "Name": "Игорь", "Surname": "Копачев", "full_name": "Игорь Копачев", "Category": "Мужчины"},
    ]

    for i, name_data in enumerate(test_names):
        # Случайная дистанция и статус
        if i == 0:
            status = "Finished"
            distance = 7.0
        elif i == 1:
            status = "Started"
            distance = random.uniform(3.0, 6.5)
        else:
            status = random.choice(["Not started", "Started"])
            distance = random.uniform(0.0, 6.5) if status == "Started" else 0.0

        # Время
        start_time = "10:00:00" if status in ["Started", "Finished"] else ""
        finish_time = "10:45:00" if status == "Finished" else ""

        # Позиция
        position = copernico_parser._calculate_position(distance)

        runner = {
            'Id': f"test_{name_data['Bib']}",
            'Bib': name_data['Bib'],
            'Name': name_data['Name'],
            'Surname': name_data['Surname'],
            'Full name': name_data['full_name'],
            'Category': name_data['Category'],
            'Gender': 'Female' if name_data['Category'] == 'Женщины' else 'Male',
            'Status': status,
            'Start': {'treal': start_time if start_time else None},
            'kt2': {'treal': start_time if distance > 3.5 else None},
            'Finish': {'treal': finish_time if finish_time else None},
            'Position': position,
            'last_update': datetime.now().isoformat()
        }

        if distance > 0:
            runner['current_distance'] = distance

        test_runners.append(runner)

    return test_runners


# API Endpoints
@app.route('/')
def serve_map():
    """Отдача главной страницы"""
    return send_from_directory(app.static_folder, 'tilda-embed.html')


@app.route('/api/runners', methods=['GET'])
def get_runners():
    """Основной endpoint для получения данных участников"""
    global cache_data, cache_time

    try:
        current_time = datetime.now()

        with cache_lock:
            if cache_data and cache_time:
                elapsed = (current_time - cache_time).total_seconds()
                if elapsed < CACHE_DURATION:
                    logger.info(f"📦 Используем кешированные данные ({elapsed:.1f} сек)")
                    return jsonify(cache_data)

        # Получаем данные из Copernico
        raw_data = fetch_copernico_data()

        if not raw_data:
            logger.warning("⚠️ Нет данных от Copernico, используем тестовые данные")
            runners = generate_test_data()
        else:
            # Трансформируем данные
            runners = transform_copernico_data(raw_data)

            if not runners:
                logger.warning("⚠️ Не удалось преобразовать данные, используем тестовые данные")
                runners = generate_test_data()

        # Сохраняем в кеш
        with cache_lock:
            cache_data = runners
            cache_time = current_time

        logger.info(f"✅ Отправляем {len(runners)} участников")
        return jsonify(runners)

    except Exception as e:
        logger.error(f"❌ Ошибка в /api/runners: {type(e).__name__}: {e}")

        with cache_lock:
            if cache_data:
                logger.info("📦 Возвращаем кешированные данные из-за ошибки")
                return jsonify(cache_data)

        return jsonify(generate_test_data())


@app.route('/api/search-runners', methods=['GET'])
def search_runners():
    """Поиск участников по номеру или фамилии"""
    global cache_data

    try:
        query = request.args.get('q', '').strip().lower()
        if not query or not cache_data:
            return jsonify([])

        results = []

        for runner in cache_data:
            # Поиск по номеру (начинается с введенного текста)
            if str(runner.get('Bib', '')).startswith(query):
                results.append(runner)
                continue

            # Поиск по фамилии (начинается с введенного текста)
            surname = runner.get('Surname', '').lower()
            if surname.startswith(query):
                results.append(runner)

        # Сортируем: сначала по номеру, потом по фамилии
        results.sort(key=lambda x: (
            not str(x.get('Bib', '')).startswith(query),
            x.get('Bib', 9999),
            x.get('Surname', '')
        ))

        return jsonify(results[:20])

    except Exception as e:
        logger.error(f"❌ Ошибка поиска: {e}")
        return jsonify([])


@app.route('/api/select-runner', methods=['POST'])
def select_runner():
    """Выбор участника для отслеживания"""
    global selected_runners

    try:
        data = request.get_json()
        runner_id = str(data.get('runner_id'))

        if not runner_id:
            return jsonify({'error': 'No runner_id provided'}), 400

        if len(selected_runners) >= MAX_SELECTED_RUNNERS:
            return jsonify({
                'error': f'Максимум можно отслеживать {MAX_SELECTED_RUNNERS} участников'
            }), 400

        selected_runners.add(runner_id)

        return jsonify({
            'success': True,
            'selected_count': len(selected_runners),
            'selected_ids': list(selected_runners)
        })

    except Exception as e:
        logger.error(f"❌ Ошибка выбора участника: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/selected-runners', methods=['GET'])
def get_selected_runners():
    """Получение данных только выбранных участников"""
    global cache_data, selected_runners

    try:
        with cache_lock:
            if not cache_data:
                return jsonify([])

            selected_data = [
                runner for runner in cache_data
                if str(runner.get('Bib')) in selected_runners
            ]

            return jsonify(selected_data)

    except Exception as e:
        logger.error(f"❌ Ошибка получения выбранных участников: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Статистика по участникам"""
    global cache_data

    try:
        with cache_lock:
            if not cache_data:
                return jsonify({
                    'total': 0,
                    'not_started': 0,
                    'on_track': 0,
                    'finished': 0
                })

            total = len(cache_data)
            not_started = sum(1 for r in cache_data if r.get('Status') == 'Not started')
            finished = sum(1 for r in cache_data if r.get('Status') == 'Finished')
            on_track = total - not_started - finished

            return jsonify({
                'total': total,
                'not_started': not_started,
                'on_track': on_track,
                'finished': finished
            })

    except Exception as e:
        logger.error(f"❌ Ошибка получения статистики: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/race-config', methods=['GET'])
def get_race_config():
    """Endpoint для получения конфигурации забега"""
    return jsonify({
        'event_name': race_config.event_name,
        'total_distance': race_config.total_distance,
        'lap_distance': race_config.lap_distance,
        'checkpoints': race_config.checkpoints
    })


@app.route('/api/test', methods=['GET'])
def test_endpoint():
    """Тестовый endpoint"""
    return jsonify({
        'status': 'ok',
        'message': 'Сервер работает',
        'timestamp': datetime.now().isoformat()
    })


if __name__ == '__main__':
    print("🚀 Запуск трекера Снежной семерки")
    print(f"📡 API доступен по адресу: http://localhost:5000")
    print(f"🏃 Забег: {race_config.event_name} ({race_config.total_distance} км)")
    print("=" * 50)
    app.run(host='0.0.0.0', port=5000, debug=True)