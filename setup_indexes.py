#!/usr/bin/env python
"""
Скрипт для проверки и создания оптимальных индексов БД для быстрой загрузки результатов
"""

import sys
from pathlib import Path
import mysql.connector
from mysql.connector import Error

# Добавляем src в PATH
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.analytics.db_connection import create_connection

def check_and_create_indexes():
    """Проверить и создать необходимые индексы"""
    
    conn = create_connection()
    cursor = conn.cursor()
    
    print("\n" + "="*70)
    print("ПРОВЕРКА И СОЗДАНИЕ ИНДЕКСОВ ДЛЯ ОПТИМИЗАЦИИ")
    print("="*70 + "\n")
    
    # Индексы для таблицы results
    results_indexes = [
        {
            'name': 'idx_results_event_dorsal',
            'table': 'results',
            'columns': '(event_id, start_number)',
            'query': 'CREATE INDEX idx_results_event_dorsal ON results(event_id, start_number)',
            'description': 'Быстрый поиск результатов по событию и номеру участника'
        },
        {
            'name': 'idx_results_event_id',
            'table': 'results',
            'columns': '(event_id)',
            'query': 'CREATE INDEX idx_results_event_id ON results(event_id)',
            'description': 'Быстрый поиск всех результатов события'
        },
    ]
    
    # Индексы для таблицы result_segments
    segments_indexes = [
        {
            'name': 'idx_segments_result_code',
            'table': 'result_segments',
            'columns': '(result_id, segment_code)',
            'query': 'CREATE UNIQUE INDEX idx_segments_result_code ON result_segments(result_id, segment_code)',
            'description': 'Уникальный индекс для ON DUPLICATE KEY UPDATE'
        },
        {
            'name': 'idx_segments_result_id',
            'table': 'result_segments',
            'columns': '(result_id)',
            'query': 'CREATE INDEX idx_segments_result_id ON result_segments(result_id)',
            'description': 'Быстрый поиск сегментов по результату'
        },
    ]
    
    all_indexes = results_indexes + segments_indexes
    
    # Проверить существующие индексы
    created_count = 0
    skipped_count = 0
    
    for idx_info in all_indexes:
        print(f"\n📋 Проверка: {idx_info['name']}")
        print(f"   Таблица: {idx_info['table']}")
        print(f"   Описание: {idx_info['description']}")
        print(f"   Колонки: {idx_info['columns']}")
        
        # Проверить, существует ли индекс
        cursor.execute(f"""
            SELECT INDEX_NAME FROM INFORMATION_SCHEMA.STATISTICS 
            WHERE TABLE_SCHEMA = 'krasmarafon' 
            AND TABLE_NAME = '{idx_info['table']}' 
            AND INDEX_NAME = '{idx_info['name']}'
        """)
        
        if cursor.fetchone():
            print(f"   ✅ Индекс уже существует")
            skipped_count += 1
        else:
            # Создать индекс
            try:
                print(f"   ⏳ Создание индекса...")
                cursor.execute(idx_info['query'])
                conn.commit()
                print(f"   ✅ Индекс успешно создан")
                created_count += 1
            except Error as e:
                if 'already exists' in str(e) or 'Duplicate key' in str(e):
                    print(f"   ℹ️ Индекс уже существует (обнаружено исключением)")
                    skipped_count += 1
                else:
                    print(f"   ❌ Ошибка: {e}")
    
    # Показать все индексы таблиц
    print("\n\n" + "="*70)
    print("ТЕКУЩИЕ ИНДЕКСЫ В ТАБЛИЦАХ")
    print("="*70 + "\n")
    
    for table_name in ['results', 'result_segments']:
        print(f"\n📊 Таблица: {table_name}")
        print("-" * 60)
        
        cursor.execute(f"""
            SELECT INDEX_NAME, COLUMN_NAME, SEQ_IN_INDEX
            FROM INFORMATION_SCHEMA.STATISTICS
            WHERE TABLE_SCHEMA = 'krasmarafon' AND TABLE_NAME = '{table_name}'
            ORDER BY INDEX_NAME, SEQ_IN_INDEX
        """)
        
        current_index = None
        for row in cursor.fetchall():
            idx_name, col_name, seq = row
            
            if idx_name != current_index:
                current_index = idx_name
                print(f"\n  {idx_name}")
            
            print(f"    - {col_name} (позиция {seq})")
    
    # Рекомендации
    print("\n\n" + "="*70)
    print("РЕКОМЕНДАЦИИ ДЛЯ ОПТИМИЗАЦИИ")
    print("="*70 + "\n")
    
    recommendations = [
        "✅ Убедитесь что all индексы созданы",
        "✅ Используйте load_race_results_optimized.py для большого количества участников",
        "✅ Для 10000+ участников ожидается загрузка за 6-10 секунд",
        "📊 Проверьте размер таблиц:",
        "   SELECT table_name, (data_length + index_length) / 1024 / 1024 AS size_mb",
        "   FROM information_schema.tables",
        "   WHERE table_schema = 'krasmarafon' AND table_name IN ('results', 'result_segments');",
        "",
        "⚡ Для еще более быстрой загрузки (если >50000 участников):",
        "   1. Отключите индексы перед вставкой: ALTER TABLE results DISABLE KEYS;",
        "   2. Вставьте данные",
        "   3. Включите индексы: ALTER TABLE results ENABLE KEYS;",
    ]
    
    for rec in recommendations:
        print(rec)
    
    # Итог
    print("\n\n" + "="*70)
    print(f"✅ ЗАВЕРШЕНО: Создано {created_count} индексов, пропущено {skipped_count}")
    print("="*70 + "\n")
    
    cursor.close()
    conn.close()


if __name__ == '__main__':
    try:
        check_and_create_indexes()
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        sys.exit(1)
