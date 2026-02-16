"""
Модуль для статистики по забегам
Работает с таблицей Все заявки, где каждая строка = одна регистрация на забег
Забег определяется по полю products
"""
import logging
from datetime import datetime
from typing import Dict, Any, Optional
from mysql.connector import Error

from ..db_connection import create_connection

logger = logging.getLogger(__name__)


class RaceStatisticsAnalytics:
    """
    Класс для статистики по забегам
    """
    
    def __init__(self,
                 table_name: str = 'Все заявки',
                 race_column: str = 'products',
                 registration_date_column: str = 'created_at',
                 name_column: str = 'name',
                 surname_column: str = 'surname',
                 birthday_column: str = 'birthday'):
        """
        Инициализация модуля
        
        Args:
            table_name: название таблицы (по умолчанию 'Все заявки')
            race_column: название колонки с названием забега (products)
            registration_date_column: название колонки с датой регистрации
            name_column: название колонки с именем
            surname_column: название колонки с фамилией
            birthday_column: название колонки с датой рождения
        """
        self.table_name = table_name
        self.race_column = race_column
        self.registration_date_column = registration_date_column
        self.name_column = name_column
        self.surname_column = surname_column
        self.birthday_column = birthday_column
    
    def _get_user_key(self) -> str:
        """Возвращает выражение для уникального ключа пользователя"""
        return f"""CONCAT(
            COALESCE(`{self.name_column}`, ''),
            '|',
            COALESCE(`{self.surname_column}`, ''),
            '|',
            COALESCE(DATE(`{self.birthday_column}`), '')
        )"""
    
    def get_customer_race_statistics(self, 
                                     user_name: str,
                                     user_surname: str,
                                     user_birthday: str) -> Dict[str, Any]:
        """
        Получить статистику по забегам для конкретного клиента
        
        Args:
            user_name: имя клиента
            user_surname: фамилия клиента
            user_birthday: дата рождения клиента (формат: 'YYYY-MM-DD')
        
        Returns:
            Словарь со статистикой по забегам клиента
        """
        connection = create_connection()
        if not connection:
            logger.error("Не удалось подключиться к базе данных")
            return {'error': 'Database connection failed'}
        
        try:
            cursor = connection.cursor(buffered=True, dictionary=True)
            
            # Получаем все забеги клиента
            query = f"""
                SELECT 
                    `{self.race_column}` as race_name,
                    `{self.registration_date_column}` as race_date,
                    COUNT(*) as participation_count
                FROM `{self.table_name}`
                WHERE `{self.name_column}` = %s
                  AND `{self.surname_column}` = %s
                  AND DATE(`{self.birthday_column}`) = %s
                GROUP BY `{self.race_column}`, `{self.registration_date_column}`
                ORDER BY `{self.registration_date_column}` DESC
            """
            
            cursor.execute(query, (user_name, user_surname, user_birthday))
            races = cursor.fetchall()
            
            # Общая статистика
            total_races = len(races)
            
            # Статистика по годам
            year_stats = {}
            for race in races:
                race_date = race['race_date']
                if race_date:
                    year = race_date.year if isinstance(race_date, datetime) else datetime.strptime(str(race_date), '%Y-%m-%d').year
                    if year not in year_stats:
                        year_stats[year] = []
                    year_stats[year].append({
                        'race_name': race['race_name'],
                        'race_date': race_date.isoformat() if isinstance(race_date, datetime) else str(race_date)
                    })
            
            year_summary = {year: len(races) for year, races in year_stats.items()}
            
            cursor.close()
            
            return {
                'user_name': user_name,
                'user_surname': user_surname,
                'user_birthday': user_birthday,
                'total_races': total_races,
                'races': [
                    {
                        'race_name': r['race_name'],
                        'race_date': r['race_date'].isoformat() if isinstance(r['race_date'], datetime) else str(r['race_date']),
                        'participation_count': r['participation_count']
                    }
                    for r in races
                ],
                'races_by_year': year_summary,
                'races_detail_by_year': {
                    year: races for year, races in year_stats.items()
                }
            }
            
        except Error as e:
            logger.error(f"Ошибка при выполнении запроса: {e}")
            return {'error': str(e)}
        finally:
            if connection.is_connected():
                connection.close()
    
    def get_race_statistics(self, race_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Получить статистику по конкретному забегу или всем забегам
        
        Args:
            race_name: название забега (если None, то по всем забегам)
        
        Returns:
            Словарь со статистикой по забегу(ам)
        """
        connection = create_connection()
        if not connection:
            logger.error("Не удалось подключиться к базе данных")
            return {'error': 'Database connection failed'}
        
        try:
            cursor = connection.cursor(buffered=True, dictionary=True)
            user_key_expr = self._get_user_key()
            
            if race_name:
                # Статистика по конкретному забегу
                query = f"""
                    SELECT 
                        `{self.race_column}` as race_name,
                        MIN(`{self.registration_date_column}`) as race_date,
                        COUNT(*) as total_registrations,
                        COUNT(DISTINCT {user_key_expr}) as unique_participants
                    FROM `{self.table_name}`
                    WHERE `{self.race_column}` = %s
                    GROUP BY `{self.race_column}`
                """
                cursor.execute(query, (race_name,))
                result = cursor.fetchone()
                
                if result:
                    # Получаем список участников с несколькими регистрациями
                    multiple_reg_query = f"""
                        SELECT 
                            {user_key_expr} as user_key,
                            `{self.name_column}` as name,
                            `{self.surname_column}` as surname,
                            DATE(`{self.birthday_column}`) as birthday,
                            COUNT(*) as registration_count
                        FROM `{self.table_name}`
                        WHERE `{self.race_column}` = %s
                        GROUP BY {user_key_expr}, `{self.name_column}`, `{self.surname_column}`, DATE(`{self.birthday_column}`)
                        HAVING COUNT(*) > 1
                        ORDER BY registration_count DESC
                    """
                    cursor.execute(multiple_reg_query, (race_name,))
                    multiple_registrations = cursor.fetchall()

                    return {
                        'race_name': result['race_name'],
                        'race_date': result['race_date'].isoformat() if isinstance(result['race_date'], datetime) else str(result['race_date']),
                        'total_registrations': result['total_registrations'] or 0,
                        'unique_participants': result['unique_participants'] or 0,
                        'participants_with_multiple_registrations': [
                            {
                                'name': row['name'] or '',
                                'surname': row['surname'] or '',
                                'birthday': str(row['birthday']) if row['birthday'] else None,
                                'registration_count': row['registration_count']
                            }
                            for row in multiple_registrations
                        ]
                    }
                else:
                    return {'error': 'Race not found'}
            else:
                # Статистика по всем забегам
                query = f"""
                    SELECT 
                        `{self.race_column}` as race_name,
                        MIN(`{self.registration_date_column}`) as race_date,
                        COUNT(*) as total_registrations,
                        COUNT(DISTINCT {user_key_expr}) as unique_participants
                    FROM `{self.table_name}`
                    GROUP BY `{self.race_column}`
                    ORDER BY MIN(`{self.registration_date_column}`) DESC
                """
                cursor.execute(query)
                races = cursor.fetchall()
                
                # Получаем участников с несколькими регистрациями по всем забегам
                multiple_reg_query = f"""
                    SELECT 
                        {user_key_expr} as user_key,
                        `{self.name_column}` as name,
                        `{self.surname_column}` as surname,
                        DATE(`{self.birthday_column}`) as birthday,
                        COUNT(*) as total_registrations,
                        GROUP_CONCAT(DISTINCT `{self.race_column}` ORDER BY `{self.race_column}` SEPARATOR ', ') as races
                    FROM `{self.table_name}`
                    WHERE `{self.race_column}` IS NOT NULL 
                      AND `{self.race_column}` != ''
                    GROUP BY {user_key_expr}, `{self.name_column}`, `{self.surname_column}`, DATE(`{self.birthday_column}`)
                    HAVING COUNT(*) > 1
                    ORDER BY total_registrations DESC
                """
                cursor.execute(multiple_reg_query)
                multiple_registrations = cursor.fetchall()
                
                total_races = len(races)
                total_participants = sum(r['unique_participants'] or 0 for r in races)
                total_registrations = sum(r['total_registrations'] or 0 for r in races)
                
                # Статистика по годам
                year_stats = {}
                for race in races:
                    race_date = race['race_date']
                    if race_date:
                        year = race_date.year if isinstance(race_date, datetime) else datetime.strptime(str(race_date), '%Y-%m-%d').year
                        if year not in year_stats:
                            year_stats[year] = {'races_count': 0, 'participants_count': 0, 'registrations_count': 0}
                        year_stats[year]['races_count'] += 1
                        year_stats[year]['participants_count'] += (race['unique_participants'] or 0)
                        year_stats[year]['registrations_count'] += (race['total_registrations'] or 0)
                
                cursor.close()
                
                return {
                    'total_races': total_races,
                    'total_participants': total_participants,
                    'total_registrations': total_registrations,
                    'average_participants_per_race': round(total_participants / total_races, 2) if total_races > 0 else 0,
                    'races': [
                        {
                            'race_name': r['race_name'],
                            'race_date': r['race_date'].isoformat() if isinstance(r['race_date'], datetime) else str(r['race_date']),
                            'total_registrations': r['total_registrations'] or 0,
                            'unique_participants': r['unique_participants'] or 0
                        }
                        for r in races
                    ],
                    'statistics_by_year': year_stats,
                    'participants_with_multiple_registrations': [
                        {
                            'name': row['name'] or '',
                            'surname': row['surname'] or '',
                            'birthday': str(row['birthday']) if row['birthday'] else None,
                            'total_registrations': row['total_registrations'],
                            'races': row['races'] or ''
                        }
                        for row in multiple_registrations
                    ]
                }
            
        except Error as e:
            logger.error(f"Ошибка при выполнении запроса: {e}")
            return {'error': str(e)}
        finally:
            if connection.is_connected():
                connection.close()

    # В методе get_average_races_per_customer в race_statistics.py
    def get_average_races_per_customer(self) -> Dict[str, Any]:
        """
        Получить среднее количество забегов на клиента

        Returns:
            Словарь со статистикой среднего количества забегов
        """
        connection = create_connection()
        if not connection:
            logger.error("Не удалось подключиться к базе данных")
            return {'error': 'Database connection failed'}

        try:
            cursor = connection.cursor(buffered=True, dictionary=True)
            user_key_expr = self._get_user_key()

            # Получаем количество забегов для каждого клиента
            query = f"""
                SELECT 
                    {user_key_expr} as user_key,
                    COUNT(DISTINCT `{self.race_column}`) as races_count
                FROM `{self.table_name}`
                WHERE `{self.race_column}` IS NOT NULL 
                  AND `{self.race_column}` != ''
                  AND `{self.race_column}` != 'NULL'
                GROUP BY {user_key_expr}
                HAVING races_count > 0
            """

            cursor.execute(query)
            results = cursor.fetchall()

            if not results:
                cursor.close()
                return {
                    'average_races': 0.0,
                    'total_customers_with_races': 0,
                    'total_races_count': 0,
                    'min_races': 0,
                    'max_races': 0,
                    'median_races': 0
                }

            races_counts = [r['races_count'] for r in results]
            total_customers = len(races_counts)
            total_races = sum(races_counts)
            average_races = total_races / total_customers if total_customers > 0 else 0

            # Вычисляем медиану
            sorted_counts = sorted(races_counts)
            n = len(sorted_counts)
            if n % 2 == 1:
                median_races = sorted_counts[n // 2]
            else:
                median_races = (sorted_counts[n // 2 - 1] + sorted_counts[n // 2]) / 2

            cursor.close()

            return {
                'average_races': round(average_races, 2),
                'total_customers_with_races': total_customers,
                'total_races_count': total_races,
                'min_races': min(races_counts) if races_counts else 0,
                'max_races': max(races_counts) if races_counts else 0,
                'median_races': round(median_races, 2)
            }

        except Error as e:
            logger.error(f"Ошибка при выполнении запроса: {e}")
            return {
                'average_races': 0.0,
                'error': str(e)
            }
        finally:
            if connection.is_connected():
                connection.close()
    
    def get_yearly_race_statistics(self, year: Optional[int] = None) -> Dict[str, Any]:
        """
        Получить статистику по забегам за год
        
        Args:
            year: год (если None, то текущий год)
        
        Returns:
            Словарь со статистикой за год
        """
        if year is None:
            year = datetime.now().year
        
        connection = create_connection()
        if not connection:
            logger.error("Не удалось подключиться к базе данных")
            return {'error': 'Database connection failed'}
        
        try:
            cursor = connection.cursor(buffered=True, dictionary=True)
            user_key_expr = self._get_user_key()
            
            query = f"""
                SELECT 
                    `{self.race_column}` as race_name,
                    MIN(`{self.registration_date_column}`) as race_date,
                    COUNT(*) as total_registrations,
                    COUNT(DISTINCT {user_key_expr}) as unique_participants
                FROM `{self.table_name}`
                WHERE YEAR(`{self.registration_date_column}`) = %s
                GROUP BY `{self.race_column}`
                ORDER BY MIN(`{self.registration_date_column}`) DESC
            """
            
            cursor.execute(query, (year,))
            races = cursor.fetchall()
            
            total_races = len(races)
            total_participants = sum(r['unique_participants'] or 0 for r in races)
            total_registrations = sum(r['total_registrations'] or 0 for r in races)
            
            cursor.close()
            
            return {
                'year': year,
                'total_races': total_races,
                'total_participants': total_participants,
                'total_registrations': total_registrations,
                'average_participants_per_race': round(total_participants / total_races, 2) if total_races > 0 else 0,
                'races': [
                    {
                        'race_name': r['race_name'],
                        'race_date': r['race_date'].isoformat() if isinstance(r['race_date'], datetime) else str(r['race_date']),
                        'total_registrations': r['total_registrations'] or 0,
                        'unique_participants': r['unique_participants'] or 0
                    }
                    for r in races
                ]
            }
            
        except Error as e:
            logger.error(f"Ошибка при выполнении запроса: {e}")
            return {'error': str(e)}
        finally:
            if connection.is_connected():
                connection.close()
