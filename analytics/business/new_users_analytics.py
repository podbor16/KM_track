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

    def _get_user_key_expr(self) -> str:
        """
        Возвращает выражение для уникального ключа пользователя
        Упрощенная версия без преобразования дат
        """
        return f"""
        CONCAT(
            COALESCE(`{self.name_column}`, ''),
            '|',
            COALESCE(`{self.surname_column}`, ''),
            '|',
            COALESCE(`{self.birthday_column}`, '')
        )
        """

    def _format_date_for_display(self, dt: Optional[datetime]) -> Optional[str]:
        """Форматирует дату для отображения"""
        if dt is None:
            return None
        return dt.strftime('%Y-%m-%d')

    def get_new_users_count(self,
                           start_date: Optional[datetime] = None,
                           end_date: Optional[datetime] = None) -> Dict[str, Any]:
        """
        Получить количество новых пользователей за период
        Новый пользователь = первая регистрация пользователя

        Args:
            start_date: начальная дата периода (если None, то с начала всех времен)
            end_date: конечная дата периода (если None, то до текущей даты)

        Returns:
            Словарь с данными
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
            cursor = connection.cursor(buffered=True, dictionary=True)

            # 1. Находим первые регистрации для каждого пользователя
            user_key_expr = self._get_user_key_expr()

            # Базовый запрос для нахождения первых регистраций
            base_query = f"""
            SELECT 
                {user_key_expr} as user_key,
                MIN(`{self.registration_date_column}`) as first_registration_date
            FROM `{self.table_name}`
            WHERE `{self.name_column}` IS NOT NULL 
              AND `{self.name_column}` != ''
              AND `{self.name_column}` != 'None'
              AND `{self.surname_column}` IS NOT NULL 
              AND `{self.surname_column}` != ''
              AND `{self.surname_column}` != 'None'
            GROUP BY {user_key_expr}
            """

            # 2. Считаем новых пользователей в периоде
            new_users_query = f"""
            WITH first_registrations AS (
                {base_query}
            )
            SELECT COUNT(*) as new_users_count
            FROM first_registrations
            WHERE 1=1
            """

            params = []

            if start_date:
                new_users_query += " AND first_registration_date >= %s"
                params.append(start_date)

            if end_date:
                new_users_query += " AND first_registration_date <= %s"
                params.append(end_date)

            logger.info(f"Выполняется запрос для новых пользователей")
            cursor.execute(new_users_query, params)
            new_users_result = cursor.fetchone()
            new_users_count = new_users_result['new_users_count'] if new_users_result else 0

            # 3. Считаем общее количество уникальных пользователей
            total_users_query = f"""
            SELECT COUNT(DISTINCT {user_key_expr}) as total_users
            FROM `{self.table_name}`
            WHERE `{self.name_column}` IS NOT NULL 
              AND `{self.name_column}` != ''
              AND `{self.name_column}` != 'None'
              AND `{self.surname_column}` IS NOT NULL 
              AND `{self.surname_column}` != ''
              AND `{self.surname_column}` != 'None'
            """

            cursor.execute(total_users_query)
            total_users_result = cursor.fetchone()
            total_users = total_users_result['total_users'] if total_users_result else 0

            # 4. Для расчета процента используем пользователей на конец периода
            total_users_in_period_query = f"""
            SELECT COUNT(DISTINCT {user_key_expr}) as total_users_in_period
            FROM `{self.table_name}`
            WHERE `{self.name_column}` IS NOT NULL 
              AND `{self.name_column}` != ''
              AND `{self.name_column}` != 'None'
              AND `{self.surname_column}` IS NOT NULL 
              AND `{self.surname_column}` != ''
              AND `{self.surname_column}` != 'None'
            """

            period_params = []
            if end_date:
                total_users_in_period_query += f" AND `{self.registration_date_column}` <= %s"
                period_params.append(end_date)

            cursor.execute(total_users_in_period_query, period_params)
            total_users_in_period_result = cursor.fetchone()
            total_users_in_period = total_users_in_period_result['total_users_in_period'] if total_users_in_period_result else 0

            # 5. Расчет процента
            percentage = 0.0
            if total_users_in_period > 0:
                percentage = (new_users_count / total_users_in_period) * 100

            cursor.close()
            connection.close()

            return {
                'new_users_count': new_users_count,
                'total_users': total_users_in_period,
                'total_all_time_users': total_users,
                'percentage': round(percentage, 2),
                'start_date': self._format_date_for_display(start_date),
                'end_date': self._format_date_for_display(end_date),
                'calculation_method': 'Уникальность определяется по name + surname + birthday',
                'filters_applied': {
                    'name_not_null': True,
                    'surname_not_null': True,
                    'exclude_none_strings': True
                }
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
            cursor = connection.cursor(buffered=True, dictionary=True)
            user_key_expr = self._get_user_key_expr()

            # Определяем формат даты для группировки
            date_format_map = {
                'day': '%Y-%m-%d',
                'week': '%Y-%u',
                'month': '%Y-%m',
                'year': '%Y'
            }

            date_format = date_format_map.get(period, '%Y-%m')

            # Находим первые регистрации и группируем по периодам
            query = f"""
            WITH first_registrations AS (
                SELECT 
                    {user_key_expr} as user_key,
                    MIN(`{self.registration_date_column}`) as first_registration_date
                FROM `{self.table_name}`
                WHERE `{self.name_column}` IS NOT NULL 
                  AND `{self.name_column}` != ''
                  AND `{self.name_column}` != 'None'
                  AND `{self.surname_column}` IS NOT NULL 
                  AND `{self.surname_column}` != ''
                  AND `{self.surname_column}` != 'None'
                GROUP BY {user_key_expr}
            )
            SELECT 
                DATE_FORMAT(first_registration_date, %s) as period,
                COUNT(*) as new_users_count
            FROM first_registrations
            WHERE first_registration_date IS NOT NULL
            GROUP BY DATE_FORMAT(first_registration_date, %s)
            ORDER BY period DESC
            LIMIT %s
            """

            cursor.execute(query, (date_format, date_format, periods_count))
            results = cursor.fetchall()

            periods_data = []
            for row in results:
                periods_data.append({
                    'period': row['period'],
                    'new_users_count': row['new_users_count']
                })

            cursor.close()
            connection.close()

            return {
                'period_type': period,
                'periods_count': periods_count,
                'total_new_users': sum(item['new_users_count'] for item in periods_data),
                'periods': periods_data
            }

        except Error as e:
            logger.error(f"Ошибка при выполнении запроса: {e}")
            return {'periods': [], 'error': str(e)}
        finally:
            if connection.is_connected():
                connection.close()