# Модуль бизнес-аналитики

Модуль для бизнес-аналитики проекта КМ, включающий анализ новых пользователей, жизненного цикла клиентов, статистики по забегам и иногородних участников.

## Структура базы данных

**База данных:** `krasmarafon_users`  
**Таблица:** `Тестовая`

**Колонки:**
- `surname` - фамилия
- `name` - имя
- `sex` - пол
- `city` - город
- `club` - клуб
- `email` - email
- `birthday` - дата рождения
- `run_time` - время забега
- `phone` - телефон
- `phone2` - дополнительный телефон
- `promocode` - промокод
- `discount` - скидка
- `amount` - сумма
- `products` - название забега (используется для определения забега)
- `file` - файл
- `created_at` - дата регистрации

## Важные особенности

1. **Одна таблица для всего:** Все данные хранятся в одной таблице `Тестовая`
2. **Одна строка = одна регистрация:** Каждая строка представляет одну регистрацию на один забег
3. **Множественные регистрации:** Один пользователь может регистрироваться на несколько забегов (несколько строк с одинаковыми персональными данными)
4. **Один email - несколько людей:** На один email может быть зарегистрировано несколько разных людей (семья/друзья)
5. **Уникальность пользователя:** Определяется по комбинации `name + surname + birthday`

## Структура модуля

- `new_users_analytics.py` - анализ новых пользователей
- `customer_lifecycle.py` - анализ жизненного цикла клиента
- `race_statistics.py` - статистика по забегам
- `out_of_town_analytics.py` - анализ иногородних участников
- `business_analytics.py` - главный модуль, объединяющий все функции
- `example_usage.py` - примеры использования

## Требования

- Python 3.7+
- mysql-connector-python
- python-dotenv

## Настройка

Перед использованием убедитесь, что в корне проекта есть файл `.env` с настройками подключения к базе данных:

```
DB_HOST=your_host
DB_NAME=krasmarafon_users
DB_USER=your_user
DB_PASSWORD=your_password
DB_PORT=your_port
```

## Использование

### Базовое использование

```python
from analytics.business import BusinessAnalytics
from datetime import datetime, timedelta

# Инициализация (с настройками по умолчанию для таблицы Тестовая)
analytics = BusinessAnalytics()

# Получить полный отчет
end_date = datetime.now()
start_date = end_date - timedelta(days=30)

full_report = analytics.get_full_report(
    start_date=start_date,
    end_date=end_date,
    year=2024
)
```

## Функциональность

### а) Новые пользователи

Получение количества новых пользователей (абсолютное и в %):

```python
from analytics.business import NewUsersAnalytics

new_users = NewUsersAnalytics()

# За период
report = new_users.get_new_users_count(
    start_date=datetime(2024, 1, 1),
    end_date=datetime(2024, 12, 31)
)

print(f"Новых пользователей: {report['new_users_count']}")
print(f"Процент от общего числа: {report['percentage']}%")

# По периодам
periods = new_users.get_new_users_by_period(period='month', periods_count=12)
```

**Примечание:** Новый пользователь определяется как первая регистрация уникальной комбинации `name + surname + birthday`.

### б) Жизненный цикл клиента

Анализ жизненного цикла клиента с лагом покупки 13 месяцев:

```python
from analytics.business import CustomerLifecycleAnalytics

lifecycle = CustomerLifecycleAnalytics()

# Для всех клиентов
report = lifecycle.calculate_customer_lifecycle()
print(f"Средний цикл жизни: {report['average_lifecycle_months']} месяцев")
print(f"Активных: {report['active_customers']}")
print(f"Неактивных: {report['inactive_customers']}")

# Для конкретного клиента
customer_report = lifecycle.calculate_customer_lifecycle(
    user_name='Иван',
    user_surname='Иванов',
    user_birthday='1990-01-15'
)

# Получить флаги состояния
status_flags = lifecycle.get_customer_status_flags()
```

**Логика активности:**
- Клиент считается **активным**, если последняя регистрация была менее 13 месяцев назад
- Клиент считается **неактивным**, если последней регистрации нет или она была более 13 месяцев назад
- Регистрация на забег = покупка (используется `created_at`)

### в) Статистика по забегам

