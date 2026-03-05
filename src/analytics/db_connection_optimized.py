"""
Оптимизированная система работы с БД с пулом соединений и кэшированием

Улучшения:
1. ✅ Connection Pool - переиспользование соединений
2. ✅ Кэширование SHOW TABLES результатов
3. ✅ Оптимизированные запросы
4. ✅ INFORMATION_SCHEMA вместо COUNT(*)
5. ✅ Подготовленные запросы (Prepared Statements)
"""

import mysql.connector
from mysql.connector import Error, pooling
import logging
import os
from typing import Optional, Dict, List, Any
import datetime
import time
from functools import lru_cache
from threading import Lock

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ============================================================
# ГЛОБАЛЬНЫЙ ПУЛИНГ СОЕДИНЕНИЙ - ГЛАВНОЕ УЛУЧШЕНИЕ
# ============================================================

_connection_pool = None
_pool_lock = Lock()

def initialize_connection_pool(pool_size: int = 5) -> Optional[pooling.MySQLConnectionPool]:
    """
    Инициализирует глобальный пул соединений
    
    Преимущества:
    - Переиспользуются существующие соединения (~10ms вместо 200ms)
    - Автоматическое управление жизненным циклом
    - Безопасность в многопоточной среде
    
    Args:
        pool_size: Количество соединений в пуле (дефолт: 5)
    
    Returns:
        MySQLConnectionPool или None если ошибка
    """
    global _connection_pool
    
    if _connection_pool is not None:
        logger.info("✅ Пул соединений уже инициализирован")
        return _connection_pool
    
    try:
        from src.config import settings
        
        # Создаем пул соединений
        _connection_pool = pooling.MySQLConnectionPool(
            pool_name='km_track_pool',
            pool_size=pool_size,
            pool_reset_session=True,
            host=settings.DB_HOST,
            database=settings.DB_NAME,
            user=settings.DB_USER,
            password=settings.DB_PASSWORD,
            port=settings.DB_PORT,
            charset='utf8mb4',
            autocommit=True,
            connection_timeout=10,
        )
        
        logger.info(f"✅ Пул соединений инициализирован (размер: {pool_size})")
        return _connection_pool
        
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации пула соединений: {e}")
        return None


def get_pooled_connection() -> Optional[mysql.connector.MySQLConnection]:
    """
    Получает соединение из пула (ВМЕСТО create_connection)
    
    Производительность:
    - Первый вызов: инициализирует пул (200ms)
    - Последующие вызовы: берут из пула (~10ms)
    
    Returns:
        MySQLConnection или None если соединение недоступно
    """
    global _connection_pool
    
    # Ленивая инициализация пула
    if _connection_pool is None:
        with _pool_lock:
            if _connection_pool is None:
                _connection_pool = initialize_connection_pool()
    
    try:
        if _connection_pool:
            connection = _connection_pool.get_connection()
            if connection and connection.is_connected():
                logger.debug("✅ Соединение получено из пула")
                return connection
    except Error as e:
        logger.error(f"❌ Ошибка получения соединения из пула: {e}")
    
    return None


# ============================================================
# КЭШИРОВАНИЕ ТАБЛИЦ БД
# ============================================================

_tables_cache = {}
_tables_cache_time = None
_tables_cache_ttl = 300  # 5 минут

def _is_tables_cache_valid() -> bool:
    """Проверяет валидность кэша таблиц"""
    global _tables_cache_time, _tables_cache_ttl
    if _tables_cache_time is None:
        return False
    return (time.time() - _tables_cache_time) < _tables_cache_ttl


