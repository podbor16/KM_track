import mysql.connector
from mysql.connector import Error
from dotenv import load_dotenv
import os
import socket
import logging
from typing import Optional, List, Dict, Any

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Загружаем переменные из .env файла
load_dotenv()


def validate_host_config(expected_host: str) -> bool:
    """
    Проверяет соответствие ожидаемого хоста из .env с реальным хостом подключения
    """
    try:
        # Получаем IP-адрес из доменного имени
        resolved_ip = socket.gethostbyname(expected_host)

        # Сравниваем с ожидаемым хостом (если это IP)
        if expected_host.replace('.', '').isdigit():
            return expected_host == resolved_ip
        else:
            return True
    except socket.gaierror:
        logger.error(f"Невозможно разрешить хост: {expected_host}")
        return False


def check_tables_exist(connection, table_names: List[str] = None) -> dict:
    """
    Проверяет наличие указанных таблиц в базе данных
    """
    # СОЗДАЕМ КУРСОР С buffered=True - ЭТО ВАЖНО!
    cursor = connection.cursor(buffered=True)
    results = {}

    try:
        if table_names is None:
            cursor.execute("SHOW TABLES")
            tables = [table[0] for table in cursor.fetchall()]
        else:
            tables = table_names

        for table in tables:
            try:
                # ВАЖНО: читаем результат запроса
                cursor.execute(f"SELECT 1 FROM `{table}` LIMIT 1")
                cursor.fetchone()  # Читаем результат, даже если не используем
                results[table] = True
            except Error as e:
                logger.warning(f"Таблица '{table}' не существует или недоступна: {e}")
                results[table] = False

    except Error as e:
        logger.error(f"Ошибка при проверке таблиц: {e}")
        results = {}
    finally:
        cursor.close()

    return results


def create_connection():
    """
    Создает подключение к базе данных с расширенной диагностикой
    """
    # Проверяем наличие всех необходимых переменных окружения
    host = os.getenv('DB_HOST')
    database = os.getenv('DB_NAME')
    user = os.getenv('DB_USER')
    password = os.getenv('DB_PASSWORD')
    port = os.getenv('DB_PORT')

    if not all([host, database, user, password, port]):
        error_msg = (
            f"Ошибка: Отсутствуют обязательные переменные окружения для подключения к БД.\n"
            f"Проверьте наличие следующих переменных: DB_HOST={host is not None}, "
            f"DB_NAME={database is not None}, DB_USER={user is not None}, "
            f"DB_PASSWORD={password is not None}, DB_PORT={port is not None}"
        )
        logger.error(error_msg)
        print(error_msg)
        return None

    # Логируем попытку подключения
    logger.info(f"Попытка подключения к базе данных: {host}:{port}, БД: {database}, Пользователь: {user}")

    # Проверяем соответствие хоста
    if not validate_host_config(host):
        error_msg = f"Ошибка: Невозможно разрешить хост {host}. Проверьте правильность настройки."
        logger.error(error_msg)
        print(error_msg)
        return None

    try:
        # Преобразуем порт в целое число
        port = int(port)

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

            # ИСПРАВЛЯЕМ: используем свойства вместо deprecated методов
            db_info = connection.server_info
            logger.info(f"Версия MySQL сервера: {db_info}")

            host_info = connection.server_host
            logger.info(f"Подключен к серверу: {host_info}, версия: {db_info}")

            print(f"Успешное подключение к БД")
            print(f"Версия MySQL сервера: {db_info}")
            print(f"Фактический хост подключения: {host_info}")

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


# Улучшенная версия main блока с обработкой курсоров
if __name__ == "__main__":
    connection = create_connection()

    if connection:
        try:
            # СОЗДАЕМ КУРСОР С buffered=True
            cursor = connection.cursor(buffered=True)

            try:
                # Выполняем универсальный запрос для получения информации о структуре БД
                cursor.execute("SHOW TABLES")
                tables = [table[0] for table in cursor.fetchall()]  # Читаем ВСЕ результаты

                print(f"\nНайдено таблиц в базе данных: {len(tables)}")
                print("Список таблиц в базе данных:")
                for table in tables:
                    print(f"  - {table}")

                # Проверяем наличие таблиц перед выполнением запросов
                if tables:
                    # Проверяем доступность таблиц
                    table_status = check_tables_exist(connection, tables[:5])

                    print("\nСтатус доступности таблиц:")
                    for table, exists in table_status.items():
                        status = "Доступна" if exists else "Недоступна"
                        print(f"  - {table}: {status}")

                    # Пробуем получить данные из первой доступной таблицы
                    available_tables = [table for table, exists in table_status.items() if exists]
                    if available_tables:
                        first_table = available_tables[0]

                        # ВАЖНО: используем отдельный курсор для нового запроса
                        cursor2 = connection.cursor(buffered=True)
                        try:
                            cursor2.execute(f"SELECT * FROM `{first_table}` LIMIT 5")
                            records = cursor2.fetchall()  # Читаем ВСЕ результаты

                            print(f"\nПервые 5 записей из таблицы '{first_table}':")
                            for record in records:
                                print(f"  {record}")
                        finally:
                            cursor2.close()
                    else:
                        print("\nНет доступных таблиц для чтения.")
                else:
                    print("\nБаза данных пуста - нет таблиц для отображения.")

            except Error as e:
                error_code = getattr(e, 'errno', 'Неизвестно')
                error_msg = f"Ошибка выполнения SQL запроса (Код: {error_code}): {e}"
                logger.error(error_msg)
                print(f"\n{error_msg}")

            finally:
                cursor.close()  # Теперь ошибки не будет

        finally:
            if connection.is_connected():
                connection.close()
                logger.info("Соединение с базой данных закрыто")
                print("\nСоединение закрыто")
    else:
        logger.error("Не удалось установить соединение с базой данных")
        print("\nНе удалось установить соединение с базой данных")