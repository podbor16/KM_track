# server/flask_server_final.py
from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
import requests
import json
from datetime import datetime, timedelta
import os
import time

# Получаем абсолютный путь к корневой папке проекта
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

app = Flask(__name__,
            static_folder=BASE_DIR,
            static_url_path='')
CORS(app)

# Конфигурация
COPERNICO_API_URL = "https://public-api.copernico.cloud/api/races/---2025-89449/preset/podbor250718@gmail.com:::%D0%A8%D1%83%D0%BC%D0%B8%D1%85%D0%B0%20%D0%B3%D1%80%D1%83%D0%BF%D0%BF%D1%8B/10%20km"

# Кеширование
cache_data = None
cache_time = None
CACHE_DURATION = 10

# Маршрут забега
RACE_TRACK = [
    [56.028855, 92.946101],
    [56.02996, 92.949893],
    [56.031108, 92.951328],
    [56.03227, 92.953744],
    [56.032565, 92.95492],
    [56.035519, 92.962478],
    [56.036558, 92.966651],
    [56.038971, 92.969956],
    [56.036558, 92.966651],
    [56.035519, 92.962478],
    [56.032565, 92.95492],
    [56.03227, 92.953744],
    [56.031108, 92.951328],
    [56.02996, 92.949893],
    [56.028855, 92.946101]
]


def fetch_copernico_data():
    """Получение данных из Copernico API"""
    try:
        print(f"🌐 Запрос к Copernico...")
        response = requests.get(COPERNICO_API_URL, timeout=15)
        response.raise_for_status()

        # Проверяем, что это действительно JSON
        content_type = response.headers.get('content-type', '')
        if 'application/json' not in content_type:
            print(f"⚠️ Ответ не JSON: {content_type}")
            print(f"📄 Ответ (первые 500 символов): {response.text[:500]}")
            return []

        data = response.json()
        print(f"✅ Получен JSON, тип данных: {type(data)}")

        # Выводим отладочную информацию о структуре
        if isinstance(data, list):
            print(f"📊 Это список из {len(data)} элементов")
            if data:
                print(f"📋 Первый элемент: {type(data[0])}")
                print(
                    f"🔍 Ключи первого элемента (если dict): {list(data[0].keys()) if isinstance(data[0], dict) else 'не словарь'}")
        elif isinstance(data, dict):
            print(f"📊 Это словарь с ключами: {list(data.keys())}")
        else:
            print(f"⚠️ Неожиданный тип данных: {type(data)}")

        return data

    except Exception as e:
        print(f"❌ Ошибка при получении данных из Copernico: {e}")
        return []


