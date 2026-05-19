"""
Конфигурация приложения FastAPI
"""

import os
import sys
import logging
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

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
RACE_DATA_FILE = BASE_DIR / "tracker" / "race_data.json"  # legacy JSON (race-stats endpoint)

# --- КОНФИГУРАЦИЯ МЕРОПРИЯТИЙ ---
# Единственная точка правды — YAML-файлы в config/events/.
# EVENTS заполняется при старте приложения через load_all_events() в app.py.
from src.config.event_loader import EventConfig  # noqa: E402
EVENTS: dict[str, EventConfig] = {}

# Текущее мероприятие по умолчанию — code из config/events/
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
DEBUG_MODE = os.getenv("DEBUG_MODE", "false").lower() == "true"

# CORS
_cors_raw = os.getenv("CORS_ORIGINS", "*")
CORS_ORIGINS = ["*"] if _cors_raw == "*" else [o.strip() for o in _cors_raw.split(",")]

# --- АВТОРИЗАЦИЯ ---
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production")
TILDA_WEBHOOK_SECRET = os.getenv("TILDA_WEBHOOK_SECRET", "")

# --- DataLens приватный embed ---
DATALENS_KEY_SECRET = os.getenv("DATALENS_KEY_SECRET", "")

def _parse_datalens_embeds() -> list:
    raw = os.getenv("DATALENS_EMBEDS", "")
    if not raw:
        return []
    try:
        import json as _json
        return _json.loads(raw)
    except Exception:
        return []

DATALENS_EMBEDS: list = _parse_datalens_embeds()

# --- БАЗА ДАННЫХ MySQL ---
DB_HOST = os.getenv("DB_HOST", "")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_NAME = os.getenv("DB_NAME", "krasmarafon")
DB_USER = os.getenv("DB_USER", "km_analytic")
DB_PASSWORD = os.getenv("DB_PASSWORD")

# Таблицы БД
DB_RUNNERS_TABLE = os.getenv("DB_RUNNERS_TABLE", "runners")           # Таблица с участниками
DB_RESULTS_TABLE = os.getenv("DB_RESULTS_TABLE", "results")           # Таблица с результатами

__all__ = [
    "BASE_DIR",
    "EVENTS",
    "CURRENT_EVENT",
    "CACHE_DURATION",
    "REQUEST_MIN_INTERVAL",
    "ROUTE_CACHE_DURATION",
    "MAX_SELECTED_RUNNERS",
    "API_TITLE",
    "API_DESCRIPTION",
    "API_VERSION",
    "HOST",
    "PORT",
    "DEBUG",
    "DEBUG_MODE",
    "CORS_ORIGINS",
    "DB_HOST",
    "DB_NAME",
    "DB_USER",
    "DB_PASSWORD",
    "DB_PORT",
    "ADMIN_USERNAME",
    "ADMIN_PASSWORD",
    "SECRET_KEY",
    "TILDA_WEBHOOK_SECRET",
    "DATALENS_KEY_SECRET",
    "DATALENS_EMBEDS",
    "logger",
]
