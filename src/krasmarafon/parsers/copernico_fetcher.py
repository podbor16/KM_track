"""
Fetcher для получения актуальных данных гонки из Copernico API в реальном времени
Загружает данные в race_data.json с интервалом
"""

import requests
import json
import time
import logging
from datetime import datetime
import os
from logging.handlers import RotatingFileHandler
from typing import Optional, Dict, Any
from pathlib import Path

from src.config import settings

# Настройка логирования для fetcher'а
log_dir = Path(__file__).parent.parent.parent.parent / "logs"
log_dir.mkdir(exist_ok=True)

log_file_path = log_dir / "race_data_fetcher.log"
file_handler = RotatingFileHandler(
    log_file_path,
    encoding='utf-8',
    maxBytes=10*1024*1024,  # 10 МБ
    backupCount=5
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)
logger.addHandler(logging.StreamHandler())


def fetch_data() -> Optional[Dict[str, Any]]:
    """
    Получение данных с Copernico API с обработкой ошибок
    
    Returns:
        Данные гонки из API или None если ошибка
    """
    headers = {
        'User-Agent': 'KM_Track_Fetcher/1.0 (Mozilla/5.0)',
        'Accept': 'application/json',
        'Accept-Encoding': 'gzip, deflate'
    }
    
    for attempt in range(settings.COPERNICO_MAX_RETRIES):
        try:
            logger.info(f"Попытка {attempt + 1} из {settings.COPERNICO_MAX_RETRIES} получить данные")
            response = requests.get(
                settings.COPERNICO_API_URL,
                headers=headers,
                timeout=15,
                verify=True
            )
            
            logger.info(f"Статус ответа: {response.status_code}")
            
            if response.status_code == 200:
                logger.info("✅ Данные успешно получены")
                return response.json()
            
            elif response.status_code == 401:
                logger.error("❌ Ошибка 401: Требуется аутентификация")
                logger.error("Проверьте URL и параметры доступа")
                return None
            
            elif response.status_code == 429:
                logger.warning("⚠️ Слишком много запросов (rate limit)")
                wait_time = settings.COPERNICO_RETRY_DELAY * (attempt + 1)
                logger.info(f"Ожидание {wait_time} секунд перед следующей попыткой...")
                time.sleep(wait_time)
            
            else:
                logger.error(f"❌ Неожиданный статус: {response.status_code}")
                response.raise_for_status()
        
        except requests.exceptions.Timeout:
            logger.error(f"❌ Timeout при попытке {attempt + 1}")
            if attempt < settings.COPERNICO_MAX_RETRIES - 1:
                time.sleep(settings.COPERNICO_RETRY_DELAY)
        
        except requests.exceptions.ConnectionError as e:
            logger.error(f"❌ Ошибка подключения при попытке {attempt + 1}: {str(e)}")
            if attempt < settings.COPERNICO_MAX_RETRIES - 1:
                time.sleep(settings.COPERNICO_RETRY_DELAY)
        
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Ошибка сети при попытке {attempt + 1}: {str(e)}")
            if attempt < settings.COPERNICO_MAX_RETRIES - 1:
                time.sleep(settings.COPERNICO_RETRY_DELAY)
        
        except json.JSONDecodeError as e:
            logger.error(f"❌ Ошибка парсинга JSON: {str(e)}")
            return None
    
    logger.error("❌ Все попытки получения данных завершились неудачно")
    return None


def save_to_file(data: Dict[str, Any]) -> bool:
    """
    Сохранение данных в JSON файл

    Args:
        data: Данные для сохранения

    Returns:
        True если успешно, False если ошибка
    """
    try:
        # Добавляем метаданные о времени обновления
        output_data = {
            "last_updated": datetime.utcnow().isoformat() + "Z",
            "data": data if isinstance(data, list) else data.get('data', data)
        }
        
        race_data_path = Path(settings.RACE_DATA_FILE)
        race_data_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(race_data_path, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)
        
        num_records = len(output_data.get('data', []))
        logger.info(f"✅ Данные успешно сохранены в {race_data_path}")
        logger.info(f"📊 Количество записей: {num_records}")
        return True
    
    except IOError as e:
        logger.error(f"❌ Ошибка при сохранении файла: {str(e)}")
        return False
    except Exception as e:
        logger.error(f"❌ Неожиданная ошибка при сохранении: {str(e)}")
        return False


def start_fetcher(interval: Optional[int] = None, max_iterations: Optional[int] = None):
    """
    Запустить fetcher для получения данных в реальном времени
    
    Args:
        interval: Интервал между запросами (по умолчанию из settings)
        max_iterations: Максимальное количество итераций (None = бесконечно)
    """
    interval = interval or settings.COPERNICO_FETCH_INTERVAL
    
    logger.info("=" * 60)
    logger.info("🚀 Запуск сбора данных Copernico в реальном времени")
    logger.info("=" * 60)
    logger.info(f"API URL: {settings.COPERNICO_API_URL[:80]}...")
    logger.info(f"Интервал запросов: {interval} секунд")
    logger.info(f"Выходной файл: {settings.RACE_DATA_FILE}")
    if max_iterations:
        logger.info(f"Максимум итераций: {max_iterations}")
    logger.info("Нажмите Ctrl+C для остановки программы")
    logger.info("=" * 60 + "\n")
    
    try:
        iteration = 0
        while True:
            if max_iterations and iteration >= max_iterations:
                logger.info(f"Достигнуто максимальное количество итераций ({max_iterations})")
                break
            
            iteration += 1
            logger.info(f"\n--- Итерация {iteration} ---")
            logger.info(f"Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            
            data = fetch_data()
            if data is not None:
                save_to_file(data)
            else:
                logger.warning("⚠️ Пропуск сохранения из-за отсутствия данных")
            
            logger.info(f"⏳ Ожидание {interval} секунд до следующего запроса...")
            time.sleep(interval)
    
    except KeyboardInterrupt:
        logger.info("\n\n🛑 Программа остановлена пользователем (Ctrl+C)")
    except Exception as e:
        logger.exception(f"❌ Критическая ошибка в fetcher: {str(e)}")
    finally:
        logger.info("👋 Программа завершена\n")


if __name__ == "__main__":
    # Для запуска как отдельного скрипта
    start_fetcher()
