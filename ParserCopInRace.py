import requests
import json
import time
import logging
from datetime import datetime
import os

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("race_data_fetcher.log"),
        logging.StreamHandler()
    ]
)

# Конфигурация (требует проверки!)
URL = "https://public-api.copernico.cloud/api/races/--2025-70363/preset/podbor250718@gmail.com:::%D0%A1%D0%BD%D0%B5%D0%B6%D0%BD%D0%B0%D1%8F%207%20%D1%82%D1%80%D0%B5%D0%BA%D0%B5%D1%80/7%20km"
# [Внимание] Этот URL содержит пробелы и специальные символы. Возможно, требуется URL-кодирование.

OUTPUT_FILE = "race_data.json"
REQUEST_INTERVAL = 10  # секунд
MAX_RETRIES = 3
RETRY_DELAY = 2  # секунд между попытками

def fetch_data():
    """Получение данных с API с обработкой ошибок"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'application/json'
    }
    
    for attempt in range(MAX_RETRIES):
        try:
            logging.info(f"Попытка {attempt + 1} из {MAX_RETRIES} получить данные")
            response = requests.get(URL, headers=headers, timeout=15)
            
            # Логируем статус ответа
            logging.info(f"Статус ответа: {response.status_code}")
            
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 401:
                logging.error("Ошибка 401: Требуется аутентификация. Проверьте URL и параметры доступа.")
                return None
            elif response.status_code == 429:
                logging.warning("Слишком много запросов. Увеличиваем задержку.")
                time.sleep(RETRY_DELAY * (attempt + 1))
            else:
                logging.error(f"Неожиданный статус: {response.status_code}")
                response.raise_for_status()
                
        except requests.exceptions.RequestException as e:
            logging.error(f"Ошибка сети при попытке {attempt + 1}: {str(e)}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)
    
    logging.error("Все попытки получения данных завершились неудачно")
    return None

def save_to_file(data):
    """Сохранение данных в JSON файл"""
    try:
        # Добавляем метаданные о времени обновления
        output_data = {
            "last_updated": datetime.utcnow().isoformat() + "Z",
            "data": data
        }
        
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)
        
        logging.info(f"Данные успешно сохранены в {OUTPUT_FILE}")
        logging.info(f"Количество записей: {len(data) if data else 0}")
        return True
    except Exception as e:
        logging.error(f"Ошибка при сохранении файла: {str(e)}")
        return False

def main():
    """Основной цикл работы программы"""
    logging.info("Запуск сбора данных в реальном времени")
    logging.info(f"URL для запросов: {URL}")
    logging.info(f"Интервал запросов: {REQUEST_INTERVAL} секунд")
    logging.info(f"Выходной файл: {OUTPUT_FILE}")
    logging.info("Нажмите Ctrl+C для остановки программы\n")
    
    try:
        iteration = 0
        while True:
            iteration += 1
            logging.info(f"\n--- Итерация {iteration} ---")
            
            data = fetch_data()
            if data is not None:
                save_to_file(data)
            else:
                logging.warning("Пропуск сохранения из-за отсутствия данных")
            
            logging.info(f"Ожидание {REQUEST_INTERVAL} секунд до следующего запроса...")
            time.sleep(REQUEST_INTERVAL)
            
    except KeyboardInterrupt:
        logging.info("\nПрограмма остановлена пользователем")
    except Exception as e:
        logging.exception(f"Критическая ошибка: {str(e)}")
    finally:
        logging.info("Программа завершена")

if __name__ == "__main__":
    main()