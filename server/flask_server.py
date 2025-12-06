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
from ParsingRaceInMap import CopernicoParser


# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

app = Flask(__name__, static_folder=os.path.join(BASE_DIR, 'server', 'static'))
CORS(app)

# --- КЛЮЧЕВОЕ ИЗМЕНЕНИЕ: ПУТЬ К ЛОКАЛЬНОМУ ФАЙЛУ ---
RACE_DATA_FILE = os.path.join(BASE_DIR, "race_data.json")  # Путь к файлу

# Конфигурация кеширования
cache_data = None
cache_time = None
CACHE_DURATION = 10
LAST_COPERNICO_REQUEST = 0
REQUEST_MIN_INTERVAL = 2

# OSM конфигурация
OSM_WAY_ID = 181589417
osm_route_data = None

# Выбранные участники. Глобальная переменная для хранения выбранных участников
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
ParsingRaceInMap = CopernicoParser(race_config)

# Блокировка
cache_lock = threading.Lock()


def fetch_copernico_data():
    """Получение данных из локального файла race_data.json"""
    try:
        if not os.path.exists(RACE_DATA_FILE):
            logger.error(f"❌ Файл НЕ НАЙДЕН: {os.path.abspath(RACE_DATA_FILE)}")
            return []
        
        with open(RACE_DATA_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Исправлено: ключ "data" вместо "data"
        raw_data = data.get("data", [])
        
        if not isinstance(raw_data, list):
            logger.error(f"⚠️ Неверный формат данных. Ожидался список, получен: {type(raw_data)}")
            logger.debug(f"Структура данных: {json.dumps(data, ensure_ascii=False, indent=2)[:500]}...")
            return []
        
        logger.info(f"✅ Успешно загружено {len(raw_data)} участников из файла")
        return raw_data

    except json.JSONDecodeError as e:
        logger.error(f"❌ Ошибка разбора JSON: {str(e)}")
        logger.error(f"Содержимое файла (первые 500 символов):")
        with open(RACE_DATA_FILE, 'r', encoding='utf-8') as f:
            logger.error(f.read()[:500])
        return []
    
    except Exception as e:
        logger.exception(f"❌ Неожиданная ошибка при чтении файла: {str(e)}")
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
            runner = ParsingRaceInMap.parse_runner_data(item)
            if runner:
                runners.append(runner)
        except Exception as e:
            logger.error(f"⚠️ Ошибка обработки спортсмена {i}: {type(e).__name__}: {e}")

    logger.info(f"✅ Успешно обработано {len(runners)} спортсменов")
    return runners


# API Endpoints
@app.route('/')
def serve_index():
    static_path = os.path.join(app.static_folder, 'index.html')
    print(f"🔍 Пытаемся найти файл: {static_path}")

    if os.path.exists(static_path):
        return send_from_directory(app.static_folder, 'index.html')
    else:
        # Попробуем найти файл в альтернативных путях
        alternative_paths = [
            os.path.join(os.path.dirname(__file__), 'static', 'index.html'),
            os.path.join(os.getcwd(), 'server', 'static', 'index.html'),
            os.path.join(os.getcwd(), 'static', 'index.html')
        ]

        for path in alternative_paths:
            print(f"🔍 Проверяем альтернативный путь: {path}")
            if os.path.exists(path):
                folder = os.path.dirname(path)
                return send_from_directory(folder, 'index.html')

        # Если ничего не найдено
        error_msg = f"""
        <h1>❌ 404 Файл не найден</h1>
        <p>Flask не может найти index.html. Проверьте файловую структуру.</p>
        <h3>Проверенные пути:</h3>
        <ul>
            <li>{static_path}</li>
        </ul>
        <h3>Текущая структура папки:</h3>
        <ul>
        {''.join(f'<li>{item}</li>' for item in os.listdir(BASE_DIR) if os.path.isdir(os.path.join(BASE_DIR, item)))}
        </ul>
        """
        return error_msg, 404



@app.route('/api/runners', methods=['GET'])
def get_runners():
    """Основной endpoint для получения данных участников"""
    global cache_data, cache_time

    current_time = datetime.now()

    with cache_lock:
        if cache_data and cache_time:
            elapsed = (current_time - cache_time).total_seconds()
            if elapsed < CACHE_DURATION:
                logger.info(f"📦 Используем кешированные данные ({elapsed:.1f} сек)")
                return jsonify(cache_data)

    # Получаем данные из Copernico
    raw_data = fetch_copernico_data()
    runners = transform_copernico_data(raw_data)

    # Сохраняем в кеш
    with cache_lock:
        cache_data = runners
        cache_time = current_time

    logger.info(f"✅ Отправляем {len(runners)} участников")
    return jsonify(runners)


@app.route('/api/search-runners', methods=['GET'])
def search_runners():
    """Поиск участников по номеру (dorsal) или фамилии (исправлены переменные)"""
    global cache_data  # Убедитесь, что эта строка есть в начале функции

    try:
        query = request.args.get('q', '').strip()
        if not query or cache_data is None:  # ИСПРАВЛЕНО: cache_ → cache_data
            logger.debug("🔍 Пустой запрос или отсутствуют данные для поиска")
            return jsonify([])
        
        query_lower = query.lower()
        logger.debug(f"🔍 Поиск участников по запросу: '{query}'")
        results = []

        # ИСПРАВЛЕНО: cache_ → cache_data
        for runner in cache_data or []:
            # 1. Поиск по dorsal (основное поле)
            dorsal_value = str(runner.get('dorsal', '')).strip()
            if dorsal_value.startswith(query):
                results.append(runner)
                continue
                
            # 2. Поиск по фамилии
            surname_value = str(runner.get('surname', '')).strip().lower()
            if surname_value.startswith(query_lower):
                results.append(runner)
                continue
                
            # 3. Поиск по полному имени
            full_name_value = str(runner.get('full_name', '')).strip().lower()
            if query_lower in full_name_value:
                results.append(runner)

        # Сортировка результатов
        def sort_key(runner):
            dorsal_match = str(runner.get('dorsal', '')).startswith(query)
            surname_match = str(runner.get('surname', '')).lower().startswith(query_lower)
            
            if dorsal_match:
                return (0, str(runner.get('dorsal', '')))
            elif surname_match:
                return (1, runner.get('surname', ''))
            else:
                return (2, runner.get('full_name', ''))

        results.sort(key=sort_key)
        
        # Безопасное логирование результатов
        results_preview = [
            f"{r.get('dorsal', '')} - {r.get('full_name', '')}" 
            for r in results[:5]
        ]
        logger.info(f"✅ Найдено {len(results)} участников по запросу '{query}'")
        logger.debug(f"Результаты (первые 5): {results_preview}")
        
        return jsonify(results[:20])

    except Exception as e:
        logger.exception(f"❌ Критическая ошибка в поиске: {str(e)}")
        return jsonify([])

@app.route('/api/select-runner', methods=['POST'])
def select_runner():
    """Выбор участника для отслеживания (исправленная версия)"""
    global selected_runners

    try:
        data = request.get_json()
        runner_id = str(data.get('runner_id', '')).strip()

        if not runner_id:
            return jsonify({'error': 'Не указан runner_id'}), 400

        # Проверяем лимит
        if len(selected_runners) >= MAX_SELECTED_RUNNERS:
            return jsonify({
                'error': f'Максимум можно отслеживать {MAX_SELECTED_RUNNERS} участников',
                'success': False
            }), 400

        # Добавляем участника
        selected_runners.add(runner_id)
        logger.info(f"✅ Добавлен участник {runner_id}. Всего: {len(selected_runners)}")
        
        return jsonify({
            'success': True,
            'selected_count': len(selected_runners),
            'selected_ids': list(selected_runners)
        })

    except Exception as e:
        logger.error(f"❌ Ошибка выбора участника: {e}")
        return jsonify({'error': str(e), 'success': False}), 500


@app.route('/api/selected-runners', methods=['GET'])
def get_selected_runners():
    """Получение данных только выбранных участников (исправленная версия)"""
    global cache_data, selected_runners

    try:
        with cache_lock:
            if not cache_data:
                return jsonify([])
            
            # Фильтруем только выбранных участников
            selected_data = [
                runner for runner in cache_data
                if str(runner.get('id')) in selected_runners
            ]

            # ДОБАВЛЕНО: Логирование для отладки
            logger.info(f"🔍 Запрошено {len(selected_data)} выбранных участников")
            return jsonify(selected_data)

    except Exception as e:
        logger.error(f"❌ Ошибка получения выбранных участников: {e}")
        return jsonify([]), 500

@app.route('/api/deselect-runner', methods=['POST'])
def deselect_runner():
    """Удаление участника из отслеживаемых"""
    global selected_runners

    try:
        data = request.get_json()
        runner_id = str(data.get('runner_id', '')).strip()

        if runner_id in selected_runners:
            selected_runners.remove(runner_id)
            logger.info(f"❌ Удален участник {runner_id}. Осталось: {len(selected_runners)}")

        return jsonify({
            'success': True,
            'selected_count': len(selected_runners),
            'selected_ids': list(selected_runners)
        })

    except Exception as e:
        logger.error(f"❌ Ошибка удаления участника: {e}")
        return jsonify({'error': str(e), 'success': False}), 500

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
    
@app.route('/api/debug-data-structure', methods=['GET'])
def debug_data_structure():
    """Отладочный endpoint для проверки структуры данных"""
    global cache_data
    
    if not cache_data:
        return jsonify({"error": "Нет данных в кеше"})
    
    # Берем первого участника для анализа структуры
    sample_runner = cache_data[0] if cache_data else {}
    
    return jsonify({
        "total_runners": len(cache_data),
        "sample_runner_keys": list(sample_runner.keys()),
        "sample_runner": sample_runner,
        "search_fields_available": {
            "has_bib": "bib" in sample_runner,
            "has_surname": "surname" in sample_runner,
            "has_full_name": "full_name" in sample_runner,
            "bib_type": type(sample_runner.get('bib')).__name__,
            "surname_type": type(sample_runner.get('surname')).__name__
        }
    })


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