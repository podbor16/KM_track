"""
Запросы к БД: поиск спортсменов и профиль результатов.
"""

import logging
from typing import List, Dict, Any

from .db_pool import get_pooled_connection, find_table, get_table_columns

logger = logging.getLogger(__name__)


def search_clients_optimized(search_query: str, limit: int = 20) -> List[Dict[str, Any]]:
    """
    Поиск спортсменов по фамилии/имени.

    Args:
        search_query: поисковая строка
        limit: максимум результатов

    Returns:
        Список найденных спортсменов
    """
    connection = get_pooled_connection()
    if not connection:
        logger.error("❌ Не удалось получить соединение")
        return []

    try:
        cursor = connection.cursor(dictionary=True, buffered=True)

        target_table = find_table(["clients", "Клиенты", "спортсмены", "athletes", "participants"])

        if not target_table:
            logger.error("❌ Таблица не найдена")
            return []

        columns = get_table_columns(target_table)

        surname_field = next((col for col in columns if col.lower() in ['surname', 'фамилия', 'last_name']), None)
        name_field = next((col for col in columns if col.lower() in ['name', 'имя', 'first_name']), None)
        birthday_field = next((col for col in columns if col.lower() in ['birthday', 'дата рождения', 'birthdate']), None)

        if not all([surname_field, name_field]):
            logger.error("❌ Не найдены поля поиска")
            return []

        select_fields = [surname_field, name_field]
        if birthday_field:
            select_fields.append(birthday_field)

        fields_str = ', '.join([f'`{f}`' for f in select_fields])
        search_term = f"%{search_query}%"

        query = f"""
        SELECT {fields_str}
        FROM `{target_table}`
        WHERE `{surname_field}` LIKE %s
           OR `{name_field}` LIKE %s
        LIMIT %s
        """

        cursor.execute(query, (search_term, search_term, limit))
        records = cursor.fetchall()

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


def get_athlete_results_optimized(surname: str, name: str) -> tuple:
    """
    Результаты спортсмена с информацией о событиях.

    Args:
        surname: Фамилия
        name: Имя

    Returns:
        Кортеж (info_dict, results_list)
    """
    logger.info(f"🔍 Поиск спортсмена: {surname} {name}")

    connection = get_pooled_connection()
    if not connection:
        logger.error("❌ Не удалось установить соединение")
        return {}, []

    try:
        cursor = connection.cursor(dictionary=True, buffered=True)

        results_table = find_table(["results", "Results", "RESULTS", "гонка", "забеги"])

        if not results_table:
            logger.error("❌ Таблица results не найдена")
            return {}, []

        columns = get_table_columns(results_table)

        surname_field = next((col for col in columns if col.lower() in ['surname', 'фамилия', 'last_name']), None)
        name_field = next((col for col in columns if col.lower() in ['name', 'имя', 'first_name']), None)

        if not surname_field or not name_field:
            logger.error("❌ Не найдены поля фамилии и имени")
            return {}, []

        query = f"""
        SELECT
            r.*,
            e.event_name,
            e.event_distance,
            e.event_year,
            e.event_date
        FROM `{results_table}` r
        LEFT JOIN events e ON r.event_id = e.id
        WHERE r.`{surname_field}` = %s
          AND r.`{name_field}` = %s
        ORDER BY r.time_gun_start DESC
        """

        cursor.execute(query, (surname, name))
        results = cursor.fetchall()

        if not results:
            logger.warning("⚠️ Спортсмен не найден")
            cursor.close()
            return {}, []

        athlete_info = dict(results[0]) if results else {}
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


# Псевдонимы для обратной совместимости
get_athlete_results = get_athlete_results_optimized
search_clients = search_clients_optimized
