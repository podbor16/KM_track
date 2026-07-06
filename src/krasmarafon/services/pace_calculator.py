"""
Сервис расчета темпа и начальной скорости спортсмена
"""

import re
import logging

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
