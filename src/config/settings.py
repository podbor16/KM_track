"""
Конфигурация приложения FastAPI
Переносит настройки из tracker/server/config.py
"""

import os
import logging
from typing import Dict, Any
from pathlib import Path

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Базовые пути
BASE_DIR = Path(__file__).resolve().parent.parent.parent
# TODO: Переместить JSON файлы в src/tracker/data/ когда структура стабилизируется
RACE_DATA_FILE = BASE_DIR / "tracker" / "race_data.json"
ROSNEFT_ROUTE_FILE = BASE_DIR / "tracker" / "rosneft_route.json"

# --- ГЛОБАЛЬНЫЕ НАСТРОЙКИ СИМУЛЯЦИИ ---
MANUAL_SPEED_KMH = 15.0       # Скорость в км/ч (поставьте 50.0 для быстрого теста)
USE_MANUAL_SPEED = False       # True = все бегут с заданной скоростью. False = случайная скорость.

# Настройки геометрии трассы
ONE_WAY_LENGTH_KM = 2.5      # Длина отрисованной линии (в одну сторону)
TOTAL_RACE_KM = 5.0           # Полная дистанция забега (2 плеча по 2.5)

# --- КОНФИГУРАЦИЯ МЕРОПРИЯТИЙ ---
EVENTS_CONFIG: Dict[str, Dict[str, Any]] = {
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
    },
    'night_run': {
        'osm_way_id': 1477580211,
        'laps': 1,  # 4 отрезка (туда-обратно-туда-обратно)
        'one_way_length_km': 2.5,  # Половина маршрута в одну сторону (2.5 км)
        'total_race_km': 5.0,       # Полная дистанция (туда 2.5 км + обратно 2.5 км)
        'distances': {
            '5km': {'one_way_length': 2.5, 'total_race': 5.0},    # 2.5 км туда, 2.5 км обратно
        },
        'name': 'Ночной забег',
        'title': 'Ночной забег. \n Трекер',
        'description': 'Набережная, Красноярск | Дистанции: 5 км'
    }
}

# Текущее мероприятие (можно менять через API)
CURRENT_EVENT = 'night_run'  

# Конфигурация кеширования
CACHE_DURATION = 2  # Обновлять позиции каждые 2 секунды (интерполяция)
REQUEST_MIN_INTERVAL = 2
ROUTE_CACHE_DURATION = 3600

# Выбранные участники
MAX_SELECTED_RUNNERS = 5

# --- COPERNICO API КОНФИГУРАЦИЯ ---
# URL для получения данных гонки в реальном времени
COPERNICO_API_URL = os.getenv(
    "COPERNICO_API_URL",
    "https://public-api.copernico.cloud/api/races/--2025-96994/preset/podbor250718@gmail.com:::%D0%A1%D0%BD%D0%B5%D0%B6%D0%BD%D0%B0%D1%8F%207%20%D1%82%D1%80%D0%B5%D0%BA%D0%B5%D1%80/%D0%9C%D1%83%D0%B6%D1%81%D0%BA%D0%B0%D1%8F%20%D0%B3%D0%BE%D0%BD%D0%BA%D0%B0%2010%20%D0%BA%D0%BC"
)
COPERNICO_FETCH_INTERVAL = 10  # секунд между запросами
COPERNICO_MAX_RETRIES = 3
COPERNICO_RETRY_DELAY = 2  # секунд между попытками

# --- FastAPI КОНФИГУРАЦИЯ ---
API_TITLE = "KM Track API"
API_DESCRIPTION = "Трекер маршрутов и аналитика спортивных мероприятий"
API_VERSION = "1.0.0"

# Сервер
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))
DEBUG = os.getenv("DEBUG", "True").lower() == "true"

# CORS
CORS_ORIGINS = ["*"]  # В продакшене укажите конкретные домены

# --- БАЗА ДАННЫХ MySQL ---
# Параметры подключения к базе данных Krasmarafon
DB_HOST = os.getenv("DB_HOST", "79.174.89.159")
DB_PORT = int(os.getenv("DB_PORT", "16171"))
DB_NAME = os.getenv("DB_NAME", "krasmarafon")
DB_USER = os.getenv("DB_USER", "km_analytic")
DB_PASSWORD = os.getenv("DB_PASSWORD", "CneZbvlOS2H-BLsQ")

# Таблицы БД
DB_RUNNERS_TABLE = os.getenv("DB_RUNNERS_TABLE", "runners")           # Таблица с участниками
DB_RESULTS_TABLE = os.getenv("DB_RESULTS_TABLE", "results")           # Таблица с результатами

__all__ = [
    "BASE_DIR",
    "RACE_DATA_FILE",
    "MANUAL_SPEED_KMH",
    "USE_MANUAL_SPEED",
    "ONE_WAY_LENGTH_KM",
    "TOTAL_RACE_KM",
    "EVENTS_CONFIG",
    "CURRENT_EVENT",
    "CACHE_DURATION",
    "REQUEST_MIN_INTERVAL",
    "ROUTE_CACHE_DURATION",
    "MAX_SELECTED_RUNNERS",
    "COPERNICO_API_URL",
    "COPERNICO_FETCH_INTERVAL",
    "COPERNICO_MAX_RETRIES",
    "COPERNICO_RETRY_DELAY",
    "API_TITLE",
    "API_DESCRIPTION",
    "API_VERSION",
    "HOST",
    "PORT",
    "DEBUG",
    "CORS_ORIGINS",
    "DB_HOST",
    "DB_NAME",
    "DB_USER",
    "DB_PASSWORD",
    "DB_PORT",
    "logger",
]