```python
from analytics.business import RaceStatisticsAnalytics

race_stats = RaceStatisticsAnalytics()

# Статистика для конкретного клиента
customer_stats = race_stats.get_customer_race_statistics(
    user_name='Иван',
    user_surname='Иванов',
    user_birthday='1990-01-15'
)
print(f"Всего забегов: {customer_stats['total_races']}")

# Статистика по конкретному забегу
race_info = race_stats.get_race_statistics(race_name='Ночной забег')

# Статистика по всем забегам
all_races = race_stats.get_race_statistics()

# Статистика за год
yearly = race_stats.get_yearly_race_statistics(year=2024)

# Среднее количество забегов на клиента
avg_races = race_stats.get_average_races_per_customer()
print(f"Среднее забегов на клиента: {avg_races['average_races_per_customer']}")
```

**Примечание:** Забег определяется по полю `products` (название забега).

### г) Иногородние участники

```python
from analytics.business import OutOfTownAnalytics

out_of_town = OutOfTownAnalytics(local_city='Красноярск')

# Общая статистика
stats = out_of_town.get_out_of_town_statistics()
print(f"Иногородних: {stats['out_of_town_count']}")
print(f"Процент иногородних: {stats['out_of_town_percentage']}%")

# По конкретному забегу
race_stats = out_of_town.get_out_of_town_statistics(race_name='Ночной забег')

# По каждому забегу
by_race = out_of_town.get_out_of_town_by_race()
```

## Настройка названий колонок

Если названия колонок в вашей таблице отличаются от стандартных, вы можете настроить их при инициализации:

```python
analytics = BusinessAnalytics(
    table_name='Тестовая',
    registration_date_column='created_at',
    name_column='name',
    surname_column='surname',
    birthday_column='birthday',
    city_column='city',
    race_column='products',  # колонка с названием забега
    local_city='Красноярск'
)
```

## Примеры вывода

### Полный отчет

```python
{
    'generated_at': '2024-01-15T10:30:00',
    'new_users': {
        'new_users_count': 150,
        'total_users': 1000,
        'percentage': 15.0
    },
    'customer_lifecycle': {
        'average_lifecycle_months': 8.5,
        'active_customers': 750,
        'inactive_customers': 250,
        'active_percentage': 75.0,
        'inactive_percentage': 25.0
    },
    'race_statistics': {
        'all_time': {
            'total_races': 50,
            'total_participants': 5000,
            'total_registrations': 5200,
            'average_participants_per_race': 100.0
        },
        'average_races_per_customer': {
            'average_races_per_customer': 2.5
        }
    },
    'out_of_town': {
        'overall': {
            'out_of_town_count': 300,
            'local_count': 700,
            'total_participants': 1000,
            'out_of_town_percentage': 30.0,
            'local_percentage': 70.0
        }
    }
}
```

## Обработка ошибок

Все методы возвращают словарь с результатами. В случае ошибки в словаре будет ключ `error`:

```python
result = analytics.get_new_users_report()
if 'error' in result:
    print(f"Ошибка: {result['error']}")
```

## Логирование

Модуль использует стандартный модуль logging Python. Для включения логирования:

```python
import logging
logging.basicConfig(level=logging.INFO)
```

## Тестирование

Для тестирования модулей используйте тестовый скрипт:

```bash
python analytics/business/test_analytics.py
```

Скрипт выполнит:
1. Проверку подключения к базе данных
2. Тестирование отдельных модулей
3. Генерацию полного отчета

**Важно:** Перед запуском убедитесь, что:
- Файл `.env` существует в корне проекта
- В `.env` указаны правильные настройки подключения к БД:
  ```
  DB_HOST=your_host
  DB_NAME=krasmarafon_users
  DB_USER=your_user
  DB_PASSWORD=your_password
  DB_PORT=your_port
  ```
- База данных доступна и содержит таблицу `Тестовая`

### Запуск из Python

Если вы хотите запустить тесты из Python кода:

```python
# Из корневой директории проекта
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from analytics.business import BusinessAnalytics
from datetime import datetime, timedelta

analytics = BusinessAnalytics()
report = analytics.get_full_report(
    start_date=datetime.now() - timedelta(days=30),
    end_date=datetime.now()
)
print(report)
```

## Важные замечания

1. **Уникальность пользователя:** Определяется по комбинации `name + surname + birthday`. Это позволяет точно идентифицировать каждого человека, даже если на один email зарегистрировано несколько разных людей.

2. **Регистрация = покупка:** В контексте жизненного цикла клиента регистрация на забег считается покупкой. Используется дата `created_at`.

3. **Определение забега:** Забег определяется по полю `products`. Убедитесь, что в этом поле хранится название забега.

4. **Кириллица в названии таблицы:** Таблица называется `Тестовая` (с кириллицей), поэтому в запросах используются обратные кавычки.