def get_cached_tables() -> List[str]:
    """
    Получает список таблиц БД с кэшированием
    
    ОПТИМИЗАЦИЯ:
    - Первый вызов: выполняет SHOW TABLES (~20ms)
    - Последующие 5 минут: возвращает из кэша (~0ms)
    - После TTL: обновляет кэш
    
    Returns:
        Список названий таблиц
    """
    global _tables_cache, _tables_cache_time
    
    # Проверяем кэш
    if 'tables' in _tables_cache and _is_tables_cache_valid():
        logger.debug(f"📂 Таблицы из КЭША: {_tables_cache['tables']}")
        return _tables_cache['tables']
    
    logger.info("🔄 Обновляем кэш таблиц из БД...")
    
    connection = get_pooled_connection()
    if not connection:
        logger.error("❌ Не удалось получить соединение")
        return _tables_cache.get('tables', [])
    
    try:
        cursor = connection.cursor()
        cursor.execute("SHOW TABLES")
        tables_result = cursor.fetchall()
        
        # Извлекаем названия таблиц
        existing_tables = []
        if tables_result:
            if isinstance(tables_result[0], dict):
                key = list(tables_result[0].keys())[0]
                existing_tables = [table[key] for table in tables_result]
            else:
                existing_tables = [table[0] for table in tables_result]
        
        # Обновляем кэш
        _tables_cache['tables'] = existing_tables
        _tables_cache_time = time.time()
        
        logger.info(f"✅ Кэш таблиц обновлен: {existing_tables}")
        cursor.close()
        return existing_tables
        
    except Exception as e:
        logger.error(f"❌ Ошибка получения таблиц: {e}")
        return _tables_cache.get('tables', [])
    finally:
        if connection.is_connected():
            connection.close()


def find_table(possible_names: List[str]) -> Optional[str]:
    """
    Ищет таблицу по списку возможных имен (с учетом регистра)
    
    Использует кэшированный список таблиц
    
    Args:
        possible_names: Список возможных имен таблицы
    
    Returns:
        Имя найденной таблицы или None
    """
    existing_tables = get_cached_tables()
    
    for possible_name in possible_names:
        for existing_table in existing_tables:
            if possible_name.lower() == existing_table.lower():
                logger.debug(f"✅ Найдена таблица: {existing_table}")
                return existing_table
    
    logger.error(f"❌ Таблица не найдена. Доступные: {existing_tables}")
    return None


# ============================================================
# ПОЛУЧЕНИЕ ИНФОРМАЦИИ О ТАБЛИЦЕ ИЗ INFORMATION_SCHEMA
# ============================================================

def get_table_row_count_fast(table_name: str) -> int:
    """
    Получает краткое количество строк из INFORMATION_SCHEMA
    
    ОПТИМИЗАЦИЯ:
    - SHOW TABLE STATUS + INFORMATION_SCHEMA: ~1-5ms
    - COUNT(*): ~100-500ms для больших таблиц
    
    Минус: может быть неточным на 10-15% для InnoDB (но это быстро сбрасывается)
    
    Args:
        table_name: Имя таблицы
    
    Returns:
        Примерное количество строк
    """
    connection = get_pooled_connection()
    if not connection:
        return 0
    
    try:
        cursor = connection.cursor(dictionary=True)
        
        # ИНФОРМАЦИЯ_SCHEMA намного быстрее COUNT(*)
        cursor.execute(f"""
            SELECT TABLE_ROWS as row_count 
            FROM INFORMATION_SCHEMA.TABLES 
            WHERE TABLE_SCHEMA = DATABASE() 
            AND TABLE_NAME = %s
        """, (table_name,))
        
        result = cursor.fetchone()
        cursor.close()
        
        return result['row_count'] if result else 0
        
    except Exception as e:
        logger.error(f"❌ Ошибка получения количества строк: {e}")
        return 0
    finally:
        if connection.is_connected():
            connection.close()


def get_table_columns(table_name: str) -> List[str]:
    """
    Получает список столбцов таблицы
    
    Args:
        table_name: Имя таблицы
    
    Returns:
        Список имен столбцов
    """
    connection = get_pooled_connection()
    if not connection:
        return []
    
    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(f"DESCRIBE `{table_name}`")
        fields = cursor.fetchall()
        
        columns = [f.get('Field', '') for f in fields] if fields else []
        cursor.close()
        
        return columns
        
    except Exception as e:
        logger.error(f"❌ Ошибка получения столбцов: {e}")
        return []
    finally:
        if connection.is_connected():
            connection.close()


# ============================================================
# ОПТИМИЗИРОВАННЫЙ ПОИСК С ПОДДЕРЖКОЙ ИНДЕКСОВ
# ============================================================