def transform_copernico_data(raw_data):
    """Трансформация данных из Copernico в наш формат"""
    runners = []

    # Если raw_data - это список
    if isinstance(raw_data, list):
        print(f"🔄 Обработка списка из {len(raw_data)} элементов")

        for i, item in enumerate(raw_data):
            try:
                # Проверяем тип элемента
                if isinstance(item, str):
                    # Если это строка, пытаемся распарсить как JSON
                    try:
                        item = json.loads(item)
                        print(f"📝 Элемент {i} был строкой, распарсен в {type(item)}")
                    except:
                        print(f"⚠️ Элемент {i} - строка, но не JSON: {item[:100]}...")
                        continue

                # Теперь item должен быть словарем
                if not isinstance(item, dict):
                    print(f"⚠️ Элемент {i} не словарь: {type(item)}")
                    continue

                # Извлекаем данные
                runner_id = item.get('dorsal')
                if runner_id is None:
                    runner_id = i + 1

                # Проверяем, что runner_id - число
                if isinstance(runner_id, str) and runner_id.isdigit():
                    runner_id = int(runner_id)
                elif not isinstance(runner_id, (int, float)):
                    runner_id = i + 1

                # Имя и фамилия
                surname = item.get('surname', '')
                name = item.get('name', '')
                full_name = f"{surname} {name}".strip()
                if not full_name:
                    full_name = f"Участник {runner_id}"

                # Категория
                category = item.get('category', 'Не указана')

                # Статус
                status = item.get('status', 'unknown')
                if status == 'finished':
                    status_text = 'finished'
                else:
                    status_text = 'started'

                # Возраст
                age = 0
                birthdate = item.get('birthdate', '')
                if birthdate and len(birthdate) >= 4:
                    try:
                        birth_year = int(birthdate[:4])
                        current_year = datetime.now().year
                        age = current_year - birth_year
                    except:
                        age = 0

                # Пол
                gender = item.get('gender', 'unknown')

                # Позиция на трассе (распределяем равномерно)
                total_runners = len(raw_data)
                progress = (i / max(total_runners, 1)) * 0.8  # 80% максимальный прогресс

                # Добавляем вариацию на основе номера
                variation = (runner_id % 100) / 1000
                progress = max(0.1, min(0.9, progress + variation))

                # Находим точку на трассе
                track_index = int(progress * (len(RACE_TRACK) - 1))
                track_index = min(track_index, len(RACE_TRACK) - 1)

                lat, lng = RACE_TRACK[track_index]

                # Небольшое смещение для каждого участника
                lat_offset = (runner_id % 10) / 10000
                lng_offset = ((runner_id + 1) % 10) / 10000

                # Темп (рассчитываем на основе времени если есть)
                pace = 6.0  # средний темп по умолчанию
                if 'times.official_:::start:::' in item and 'times.official_:::finish:::' in item:
                    start_time = item.get('times.official_:::start:::', 0)
                    finish_time = item.get('times.official_:::finish:::', 0)
                    if finish_time > start_time > 0:
                        race_time_minutes = (finish_time - start_time) / 60000
                        pace = race_time_minutes / 10  # для 10 км
                        pace = round(pace, 2)

                runner = {
                    'id': int(runner_id),
                    'dorsal': int(runner_id),
                    'name': name,
                    'surname': surname,
                    'full_name': full_name,
                    'category': category,
                    'age': age,
                    'gender': gender,
                    'status': status_text,
                    'pace': pace,
                    'predicted_finish': None,
                    'position': {
                        'lat': lat + lat_offset - 0.00005,
                        'lng': lng + lng_offset - 0.00005
                    }
                }

                runners.append(runner)

            except Exception as e:
                print(f"⚠️ Ошибка обработки элемента {i}: {type(e).__name__}: {e}")
                print(f"   Элемент: {item}")
                continue

    # Если raw_data - это словарь (возможно другой формат)
    elif isinstance(raw_data, dict):
        print(f"🔄 Обработка словаря с ключами: {list(raw_data.keys())}")

        # Проверяем, есть ли ключ, содержащий список участников
        possible_keys = ['participants', 'runners', 'data', 'results', 'items']
        for key in possible_keys:
            if key in raw_data and isinstance(raw_data[key], list):
                print(f"📁 Найден ключ с участниками: {key}")
                # Рекурсивно обрабатываем этот список
                sub_runners = transform_copernico_data(raw_data[key])
                runners.extend(sub_runners)
                break

        if not runners:
            print("⚠️ Не удалось найти список участников в словаре")

    else:
        print(f"⚠️ Неизвестный формат данных: {type(raw_data)}")
        print(f"📄 Данные: {str(raw_data)[:500]}...")

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
        # Для отладки: можно временно использовать тестовые данные
        USE_TEST_DATA = False

        if USE_TEST_DATA:
            # Тестовые данные для проверки
            runners = []
            for i in range(1, 51):
                runner = {
                    'id': i,
                    'dorsal': i,
                    'name': f'Имя{i}',
                    'surname': f'Фамилия{i}',
                    'full_name': f'Фамилия{i} Имя{i}',
                    'category': 'Мужчины 20-30' if i % 2 == 0 else 'Женщины 20-30',
                    'age': 20 + (i % 20),
                    'gender': 'male' if i % 2 == 0 else 'female',
                    'status': 'started' if i < 40 else 'finished',
                    'pace': 5.0 + (i % 30) / 10,
                    'predicted_finish': None,
                    'position': {
                        'lat': 56.03266 + (i * 0.0005),
                        'lng': 92.95386 + (i * 0.0005)
                    }
                }
                runners.append(runner)

            print(f"🧪 Используем тестовые данные: {len(runners)} участников")
            return jsonify(runners)

        # Проверяем кеш
        if cache_data and cache_time:
            elapsed = (datetime.now() - cache_time).total_seconds()
            if elapsed < CACHE_DURATION:
                print(f"📦 Используем кешированные данные ({elapsed:.1f} сек)")
                return jsonify(cache_data)

        # Получаем данные из Copernico
        print("🌐 Получение данных из Copernico API...")
        raw_data = fetch_copernico_data()

        if not raw_data:
            print("⚠️ Нет данных от Copernico")

            # Если нет данных, но есть кеш - вернем его даже если просрочен
            if cache_data:
                print("📦 Возвращаем устаревшие кешированные данные")
                return jsonify(cache_data)

            return jsonify([])

        print(f"✅ Получены данные из Copernico, тип: {type(raw_data)}")

        # Трансформируем данные
        runners = transform_copernico_data(raw_data)

        # Если не удалось получить участников, используем тестовые данные
        if not runners:
            print("⚠️ Не удалось преобразовать данные, используем тестовые")
            runners = []
            for i in range(1, 51):
                runners.append({
                    'id': i,
                    'dorsal': i,
                    'name': f'Участник',
                    'surname': f'№{i}',
                    'full_name': f'Участник №{i}',
                    'category': 'Тестовая категория',
                    'age': 25,
                    'gender': 'male',
                    'status': 'started',
                    'pace': 6.0,
                    'predicted_finish': None,
                    'position': {
                        'lat': 56.03266 + (i * 0.001),
                        'lng': 92.95386 + (i * 0.001)
                    }
                })

        # Сохраняем в кеш
        cache_data = runners
        cache_time = datetime.now()

        print(f"✅ Отправляем {len(runners)} участников")
        return jsonify(runners)

    except Exception as e:
        print(f"❌ Ошибка в /api/runners: {type(e).__name__}: {e}")

        # В случае ошибки вернем пустой список или кеш
        if cache_data:
            print("📦 Возвращаем кешированные данные из-за ошибки")
            return jsonify(cache_data)

        return jsonify({"error": str(e), "message": "Ошибка сервера"}), 500


