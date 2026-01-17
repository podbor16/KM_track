"""
Пример использования модулей бизнес-аналитики
Работает с таблицей Тестовая
"""
from datetime import datetime, timedelta
from .business_analytics import BusinessAnalytics

# Инициализация модуля бизнес-аналитики
# Все настройки по умолчанию соответствуют таблице Тестовая
analytics = BusinessAnalytics(
    table_name='Тестовая',  # название таблицы
    registration_date_column='created_at',  # дата регистрации
    name_column='name',  # имя
    surname_column='surname',  # фамилия
    birthday_column='birthday',  # дата рождения
    city_column='city',  # город
    race_column='products',  # название забега
    local_city='Красноярск'  # локальный город
)

# Пример 1: Получить полный отчет
print("=" * 50)
print("ПОЛНЫЙ ОТЧЕТ ПО БИЗНЕС-АНАЛИТИКЕ")
print("=" * 50)

end_date = datetime.now()
start_date = end_date - timedelta(days=30)  # За последние 30 дней

full_report = analytics.get_full_report(
    start_date=start_date,
    end_date=end_date,
    year=2024
)

print("\nа) Новые пользователи:")
print(f"  - Новых пользователей: {full_report['new_users']['new_users_count']}")
print(f"  - Всего пользователей: {full_report['new_users']['total_users']}")
print(f"  - Процент новых: {full_report['new_users']['percentage']}%")

print("\nб) Жизненный цикл клиента:")
print(f"  - Средний цикл жизни: {full_report['customer_lifecycle']['average_lifecycle_months']} месяцев")
print(f"  - Активных клиентов: {full_report['customer_lifecycle']['active_customers']}")
print(f"  - Неактивных клиентов: {full_report['customer_lifecycle']['inactive_customers']}")
print(f"  - Процент активных: {full_report['customer_lifecycle']['active_percentage']}%")

print("\nв) Статистика по забегам:")
print(f"  - Всего забегов: {full_report['race_statistics']['all_time']['total_races']}")
print(f"  - Всего участников: {full_report['race_statistics']['all_time']['total_participants']}")
print(f"  - Среднее забегов на клиента: {full_report['race_statistics']['average_races_per_customer']['average_races_per_customer']}")

print("\nг) Иногородние участники:")
print(f"  - Иногородних: {full_report['out_of_town']['overall']['out_of_town_count']}")
print(f"  - Местных: {full_report['out_of_town']['overall']['local_count']}")
print(f"  - Процент иногородних: {full_report['out_of_town']['overall']['out_of_town_percentage']}%")

# Пример 2: Анализ новых пользователей
print("\n" + "=" * 50)
print("АНАЛИЗ НОВЫХ ПОЛЬЗОВАТЕЛЕЙ")
print("=" * 50)

new_users_report = analytics.get_new_users_report(
    start_date=start_date,
    end_date=end_date
)
print(f"Новых пользователей за период: {new_users_report['new_users_count']}")
print(f"Процент от общего числа: {new_users_report['percentage']}%")

# Пример 3: Жизненный цикл конкретного клиента
print("\n" + "=" * 50)
print("ЖИЗНЕННЫЙ ЦИКЛ КЛИЕНТА")
print("=" * 50)

# Для конкретного клиента
# customer_lifecycle = analytics.get_customer_lifecycle_report(
#     user_name='Иван',
#     user_surname='Иванов',
#     user_birthday='1990-01-15'
# )
# print(f"Цикл жизни клиента: {customer_lifecycle['average_lifecycle_months']} месяцев")

# Для всех клиентов
all_customers_lifecycle = analytics.get_customer_lifecycle_report()
print(f"Средний цикл жизни: {all_customers_lifecycle['average_lifecycle_months']} месяцев")
print(f"Активных: {all_customers_lifecycle['active_customers']}")
print(f"Неактивных: {all_customers_lifecycle['inactive_customers']}")

# Пример 4: Статистика по забегам
print("\n" + "=" * 50)
print("СТАТИСТИКА ПО ЗАБЕГАМ")
print("=" * 50)

race_stats = analytics.get_race_statistics_report(year=2024)
print(f"Среднее количество забегов на клиента: {race_stats['average_races_per_customer']['average_races_per_customer']}")

# Статистика по конкретному забегу
# race_info = analytics.get_race_statistics_report(race_name='Ночной забег')
# print(f"Участников в забеге: {race_info['race_statistics']['unique_participants']}")

# Статистика для конкретного клиента
# customer_races = analytics.get_race_statistics_report(
#     user_name='Иван',
#     user_surname='Иванов',
#     user_birthday='1990-01-15'
# )
# print(f"Клиент участвовал в {customer_races['customer_statistics']['total_races']} забегах")

# Пример 5: Иногородние участники
print("\n" + "=" * 50)
print("ИНОГОРОДНИЕ УЧАСТНИКИ")
print("=" * 50)

out_of_town = analytics.get_out_of_town_report()
print(f"Иногородних участников: {out_of_town['out_of_town_count']}")
print(f"Процент иногородних: {out_of_town['out_of_town_percentage']}%")

# По конкретному забегу
# race_out_of_town = analytics.get_out_of_town_report(race_name='Ночной забег')
# print(f"Иногородних в забеге: {race_out_of_town['out_of_town_count']}")