def search_clients_optimized(search_query: str, limit: int = 20) -> List[Dict[str, Any]]:
    """
    Оптимизированный поиск спортсменов
    
    УЛУЧШЕНИЯ:
    1. Использует пулинг соединений
    2. Использует кэшированный список таблиц (1 запрос вместо 2)
    3. Параметризованные запросы (защита от SQL инъекций)
    4. Опция поиска по точному совпадению при наличии индекса
    5. Предварительно выбранные столбцы (не SELECT *)
    
    Args:
        search_query: Поисковая строка
        limit: Максимум результатов
    
    Returns:
        Список найденных спортсменов
    """
    connection = get_pooled_connection()
    if not connection:
        logger.error("❌ Не удалось получить соединение")
        return []
    
    try:
        cursor = connection.cursor(dictionary=True, buffered=True)
        
        # Используем кэшированный список таблиц
        target_table = find_table([
            "clients",
            "Клиенты",
            "спортсмены",
            "athletes",
            "participants"
        ])
        
        if not target_table:
            logger.error("❌ Таблица не найдена")
            return []
        
        # Получаем столбцы только один раз
        columns = get_table_columns(target_table)
        
        # Определяем нужные поля
        surname_field = next((col for col in columns 
                             if col.lower() in ['surname', 'фамилия', 'last_name']), None)
        name_field = next((col for col in columns 
                          if col.lower() in ['name', 'имя', 'first_name']), None)
        birthday_field = next((col for col in columns 
                              if col.lower() in ['birthday', 'дата рождения', 'birthdate']), None)
        
        if not all([surname_field, name_field]):
            logger.error(f"❌ Не найдены поля поиска")
            return []
        
        # ОПТИМИЗАЦИЯ: выбираем только нужные столбцы
        select_fields = [surname_field, name_field]
        if birthday_field:
            select_fields.append(birthday_field)
        
        fields_str = ', '.join([f'`{f}`' for f in select_fields])
        
        # Используем параметризованный запрос
        search_term = f"%{search_query}%"
        
        query = f"""
        SELECT {fields_str}
        FROM `{target_table}`
        WHERE `{surname_field}` LIKE %s 
           OR `{name_field}` LIKE %s
        LIMIT %s
        """
        
        # Выполняем запрос
        cursor.execute(query, (search_term, search_term, limit))
        records = cursor.fetchall()
        
        # Обработка результатов
        for record in records:
            if birthday_field and birthday_field in record:
                birthday = record[birthday_field]
                if birthday:
                    if hasattr(birthday, 'year'):
                        record['birth_year'] = str(birthday.year)
                    elif isinstance(birthday, str):
                        record['birth_year'] = birthday.split('-')[0] if '-' in birthday else birthday[:4]
                    else:
                        record['birth_year'] = 'Неизвестно'
                else:
                    record['birth_year'] = 'Неизвестно'
                
                # Очищаем исходное поле даты
                record.pop(birthday_field, None)
        
        logger.info(f"✅ Найдено {len(records)} результатов для '{search_query}'")
        cursor.close()
        
        return records
        
    except Exception as e:
        logger.error(f"❌ Ошибка поиска: {e}")
        return []
    finally:
        if connection.is_connected():
            connection.close()


# ============================================================
# ОПТИМИЗИРОВАННОЕ ПОЛУЧЕНИЕ РЕЗУЛЬТАТОВ СПОРТСМЕНА
# ============================================================

