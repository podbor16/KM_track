"""
Пул соединений MySQL: инициализация, кэш таблиц, утилиты.
"""

import mysql.connector
from mysql.connector import Error, pooling
import logging
import time
from typing import Optional, List
from threading import Lock

logger = logging.getLogger(__name__)

# ============================================================
# БЕЗОПАСНОСТЬ: whitelist допустимых имён таблиц
# ============================================================

_ALLOWED_TABLES = {'clients', 'events', 'leads', 'result_segments', 'results'}


def _validate_table_name(name: str) -> str:
    if name not in _ALLOWED_TABLES:
        raise ValueError(f"Недопустимое имя таблицы: {name!r}")
    return name


# ============================================================
# ГЛОБАЛЬНЫЙ ПУЛИНГ СОЕДИНЕНИЙ
# ============================================================

_connection_pool = None
_pool_lock = Lock()


def initialize_connection_pool(pool_size: int = 5) -> Optional[pooling.MySQLConnectionPool]:
    """Инициализирует глобальный пул соединений."""
    global _connection_pool

    if _connection_pool is not None:
        logger.info("✅ Пул соединений уже инициализирован")
        return _connection_pool

    try:
        from src.config import settings

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
    """Получает соединение из пула (с ленивой инициализацией)."""
    global _connection_pool

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
    global _tables_cache_time, _tables_cache_ttl
    if _tables_cache_time is None:
        return False
    return (time.time() - _tables_cache_time) < _tables_cache_ttl


def get_cached_tables() -> List[str]:
    """Получает список таблиц БД с кэшированием (TTL 5 мин)."""
    global _tables_cache, _tables_cache_time

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

        existing_tables = []
        if tables_result:
            if isinstance(tables_result[0], dict):
                key = list(tables_result[0].keys())[0]
                existing_tables = [table[key] for table in tables_result]
            else:
                existing_tables = [table[0] for table in tables_result]

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
    """Ищет таблицу по списку возможных имён (case-insensitive)."""
    existing_tables = get_cached_tables()

    for possible_name in possible_names:
        for existing_table in existing_tables:
            if possible_name.lower() == existing_table.lower():
                logger.debug(f"✅ Найдена таблица: {existing_table}")
                return existing_table

    logger.error(f"❌ Таблица не найдена. Доступные: {existing_tables}")
    return None


# ============================================================
# ИНФОРМАЦИЯ О ТАБЛИЦЕ
# ============================================================

def get_table_row_count_fast(table_name: str) -> int:
    """Приблизительное число строк из INFORMATION_SCHEMA (быстро, ~1-5ms)."""
    connection = get_pooled_connection()
    if not connection:
        return 0

    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            "SELECT TABLE_ROWS as row_count FROM INFORMATION_SCHEMA.TABLES "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s",
            (table_name,)
        )
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
    """Возвращает список столбцов таблицы."""
    connection = get_pooled_connection()
    if not connection:
        return []

    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(f"DESCRIBE `{_validate_table_name(table_name)}`")
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
