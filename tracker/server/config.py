# server/config.py
import os
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Пути
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RACE_DATA_FILE = os.path.join(BASE_DIR, "race_data.json")

# --- ГЛОБАЛЬНЫЕ НАСТРОЙКИ СИМУЛЯЦИИ ---
MANUAL_SPEED_KMH = 15.0       # Скорость в км/ч (поставьте 50.0 для быстрого теста)
USE_MANUAL_SPEED = False       # True = все бегут с заданной скоростью. False = случайная скорость.

# Настройки геометрии трассы
ONE_WAY_LENGTH_KM = 1.75      # Длина отрисованной линии (в одну сторону)
TOTAL_RACE_KM = 7.0           # Полная дистанция забега (4 плеча по 1.75)

# --- КОНФИГУРАЦИЯ МЕРОПРИЯТИЙ ---
EVENTS_CONFIG = {
    'snow7': {
        'osm_way_id': 181589417,
        'one_way_length_km': 1.75,
        'total_race_km': 7.0,
        'laps': 4,  # 4 отрезка (туда-обратно-туда-обратно)
        'name': 'Снежная семерка',
        'title': '🏃 Трекер забега Снежная Семёрка',
        'description': 'МСК "Радуга", Красноярск | Дистанция: 7 км (челночная)'
    },
    'rosneft': {
        'osm_way_id': 553966988,
        'one_way_length_km': 5,  # Длина одного круга
        'distances': {
            '3km': {'laps': 2, 'lap_length': 1.5},  # 2 круга по 1.5 км
            '5km': {'laps': 1, 'lap_length': 4.94},  # 1 круг 5 км
            '10km': {'laps': 2, 'lap_length': 4.94}  # 2 круга по 5 км
        },
        'name': 'Роснефть',
        'title': '🏃 Трекер забега Роснефть',
        'description': 'МСК "Радуга", Красноярск | Дистанции: 3 км, 5 км, 10 км'
    }
}

# Текущее мероприятие (можно менять через API)
CURRENT_EVENT = 'rosneft'

# Конфигурация кеширования
CACHE_DURATION = 2  # Обновлять позиции каждые 2 секунды (интерполяция)
REQUEST_MIN_INTERVAL = 2
ROUTE_CACHE_DURATION = 3600

# Выбранные участники
MAX_SELECTED_RUNNERS = 5
