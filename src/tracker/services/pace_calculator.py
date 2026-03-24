"""
Сервис расчета темпа и начальной скорости спортсмена
Используется для инициализации маркера и корректировки при прохождении сегментов
"""

import re
import logging
from typing import Optional, Dict, Any
from src.analytics.db_connection_optimized import (
    get_race_results_by_event_id_and_year,
)

logger = logging.getLogger(__name__)


def parse_distance(distance_str: str) -> float:
    """
    Парсит строку дистанции в число (км).
    
    Примеры:
        "5 км" → 5.0
        "10 км" → 10.0
        "5" → 5.0
    
    Args:
        distance_str: строка с дистанцией (например, "5 км")
    
    Returns:
        Дистанция в км (float)
    """
    if not distance_str:
        return 0.0
    
    # Извлекаем все цифры и десятичные точки
    match = re.search(r'(\d+[\.,]?\d*)', str(distance_str))
    if match:
        distance_num = match.group(1).replace(',', '.')
        try:
            return float(distance_num)
        except ValueError:
            return 0.0
    
    return 0.0


def parse_pace_to_kmh(pace_str: str) -> float:
    """
    Преобразует строку темпа в скорость км/ч.
    
    Примеры:
        "7:22" → 8.13 км/ч (7 мин 22 сек на км = 60 / 7.367 ≈ 8.13 км/ч)
        "6:00" → 10.0 км/ч
        "5:30" → 10.91 км/ч
    
    Args:
        pace_str: строка темпа в формате "м:сс" или "мм:сс"
    
    Returns:
        Скорость в км/ч (float)
    
    Raises:
        ValueError: если формат неправильный
    """
    if not pace_str or pace_str.lower() == 'null' or pace_str.strip() == '':
        return 10.0  # скорость по умолчанию
    
    # Парсим формат "7:22" или "7'22"
    match = re.search(r'(\d+)[:\'](\d+)', str(pace_str))
    if match:
        minutes = int(match.group(1))
        seconds = int(match.group(2))
        
        total_seconds_per_km = minutes * 60 + seconds
        if total_seconds_per_km == 0:
            return 10.0
        
        # Скорость (км/ч) = 3600 сек/час / секунды на км
        speed_kmh = 3600.0 / total_seconds_per_km
        return round(speed_kmh, 2)
    
    # Если не парсится, возвращаем скорость по умолчанию
    logger.warning(f"Не удалось распарсить темп: {pace_str}")
    return 10.0


