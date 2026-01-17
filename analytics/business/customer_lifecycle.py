"""
Модуль для анализа жизненного цикла клиента
Работает с таблицей Тестовая, где каждая строка = одна регистрация на забег
Регистрация = покупка (created_at)
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from mysql.connector import Error

from ..db_connection import create_connection

logger = logging.getLogger(__name__)


class CustomerLifecycleAnalytics:
    """
    Класс для анализа жизненного цикла клиента
    Лаг покупки - 13 месяцев (если у клиента нет покупок более 13 месяцев, 
    то считаем что его «жизнь» закончена)
    """
    
    def __init__(self,
                 table_name: str = 'Тестовая',
                 registration_date_column: str = 'created_at',
                 name_column: str = 'name',
                 surname_column: str = 'surname',
                 birthday_column: str = 'birthday',
                 products_column: str = 'products'):
        """
        Инициализация модуля
        
        Args:
            table_name: название таблицы (по умолчанию 'Тестовая')
            registration_date_column: название колонки с датой регистрации (покупки)
            name_column: название колонки с именем
            surname_column: название колонки с фамилией
            birthday_column: название колонки с датой рождения
            products_column: название колонки с товарами/забегами
        """
        self.table_name = table_name
        self.registration_date_column = registration_date_column
        self.name_column = name_column
        self.surname_column = surname_column
        self.birthday_column = birthday_column
        self.products_column = products_column
        self.purchase_lag_months = 13
    
    def _get_user_key(self) -> str:
        """Возвращает выражение для уникального ключа пользователя"""
        return f"""CONCAT(
            COALESCE(`{self.name_column}`, ''),
            '|',
            COALESCE(`{self.surname_column}`, ''),
            '|',
            COALESCE(DATE(`{self.birthday_column}`), '')
        )"""
    
    def calculate_customer_lifecycle(self, 
                                     user_name: Optional[str] = None,
                                     user_surname: Optional[str] = None,
                                     user_birthday: Optional[str] = None) -> Dict[str, Any]:
        """
        Рассчитать жизненный цикл клиента(ов)
        
        Args:
            user_name: имя конкретного клиента (если None, то для всех)
            user_surname: фамилия конкретного клиента
            user_birthday: дата рождения конкретного клиента (формат: 'YYYY-MM-DD')
        
        Returns:
            Словарь с данными о жизненном цикле
        """
        connection = create_connection()
        if not connection:
            logger.error("Не удалось подключиться к базе данных")
            return {'error': 'Database connection failed'}
        
        try:
            cursor = connection.cursor(buffered=True, dictionary=True)
            
            user_key_expr = self._get_user_key()
            
            # Получаем данные о регистрациях (покупках) клиентов
            if user_name and user_surname and user_birthday:
                # Для конкретного клиента
                query = f"""
                    SELECT 
                        {user_key_expr} as user_key,
                        MIN(`{self.registration_date_column}`) as first_purchase,
                        MAX(`{self.registration_date_column}`) as last_purchase,
                        COUNT(*) as purchase_count
                    FROM `{self.table_name}`
                    WHERE `{self.name_column}` = %s
                      AND `{self.surname_column}` = %s
                      AND DATE(`{self.birthday_column}`) = %s
                    GROUP BY {user_key_expr}
                """
                cursor.execute(query, (user_name, user_surname, user_birthday))
            else:
                # Для всех клиентов
                query = f"""
                    SELECT 
                        {user_key_expr} as user_key,
                        MIN(`{self.registration_date_column}`) as first_purchase,
                        MAX(`{self.registration_date_column}`) as last_purchase,
                        COUNT(*) as purchase_count
                    FROM `{self.table_name}`
                    GROUP BY {user_key_expr}
                """
                cursor.execute(query)
            
            results = cursor.fetchall()
            
            # Получаем детальную информацию о последних покупках
            customers_detail = []
            for row in results:
                user_key = row['user_key']
                parts = user_key.split('|')
                name = parts[0] if len(parts) > 0 else ''
                surname = parts[1] if len(parts) > 1 else ''
                birthday = parts[2] if len(parts) > 2 else ''
                
                # Получаем последнюю покупку с товарами
                last_purchase_query = f"""
                    SELECT 
                        `{self.registration_date_column}` as purchase_date,
                        `{self.products_column}` as products
                    FROM `{self.table_name}`
                    WHERE CONCAT(
                        COALESCE(`{self.name_column}`, ''),
                        '|',
                        COALESCE(`{self.surname_column}`, ''),
                        '|',
                        COALESCE(DATE(`{self.birthday_column}`), '')
                    ) = %s
                    ORDER BY `{self.registration_date_column}` DESC
                    LIMIT 1
                """
                cursor.execute(last_purchase_query, (user_key,))
                last_purchase_detail = cursor.fetchone()
                
                customers_detail.append({
                    'user_key': user_key,
                    'name': name,
                    'surname': surname,
                    'birthday': birthday,
                    'last_purchase_date': last_purchase_detail['purchase_date'].isoformat() if last_purchase_detail and last_purchase_detail['purchase_date'] else None,
                    'last_purchase_products': last_purchase_detail['products'] if last_purchase_detail else None
                })
            
            if not results:
                cursor.close()
                return {
                    'average_lifecycle_days': 0,
                    'average_lifecycle_months': 0,
                    'active_customers': 0,
                    'inactive_customers': 0,
                    'total_customers': 0,
                    'customers': []
                }
            
            # Обрабатываем данные
            now = datetime.now()
            lag_threshold = timedelta(days=self.purchase_lag_months * 30)  # Приблизительно 13 месяцев
            
            lifecycles = []
            active_count = 0
            inactive_count = 0
            
            for row in results:
                first_purchase = row['first_purchase']
                last_purchase = row['last_purchase']
                
                if not first_purchase:
                    # Клиент без регистраций
                    lifecycle_days = 0
                    is_active = False
                else:
                    if last_purchase:
                        # Есть последняя регистрация
                        lifecycle_days = (last_purchase - first_purchase).days
                        time_since_last = now - last_purchase
                        is_active = time_since_last <= lag_threshold
                    else:
                        # Только первая регистрация
                        lifecycle_days = (now - first_purchase).days
                        is_active = True
                
                lifecycle_months = lifecycle_days / 30.0
                
                # Извлекаем name, surname, birthday из user_key
                user_key = row['user_key']
                parts = user_key.split('|')
                name = parts[0] if len(parts) > 0 else ''
                surname = parts[1] if len(parts) > 1 else ''
                birthday = parts[2] if len(parts) > 2 else ''
                
                # Находим детальную информацию о последней покупке
                customer_detail = next((cd for cd in customers_detail if cd['user_key'] == user_key), None)
                
                lifecycles.append({
                    'user_key': user_key,
                    'name': name,
                    'surname': surname,
                    'birthday': birthday,
                    'first_purchase': first_purchase.isoformat() if first_purchase else None,
                    'last_purchase': last_purchase.isoformat() if last_purchase else None,
                    'last_purchase_date': customer_detail['last_purchase_date'] if customer_detail else None,
                    'last_purchase_products': customer_detail['last_purchase_products'] if customer_detail else None,
                    'lifecycle_days': lifecycle_days,
                    'lifecycle_months': round(lifecycle_months, 2),
                    'is_active': is_active,
                    'purchase_count': row['purchase_count'] or 0
                })
                
                if is_active:
                    active_count += 1
                else:
                    inactive_count += 1
            
            # Вычисляем средний жизненный цикл
            valid_lifecycles = [l['lifecycle_days'] for l in lifecycles if l['lifecycle_days'] > 0]
            avg_lifecycle_days = sum(valid_lifecycles) / len(valid_lifecycles) if valid_lifecycles else 0
            avg_lifecycle_months = avg_lifecycle_days / 30.0
            
            return {
                'average_lifecycle_days': round(avg_lifecycle_days, 2),
                'average_lifecycle_months': round(avg_lifecycle_months, 2),
                'active_customers': active_count,
                'inactive_customers': inactive_count,
                'total_customers': len(results),
                'active_percentage': round((active_count / len(results) * 100), 2) if results else 0,
                'inactive_percentage': round((inactive_count / len(results) * 100), 2) if results else 0,
                'customers': lifecycles  # Детали для всех клиентов
            }
            
            cursor.close()
            
        except Error as e:
            logger.error(f"Ошибка при выполнении запроса: {e}")
            return {'error': str(e)}
        finally:
            if connection.is_connected():
                connection.close()
    
    def get_customer_status_flags(self) -> Dict[str, Any]:
        """
        Получить флаги состояния всех клиентов (активный/неактивный)
        
        Returns:
            Словарь с флагами состояния клиентов
        """
        connection = create_connection()
        if not connection:
            logger.error("Не удалось подключиться к базе данных")
            return {'error': 'Database connection failed'}
        
        try:
            cursor = connection.cursor(buffered=True, dictionary=True)
            
            user_key_expr = self._get_user_key()
            
            # Получаем последнюю регистрацию каждого клиента
            query = f"""
                SELECT 
                    {user_key_expr} as user_key,
                    MAX(`{self.registration_date_column}`) as last_purchase
                FROM `{self.table_name}`
                GROUP BY {user_key_expr}
            """
            
            cursor.execute(query)
            results = cursor.fetchall()
            cursor.close()
            
            now = datetime.now()
            lag_threshold = timedelta(days=self.purchase_lag_months * 30)
            
            status_flags = []
            active_count = 0
            inactive_count = 0
            
            for row in results:
                last_purchase = row['last_purchase']
                
                if not last_purchase:
                    # Клиент без регистраций - считаем неактивным
                    is_active = False
                else:
                    time_since_last = now - last_purchase
                    is_active = time_since_last <= lag_threshold
                
                # Извлекаем name, surname, birthday из user_key
                user_key = row['user_key']
                parts = user_key.split('|')
                name = parts[0] if len(parts) > 0 else ''
                surname = parts[1] if len(parts) > 1 else ''
                birthday = parts[2] if len(parts) > 2 else ''
                
                status_flags.append({
                    'user_key': user_key,
                    'name': name,
                    'surname': surname,
                    'birthday': birthday,
                    'is_active': is_active,
                    'status': 'active' if is_active else 'inactive',
                    'last_purchase': last_purchase.isoformat() if last_purchase else None,
                    'months_since_last_purchase': round((now - last_purchase).days / 30.0, 2) if last_purchase else None
                })
                
                if is_active:
                    active_count += 1
                else:
                    inactive_count += 1
            
            return {
                'total_customers': len(results),
                'active_customers': active_count,
                'inactive_customers': inactive_count,
                'active_percentage': round((active_count / len(results) * 100), 2) if results else 0,
                'inactive_percentage': round((inactive_count / len(results) * 100), 2) if results else 0,
                'status_flags': status_flags
            }
            
        except Error as e:
            logger.error(f"Ошибка при выполнении запроса: {e}")
            return {'error': str(e)}
        finally:
            if connection.is_connected():
                connection.close()
