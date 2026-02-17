#!/usr/bin/env python
"""
Скрипт для запуска Copernico data fetcher

Использование:
    python fetch_race_data.py              # Запуск с интервалом по умолчанию (10 сек)
    python fetch_race_data.py --interval 5 # Запуск с интервалом 5 сек
    python fetch_race_data.py --max 100    # Запуск на 100 итераций
"""

import sys
import argparse
from pathlib import Path

# Добавляем src директорию в путь Python
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.tracker.parsers import start_fetcher


def main():
    parser = argparse.ArgumentParser(
        description='Fetcher для получения данных гонки из Copernico API',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры:
  python fetch_race_data.py                 # Запуск с дефолтными параметрами
  python fetch_race_data.py --interval 5    # Интервал 5 сек между запросами
  python fetch_race_data.py --max 100       # Получить 100 итераций и выйти
  python fetch_race_data.py --interval 10 --max 50  # Комбинировать параметры
        """
    )
    
    parser.add_argument(
        '--interval',
        type=int,
        default=None,
        help='Интервал между запросами в секундах (default: 10)'
    )
    
    parser.add_argument(
        '--max',
        type=int,
        dest='max_iterations',
        default=None,
        help='Максимальное количество итераций (default: бесконечно)'
    )
    
    args = parser.parse_args()
    
    start_fetcher(
        interval=args.interval,
        max_iterations=args.max_iterations
    )


if __name__ == "__main__":
    main()