def kmh_to_pace(speed_kmh: float) -> str:
    """
    Преобразует скорость км/ч в строку темпа.
    
    Примеры:
        8.13 км/ч → "7:22"
        10.0 км/ч → "6:00"
        10.91 км/ч → "5:30"
    
    Args:
        speed_kmh: скорость в км/ч
    
    Returns:
        Строка темпа в формате "м:сс"
    """
    if speed_kmh <= 0:
        return "0:00"
    
    # Секунды на км = 3600 / скорость
    seconds_per_km = 3600.0 / speed_kmh
    
    minutes = int(seconds_per_km // 60)
    seconds = int(seconds_per_km % 60)
    
    return f"{minutes}:{seconds:02d}"


def get_initial_pace(
    client_id: int,
    category: str,
    event_name: str,
    current_year: int
) -> str:
    """
    Определяет начальный темп спортсмена для трекера.
    
    Логика:
    1. Если спортсмен бежал в прошлом году (year-1):
       → используется его средний темп по всем завершенным забегам
    2. Если спортсмен бежит впервые (нет истории):
       → используется средний темп его категории на этом забеге в прошлом году
    
    Args:
        client_id: ID спортсмена
        category: возрастная категория (например, "мужчины до 49 лет")
        event_name: название события (например, "Краевой Марафон")
        current_year: текущий год события
    
    Returns:
        Темп в формате "м:сс" (например, "7:22")
    """
    try:
        past_year = current_year - 1
        
        # Попытка 1: найти результаты спортсмена в прошлом году
        past_results = get_race_results_by_event_id_and_year(event_name, past_year)
        
        if past_results:
            # Ищем результаты этого спортсмена
            runner_paces = [
                result.get('finish_pace_avg')
                for result in past_results
                if result.get('client_id') == client_id and result.get('race_status') == 'finished'
            ]
            
            if runner_paces:
                # Вычисляем средний темп (в км/ч)
                paces_kmh = [parse_pace_to_kmh(pace) for pace in runner_paces if pace]
                if paces_kmh:
                    avg_kmh = sum(paces_kmh) / len(paces_kmh)
                    pace_str = kmh_to_pace(avg_kmh)
                    logger.info(f"Client {client_id}: темп из истории за {past_year} год = {pace_str}")
                    return pace_str
        
        # Попытка 2: использовать средний темп категории в прошлом году
        if past_results:
            category_paces = [
                result.get('finish_pace_avg')
                for result in past_results
                if result.get('category') == category and result.get('race_status') == 'finished'
            ]
            
            if category_paces:
                # Вычисляем средний темп по категории
                paces_kmh = [parse_pace_to_kmh(pace) for pace in category_paces if pace]
                if paces_kmh:
                    avg_kmh = sum(paces_kmh) / len(paces_kmh)
                    pace_str = kmh_to_pace(avg_kmh)
                    logger.info(f"Client {client_id}: темп из категории {category} за {past_year} год = {pace_str}")
                    return pace_str
        
        # Вариант по умолчанию: средний темп (10 км/ч)
        logger.warning(f"Client {client_id}: нет данных, используется темп по умолчанию")
        return "6:00"
    
    except Exception as e:
        logger.error(f"Ошибка при расчете начального темпа для client_id {client_id}: {e}")
        return "6:00"


def get_runner_average_pace(client_id: int, event_name: str, year: int) -> Optional[str]:
    """
    Получить средний темп спортсмена за конкретный год и событие.
    
    Args:
        client_id: ID спортсмена
        event_name: название события
        year: год события
    
    Returns:
        Средний темп в формате "м:сс" или None если нет данных
    """
    try:
        results = get_race_results_by_event_id_and_year(event_name, year)
        
        runner_results = [
            r for r in results
            if r.get('client_id') == client_id and r.get('race_status') == 'finished'
        ]
        
        if not runner_results:
            return None
        
        paces_kmh = [parse_pace_to_kmh(r.get('finish_pace_avg')) for r in runner_results if r.get('finish_pace_avg')]
        
        if paces_kmh:
            avg_kmh = sum(paces_kmh) / len(paces_kmh)
            return kmh_to_pace(avg_kmh)
        
        return None
    
    except Exception as e:
        logger.error(f"Ошибка при получении среднего темпа для client_id {client_id}: {e}")
        return None


def get_category_average_pace(category: str, event_name: str, year: int) -> Optional[str]:
    """
    Получить средний темп категории за конкретный год и событие.
    
    Args:
        category: возрастная категория
        event_name: название события
        year: год события
    
    Returns:
        Средний темп в формате "м:сс" или None если нет данных
    """
    try:
        results = get_race_results_by_event_id_and_year(event_name, year)
        
        category_results = [
            r for r in results
            if r.get('category') == category and r.get('race_status') == 'finished'
        ]
        
        if not category_results:
            return None
        
        paces_kmh = [parse_pace_to_kmh(r.get('finish_pace_avg')) for r in category_results if r.get('finish_pace_avg')]
        
        if paces_kmh:
            avg_kmh = sum(paces_kmh) / len(paces_kmh)
            return kmh_to_pace(avg_kmh)
        
        return None
    
    except Exception as e:
        logger.error(f"Ошибка при получении среднего темпа категории {category}: {e}")
        return None
