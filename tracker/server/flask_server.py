# server/flask_server.py
"""
Главный файл сервера трекера забега
Объединяет все модули: config, models, routes, runners, api
"""
from flask import Flask
from flask_cors import CORS
import logging
import os
import sys

# Добавляем путь к текущему модулю (server/)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import CURRENT_EVENT, MANUAL_SPEED_KMH, USE_MANUAL_SPEED, BASE_DIR
from api import init_routes
from routes_service import fetch_route_from_osm

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Инициализация Flask
app = Flask(__name__, static_folder=os.path.join(BASE_DIR, 'server', 'static'))
CORS(app)

# Регистрируем все API routes
init_routes(app)


if __name__ == '__main__':
    print("Запуск трекера Красмарафон")
    print(f"Режим скорости: {'РУЧНОЙ' if USE_MANUAL_SPEED else 'АВТО'}")
    print(f"Скорость: {MANUAL_SPEED_KMH} км/ч")
    print("=" * 50)
    
    # Предварительная загрузка маршрута при старте
    fetch_route_from_osm()
    
    app.run(host='0.0.0.0', port=5000, debug=True)