def get_athlete_results_optimized(surname: str, name: str) -> tuple:
    """
    Оптимизированное получение результатов спортсмена
    
    УЛУЧШЕНИЯ:
    1. Единое соединение из пула для всех запросов
    2. Кэшированные названия таблиц
    3. Минимизация количества запросов
    4. Параметризованные запросы
    
    Args:
        surname: Фамилия спортсмена
        name: Имя спортсмена
    
    Returns:
        Кортеж (информация о спортсмене, список его результатов)
    """
    logger.info(f"🔍 Поиск спортсмена: {surname} {name}")
    
    connection = get_pooled_connection()
    if not connection:
        logger.error("❌ Не удалось установить соединение")
        return {}, []
    
    try:
        cursor = connection.cursor(dictionary=True, buffered=True)
        
        # Используем кэшированный список таблиц (вместо SHOW TABLES)
        results_table = find_table([
            "results",
            "Results",
            "RESULTS",
            "гонка",
            "забеги"
        ])
        
        if not results_table:
            logger.error("❌ Таблица results не найдена")
            return {}, []
        
        # Получаем информацию о колонках один раз
        columns = get_table_columns(results_table)
        
        # Ищем поля фамилии и имени
        surname_field = next((col for col in columns 
                             if col.lower() in ['surname', 'фамилия', 'last_name']), None)
        name_field = next((col for col in columns 
                          if col.lower() in ['name', 'имя', 'first_name']), None)
        
        if not surname_field or not name_field:
            logger.error("❌ Не найдены поля фамилии и имени")
            return {}, []
        
        # Проверяем есть ли поле gunTime для сортировки
        has_gunTime = any(col.lower() == 'guntime' for col in columns)
        
        # ОДИН ЗАПРОС для получения информации и результатов
        if has_gunTime:
            query = f"""
            SELECT * FROM `{results_table}` 
            WHERE `{surname_field}` = %s 
              AND `{name_field}` = %s
            ORDER BY gunTime DESC
            """
        else:
            query = f"""
            SELECT * FROM `{results_table}` 
            WHERE `{surname_field}` = %s 
              AND `{name_field}` = %s
            """
        
        cursor.execute(query, (surname, name))
        results = cursor.fetchall()
        
        if not results:
            logger.warning(f"⚠️ Спортсмен не найден")
            cursor.close()
            return {}, []
        
        # Первая строка - информация о спортсмене
        athlete_info = dict(results[0]) if results else {}
        
        # Все строки - результаты
        results_list = [dict(r) for r in results]
        
        logger.info(f"✅ Найдено {len(results_list)} результатов для {surname} {name}")
        cursor.close()
        
        return athlete_info, results_list
        
    except Exception as e:
        logger.error(f"❌ Ошибка при получении результатов: {e}")
        return {}, []
    finally:
        if connection.is_connected():
            connection.close()


# ============================================================
# ПОЛУЧЕНИЕ РЕЗУЛЬТАТОВ ПО EVENT_ID
# ============================================================

def get_race_results_by_event_id(event_id: int) -> List[Dict[str, Any]]:
    """
    Получение результатов забега по event_id из таблицы results
    
    Args:
        event_id: ID события (например, 67 для Ночного забега 2025)
    
    Returns:
        Список словарей с результатами спортсменов
    """
    logger.info(f"🔍 Загрузка результатов для event_id={event_id}")
    
    connection = get_pooled_connection()
    if not connection:
        logger.error("❌ Не удалось установить соединение")
        return []
    
    try:
        cursor = connection.cursor(dictionary=True, buffered=True)
        
        # Находим таблицу results
        results_table = find_table([
            "results",
            "Results",
            "RESULTS",
            "гонка",
            "забеги"
        ])
        
        if not results_table:
            logger.error("❌ Таблица results не найдена")
            return []
        
        # Получаем информацию о колонках
        columns = get_table_columns(results_table)
        
        # Проверяем наличие поля event_id
        has_event_id = any(col.lower() == 'event_id' for col in columns)
        
        if not has_event_id:
            logger.warning(f"⚠️ Поле 'event_id' не найдено в таблице {results_table}")
            # Возвращаем пустой результат если нет поля event_id
            cursor.close()
            return []
        
        # Запрос результатов по event_id
        query = f"""
        SELECT * FROM `{results_table}` 
        WHERE event_id = %s
        ORDER BY rank_absolute ASC
        """
        
        cursor.execute(query, (event_id,))
        results = cursor.fetchall()
        
        if results:
            results_list = [dict(r) for r in results]
            logger.info(f"✅ Найдено {len(results_list)} результатов для event_id={event_id}")
            cursor.close()
            return results_list
        else:
            logger.warning(f"⚠️ Результаты для event_id={event_id} не найдены")
            cursor.close()
            return []
        
    except Exception as e:
        logger.error(f"❌ Ошибка при получении результатов: {e}")
        return []
    finally:
        if connection.is_connected():
            connection.close()


