"""
Конфигурация приложения FastAPI
Переносит настройки из tracker/server/config.py
"""

import os
import sys
import logging
from typing import Dict, Any
from pathlib import Path

# UTF-8 вывод в консоль на Windows (иначе кириллица — кракозябры)
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

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
# name       — event_name точно как в БД (используется для matching)
# display_name — название для пользователей (только если отличается от name)
# gpx_file   — путь к GPX-файлу маршрута (заменил osm_way_id)
# Остальные поля, специфичные для маршрута: laps, one_way_length_km, total_race_km
EVENTS_CONFIG: Dict[str, Dict[str, Any]] = {
    'night_run': {
        'name': 'Ночной забег',
        'title': 'Ночной забег | Трекер',
        'description': 'Набережная, Красноярск | Дистанция: 5 км',
        'laps': 1,
        'one_way_length_km': 2.5,
        'total_race_km': 5.0,
    },
    'vesna': {
        'name': 'Весна',
        'title': 'Весна | Трекер',
        'description': 'Событие Весна | Дистанция: 5 км',
    },
    'colorrun': {
        'name': 'Красочный забег',
        'title': 'Красочный забег | Трекер',
        'description': 'Красочный забег | Дистанция: 5 км',
    },
    'girlseven': {
        'name': 'Женская семерка',
        'title': 'Женская семерка | Трекер',
        'description': 'Женская семерка | Дистанция: 7 км',
    },
    'zhara': {
        'name': 'Жара',
        'title': 'Жара | Трекер',
        'description': 'Жара | Дистанции: 5 км, 21.1 км',
    },
    'kids': {
        'name': 'Детский забег',
        'title': 'Детский забег | Трекер',
        'description': 'Детский забег | Дистанция: 1 км',
    },
    'xtrailrun': {
        'name': 'Х Трейл',
        'display_name': 'Забег Икс',  # показывается пользователям
        'title': 'Забег Икс | Трекер',
        'description': 'Забег Икс | Дистанция: 10 км',
    },
    'snow7': {
        'name': 'Снежная семерка',
        'title': 'Снежная семерка | Трекер',
        'description': 'МСК "Радуга", Красноярск | Дистанция: 7 км (челночная)',
        'laps': 4,
        'one_way_length_km': 1.75,
        'total_race_km': 7.0,
    },
    'rosneft': {
        'name': 'Роснефть',
        'title': 'Роснефть | Трекер',
        'description': 'МСК "Радуга", Красноярск | Дистанции: 3 км, 5 км, 10 км',
        'distances': {
            '3km': {'laps': 2, 'lap_length': 1.5},
            '5km': {'laps': 1, 'lap_length': 4.94},
            '10km': {'laps': 2, 'lap_length': 4.94},
        },
    },
}


def get_display_name(code: str) -> str:
    """Возвращает пользовательское название события по его коду.
    Для большинства совпадает с name; для 'xtrailrun' → 'Забег Икс'.
    """
    cfg = EVENTS_CONFIG.get(code, {})
    return cfg.get('display_name') or cfg.get('name') or code


# Текущее мероприятие — ключ из EVENTS_CONFIG, используется как fallback в /tracker
CURRENT_EVENT = 'night_run'

# Конфигурация кеширования
CACHE_DURATION = 2  # Обновлять позиции каждые 2 секунды (интерполяция)
REQUEST_MIN_INTERVAL = 2
ROUTE_CACHE_DURATION = 3600

# Выбранные участники
MAX_SELECTED_RUNNERS = 5

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
