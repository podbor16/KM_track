# Скрипт загрузки результатов гонки (load_race_results.py)

## Описание

Скрипт `load_race_results.py` загружает данные хронометража из `race_data.json` в таблицы `results` и `result_segments` MySQL базы данных.

Основные функции:
- 📊 **Загрузка результатов** участников из системы хронометража Copernico
- ⏱️ **Вычисление темпов** (дистанция / чистое время)
- 🏆 **Сохранение рангов** (абсолютный, по полу, по категориям)
- 📈 **Анализ сегментов** маршрута (от КТ до КТ)
- 🔄 **Непрерывное обновление** в реальном времени во время гонки
- ✏️ **Автоматическое обновление** измененных данных в race_data.json (v2.1+)

## ✨ НОВОЕ: Поддержка обновлений (v2.1)

**Что изменилось?** Теперь скрипт **автоматически обновляет** данные в БД, если вы измените значения в race_data.json:

- Если вы измените **status** на "finished" → обновится в БД
- Если вы исправите **фамилию** участника → обновится в БД  
- Если вы измените **категорию** → обновится в БД

Это работает благодаря `INSERT ... ON DUPLICATE KEY UPDATE` - технике, которая:
1. **INSERT** новые записи (если их нет в БД)
2. **UPDATE** существующие записи (если они уже в БД)
3. Все в **ОДНОЙ операции**

Детальный гайд: смотрите [UPDATE_GUIDE.md](UPDATE_GUIDE.md)

---

## Структура данных

### Таблица `results`
Основная информация о результате участника:

| Поле | Тип | Описание |
|------|-----|---------|
| `id` | BIGINT | Уникальный ID |
| `surname` | VARCHAR | Фамилия участника |
| `name` | VARCHAR | Имя участника |
| `birthday` | DATE | Дата рождения |
| `client_id` | INT | Ссылка на таблицу `clients` |
| `event_id` | INT | Ссылка на таблицу `events` |
| `sex` | VARCHAR | Пол (Male/Female/Unknown) |
| `start_number` | VARCHAR | Номер участника (dorsal) |
| `category` | VARCHAR | Возрастная категория |
| `race_status` | VARCHAR | Статус (Not started, Running, Finished, DNF, DSQ, Withdrawn) |
| `time_gun_start` | TIME | Время старта (gun time) |
| `time_clear_start` | TIME | Чистое время старта |
| `time_gun_finish` | TIME | Время финиша (gun time) |
| `time_clear_finish` | TIME | **Чистое время финиша** (используется для рангов) |
| `rank_absolute` | INT | Место в общем зачете |
| `rank_sex` | INT | Место среди своего пола |
| `rank_category` | INT | Место в своей категории |
| `finish_pace_avg` | VARCHAR | Средний темп на финише (мм:сс мин/км) |
| `time_clear_kt1` ... `time_clear_kt5` | TIME | Чистые времена контрольных точек |
| `pace_avg_kt1` ... `pace_avg_kt5` | VARCHAR | Темпы на контрольных точках |

### Таблица `result_segments`
Результаты по отдельным сегментам маршрута:

| Поле | Тип | Описание |
|------|-----|---------|
| `id` | BIGINT | Уникальный ID |
| `result_id` | BIGINT | Ссылка на результат |
| `segment_code` | VARCHAR | Код сегмента (start-kt1, kt1-kt2, и т.д.) |
| `sg_time_clear` | TIME | Чистое время прохождения сегмента |
| `sg_pace_avg` | VARCHAR | Темп на сегменте (мм:сс мин/км) |
| `sg_rank_absolute` | INT | Ранг на этом сегменте |
| `sg_rank_sex` | INT | Ранг по полу на сегменте |
| `sg_rank_category` | INT | Ранг по категории на сегменте |

#### Возможные коды сегментов:
```
start-kt1, start-kt2, start-kt3, start-kt4, start-kt5
kt1-kt2, kt1-kt3, kt1-kt4, kt1-kt5, kt1-finish
kt2-kt3, kt2-kt4, kt2-kt5, kt2-finish
kt3-kt4, kt3-kt5, kt3-finish
kt4-kt5, kt4-finish
kt5-finish
```

---

## Установка и настройка

### 1. Убедитесь, что таблицы созданы

✅ **Хорошая новость:** таблицы `results`, `result_segments`, `events` и `clients` **уже существуют** в БД!

