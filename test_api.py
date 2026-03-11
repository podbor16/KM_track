#!/usr/bin/env python
# -*- coding: utf-8 -*-

from src.analytics.db_connection_optimized import get_race_stats_from_db
import json
import sys

print('=== Тест функции get_race_stats_from_db ===')
print('Вызываю функцию для "Ночной забег"...')

results = get_race_stats_from_db('Ночной забег')

print('✅ Функция выполнена')

if results:
    print(f'✅ Получено {len(results.get("years_data", []))} лет данных')
    print('\n=== РЕЗУЛЬТАТ ===')
    print(json.dumps(results, indent=2, ensure_ascii=False))
else:
    print('⚠️ Результат пуст')
    sys.exit(1)
