"""
Модуль для анализа иногородних участников
Работает с таблицей Тестовая
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
                 table_name: str = 'Тестовая',
                 city_column: str = 'city',
                 race_column: str = 'products',
                 local_city: str = 'Красноярск'):
        """
        Инициализация модуля
        
        Args:
            table_name: название таблицы (по умолчанию 'Тестовая')
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
            
            # Формируем запрос в зависимости от наличия race_name
            if race_name:
                query = f"""
                    SELECT 
                        CASE 
                            WHEN LOWER(TRIM(`{self.city_column}`)) = LOWER(TRIM(%s)) 
                            THEN 'local'
                            ELSE 'out_of_town'
                        END as participant_type,
                        COUNT(*) as count
                    FROM `{self.table_name}`
                    WHERE `{self.race_column}` = %s
                    GROUP BY participant_type
                """
                cursor.execute(query, (self.local_city, race_name))
            else:
                query = f"""
                    SELECT 
                        CASE 
                            WHEN LOWER(TRIM(`{self.city_column}`)) = LOWER(TRIM(%s)) 
                            THEN 'local'
                            ELSE 'out_of_town'
                        END as participant_type,
                        COUNT(*) as count
                    FROM `{self.table_name}`
                    GROUP BY participant_type
                """
                cursor.execute(query, (self.local_city,))
            
            results = cursor.fetchall()
            
            # Инициализируем счетчики
            out_of_town_count = 0
            local_count = 0
            
            for row in results:
                if row['participant_type'] == 'out_of_town':
                    out_of_town_count = row['count']
                elif row['participant_type'] == 'local':
                    local_count = row['count']
            
            total_participants = out_of_town_count + local_count
            
            # Вычисляем проценты
            out_of_town_percentage = (out_of_town_count / total_participants * 100) if total_participants > 0 else 0.0
            local_percentage = (local_count / total_participants * 100) if total_participants > 0 else 0.0
            
            # Получаем список городов по убыванию количества участников
            cities_query = f"""
                SELECT 
                    `{self.city_column}` as city,
                    COUNT(*) as participants_count
                FROM `{self.table_name}`
                {f"WHERE `{self.race_column}` = %s" if race_name else ""}
                GROUP BY `{self.city_column}`
                ORDER BY participants_count DESC
            """
            
            if race_name:
                cursor.execute(cities_query, (race_name,))
            else:
                cursor.execute(cities_query)
            
            cities_list = cursor.fetchall()
            
            cursor.close()
            
            return {
                'out_of_town_count': out_of_town_count,
                'local_count': local_count,
                'total_participants': total_participants,
                'out_of_town_percentage': round(out_of_town_percentage, 2),
                'local_percentage': round(local_percentage, 2),
                'local_city': self.local_city,
                'race_name': race_name,
                'cities_by_participants': [
                    {
                        'city': row['city'] or 'Не указан',
                        'participants_count': row['participants_count'],
                        'is_local': (row['city'] or '').lower().strip() == self.local_city.lower().strip()
                    }
                    for row in cities_list
                ]
            }
            
        except Error as e:
            logger.error(f"Ошибка при выполнении запроса: {e}")
            return {'error': str(e)}
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
            
            query = f"""
                SELECT 
                    `{self.race_column}` as race_name,
                    CASE 
                        WHEN LOWER(TRIM(`{self.city_column}`)) = LOWER(TRIM(%s)) 
                        THEN 'local'
                        ELSE 'out_of_town'
                    END as participant_type,
                    COUNT(*) as count
                FROM `{self.table_name}`
                WHERE `{self.race_column}` IS NOT NULL 
                  AND `{self.race_column}` != ''
                GROUP BY `{self.race_column}`, participant_type
                ORDER BY `{self.race_column}`
            """
            
            cursor.execute(query, (self.local_city,))
            results = cursor.fetchall()
            
            # Группируем по забегам
            races_stats = {}
            for row in results:
                race_name = row['race_name']
                if race_name not in races_stats:
                    races_stats[race_name] = {
                        'race_name': race_name,
                        'out_of_town_count': 0,
                        'local_count': 0,
                        'total_participants': 0
                    }
                
                if row['participant_type'] == 'out_of_town':
                    races_stats[race_name]['out_of_town_count'] = row['count']
                elif row['participant_type'] == 'local':
                    races_stats[race_name]['local_count'] = row['count']
            
            # Вычисляем итоги и проценты
            for race_name, stats in races_stats.items():
                stats['total_participants'] = stats['out_of_town_count'] + stats['local_count']
                stats['out_of_town_percentage'] = round(
                    (stats['out_of_town_count'] / stats['total_participants'] * 100) 
                    if stats['total_participants'] > 0 else 0.0, 
                    2
                )
                stats['local_percentage'] = round(
                    (stats['local_count'] / stats['total_participants'] * 100) 
                    if stats['total_participants'] > 0 else 0.0, 
                    2
                )
            
            cursor.close()
            
            return {
                'local_city': self.local_city,
                'races': list(races_stats.values())
            }
            
        except Error as e:
            logger.error(f"Ошибка при выполнении запроса: {e}")
            return {'error': str(e)}
        finally:
            if connection.is_connected():
                connection.close()
