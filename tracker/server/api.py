# server/api.py
"""
API endpoints для трекера забега
"""
from flask import jsonify, request, send_from_directory
import os
import threading
import logging
from datetime import datetime

from config import BASE_DIR, EVENTS_CONFIG, CURRENT_EVENT, CACHE_DURATION, MAX_SELECTED_RUNNERS
from routes_service import fetch_route_from_osm, get_route_calculator
from runners_service import (
    fetch_copernico_data, transform_copernico_data,
    update_runner_positions, race_config
)
from analytics_service import get_formatted_analytics
from analytics.db_connection import get_test_table_data
import config

logger = logging.getLogger(__name__)

# Кеш данных бегунов
cache_data = None
cache_time = None
cache_lock = threading.Lock()

# Выбранные участники
selected_runners = set()


def init_routes(app):
    """Регистрирует все API routes в Flask приложении"""

    @app.route('/api/current-event')
    def get_current_event():
        """Получить текущее событие из конфига"""
        event = config.CURRENT_EVENT
        storage_key = f"{event}_selected_runners"
        event_config = EVENTS_CONFIG.get(event, {})
        return jsonify({
            'event': event,
            'storage_key': storage_key,
            'name': event_config.get('name', event),
            'title': event_config.get('title', f'Трекер забега {event}'),
            'description': event_config.get('description', ''),
            'route_type': 'loop' if event == 'rosneft' else 'shuttle'
        })

    @app.route('/api/route')
    def get_route():
        """Получение данных маршрута"""
        try:
            event_name = request.args.get('event', config.CURRENT_EVENT)
            if event_name not in EVENTS_CONFIG:
                event_name = config.CURRENT_EVENT

            event_config = EVENTS_CONFIG[event_name]
            route_data = fetch_route_from_osm(event_name)
            route_calc = get_route_calculator()

            if route_data:
                route_calc.set_path(route_data)
                return jsonify({
                    'coordinates': route_data,
                    'distance': event_config.get('total_race_km', event_config.get('one_way_length_km', 5.0)),
                    'way_id': event_config['osm_way_id'],
                    'event': event_name,
                    'event_name': event_config['name'],
                    'route_type': 'loop' if event_name == 'rosneft' else 'shuttle'
                })
            else:
                from routes_service import get_fallback_route
                return jsonify({
                    'coordinates': get_fallback_route(),
                    'distance': 7.0,
                    'fallback': True
                }), 503
        except Exception as e:
            logger.error(f"❌ Ошибка в /api/route: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/runners', methods=['GET'])
    def get_runners():
        """Получение списка бегунов с обновленными позициями"""
        global cache_data, cache_time

        try:
            event_name = request.args.get('event', config.CURRENT_EVENT)
            if event_name not in EVENTS_CONFIG:
                event_name = config.CURRENT_EVENT

            current_time = datetime.now()

            with cache_lock:
                # Проверяем кеш
                if cache_data and cache_time and (current_time - cache_time).total_seconds() < CACHE_DURATION:
                    cache_data = update_runner_positions(cache_data, event_name)
                    return jsonify(cache_data)

            # Загружаем новые данные из файла
            raw_data = fetch_copernico_data()
            
            if not raw_data:
                if cache_data:
                    runners = cache_data
                else:
                    return jsonify([])
            else:
                # Сохраняем прогресс старых данных
                new_runners_map = {str(r.get('dorsal')): r for r in transform_copernico_data(raw_data)}
                
                if cache_data:
                    for cached_runner in cache_data:
                        rid = str(cached_runner.get('dorsal'))
                        if rid in new_runners_map:
                            new_runners_map[rid]['current_distance'] = cached_runner.get('current_distance', 0)
                            new_runners_map[rid]['last_update'] = cached_runner.get('last_update')
                
                runners = list(new_runners_map.values())

            runners = update_runner_positions(runners, event_name)

            with cache_lock:
                cache_data = runners
                cache_time = current_time

            return jsonify(runners)

        except Exception as e:
            logger.error(f"❌ Ошибка в /api/runners: {e}")
            return jsonify([])

    @app.route('/api/search-runners', methods=['GET'])
    def search_runners():
        """Поиск бегунов по номеру или фамилии"""
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
        """Выбрать бегуна для отслеживания"""
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
        """Отменить выбор бегуна"""
        global selected_runners
        data = request.get_json()
        runner_id = str(data.get('runner_id', '')).strip()
        if runner_id in selected_runners:
            selected_runners.remove(runner_id)
        return jsonify({'success': True, 'selected_ids': list(selected_runners)})

    @app.route('/api/selected-runners', methods=['GET'])
    def get_selected_runners():
        """Получить выбранных бегунов"""
        global cache_data, selected_runners
        if not cache_data:
            return jsonify([])
        res = [r for r in cache_data if str(r.get('id')) in selected_runners or str(r.get('dorsal')) in selected_runners]
        return jsonify(res)

    @app.route('/api/race-config', methods=['GET'])
    def get_race_config_api():
        """Получить конфигурацию забега"""
        return jsonify({
            'event_name': race_config.event_name,
            'total_distance': race_config.total_distance,
            'checkpoints': race_config.checkpoints
        })

    @app.route('/')
    def serve_index():
        """Главная страница"""
        maps_folder = os.path.join(BASE_DIR, 'maps')
        if os.path.exists(os.path.join(maps_folder, 'snow7.html')):
            return send_from_directory(maps_folder, 'snow7.html')
        return "Map not found", 404

    @app.route('/maps/<map_name>')
    def serve_map(map_name):
        """Обслуживание конкретной карты мероприятия"""
        maps_folder = os.path.join(BASE_DIR, 'maps')
        if map_name.endswith('.html') and os.path.exists(os.path.join(maps_folder, map_name)):
            return send_from_directory(maps_folder, map_name)
        return f"Map '{map_name}' not found", 404

    @app.route('/api/events')
    def get_events():
        """Получение списка доступных мероприятий"""
        events = []
        for event_id, config in EVENTS_CONFIG.items():
            events.append({
                'id': event_id,
                'name': config['name'],
                'way_id': config['osm_way_id']
            })
        return jsonify({'events': events, 'current': CURRENT_EVENT})

    @app.route('/api/analytics', methods=['GET'])
    def get_analytics():
        """Получить аналитику по всем участникам"""
        try:
            analytics_data = get_formatted_analytics()
            return jsonify(analytics_data)
        except Exception as e:
            logger.error(f"❌ Ошибка в /api/analytics: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/registered-runners', methods=['GET'])
    def get_registered_runners():
        """Получить зарегистрированных участников из таблицы 'Тестовая'"""
        try:
            runners_data = get_test_table_data()
            return jsonify(runners_data)
        except Exception as e:
            logger.error(f"❌ Ошибка в /api/registered-runners: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/race-results', methods=['GET'])
    def get_race_results():
        """Получить результаты гонки из race_data.json"""
        try:
            import json
            with open('tracker/race_data.json', 'r', encoding='utf-8') as file:
                data = json.load(file)
            return jsonify(data.get('data', []))
        except Exception as e:
            logger.error(f"❌ Ошибка в /api/race-results: {e}")
            return jsonify([]), 500

    @app.route('/analytics', methods=['GET'])
    def serve_analytics_page():
        """Обслуживание страницы аналитики участников"""
        from flask import send_from_directory
        import os
        
        analytics_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'personal')
        return send_from_directory(analytics_dir, 'start_list.html')

    # Маршрут для статических файлов аналитики
    @app.route('/analytics/static/<path:filename>')
    def serve_analytics_static(filename):
        """Обслуживание статических файлов для страницы аналитики"""
        from flask import send_from_directory
        import os
        
        static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'personal', 'static')
        return send_from_directory(static_dir, filename)

    @app.route('/api/analytics/refresh', methods=['POST'])
    def refresh_analytics():
        """Обновить аналитику (вручную вызвать пересчет)"""
        try:
            analytics_data = get_formatted_analytics()
            return jsonify(analytics_data)
        except Exception as e:
            logger.error(f"❌ Ошибка в /api/analytics/refresh: {e}")
            return jsonify({'error': str(e)}), 500
