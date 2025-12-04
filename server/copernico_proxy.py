# server/copernico_proxy.py
from flask import Flask, jsonify, request, make_response
from flask_cors import CORS
import requests
import json
from datetime import datetime, timedelta
import time

app = Flask(__name__)
CORS(app)  # Разрешаем CORS для всех доменов

# Конфигурация
COPERNICO_API_URL = "https://public-api.copernico.cloud/api/races/---2025-89449/preset/podbor250718@gmail.com:::%D0%A8%D1%83%D0%BC%D0%B8%D1%85%D0%B0%20%D0%B3%D1%80%D1%83%D0%BF%D0%BF%D1%8B/10%20km"

# Кеширование данных
cache_data = None
cache_time = None
CACHE_DURATION = 30  # секунд


def fetch_copernico_data():
    """Получение данных из Copernico API"""
    try:
        response = requests.get(COPERNICO_API_URL, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Ошибка при получении данных из Copernico: {e}")
        return []


def calculate_pace(runner_data):
    """Расчет темпа участника (в минутах на километр)"""
    try:
        # Время старта и финиша в миллисекундах
        start_time = runner_data.get('times.official_:::start:::', 0)
        finish_time = runner_data.get('times.official_:::finish:::', None)

        if finish_time and start_time > 0:
            # Время забега в минутах
            race_time_minutes = (finish_time - start_time) / 60000

            # Для дистанции 10 км
            pace = race_time_minutes / 10
            return round(pace, 2)

        # Для участников на трассе используем прогноз
        # Берем средний темп 6 мин/км как базовый
        return 6.0 + (hash(str(runner_data.get('dorsal', 0))) % 10) / 10

    except:
        return 6.5


def predict_finish_time(runner_data):
    """Прогнозирование времени финиша для участников на трассе"""
    try:
        start_time = runner_data.get('times.official_:::start:::', 0)

        if runner_data.get('status') == 'finished':
            # Участник уже финишировал
            finish_time = runner_data.get('times.official_:::finish:::')
            if finish_time:
                return finish_time

        # Для участников на трассе: прогноз на основе темпа
        pace = calculate_pace(runner_data)  # мин/км
        # Среднее время на 10 км в миллисекундах
        predicted_time_ms = pace * 10 * 60000

        # Добавляем случайную вариацию для реалистичности
        variation = (hash(str(runner_data.get('dorsal', 0))) % 20000) - 10000
        return start_time + predicted_time_ms + variation

    except:
        return None


def simulate_position(runner_data, index, total_runners):
    """Симуляция позиции участника на трассе"""
    try:
        # Базовые координаты трассы в Красноярске
        base_lat = 56.03266
        base_lng = 92.95386

        # Симулируем прогресс на основе номера участника
        progress = (index / total_runners) * 0.8  # 80% максимум, чтобы не все были у финиша

        # Добавляем вариацию
        variation_lat = (hash(str(runner_data.get('dorsal', 0))) % 1000) / 100000
        variation_lng = (hash(str(runner_data.get('dorsal', 0) + 1)) % 1000) / 100000

        # Двигаемся по "восьмерке" для демонстрации
        lat = base_lat + (progress * 0.02) + variation_lat
        lng = base_lng + (progress * 0.04) + variation_lng

        return {"lat": lat, "lng": lng}

    except:
        return {"lat": 56.03266, "lng": 92.95386}


@app.route('/api/runners', methods=['GET'])
def get_runners():
    """Основной endpoint для получения данных участников"""
    global cache_data, cache_time

    try:
        # Проверяем кеш
        if cache_data and cache_time:
            elapsed = (datetime.now() - cache_time).total_seconds()
            if elapsed < CACHE_DURATION:
                return jsonify(cache_data)

        # Получаем сырые данные из Copernico
        raw_data = fetch_copernico_data()

        if not raw_data:
            return jsonify([])

        # Трансформируем данные в нужный формат
        runners = []

        for i, item in enumerate(raw_data):
            try:
                runner_id = item.get('dorsal', i + 1)

                # Рассчитываем возраст
                birthdate = item.get('birthdate', '')
                age = 0
                if birthdate and len(birthdate) >= 4:
                    birth_year = int(birthdate[:4])
                    age = datetime.now().year - birth_year

                # Формируем полное имя
                full_name = f"{item.get('surname', '')} {item.get('name', '')}".strip()
                if not full_name:
                    full_name = f"Участник {runner_id}"

                # Определяем статус
                status = item.get('status', 'unknown')
                if status == 'finished':
                    status_text = 'finished'
                else:
                    # Симулируем разные статусы
                    statuses = ['registered', 'started', 'started', 'started']
                    status_text = statuses[hash(str(runner_id)) % len(statuses)]

                # Создаем объект участника
                runner = {
                    'id': runner_id,
                    'dorsal': runner_id,
                    'name': item.get('name', ''),
                    'surname': item.get('surname', ''),
                    'full_name': full_name,
                    'category': item.get('category', 'Не указана'),
                    'age': age,
                    'gender': item.get('gender', 'unknown'),
                    'status': status_text,
                    'pace': calculate_pace(item),
                    'predicted_finish': predict_finish_time(item),
                    'position': simulate_position(item, i, len(raw_data))
                }

                runners.append(runner)

            except Exception as e:
                print(f"Ошибка обработки участника {i}: {e}")
                continue

        # Сохраняем в кеш
        cache_data = runners
        cache_time = datetime.now()

        return jsonify(runners)

    except Exception as e:
        print(f"Ошибка в /api/runners: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/race/info', methods=['GET'])
def get_race_info():
    """Информация о забеге"""
    try:
        info = {
            'name': 'Красмарафон 2024 - 10 км',
            'date': '2024-12-07',
            'location': 'Красноярск',
            'distance': '10 км',
            'total_participants': 172,
            'start_time': '10:00',
            'last_update': datetime.now().isoformat()
        }
        return jsonify(info)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/health', methods=['GET'])
def health_check():
    """Проверка здоровья сервера"""
    return jsonify({
        'status': 'ok',
        'timestamp': datetime.now().isoformat(),
        'service': 'Copernico Proxy'
    })


if __name__ == '__main__':
    print("🚀 Запуск прокси-сервера Copernico на http://localhost:5000")
    print(f"📡 Endpoint: /api/runners")
    print(f"📡 Endpoint: /api/race/info")
    print(f"📡 Endpoint: /api/health")
    app.run(host='0.0.0.0', port=5000, debug=True)