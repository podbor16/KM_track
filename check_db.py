#!/usr/bin/env python
# -*- coding: utf-8 -*-

from src.analytics.db_connection_optimized import get_pooled_connection
import json

print('=== Проверка реальных значений в БД ===\n')

# Получаем образцы данных
conn = get_pooled_connection()
cursor = conn.cursor(dictionary=True, buffered=True)

# Смотрим уникальные значения sex
print('1. Уникальные значения sex:')
cursor.execute('SELECT DISTINCT sex FROM results LIMIT 20')
sexes = cursor.fetchall()
for s in sexes:
    sex_val = s.get('sex', 'NULL')
    print(f"   Sex value: '{sex_val}' (type: {type(sex_val).__name__})")

if not sexes:
    print("   (Нет данных)")

# Смотрим образцы finish_pace_avg и пол
print('\n2. Образцы данных с полом и темпом:')
cursor.execute('''
SELECT 
    sex, 
    finish_pace_avg, 
    time_clear_finish,
    race_status
FROM results 
WHERE race_status IN ('Finished', 'finished') 
LIMIT 20
''')
results = cursor.fetchall()
for r in results:
    sex = r.get('sex', 'NULL')
    pace = r.get('finish_pace_avg', 'NULL')
    time = r.get('time_clear_finish', 'NULL')
    status = r.get('race_status', 'NULL')
    print(f"   Sex: '{sex}' | Pace: '{pace}' ({type(pace).__name__}) | Time: {time} | Status: {status}")

if not results:
    print("   (Нет данных)")

cursor.close()