Структура полностью готова:
- **results** - 28 колонок (все временные метки, ранги, темпы)
- **result_segments** - 8 колонок (сегменты маршрута)  
- **events** - 7 колонок (события с JSON polем checkpoint_distances)
- **clients** - база спортсменов для связи с результатами

### 2. Убедитесь, что таблица `events` имеет событие

Добавьте событие (если еще нет):

```sql
INSERT INTO events (event_name, event_distance, event_year, event_date, num_checkpoints, checkpoint_distances)
VALUES (
    '7 km',
    '7 km',
    2025,
    '2025-12-07',
    1,
    JSON_ARRAY(0, 3.5, 7.0)
);
```

Для события с одной КТ (разворотом):
```sql
INSERT INTO events (event_name, checkpoint_distances)
VALUES ('5 km', JSON_ARRAY(0, 2.5, 5.0));
```

### 3. Убедитесь, что таблица `clients` заполнена

Таблица должна содержать базу всех участников с их личными данными:
- `surname` - фамилия
- `name` - имя
- `birthday` - дата рождения (YYYY-MM-DD)

Скрипт будет пытаться связать данные из `race_data.json` с записями в `clients` по ФИ и дате рождения.

---

## Использование

### ⚠️ ОБЯЗАТЕЛЬНЫЙ параметр: --event-id

**Перед запуском скрипта ВСЕГДА указывайте ID события из таблицы `events`:**

```bash
# Узнать ID своего события
SELECT id, event_name FROM events;
```

**Примеры для события с ID 1:**

### Базовый запуск (одноразовая загрузка)

```bash
python load_race_results.py --event-id 1
```

**Что происходит:**
1. Проверяет событие с ID 1 в таблице `events`
2. Получает информацию о контрольных точках из JSON поля
3. Читает `tracker/race_data.json`
4. Для каждого участника:
   - Получает/создает запись в `results`
   - Вычисляет все временные метки
   - Вычисляет темпы
   - Вставляет/обновляет сегменты в `result_segments`
5. Выводит статус: сколько успешно загружено, сколько ошибок

### Непрерывная загрузка (для живого обновления во время гонки)

```bash
python load_race_results.py --event-id 1 --continuous
```

**Параметры:**
- `--interval N` - интервал обновления в секундах (default: 10)

**Примеры:**

```bash
# Обновление каждые 10 секунд (по умолчанию)
python load_race_results.py --event-id 1 --continuous

# Обновление каждые 5 секунд
python load_race_results.py --event-id 1 --continuous --interval 5

# Обновление каждые 30 секунд
python load_race_results.py --event-id 1 --continuous --interval 30
```

**Как остановить:**
- Нажмите `Ctrl+C` в терминале

---

## Логирование

Скрипт выводит подробные логи с информацией о:
- ✅ Успешно загруженных результатах
- ⚠️ Предупреждениях и пропущенных участниках
- ❌ Ошибках и их причинах
- 📊 Статистике загрузки

Пример вывода:
```
2026-03-24 14:30:45,123 - __main__ - INFO - 🏃 Загрузка результатов события '7 km' (ID: 1)
2026-03-24 14:30:45,124 - __main__ - INFO - 📌 Контрольные точки: [0, 3.5, 7.0]
2026-03-24 14:30:46,234 - __main__ - INFO - ✅ Создан результат (ID: 1) для Иванов Иван (dorsal: 212)
2026-03-24 14:30:47,345 - __main__ - INFO - ✅ Загрузка завершена. Успешно: 150, Ошибок: 2
```

---

## Примеры использования в день забега

### Сценарий 1: Развертывание в день гонки

```bash
# За час до старта: проверить один раз (для события ID 1)
python load_race_results.py --event-id 1

# За 10 минут до старта: запустить непрерывное обновление
python load_race_results.py --event-id 1 --continuous --interval 5

# Скрипт будет обновлять данные каждые 5 секунд
# Оставить работать до конца гонки
# Нажать Ctrl+C когда гонка закончена
```

### Сценарий 2: Использование в background (Linux/Mac)

```bash
# Запустить в фоне с редиректом логов (для события ID 1)
nohup python load_race_results.py --event-id 1 --continuous --interval 5 > logs/race_results.log 2>&1 &

# Потом просмотреть логи в реальном времени
tail -f logs/race_results.log
```

