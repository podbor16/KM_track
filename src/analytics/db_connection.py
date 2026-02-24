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


def search_clients(search_query: str) -> List[Dict[str, Any]]:
    """
    Поиск спортсменов в таблице 'clients' по фамилии и имени
    
    Args:
        search_query: Поисковая строка (фамилия или имя)
    
    Returns:
        Список найденных спортсменов с полями: surname, name, birth_year
    """
    connection = create_connection()
    
    if not connection:
        logger.error("❌ Не удалось установить соединение с БД")
        return []
    
    try:
        cursor = connection.cursor(dictionary=True, buffered=True)
        
        # Варианты названий таблицы clients
        possible_tables = [
            "clients",
            "Клиенты",
            "спортсмены",
            "athletes",
            "participants"
        ]
        
        # Получаем список всех таблиц в БД
        cursor.execute("SHOW TABLES")
        tables_result = cursor.fetchall()
        
        existing_tables = []
        if tables_result:
            if isinstance(tables_result[0], dict):
                key = list(tables_result[0].keys())[0]
                existing_tables = [table[key] for table in tables_result]
            else:
                existing_tables = [table[0] for table in tables_result]
        
        logger.info(f"📋 Таблицы в БД: {existing_tables}")
        
        # Пытаемся найти подходящую таблицу
        target_table = None
        for possible_table in possible_tables:
            if possible_table.lower() in [t.lower() for t in existing_tables]:
                target_table = next(t for t in existing_tables if t.lower() == possible_table.lower())
                logger.info(f"✅ Найдена таблица: {target_table}")
                break
        
        if not target_table:
            logger.error(f"❌ Таблица not found. Доступные таблицы: {existing_tables}")
            return []
        
        # Получаем список столбцов таблицы
        cursor.execute(f"DESCRIBE `{target_table}`")
        columns_result = cursor.fetchall()
        
        available_columns = []
        if columns_result:
            if isinstance(columns_result[0], dict):
                available_columns = [col['Field'] for col in columns_result]
            else:
                available_columns = [col[0] for col in columns_result]
        
        logger.info(f"📋 Столбцы в таблице '{target_table}': {available_columns}")
        
        # Определяем какие поля существуют
        surname_field = None
        name_field = None
        birthday_field = None
        
        # Ищем поле фамилии
        for field in ['surname', 'Фамилия', 'last_name', 'lastname']:
            if field.lower() in [col.lower() for col in available_columns]:
                surname_field = next(col for col in available_columns if col.lower() == field.lower())
                break
        
        # Ищем поле имени
        for field in ['name', 'Имя', 'first_name', 'firstname']:
            if field.lower() in [col.lower() for col in available_columns]:
                name_field = next(col for col in available_columns if col.lower() == field.lower())
                break
        
        # Ищем поле даты рождения
        for field in ['birthday', 'Дата рождения', 'birthdate', 'birth_date', 'date_of_birth']:
            if field.lower() in [col.lower() for col in available_columns]:
                birthday_field = next(col for col in available_columns if col.lower() == field.lower())
                break
        
        # Если требуемые поля не найдены, выбираем первые 3 доступные
        if not all([surname_field, name_field, birthday_field]):
            logger.warning(f"⚠️ Не все поля найдены. surname={surname_field}, name={name_field}, birthday={birthday_field}")
            if not surname_field and available_columns:
                surname_field = available_columns[0]
            if not name_field and len(available_columns) > 1:
                name_field = available_columns[1]
            if not birthday_field and len(available_columns) > 2:
                birthday_field = available_columns[2]
        
        # Выполняем поиск
        search_term = f"%{search_query}%"
        
        if surname_field and name_field and birthday_field:
            query = f"""
            SELECT `{surname_field}` as surname, `{name_field}` as name, `{birthday_field}` as birthday 
            FROM `{target_table}`
            WHERE `{surname_field}` LIKE %s OR `{name_field}` LIKE %s
            LIMIT 20
            """
        else:
            # Если не можем определить поля, берем все и фильтруем на стороне Python
            query = f"SELECT * FROM `{target_table}` LIMIT 100"
        
        if surname_field and name_field and birthday_field:
            cursor.execute(query, (search_term, search_term))
        else:
            cursor.execute(query)
        
        records = cursor.fetchall()
        
        # Если не получилось определить поля, фильтруем результаты на стороне Python
        if not (surname_field and name_field and birthday_field):
            filtered_records = []
            for record in records:
                if isinstance(record, dict):
                    record_str = str(record).lower()
                else:
                    record_str = str(record).lower()
                
                if search_query.lower() in record_str:
                    filtered_records.append(record)
            
            records = filtered_records[:20]
        
        # Извлекаем год рождения из даты рождения
        for record in records:
            if isinstance(record, dict):
                birthday = record.get('birthday')
                if birthday:
                    # Если это datetime объект
                    if hasattr(birthday, 'year'):
                        record['birth_year'] = str(birthday.year)
                    # Если это строка
                    elif isinstance(birthday, str):
                        try:
                            year = birthday.split('-')[0] if '-' in birthday else birthday[:4]
                            record['birth_year'] = year
                        except:
                            record['birth_year'] = 'Неизвестно'
                    else:
                        record['birth_year'] = 'Неизвестно'
                else:
                    record['birth_year'] = 'Неизвестно'
                # Убираем поле birthday
                record.pop('birthday', None)
        
        logger.info(f"✅ Найдено {len(records)} соответствий для запроса '{search_query}'")
        
        return records
        
    except Error as e:
        logger.error(f"❌ Ошибка при поиске в таблице: {e}")
        return []
    finally:
        cursor.close()
        if connection.is_connected():
            connection.close()


