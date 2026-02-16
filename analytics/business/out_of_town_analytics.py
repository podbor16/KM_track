"""
Модуль для анализа иногородних участников
Работает с таблицей Все заявки
"""
import logging
from typing import Dict, Any, Optional
from mysql.connector import Error

from ..db_connection import create_connection

logger = logging.getLogger(__name__)


class OutOfTownAnalytics:
    """
    Класс для анализа иногородних участников
    """
    
    def __init__(self,
                 table_name: str = 'Все заявки',
                 city_column: str = 'city',
                 race_column: str = 'products',
                 local_city: str = 'Красноярск'):
        """
        Инициализация модуля
        
        Args:
            table_name: название таблицы (по умолчанию 'Все заявки')
            city_column: название колонки с городом
            race_column: название колонки с названием забега (products)
            local_city: название локального города (по умолчанию Красноярск)
        """
        self.table_name = table_name
        self.city_column = city_column
        self.race_column = race_column
        self.local_city = local_city
    
    def get_out_of_town_statistics(self, 
                                   race_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Получить статистику по иногородним участникам
        
        Args:
            race_name: название забега (если None, то по всем забегам)
        
        Returns:
            Словарь со статистикой:
            - out_of_town_count: абсолютное количество иногородних
            - total_participants: общее количество участников
            - out_of_town_percentage: процент иногородних
            - local_count: количество местных участников
            - local_percentage: процент местных участников
        """
        connection = create_connection()
        if not connection:
            logger.error("Не удалось подключиться к базе данных")
            return {'error': 'Database connection failed'}
        
        try:
            cursor = connection.cursor(buffered=True, dictionary=True)
            
            # Базовый запрос для подсчета участников
            base_query = f"FROM `{self.table_name}`"
            where_clauses = []
            params = []

            # Добавляем условие по забегу, если указано
            if race_name:
                where_clauses.append(f"`{self.race_column}` = %s")
                params.append(race_name)

            # Формируем WHERE часть
            where_clause = ""
            if where_clauses:
                where_clause = "WHERE " + " AND ".join(where_clauses)

            # Считаем общее количество участников
            total_query = f"""
                SELECT COUNT(*) as total_participants
                {base_query}
                {where_clause}
            """

            cursor.execute(total_query, params)
            total_result = cursor.fetchone()
            total_participants = total_result['total_participants'] if total_result else 0

            # Считаем местных участников (используем LIKE для учета разных написаний)
            local_query = f"""
                SELECT COUNT(*) as local_count
                {base_query}
                {where_clause + ' AND ' if where_clause else 'WHERE '}
                (
                    TRIM(LOWER(`{self.city_column}`)) = TRIM(LOWER(%s)) OR
                    `{self.city_column}` LIKE %s OR
                    `{self.city_column}` LIKE %s
                )
            """

            local_params = params.copy()
            local_params.extend([self.local_city, f"%{self.local_city}%", f"{self.local_city}%"])

            cursor.execute(local_query, local_params)
            local_result = cursor.fetchone()
            local_count = local_result['local_count'] if local_result else 0

            # Иногородние = общее количество - местные
            out_of_town_count = total_participants - local_count

            # Вычисляем проценты
            out_of_town_percentage = (out_of_town_count / total_participants * 100) if total_participants > 0 else 0.0
            local_percentage = (local_count / total_participants * 100) if total_participants > 0 else 0.0

            # Получаем список городов по убыванию количества участников
            cities_query = f"""
                SELECT 
                    `{self.city_column}` as city,
                    COUNT(*) as participants_count
                {base_query}
                {where_clause + ' AND ' if where_clause else 'WHERE '}
                `{self.city_column}` IS NOT NULL AND `{self.city_column}` != ''
                GROUP BY `{self.city_column}`
                ORDER BY participants_count DESC
                LIMIT 20
            """

            cursor.execute(cities_query, params)
            cities_list = cursor.fetchall()

            # Получаем список иногородних городов отдельно
            out_of_town_cities_query = f"""
                SELECT 
                    `{self.city_column}` as city,
                    COUNT(*) as participants_count
                {base_query}
                {where_clause + ' AND ' if where_clause else 'WHERE '}
                `{self.city_column}` IS NOT NULL AND 
                `{self.city_column}` != '' AND
                (
                    TRIM(LOWER(`{self.city_column}`)) != TRIM(LOWER(%s)) AND
                    `{self.city_column}` NOT LIKE %s AND
                    `{self.city_column}` NOT LIKE %s
                )
                GROUP BY `{self.city_column}`
                ORDER BY participants_count DESC
            """

            out_of_town_params = params.copy()
            out_of_town_params.extend([self.local_city, f"%{self.local_city}%", f"{self.local_city}%"])

            cursor.execute(out_of_town_cities_query, out_of_town_params)
            out_of_town_cities = cursor.fetchall()

            cursor.close()

            return {
                'total_out_of_town': out_of_town_count,
                'total_registrations': total_participants,
                'local_count': local_count,
                'percentage': round(out_of_town_percentage, 2),
                'local_percentage': round(local_percentage, 2),
                'local_city': self.local_city,
                'race_name': race_name,
                'cities_by_participants': [
                    {
                        'city': row['city'] or 'Не указан',
                        'participants_count': row['participants_count'],
                        'is_local': (
                            (row['city'] or '').lower().strip() == self.local_city.lower().strip() or
                            (self.local_city.lower() in (row['city'] or '').lower())
                        )
                    }
                    for row in cities_list
                ],
                'out_of_town_cities': [
                    {
                        'city': row['city'],
                        'participants_count': row['participants_count']
                    }
                    for row in out_of_town_cities
                ]
            }

        except Error as e:
            logger.error(f"Ошибка при выполнении запроса: {e}")
            return {
                'total_out_of_town': 0,
                'total_registrations': 0,
                'local_count': 0,
                'percentage': 0,
                'error': str(e)
            }
        finally:
            if connection.is_connected():
                connection.close()

    def get_out_of_town_by_race(self) -> Dict[str, Any]:
        """
        Получить статистику по иногородним участникам по каждому забегу

        Returns:
            Словарь со статистикой по каждому забегу
        """
        connection = create_connection()
        if not connection:
            logger.error("Не удалось подключиться к базе данных")
            return {'error': 'Database connection failed'}

        try:
            cursor = connection.cursor(buffered=True, dictionary=True)

            # Получаем все уникальные забеги
            races_query = f"""
                SELECT DISTINCT `{self.race_column}` as race_name
                FROM `{self.table_name}`
                WHERE `{self.race_column}` IS NOT NULL 
                  AND `{self.race_column}` != ''
                ORDER BY `{self.race_column}`
            """

            cursor.execute(races_query)
            races = cursor.fetchall()

            races_stats = []

            for race in races:
                race_name = race['race_name']

                # Общее количество участников для этого забега
                total_query = f"""
                    SELECT COUNT(*) as total_participants
                    FROM `{self.table_name}`
                    WHERE `{self.race_column}` = %s
                """

                cursor.execute(total_query, (race_name,))
                total_result = cursor.fetchone()
                total_participants = total_result['total_participants'] if total_result else 0

                # Местные участники для этого забега
                local_query = f"""
                    SELECT COUNT(*) as local_count
                    FROM `{self.table_name}`
                    WHERE `{self.race_column}` = %s AND
                    (
                        TRIM(LOWER(`{self.city_column}`)) = TRIM(LOWER(%s)) OR
                        `{self.city_column}` LIKE %s OR
                        `{self.city_column}` LIKE %s
                    )
                """

                cursor.execute(local_query, (race_name, self.local_city, f"%{self.local_city}%", f"{self.local_city}%"))
                local_result = cursor.fetchone()
                local_count = local_result['local_count'] if local_result else 0

                # Иногородние для этого забега
                out_of_town_count = total_participants - local_count

                # Проценты
                out_of_town_percentage = (out_of_town_count / total_participants * 100) if total_participants > 0 else 0.0
                local_percentage = (local_count / total_participants * 100) if total_participants > 0 else 0.0

                races_stats.append({
                    'race_name': race_name,
                    'total_participants': total_participants,
                    'local_count': local_count,
                    'out_of_town_count': out_of_town_count,
                    'out_of_town_percentage': round(out_of_town_percentage, 2),
                    'local_percentage': round(local_percentage, 2)
                })

            cursor.close()

            return {
                'local_city': self.local_city,
                'races': races_stats
            }

        except Error as e:
            logger.error(f"Ошибка при выполнении запроса: {e}")
            return {'error': str(e)}
        finally:
            if connection.is_connected():
                connection.close()