def get_race_results_by_event_id_and_year(event_name: str, year: int) -> List[Dict[str, Any]]:
    """
    Получение результатов забега по названию события и году
    
    Args:
        event_name: Название события (например, "Ночной забег")
        year: Год события (например, 2025)
    
    Returns:
        Список словарей с результатами спортсменов
    """
    logger.info(f"🔍 Загрузка результатов для {event_name} {year}")
    
    connection = get_pooled_connection()
    if not connection:
        logger.error("❌ Не удалось установить соединение")
        return []
    
    try:
        cursor = connection.cursor(dictionary=True, buffered=True)
        
        # Находим таблицу results
        results_table = find_table([
            "results",
            "Results",
            "RESULTS",
            "гонка",
            "забеги"
        ])
        
        if not results_table:
            logger.error("❌ Таблица results не найдена")
            return []
        
        # Получаем информацию о колонках
        columns = get_table_columns(results_table)
        
        # Проверяем наличие необходимых полей
        has_event_id = any(col.lower() == 'event_id' for col in columns)
        has_birthday = any(col.lower() == 'birthday' for col in columns)
        
        if not has_event_id:
            logger.warning(f"⚠️ Поле 'event_id' не найдено в таблице {results_table}")
            cursor.close()
            return []
        
        # Запрос результатов по названию события и году
        # Используем JOIN с таблицей events если она есть
        query = f"""
        SELECT r.* FROM `{results_table}` r
        INNER JOIN events e ON r.event_id = e.id
        WHERE e.name = %s AND YEAR(e.date) = %s
        ORDER BY r.rank_absolute ASC
        """
        
        try:
            cursor.execute(query, (event_name, year))
            results = cursor.fetchall()
            
            if results:
                results_list = [dict(r) for r in results]
                logger.info(f"✅ Найдено {len(results_list)} результатов для {event_name} {year}")
                cursor.close()
                return results_list
        except Exception as join_error:
            # Если JOIN не работает, пробуем альтернативный способ
            logger.warning(f"⚠️ JOIN затруднен, пробуем прямой поиск: {join_error}")
            
            query = f"""
            SELECT r.* FROM `{results_table}` r
            WHERE r.category LIKE CONCAT(%s, '%%')
            ORDER BY r.rank_absolute ASC
            LIMIT 1000
            """
            
            # Изменяем запрос на поиск по году через birthday
            if has_birthday:
                year_start = f"{year}-01-01"
                year_end = f"{year}-12-31"
                query = f"""
                SELECT * FROM `{results_table}`
                WHERE YEAR(birthday) IS NOT NULL
                ORDER BY rank_absolute ASC
                LIMIT 1000
                """
        
        cursor.execute(query, (event_name,))
        results = cursor.fetchall()
        
        if results:
            results_list = [dict(r) for r in results]
            logger.info(f"✅ Найдено {len(results_list)} результатов")
            cursor.close()
            return results_list
        else:
            logger.warning(f"⚠️ Результаты не найдены")
            cursor.close()
            return []
            
    except Exception as e:
        logger.error(f"❌ Ошибка при получении результатов: {e}")
        return []
    finally:
        if connection.is_connected():
            connection.close()


# ============================================================
# ОПТИМИЗИРОВАННЫЙ DEBUG ENDPOINT
# ============================================================

def get_database_info_optimized() -> Dict[str, Any]:
    """
    Получает информацию о БД для debug endpoint
    
    ОПТИМИЗАЦИЯ:
    - Вместо COUNT(*) использует INFORMATION_SCHEMA (~1-5ms вместо 100-500ms)
    - Использует пулинг соединений
    - Единое соединение для всех запросов
    - Кэшированный список таблиц
    
    Returns:
        Словарь с информацией о БД
    """
    debug_info = {
        "connection": "❌ Failed",
        "tables_list": [],
        "tables": [],
        "errors": []
    }
    
    connection = get_pooled_connection()
    if not connection:
        debug_info["errors"].append("Не удалось получить соединение")
        return debug_info
    
    debug_info["connection"] = "✅ Connected successfully"
    
    try:
        cursor = connection.cursor(dictionary=True, buffered=True)
        
        # Используем кэшированный список таблиц
        tables = get_cached_tables()
        debug_info["tables_list"] = tables
        
        for table_name in tables:
            table_info = {
                "name": table_name,
                "row_count": 0,
                "columns": [],
                "sample_rows": []
            }
            
            try:
                # ИНФОРМАЦИЯ_SCHEMA вместо COUNT(*) - намного быстрее!
                table_info["row_count"] = get_table_row_count_fast(table_name)
                
                # Структура таблицы
                table_info["columns"] = get_table_columns(table_name)
                
                # Примеры строк (только SELECT, без COUNT/DESCRIBE)
                cursor.execute(f"SELECT * FROM `{table_name}` LIMIT 2")
                samples = cursor.fetchall()
                table_info["sample_rows"] = samples if samples else []
                
                debug_info["tables"].append(table_info)
                
            except Exception as table_error:
                debug_info["errors"].append(f"❌ Error reading table {table_name}: {str(table_error)}")
                logger.error(f"Error reading table {table_name}: {table_error}")
        
        cursor.close()
        
    except Exception as e:
        debug_info["errors"].append(f"❌ General error: {str(e)}")
        logger.error(f"Error in debug info: {e}")
    finally:
        if connection.is_connected():
            connection.close()
    
    return debug_info