# В файле server/flask_server.py исправьте функцию calculate_pace_from_times:

def calculate_pace_from_times(runner_data):
    """Расчет темпа на основе времени старта и финиша"""
    try:
        start_time = runner_data.get('times.official_:::start:::')
        finish_time = runner_data.get('times.official_:::finish:::')

        # Проверяем, что оба времени не None и являются числами
        if start_time is not None and finish_time is not None:
            # Преобразуем в числа, если они строки
            try:
                start_time = float(start_time) if isinstance(start_time, str) else start_time
                finish_time = float(finish_time) if isinstance(finish_time, str) else finish_time

                # Проверяем, что это действительно числа
                if isinstance(start_time, (int, float)) and isinstance(finish_time, (int, float)):
                    if finish_time > start_time > 0:
                        race_time_minutes = (finish_time - start_time) / 60000
                        pace = race_time_minutes / 10  # для 10 км
                        return round(pace, 2)
            except (ValueError, TypeError) as e:
                print(f"⚠️ Ошибка преобразования времени для участника: {e}")

        # Если нет времени финиша или другие проблемы, возвращаем средний темп
        # Используем номер участника для псевдослучайного темпа
        dorsal = runner_data.get('dorsal', 0)
        if not isinstance(dorsal, (int, float)):
            dorsal = 0

        # Средний темп 6.0 ± 1.5 мин/км
        return 6.0 + (dorsal % 30) / 10

    except Exception as e:
        print(f"⚠️ Ошибка расчета темпа: {e}")
        return 6.0


@app.route('/api/test', methods=['GET'])
def test_endpoint():
    """Тестовый endpoint для проверки"""
    return jsonify({
        "status": "ok",
        "message": "Сервер работает",
        "timestamp": datetime.now().isoformat()
    })


if __name__ == '__main__':
    print("🚀 Запуск финальной версии сервера Красмарафон")
    print("=" * 60)
    print(f"🌐 Главная страница: http://localhost:5000/")
    print(f"📡 API участников: http://localhost:5000/api/runners")
    print(f"🧪 Тестовый endpoint: http://localhost:5000/api/test")
    print("=" * 60)

    app.run(host='0.0.0.0', port=5000, debug=True)