def get_athlete_results(surname: str, name: str) -> tuple:
    """
    Получить информацию о спортсмене и его все результаты из таблицы results
    
    Args:
        surname: Фамилия спортсмена
        name: Имя спортсмена
    
    Returns:
        Кортеж (информация о спортсмене, список его результатов)
    """
    logger.info(f"🔍 Поиск спортсмена: {surname} {name}")
    
    connection = create_connection()
    
    if not connection:
        logger.error("❌ Не удалось установить соединение с БД")
        return {}, []
    
    try:
        cursor = connection.cursor(dictionary=True, buffered=True)
        
        # Получаем список таблиц в БД
        try:
            cursor.execute("SHOW TABLES")
            tables_result = cursor.fetchall()
            
            existing_tables = []
            if tables_result:
                if isinstance(tables_result[0], dict):
                    key = list(tables_result[0].keys())[0]
                    existing_tables = [table[key] for table in tables_result]
                else:
                    existing_tables = [table[0] for table in tables_result]
            
            logger.info(f"📋 Таблицы в БД: {existing_tables}")
        except Exception as e:
            logger.error(f"⚠️ Не удалось получить список таблиц: {e}")
            existing_tables = []
        
        # Пытаемся найти таблицу results
        results_table = None
        possible_results_tables = ["results", "Results", "RESULTS", "гонка", "забеги"]
        
        for possible_table in possible_results_tables:
            if possible_table.lower() in [t.lower() for t in existing_tables]:
                results_table = next(t for t in existing_tables if t.lower() == possible_table.lower())
                logger.info(f"✅ Найдена таблица результатов: {results_table}")
                break
        
        if not results_table:
            logger.error(f"❌ Таблица results не найдена. Доступные таблицы: {existing_tables}")
            return {}, []
        
        # Получаем информацию о колонках в таблице results
        try:
            cursor.execute(f"DESCRIBE `{results_table}`")
            columns_info = cursor.fetchall()
            available_columns = [col['Field'] for col in columns_info]
            logger.info(f"📄 Колонки в таблице {results_table}: {available_columns}")
        except Exception as e:
            logger.error(f"⚠️ Не удалось получить описание таблицы: {e}")
            available_columns = []
        
        # Ищем поля фамилии и имени
        surname_field = None
        name_field = None
        
        for field in ['surname', 'Фамилия', 'last_name', 'lastname']:
            if field.lower() in [col.lower() for col in available_columns]:
                surname_field = next(col for col in available_columns if col.lower() == field.lower())
                logger.info(f"✅ Найдено поле фамилии: {surname_field}")
                break
        
        for field in ['name', 'Имя', 'first_name', 'firstname']:
            if field.lower() in [col.lower() for col in available_columns]:
                name_field = next(col for col in available_columns if col.lower() == field.lower())
                logger.info(f"✅ Найдено поле имени: {name_field}")
                break
        
        if not surname_field or not name_field:
            logger.error(f"❌ Не удалось найти поля фамилии и имени. surname_field={surname_field}, name_field={name_field}")
            return {}, []
        
        # Получаем всю информацию о спортсмене
        athlete_info = {}
        try:
            query = f"SELECT * FROM `{results_table}` WHERE `{surname_field}` = %s AND `{name_field}` = %s LIMIT 1"
            logger.info(f"📝 Запрос: {query} | Параметры: ({surname}, {name})")
            cursor.execute(query, (surname, name))
            athlete_data = cursor.fetchone()
            
            if athlete_data:
                athlete_info = dict(athlete_data)
                logger.info(f"✅ Данные спортсмена найдены")
            else:
                logger.warning(f"⚠️ Спортсмен не найден в таблице {results_table}")
        except Exception as e:
            logger.error(f"❌ Ошибка при запросе информации спортсмена: {e}")
            return {}, []
        
        # Получаем все результаты спортсмена
        results_list = []
        try:
            # Проверяем есть ли поле gunTime для сортировки
            has_gunTime = 'gunTime' in [col.lower() for col in available_columns]
            
            if has_gunTime:
                query = f"SELECT * FROM `{results_table}` WHERE `{surname_field}` = %s AND `{name_field}` = %s ORDER BY gunTime DESC"
            else:
                query = f"SELECT * FROM `{results_table}` WHERE `{surname_field}` = %s AND `{name_field}` = %s"
            
            logger.info(f"📝 Запрос результатов: {query} | Параметры: ({surname}, {name})")
            cursor.execute(query, (surname, name))
            results = cursor.fetchall()
            
            # Преобразуем datetime объекты в строки для JSON сериализации
            for result in results:
                result_dict = dict(result)
                results_list.append(result_dict)
            
            logger.info(f"✅ Найдено {len(results_list)} результатов для {surname} {name}")
        except Exception as e:
            logger.error(f"❌ Ошибка при запросе результатов: {e}")
        
        return athlete_info, results_list
        
    except Exception as e:
        logger.error(f"❌ Ошибка при получении результатов спортсмена: {e}", exc_info=True)
        return {}, []
    finally:
        try:
            cursor.close()
        except:
            pass
        if connection and connection.is_connected():
            connection.close()
