"""
Тестовый скрипт для отладки функции get_athlete_results
"""
import os
import sys
import logging

# Настройка логирования
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Импортируем функцию
from src.analytics.db_connection import create_connection, get_athlete_results, search_clients

print("=" * 80)
print("🧪 ТЕСТ 1: Проверка подключения к БД")
print("=" * 80)

conn = create_connection()
if conn:
    print("✅ Подключение к БД успешно!")
    
    # Получаем список таблиц
    try:
        cursor = conn.cursor()
        cursor.execute("SHOW TABLES")
        tables = cursor.fetchall()
        print(f"\n📋 Таблицы в БД:")
        for table in tables:
            print(f"   - {table[0]}")
        cursor.close()
    except Exception as e:
        print(f"❌ Ошибка при получении таблиц: {e}")
    
    conn.close()
else:
    print("❌ Не удалось подключиться к БД")
    sys.exit(1)

print("\n" + "=" * 80)
print("🧪 ТЕСТ 2: Поиск спортсменов")
print("=" * 80)

# Ищем спортсменов
athletes = search_clients("Дементьева")
print(f"\n🔍 Найдено спортсменов по слову 'Дементьева': {len(athletes)}")
for athlete in athletes[:5]:
    print(f"   - {athlete.get('surname', '?')} {athlete.get('name', '?')} ({athlete.get('birth_year', '?')})")

print("\n" + "=" * 80)
print("🧪 ТЕСТ 3: Получение профиля спортсмена")
print("=" * 80)

if athletes:
    athlete = athletes[0]
    surname = athlete.get('surname', '')
    name = athlete.get('name', '')
    
    print(f"\nПолучаю профиль: {surname} {name}")
    
    athlete_info, results = get_athlete_results(surname, name)
    
    print(f"\n✅ Информация о спортсмене:")
    if athlete_info:
        for key, value in list(athlete_info.items())[:10]:
            print(f"   {key}: {value}")
    else:
        print("   (нет информации)")
    
    print(f"\n✅ Результаты ({len(results)} гонок):")
    for i, result in enumerate(results[:3]):
        print(f"   [{i+1}] {result.get('event', '?')} - {result.get('status', '?')}")
else:
    print("❌ Спортсменов не найдено, невозможно продолжить тест")

print("\n" + "=" * 80)
print("✅ ТЕСТИРОВАНИЕ ЗАВЕРШЕНО")
print("=" * 80)
