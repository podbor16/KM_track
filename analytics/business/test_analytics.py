"""
Тестовый скрипт для проверки работы модулей бизнес-аналитики
"""
import sys
import os
from datetime import datetime, timedelta

# Добавляем корневую директорию проекта в путь
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from analytics.business import BusinessAnalytics

def test_full_report():
    """Тест полного отчета"""
    print("=" * 60)
    print("ТЕСТ: Полный отчет по бизнес-аналитике")
    print("=" * 60)
    
    try:
        analytics = BusinessAnalytics()
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=90)  # За последние 90 дней
        
        print(f"\nПериод анализа: {start_date.date()} - {end_date.date()}")
        print("Генерация отчета...\n")
        
        report = analytics.get_full_report(
            start_date=start_date,
            end_date=end_date,
            year=datetime.now().year
        )
        
        if 'error' in report:
            print(f"❌ Ошибка: {report['error']}")
            return
        
        # а) Новые пользователи
        print("а) НОВЫЕ ПОЛЬЗОВАТЕЛИ:")
        new_users = report.get('new_users', {})
        if 'error' in new_users:
            print(f"   ❌ Ошибка: {new_users['error']}")
        else:
            print(f"   ✅ Новых пользователей: {new_users.get('new_users_count', 0)}")
            print(f"   ✅ Всего пользователей: {new_users.get('total_users', 0)}")
            print(f"   ✅ Процент новых: {new_users.get('percentage', 0)}%")
            
            # Детальный список новых пользователей
            new_users_list = new_users.get('new_users_list', [])
            if new_users_list:
                print(f"\n   📋 Список новых пользователей ({len(new_users_list)}):")
                for i, user in enumerate(new_users_list[:20], 1):  # Показываем первые 20
                    print(f"      {i}. {user.get('surname', '')} {user.get('name', '')} "
                          f"(Дата рождения: {user.get('birthday', 'Не указана')}, "
                          f"Первая регистрация: {user.get('first_registration', 'Не указана')})")
                if len(new_users_list) > 20:
                    print(f"      ... и еще {len(new_users_list) - 20} пользователей")
        
        # б) Жизненный цикл клиента
        print("\nб) ЖИЗНЕННЫЙ ЦИКЛ КЛИЕНТА:")
        lifecycle = report.get('customer_lifecycle', {})
        if 'error' in lifecycle:
            print(f"   ❌ Ошибка: {lifecycle['error']}")
        else:
            print(f"   ✅ Средний цикл жизни: {lifecycle.get('average_lifecycle_months', 0)} месяцев")
            print(f"   ✅ Активных клиентов: {lifecycle.get('active_customers', 0)}")
            print(f"   ✅ Неактивных клиентов: {lifecycle.get('inactive_customers', 0)}")
            print(f"   ✅ Процент активных: {lifecycle.get('active_percentage', 0)}%")
            
            # Детальная информация о клиентах
            customers = lifecycle.get('customers', [])
            if customers:
                print(f"\n   📋 Детальная информация о клиентах ({len(customers)}):")
                for i, customer in enumerate(customers[:20], 1):  # Показываем первые 20
                    status = "🟢 Активный" if customer.get('is_active') else "🔴 Неактивный"
                    print(f"      {i}. {customer.get('surname', '')} {customer.get('name', '')} "
                          f"(Дата рождения: {customer.get('birthday', 'Не указана')}) - {status}")
                    if customer.get('last_purchase_date'):
                        print(f"         Последняя покупка: {customer.get('last_purchase_date')}")
                    if customer.get('last_purchase_products'):
                        print(f"         Товары: {customer.get('last_purchase_products')}")
                    print(f"         Количество покупок: {customer.get('purchase_count', 0)}")
                if len(customers) > 20:
                    print(f"      ... и еще {len(customers) - 20} клиентов")
        
        # в) Статистика по забегам
        print("\nв) СТАТИСТИКА ПО ЗАБЕГАМ:")
        race_stats = report.get('race_statistics', {})
        if 'error' in race_stats:
            print(f"   ❌ Ошибка: {race_stats['error']}")
        else:
            all_time = race_stats.get('all_time', {})
            print(f"   ✅ Всего забегов: {all_time.get('total_races', 0)}")
            print(f"   ✅ Всего участников: {all_time.get('total_participants', 0)}")
            print(f"   ✅ Всего регистраций: {all_time.get('total_registrations', 0)}")
            
            avg_races = race_stats.get('average_races_per_customer', {})
            print(f"   ✅ Среднее забегов на клиента: {avg_races.get('average_races_per_customer', 0)}")
            
            # Список забегов
            races_list = all_time.get('races', [])
            if races_list:
                print(f"\n   📋 Список забегов ({len(races_list)}):")
                for i, race in enumerate(races_list, 1):
                    print(f"      {i}. {race.get('race_name', 'Не указан')} "
                          f"(Дата: {race.get('race_date', 'Не указана')}, "
                          f"Участников: {race.get('unique_participants', 0)}, "
                          f"Регистраций: {race.get('total_registrations', 0)})")
            
            # Пользователи с несколькими регистрациями
            multiple_reg = all_time.get('participants_with_multiple_registrations', [])
            if multiple_reg:
                print(f"\n   📋 Пользователи с несколькими регистрациями ({len(multiple_reg)}):")
                for i, participant in enumerate(multiple_reg[:20], 1):  # Показываем первые 20
                    print(f"      {i}. {participant.get('surname', '')} {participant.get('name', '')} "
                          f"(Дата рождения: {participant.get('birthday', 'Не указана')}) - "
                          f"{participant.get('total_registrations', 0)} регистраций")
                    if participant.get('races'):
                        print(f"         Забеги: {participant.get('races')}")
                if len(multiple_reg) > 20:
                    print(f"      ... и еще {len(multiple_reg) - 20} пользователей")
        
        # г) Иногородние участники
        print("\nг) ИНОГОРОДНИЕ УЧАСТНИКИ:")
        out_of_town = report.get('out_of_town', {})
        if 'error' in out_of_town:
            print(f"   ❌ Ошибка: {out_of_town['error']}")
        else:
            overall = out_of_town.get('overall', {})
            if 'error' in overall:
                print(f"   ❌ Ошибка: {overall['error']}")
            else:
                print(f"   ✅ Иногородних: {overall.get('out_of_town_count', 0)}")
                print(f"   ✅ Местных: {overall.get('local_count', 0)}")
                print(f"   ✅ Процент иногородних: {overall.get('out_of_town_percentage', 0)}%")
                
                # Список городов по убыванию
                cities_list = overall.get('cities_by_participants', [])
                if cities_list:
                    print(f"\n   📋 Города по количеству участников (по убыванию):")
                    for i, city_info in enumerate(cities_list, 1):
                        city_type = "🏠 Локальный" if city_info.get('is_local') else "✈️ Иногородний"
                        print(f"      {i}. {city_info.get('city', 'Не указан')} - "
                              f"{city_info.get('participants_count', 0)} участников {city_type}")
        
        print("\n" + "=" * 60)
        print("✅ Тест завершен успешно!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ КРИТИЧЕСКАЯ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()


def test_individual_modules():
    """Тест отдельных модулей"""
    print("\n" + "=" * 60)
    print("ТЕСТ: Отдельные модули")
    print("=" * 60)
    
    try:
        analytics = BusinessAnalytics()
        
        # Тест новых пользователей
        print("\n1. Тест новых пользователей...")
        new_users = analytics.get_new_users_report(
            start_date=datetime.now() - timedelta(days=30),
            end_date=datetime.now()
        )
        if 'error' in new_users:
            print(f"   ❌ Ошибка: {new_users['error']}")
        else:
            print(f"   ✅ Новых пользователей: {new_users.get('new_users_count', 0)}")
        
        # Тест жизненного цикла
        print("\n2. Тест жизненного цикла клиентов...")
        lifecycle = analytics.get_customer_lifecycle_report()
        if 'error' in lifecycle:
            print(f"   ❌ Ошибка: {lifecycle['error']}")
        else:
            print(f"   ✅ Всего клиентов: {lifecycle.get('total_customers', 0)}")
            print(f"   ✅ Активных: {lifecycle.get('active_customers', 0)}")
        
        # Тест статистики по забегам
        print("\n3. Тест статистики по забегам...")
        race_stats = analytics.get_race_statistics_report()
        if 'error' in race_stats:
            print(f"   ❌ Ошибка: {race_stats['error']}")
        else:
            avg_races = race_stats.get('average_races_per_customer', {})
            print(f"   ✅ Среднее забегов на клиента: {avg_races.get('average_races_per_customer', 0)}")
        
        # Тест иногородних участников
        print("\n4. Тест иногородних участников...")
        out_of_town = analytics.get_out_of_town_report()
        if 'error' in out_of_town:
            print(f"   ❌ Ошибка: {out_of_town['error']}")
        else:
            print(f"   ✅ Иногородних: {out_of_town.get('out_of_town_count', 0)}")
            print(f"   ✅ Процент: {out_of_town.get('out_of_town_percentage', 0)}%")
        
        print("\n" + "=" * 60)
        print("✅ Все тесты модулей завершены!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ КРИТИЧЕСКАЯ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()


def test_database_connection():
    """Тест подключения к базе данных"""
    print("=" * 60)
    print("ТЕСТ: Подключение к базе данных")
    print("=" * 60)

    try:
        from analytics.db_connection import create_connection

        print("\nПопытка подключения к базе данных...")
        connection = create_connection()

        if not connection:
            print("❌ Не удалось подключиться к базе данных")
            print("   Проверьте настройки в файле .env")
            return False

        print("✅ Подключение установлено успешно!")

        # Создаем обычный курсор (не словарный)
        cursor = connection.cursor(buffered=True)

        # Проверяем наличие таблицы
        cursor.execute("SHOW TABLES LIKE 'Все заявки'")
        result = cursor.fetchone()

        if result:
            print("✅ Таблица 'Все заявки' найдена")

            # Проверяем структуру таблицы
            cursor.execute("DESCRIBE `Все заявки`")
            columns = cursor.fetchall()
            print(f"\nКолонки в таблице ({len(columns)}):")

            for i, col in enumerate(columns[:10], 1):  # Показываем первые 10, начинаем нумерацию с 1
                # col - это кортеж: (Field, Type, Null, Key, Default, Extra)
                field_name = col[0] if len(col) > 0 else 'Неизвестно'
                field_type = col[1] if len(col) > 1 else 'Неизвестно'
                print(f"   {i}. {field_name} ({field_type})")

            if len(columns) > 10:
                print(f"   ... и еще {len(columns) - 10} колонок")

            # Проверяем количество записей
            cursor.execute("SELECT COUNT(*) FROM `Все заявки`")
            count_result = cursor.fetchone()
            count = count_result[0] if count_result else 0
            print(f"\n✅ Количество записей в таблице: {count}")
        else:
            print("❌ Таблица 'Все заявки' не найдена")

        cursor.close()
        connection.close()
        print("\n✅ Тест подключения завершен успешно!")
        return True

    except Exception as e:
        print(f"\n❌ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("ТЕСТИРОВАНИЕ МОДУЛЕЙ БИЗНЕС-АНАЛИТИКИ")
    print("=" * 60)
    
    # Сначала проверяем подключение к БД
    if test_database_connection():
        print("\n")
        # Затем тестируем модули
        test_individual_modules()
        print("\n")
        test_full_report()
    else:
        print("\n❌ Невозможно продолжить тестирование без подключения к БД")
        print("   Убедитесь, что:")
        print("   1. Файл .env существует в корне проекта")
        print("   2. В .env указаны правильные настройки подключения к БД")
        print("   3. База данных доступна и содержит таблицу 'Все заявки'")
