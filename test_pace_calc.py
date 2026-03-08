#!/usr/bin/env python
"""Тестируем функции JavaScript локально в Python"""

# Имитируем функции calculatePace из JavaScript

def calculatePace(timeData, distanceStr):
    if not timeData or not distanceStr:
        return '-'
    
    # Парсим дистанцию (например, "5 км" -> 5)
    distanceNum = float(distanceStr.split()[0]) if ' ' in distanceStr else float(distanceStr)
    if distanceNum <= 0:
        return '-'
    
    # Парсим время
    totalSeconds = 0
    
    # Если это строка формата "0:16:01"
    if isinstance(timeData, str) and ':' in timeData:
        parts = timeData.split(':')
        if len(parts) == 3:
            totalSeconds = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        elif len(parts) == 2:
            totalSeconds = int(parts[0]) * 60 + int(parts[1])
    
    # Если это число (миллисекунды или секунды)
    elif isinstance(timeData, (int, float)):
        # Если больше 60000, это миллисекунды
        totalSeconds = timeData / 1000 if timeData > 60000 else timeData
    
    # Если это ISO 8601 формат PT2490S или PT961S
    elif isinstance(timeData, str) and timeData.startswith('PT'):
        import re
        match = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?', timeData)
        if match:
            h = int(match.group(1) or 0)
            m = int(match.group(2) or 0)
            s = float(match.group(3) or 0)
            totalSeconds = h * 3600 + m * 60 + int(s)
    
    if totalSeconds <= 0:
        return '-'
    
    totalMinutes = totalSeconds / 60
    pace = totalMinutes / distanceNum
    return f"{pace:.2f}"

# Тестируем
print("ТЕСТ ФУНКЦИИ calculatePace")
print("=" * 70)

test_cases = [
    ("PT961S", "5 км", "961 сек / 5 км = 16 мин 1 сек / 5 км"),
    ("0:16:01", "5 км", "16 мин 1 сек / 5 км"),
    ("PT2490S", "5 км", "2490 сек = 41.5 мин / 5 км"),
]

for time_val, dist_val, desc in test_cases:
    result = calculatePace(time_val, dist_val)
    print(f"\nВремя: {time_val}, Дистанция: {dist_val}")
    print(f"Описание: {desc}")
    print(f"Результат: {result} мин/км")
    
    # Вручную проверяем
    if time_val.startswith('PT'):
        import re
        match = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?', time_val)
        if match:
            s = float(match.group(3) or 0)
            print(f"Проверка: {s} сек / 60 сек/мин / 5 км = {s/60/5:.2f} мин/км")
