"""
Модуль для анализа новых пользователей
Работает с таблицей Тестовая, где каждая строка = одна регистрация на забег
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from mysql.connector import Error

from ..db_connection import create_connection

logger = logging.getLogger(__name__)


class NewUsersAnalytics:
    """
    Класс для анализа новых пользователей
    Учитывает, что один email может иметь несколько регистраций (разные люди)
    Уникальность пользователя определяется по комбинации name + surname + birthday
    """
    
    def __init__(self, 
                 table_name: str = 'Тестовая',
                 registration_date_column: str = 'created_at',
                 name_column: str = 'name',
                 surname_column: str = 'surname',
                 email_column: str = 'email',
                 birthday_column: str = 'birthday'):
        """
        Инициализация модуля
        
        Args:
            table_name: название таблицы (по умолчанию 'Тестовая')
            registration_date_column: название колонки с датой регистрации
            name_column: название колонки с именем
            surname_column: название колонки с фамилией
            birthday_column: название колонки с датой рождения
        """
        self.table_name = table_name
        self.registration_date_column = registration_date_column
        self.name_column = name_column
        self.surname_column = surname_column
        self.email_column = email_column
        self.birthday_column = birthday_column
    
    def get_new_users_count(self, 
                           start_date: Optional[datetime] = None,
                           end_date: Optional[datetime] = None) -> Dict[str, Any]:
        """
        Получить количество новых пользователей за период
        Новый пользователь = первая регистрация (email + name + surname)
        
        Args:
            start_date: начальная дата периода (если None, то с начала всех времен)
            end_date: конечная дата периода (если None, то до текущей даты)
        
        Returns:
            Словарь с данными:
            - new_users_count: абсолютное количество новых пользователей
            - total_users: общее количество уникальных пользователей на конец периода
            - percentage: процент новых пользователей от общего числа
        """
        connection = create_connection()
        if not connection:
            logger.error("Не удалось подключиться к базе данных")
            return {
                'new_users_count': 0,
                'total_users': 0,
                'percentage': 0.0,
                'error': 'Database connection failed'
            }
        
        try:
            cursor = connection.cursor(buffered=True)
            
            # Формируем условия для дат
            date_conditions = []
            params = []
            
            if start_date:
                date_conditions.append(f"`{self.registration_date_column}` >= %s")
                params.append(start_date)
            
            if end_date:
                date_conditions.append(f"`{self.registration_date_column}` <= %s")
                params.append(end_date)
            
            where_clause = ""
            if date_conditions:
                where_clause = "WHERE " + " AND ".join(date_conditions)
            
            # Количество новых пользователей за период
            # Новый пользователь = первая регистрация этого человека (email + name + surname)
            new_users_query = f"""
                SELECT COUNT(DISTINCT CONCAT(
                    COALESCE(`{self.email_column}`, ''),
                    '|',
                    COALESCE(`{self.name_column}`, ''),
                    '|',
                    COALESCE(`{self.surname_column}`, '')
                ))
                FROM `{self.table_name}`
                {where_clause}
                AND CONCAT(
                    COALESCE(`{self.email_column}`, ''),
                    '|',
                    COALESCE(`{self.name_column}`, ''),
                    '|',
                    COALESCE(`{self.surname_column}`, '')
                ) IN (
                    SELECT DISTINCT CONCAT(
                        COALESCE(`{self.email_column}`, ''),
                        '|',
                        COALESCE(`{self.name_column}`, ''),
                        '|',
                        COALESCE(`{self.surname_column}`, '')
                    )
                    FROM `{self.table_name}` t2
                    WHERE t2.`{self.registration_date_column}` = (
                        SELECT MIN(t3.`{self.registration_date_column}`)
                        FROM `{self.table_name}` t3
                        WHERE CONCAT(
                            COALESCE(t3.`{self.email_column}`, ''),
                            '|',
                            COALESCE(t3.`{self.name_column}`, ''),
                            '|',
                            COALESCE(t3.`{self.surname_column}`, '')
                        ) = CONCAT(
                            COALESCE(t2.`{self.email_column}`, ''),
                            '|',
                            COALESCE(t2.`{self.name_column}`, ''),
                            '|',
                            COALESCE(t2.`{self.surname_column}`, '')
                        )
                    )
                    {where_clause.replace('WHERE', 'AND') if where_clause else ''}
                )
            """
            
            # Упрощенный вариант: считаем уникальных пользователей, у которых первая регистрация в этом периоде
            new_users_query = f"""
                SELECT COUNT(DISTINCT CONCAT(
                    COALESCE(`{self.email_column}`, ''),
                    '|',
                    COALESCE(`{self.name_column}`, ''),
                    '|',
                    COALESCE(`{self.surname_column}`, '')
                ))
                FROM `{self.table_name}` t1
                {where_clause}
                AND t1.`{self.registration_date_column}` = (
                    SELECT MIN(t2.`{self.registration_date_column}`)
                    FROM `{self.table_name}` t2
                    WHERE CONCAT(
                        COALESCE(t2.`{self.email_column}`, ''),
                        '|',
                        COALESCE(t2.`{self.name_column}`, ''),
                        '|',
                        COALESCE(t2.`{self.surname_column}`, '')
                    ) = CONCAT(
                        COALESCE(t1.`{self.email_column}`, ''),
                        '|',
                        COALESCE(t1.`{self.name_column}`, ''),
                        '|',
                        COALESCE(t1.`{self.surname_column}`, '')
                    )
                )
            """
            
            cursor.execute(new_users_query, params)
            new_users_count = cursor.fetchone()[0] if cursor.rowcount > 0 else 0
            
            # Общее количество уникальных пользователей на конец периода
            end_date_for_total = end_date if end_date else datetime.now()
            total_users_query = f"""
                SELECT COUNT(DISTINCT CONCAT(
                    COALESCE(`{self.email_column}`, ''),
                    '|',
                    COALESCE(`{self.name_column}`, ''),
                    '|',
                    COALESCE(`{self.surname_column}`, '')
                ))
                FROM `{self.table_name}`
                WHERE `{self.registration_date_column}` <= %s
            """
            
            cursor.execute(total_users_query, (end_date_for_total,))
            total_users = cursor.fetchone()[0] if cursor.rowcount > 0 else 0
            
            # Вычисляем процент
            percentage = (new_users_count / total_users * 100) if total_users > 0 else 0.0
            
            cursor.close()
            
            return {
                'new_users_count': new_users_count,
                'total_users': total_users,
                'percentage': round(percentage, 2),
                'start_date': start_date.isoformat() if start_date else None,
                'end_date': end_date.isoformat() if end_date else None
            }
            
        except Error as e:
            logger.error(f"Ошибка при выполнении запроса: {e}")
            return {
                'new_users_count': 0,
                'total_users': 0,
                'percentage': 0.0,
                'error': str(e)
            }
        finally:
            if connection.is_connected():
                connection.close()
    
    def get_new_users_by_period(self, 
                                period: str = 'month',
                                periods_count: int = 12) -> Dict[str, Any]:
        """
        Получить статистику новых пользователей по периодам
        
        Args:
            period: тип периода ('day', 'week', 'month', 'year')
            periods_count: количество периодов для анализа
        
        Returns:
            Словарь с данными по каждому периоду
        """
        connection = create_connection()
        if not connection:
            logger.error("Не удалось подключиться к базе данных")
            return {'periods': [], 'error': 'Database connection failed'}
        
        try:
            cursor = connection.cursor(buffered=True)
            
            # Определяем формат даты для группировки
            date_format_map = {
                'day': '%Y-%m-%d',
                'week': '%Y-%u',
                'month': '%Y-%m',
                'year': '%Y'
            }
            
            date_format = date_format_map.get(period, '%Y-%m')
            
            # Считаем новых пользователей по периодам (первая регистрация)
            query = f"""
                SELECT 
                    DATE_FORMAT(first_reg.period_date, %s) as period,
                    COUNT(DISTINCT first_reg.user_key) as new_users_count
                FROM (
                    SELECT 
                        CONCAT(
                            COALESCE(`{self.email_column}`, ''),
                            '|',
                            COALESCE(`{self.name_column}`, ''),
                            '|',
                            COALESCE(`{self.surname_column}`, '')
                        ) as user_key,
                        MIN(`{self.registration_date_column}`) as period_date
                    FROM `{self.table_name}`
                    WHERE `{self.registration_date_column}` >= DATE_SUB(NOW(), INTERVAL %s {period.upper()})
                    GROUP BY user_key
                ) as first_reg
                GROUP BY period
                ORDER BY period DESC
                LIMIT %s
            """
            
            cursor.execute(query, (date_format, periods_count, periods_count))
            results = cursor.fetchall()
            
            periods_data = []
            for row in results:
                periods_data.append({
                    'period': row[0],
                    'new_users_count': row[1]
                })
            
            cursor.close()
            
            return {
                'period_type': period,
                'periods': periods_data
            }
            
        except Error as e:
            logger.error(f"Ошибка при выполнении запроса: {e}")
            return {'periods': [], 'error': str(e)}
        finally:
            if connection.is_connected():
                connection.close()
