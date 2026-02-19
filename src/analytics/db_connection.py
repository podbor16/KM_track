import mysql.connector
from mysql.connector import Error
import logging
import os
from typing import Optional, Dict, List, Any
import datetime

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def validate_host_config():
    """
    Проверяет наличие переменных окружения для подключения к БД
    """
    required_vars = ['DB_HOST', 'DB_NAME', 'DB_USER', 'DB_PASSWORD', 'DB_PORT']
    missing_vars = []

    for var in required_vars:
        if not os.getenv(var):
            missing_vars.append(var)

    if missing_vars:
        error_msg = f"Отсутствуют переменные окружения: {', '.join(missing_vars)}"
        logger.warning(error_msg)
        return False
    return True


def check_tables_exist(connection, table_names: List[str]) -> Dict[str, bool]:
    """
    Проверяет наличие таблиц в БД
    """
    result = {}
    if not connection or not connection.is_connected():
        return {table: False for table in table_names}

    try:
        cursor = connection.cursor()
        for table_name in table_names:
            try:
                cursor.execute(f"SELECT 1 FROM `{table_name}` LIMIT 1")
                result[table_name] = True
            except Error:
                result[table_name] = False
        cursor.close()
    except Exception as e:
        logger.error(f"Ошибка при проверке таблиц: {e}")
        result = {table: False for table in table_names}

    return result


def create_connection() -> Optional[mysql.connector.MySQLConnection]:
    """
    Создает подключение к базе данных MySQL используя параметры из settings.py
    """
    from src.config import settings
    
    host = settings.DB_HOST
    database = settings.DB_NAME
    user = settings.DB_USER
    password = settings.DB_PASSWORD
    port = settings.DB_PORT

    if not all([host, database, user, password]):
        error_msg = (
            f"Ошибка: Отсутствуют необходимые параметры БД в settings.py.\n"
            f"Требуемые переменные: DB_HOST, DB_NAME, DB_USER, DB_PASSWORD\n"
            f"Текущие значения:\n"
            f"  - DB_HOST: {host}\n"
            f"  - DB_NAME: {database}\n"
            f"  - DB_USER: {user}\n"
            f"  - DB_PASSWORD: {'***' if password else 'Не установлен'}\n"
            f"  - DB_PORT: {port}"
        )
        logger.error(error_msg)
        print(error_msg)
        return None

    try:
        # Портовое число уже установлено в settings.py как int
        # Создаем строку подключения для логирования (без пароля)
        connection_info = f"host='{host}', database='{database}', user='{user}', port={port}"
        logger.info(f"Подключение с параметрами: {connection_info}")

        # ДОБАВЛЯЕМ buffered=True и другие параметры
        connection = mysql.connector.connect(
            host=host,
            database=database,
            user=user,
            password=password,
            port=port,
            buffered=True,  # ВАЖНО: включаем буферизацию
            autocommit=True,  # Автоматический commit для SELECT запросов
            connection_timeout=10,
            charset='utf8mb4'
        )

        if connection.is_connected():
            logger.info("Успешное подключение к базе данных установлено")

            print(f"Успешное подключение к БД")
            print(f"Хост подключения: {host}")

            return connection

    except ValueError as ve:
        error_msg = f"Ошибка: Неверный формат порта '{port}'. Порт должен быть числом. Ошибка: {ve}"
        logger.error(error_msg)
        print(error_msg)
        return None
    except Error as e:
        error_code = getattr(e, 'errno', 'Неизвестно')
        sql_state = getattr(e, 'sqlstate', 'Неизвестно')

        error_msg = (
            f"Ошибка подключения к MySQL (Код: {error_code}, SQLState: {sql_state}):\n"
            f"  - Сообщение: {str(e)}\n"
            f"  - Параметры подключения: host='{host}', port={port}, database='{database}', user='{user}'\n"
            f"  - Проверьте:\n"
            f"    - Доступность сервера {host}:{port}\n"
            f"    - Правильность учетных данных\n"
            f"    - Наличие доступа к базе данных '{database}' пользователю '{user}'"
        )

        logger.error(error_msg)
        print(error_msg)
        return None
    except Exception as e:
        error_msg = f"Неожиданная ошибка при подключении к базе данных: {str(e)}"
        logger.critical(error_msg)
        print(error_msg)
        return None


def calculate_age_group(birthdate_or_age) -> str:
    """
    Рассчитывает возрастную группу по дате рождения или возрасту
    
    Возрастные группы:
    - <49: до 49 лет
    - 50-59: 50-59 лет
    - 60-64: 60-64 лет
    - 65-69: 65-69 лет
    - 70-74: 70-74 лет
    - >75: 75+ лет
    """
    if not birthdate_or_age:
        return 'Неизвестно'
    
    try:
        age = None
        
        # Если это DATE или DATETIME объект
        if isinstance(birthdate_or_age, (datetime.date, datetime.datetime)):
            birth_year = birthdate_or_age.year
            current_year = datetime.datetime.now().year
            age = current_year - birth_year
        # Если это строка с датой
        elif isinstance(birthdate_or_age, str):
            # Пытаемся распарсить как дату (YYYY-MM-DD)
            try:
                birth_date = datetime.datetime.strptime(birthdate_or_age[:10], '%Y-%m-%d')
                birth_year = birth_date.year
                current_year = datetime.datetime.now().year
                age = current_year - birth_year
            except:
                # Пытаемся распарсить как просто число (возраст)
                try:
                    age = int(birthdate_or_age)
                except:
                    return 'Неизвестно'
        # Если это число (возраст)
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


def get_test_table_data() -> List[Dict[str, Any]]:
    """
    Получает данные участников из БД
    Автоматически ищет таблицу с данными участников
    Если БД недоступна, возвращает тестовые данные
    """
    connection = create_connection()
    
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
                
                # Получаем список всех таблиц в БД
                cursor.execute("SHOW TABLES")
                tables_result = cursor.fetchall()
                # Для dictionary=True, результаты приходят как список словарей
                # Таблица 'SHOW TABLES' возвращает один столбец с именем вроде "Tables_in_<database>"
                existing_tables = []
                if tables_result:
                    if isinstance(tables_result[0], dict):
                        # Если результат словарь, берем первое значение из него
                        key = list(tables_result[0].keys())[0]
                        existing_tables = [table[key] for table in tables_result]
                    else:
                        # Если результат кортеж (старый формат), берем первый элемент
                        existing_tables = [table[0] for table in tables_result]
                
                logger.info(f"📋 Таблицы в БД: {existing_tables}")
                
                # Пытаемся найти подходящую таблицу
                target_table = None
                for possible_table in possible_tables:
                    if possible_table.lower() in [t.lower() for t in existing_tables]:
                        # Находим точное название (с правильным регистром)
                        target_table = next(t for t in existing_tables if t.lower() == possible_table.lower())
                        logger.info(f"✅ Найдена таблица: {target_table}")
                        break
                
                if not target_table:
                    logger.error(f"❌ Таблица не найдена. Доступные таблицы: {existing_tables}")
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