### Сценарий 3: Использование с cron (периодическое обновление)

```bash
# Отредактировать crontab
crontab -e

# Добавить строку для обновления каждые 2 минуты (для события ID 1)
*/2 * * * * cd /path/to/KM_track && python load_race_results.py --event-id 1 >> logs/cron_results.log 2>&1
```

---

## Обработка ошибок

### Ошибка: "Событие 'X km' не найдено в БД"

**Причина:** Название события в `race_data.json` не совпадает с названием в таблице `events`.

**Решение:**
1. Проверьте значение поля `event` в `race_data.json`
2. Добавьте это событие в таблицу `events`:
   ```sql
   INSERT INTO events (event_name, checkpoint_distances)
   VALUES ('X km', JSON_ARRAY(0, 2.5, 5.0));
   ```

### Ошибка: "Спортсмен X не найден в БД clients"

**Причина:** Участник из `race_data.json` не найден в таблице `clients`.

**Решение:** 
- Без записи в `clients` скрипт все равно создаст результат, но `client_id` будет NULL
- Если нужна связь с личным кабинетом, добавьте участника в `clients`:
  ```sql
  INSERT INTO clients (surname, name, birthday, sex)
  VALUES ('Иванов', 'Иван', '1990-01-15', 'Male');
  ```

### Ошибка: "Не удалось подключиться к БД"

**Причина:** Неверные параметры подключения в `.env`.

**Решение:**
1. Проверьте файл `.env`:
   ```
   DB_HOST=79.174.89.159
   DB_USER=km_analytic
   DB_PASSWORD=CneZbvlOS2H-BLsQ
   DB_NAME=krasmarafon
   DB_PORT=16171
   ```
2. Если параметры неверны, обновите их

---

## Формулы расчёта

### Темп (мм:сс мин/км)
```
Темп = (Время в секундах на дистанцию) / (Дистанция в км)
Пример: для дистанции 7 км с временем 00:35:00
Темп = (35*60) / 7 = 300 / 7 ≈ 42.86 сек/км ≈ 00:42 мин/км
```

### Ранги
Ранги берутся из API `race_data.json`:
- `rankings_:::full-1:::` - ранг в общем зачете
- `rankings.gen_:::full-1:::` - ранг по полу
- `rankings.cat_:::full-1:::` - ранг по категории

Для каждой КТ:
- `rankings_ktN` 
- `rankings.gen_ktN`
- `rankings.cat_ktN`

### Время на сегменте
```
Время сегмента = time_clear_to - time_clear_from
Пример: от КТ1 до КТ2
  Время сегмента = time_clear_kt2 - time_clear_kt1
```

---

## Производительность

Скрипт оптимизирован для:
- ✅ Кэширование событий и клиентов (нет повторных запросов)
- ✅ Пакетная обработка всех участников через один запрос
- ✅ Использование UNIQUE KEY для избежания дублей
- ✅ Индексы на часто используемые поля

### Примерное время обработки:
- 100 участников: ~500ms
- 1000 участников: ~3-5 сек
- 10000 участников: ~30-50 сек

---

## Проверка результатов

После загрузки выполните эти запросы для проверки:

```sql
-- Количество загруженных результатов
SELECT COUNT(*) FROM results WHERE event_id = 1;

-- Топ-10 финишеров
SELECT surname, name, start_number, time_clear_finish, finish_pace_avg, rank_absolute
FROM results 
WHERE event_id = 1 AND race_status = 'Finished'
ORDER BY rank_absolute 
LIMIT 10;

-- Статистика по полам
SELECT sex, COUNT(*) as count, AVG(CAST(time_clear_finish as UNSIGNED)) as avg_time
FROM results
WHERE event_id = 1 AND race_status = 'Finished'
GROUP BY sex;

-- Сегменты для конкретного участника
SELECT segment_code, sg_time_clear, sg_pace_avg, sg_rank_absolute
FROM result_segments
WHERE result_id = 1
ORDER BY segment_code;
```

---

## Возможные расширения

1. **Экспорт в Excel** - создать скрипт для выгрузки результатов в Excel/CSV
2. **API для получения результатов** - добавить REST API для получения результатов
3. **Сравнение результатов** - анализ производительности по КТ
4. **Прогнозирование** - прогноз финишного времени на основе текущего прогресса
5. **Интеграция с веб-сайтом** - живой трансляция результатов