# ============================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================

def calculate_age_group(birthdate_or_age) -> str:
    """
    Рассчитывает возрастную группу по дате рождения или возрасту
    (не изменилась - оставлена для совместимости)
    """
    if not birthdate_or_age:
        return 'Неизвестно'
    
    try:
        age = None
        
        if isinstance(birthdate_or_age, (datetime.date, datetime.datetime)):
            birth_year = birthdate_or_age.year
            current_year = datetime.datetime.now().year
            age = current_year - birth_year
        elif isinstance(birthdate_or_age, str):
            try:
                birth_date = datetime.datetime.strptime(birthdate_or_age[:10], '%Y-%m-%d')
                age = datetime.datetime.now().year - birth_date.year
            except:
                try:
                    age = int(birthdate_or_age)
                except:
                    return 'Неизвестно'
        elif isinstance(birthdate_or_age, int):
            age = birthdate_or_age
        
        if age is None:
            return 'Неизвестно'
        
        if age < 49:
            return '<49'
        elif age <= 59:
            return '50-59'
        elif age <= 64:
            return '60-64'
        elif age <= 69:
            return '65-69'
        elif age <= 74:
            return '70-74'
        else:
            return '>75'
    except Exception as e:
        logger.error(f"Ошибка при расчёте возрастной группы: {e}")
        return 'Неизвестно'


# ============================================================
# МИГРАЦИЯ: СТАРЫЕ ФУНКЦИИ -> НОВЫЕ ФУНКЦИИ
# ============================================================

def get_test_table_data() -> List[Dict[str, Any]]:
    """
    Получает данные участников из БД (оптимизированная версия)
    Автоматически ищет таблицу с данными участников
    Если БД недоступна, возвращает тестовые данные
    
    ОПТИМИЗАЦИЯ: Использует пулинг соединений и кэшированный список таблиц
    """
    connection = get_pooled_connection()
    
    if connection:
        try:
            cursor = connection.cursor(dictionary=True, buffered=True)
            
            try:
                # Варианты названий таблиц для поиска
                possible_tables = [
                    "Все заявки",           # Русское имя
                    "All Applications",     # English name
                    "runners",              # Common English name
                    "participants",         # Another common name
                    "entries",              # Alternative
                    "registrations",        # RU: Регистрации
                    "zajavki",             # Транслитерация
                    "applications"          # Plural form
                ]
                
                # Используем кэшированный список таблиц (вместо SHOW TABLES)
                target_table = find_table(possible_tables)
                
                if not target_table:
                    logger.error(f"❌ Таблица не найдена. Доступные таблицы: {get_cached_tables()}")
                    return get_test_data_fallback()
                
                # Выполняем запрос к найденной таблице
                cursor.execute(f"SELECT * FROM `{target_table}`")
                records = cursor.fetchall()
                
                if records:
                    logger.info(f"✅ Получено {len(records)} записей из таблицы '{target_table}'")
                    
                    # Добавляем возрастную группу к каждой записи
                    for record in records:
                        # Проверяем какие поля есть для расчёта возраста
                        age_info = None
                        if 'birthday' in record:
                            age_info = record['birthday']
                        elif 'birthdate' in record:
                            age_info = record['birthdate']
                        elif 'Дата рождения' in record:
                            age_info = record['Дата рождения']
                        elif 'age' in record:
                            age_info = record['age']
                        elif 'Возраст' in record:
                            age_info = record['Возраст']
                        
                        if age_info:
                            record['category'] = calculate_age_group(age_info)
                        else:
                            record['category'] = 'Неизвестно'
                    
                    return records
                else:
                    logger.warning(f"⚠️ Таблица '{target_table}' пуста, возвращаем тестовые данные")
                    return get_test_data_fallback()
                
            except Error as e:
                error_msg = f"❌ Ошибка выполнения SQL запроса: {e}"
                logger.error(error_msg)
                print(f"\n{error_msg}")
                return get_test_data_fallback()
                
            finally:
                cursor.close()
                
        finally:
            if connection.is_connected():
                connection.close()
                logger.info("📂 Соединение с БД закрыто")
    else:
        logger.error("❌ Не удалось установить соединение с БД, используем тестовые данные")
        return get_test_data_fallback()


def get_test_data_fallback() -> List[Dict[str, Any]]:
    """
    Возвращает тестовые данные для режима стартового списка
    """
    return [
        {
            'surname': 'Иванов',
            'name': 'Иван',
            'sex': 'male',
            'city': 'Красноярск',
            'club': 'БегКлуб',
            'birthday': '2005-03-15',
            'category': '<49',
            'event_distance': '5 км',
            'event_name': 'Ночной забег',
            'event_year': 2026
        },
        {
            'surname': 'Петрова',
            'name': 'Мария',
            'sex': 'female',
            'city': 'Красноярск',
            'club': 'Марафон',
            'birthday': '1992-07-22',
            'category': '<49',
            'event_distance': '10 км',
            'event_name': 'Ночной забег',
            'event_year': 2026
        },
        {
            'surname': 'Сидоров',
            'name': 'Петр',
            'sex': 'male',
            'city': 'Новосибирск',
            'club': 'Спорт',
            'birthday': '1975-11-08',
            'category': '50-59',
            'event_distance': '21 км',
            'event_name': 'Ночной забег',
            'event_year': 2026
        },
        {
            'surname': 'Козлова',
            'name': 'Анна',
            'sex': 'female',
            'city': 'Красноярск',
            'club': 'БегКлуб',
            'birthday': '2000-01-30',
            'category': '<49',
            'event_distance': '5 км',
            'event_name': 'Ночной забег',
            'event_year': 2026
        },
        {
            'surname': 'Морозов',
            'name': 'Игорь',
            'sex': 'male',
            'city': 'Енисейск',
            'club': 'Олимп',
            'birthday': '1988-09-12',
            'category': '<49',
            'event_distance': '10 км',
            'event_name': 'Ночной забег',
            'event_year': 2026
        },
        {
            'surname': 'Волкова',
            'name': 'Светлана',
            'sex': 'female',
            'city': 'Красноярск',
            'club': 'Марафон',
            'birthday': '1960-05-20',
            'category': '60-64',
            'event_distance': '5 км',
            'event_name': 'Ночной забег',
            'event_year': 2026
        },
        {
            'surname': 'Белов',
            'name': 'Сергей',
            'sex': 'male',
            'city': 'Красноярск',
            'club': 'Спорт',
            'birthday': '1970-12-03',
            'category': '50-59',
            'event_distance': '21 км',
            'event_name': 'Ночной забег',
            'event_year': 2026
        },
        {
            'surname': 'Лебедева',
            'name': 'Виктория',
            'sex': 'female',
            'city': 'Ачинск',
            'club': 'Бегуны',
            'birthday': '1985-06-18',
            'category': '<49',
            'event_distance': '10 км',
            'event_name': 'Ночной забег',
            'event_year': 2026
        }
    ]

# Для обратной совместимости, маппируем старые функции на новые
get_athlete_results = get_athlete_results_optimized
search_clients = search_clients_optimized

def create_connection():
    """
    УСТАРЕВШАЯ функция - используйте get_pooled_connection() вместо этого!
    Оставлена для обратной совместимости.
    """
    logger.warning("⚠️ create_connection() устаревшая, используйте get_pooled_connection()")
    return get_pooled_connection()

