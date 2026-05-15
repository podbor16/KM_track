# Вкладка «Подготовка стартовых» — DataLens Implementation Plan

> **Важно:** Это пошаговая инструкция по настройке в интерфейсе DataLens. Нет кода в репозитории — только клики в UI DataLens.

**Goal:** Создать вкладку «Подготовка стартовых» в существующем дашборде DataLens с 5 проверками регистраций (10 виджетов: 5 индикаторов + 5 QL-таблиц).

**Architecture:** Один датасет `ds_leads_checks` на таблице `leads`. Два Selector-виджета (`event_name`, `event_year`) связаны со всеми 10 QL-чартами. Каждый чарт — отдельный QL-чарт с параметрами `{{event_name}}` и `{{event_year}}`.

**Tech Stack:** Yandex DataLens — QL Charts (тип «Индикатор» и «Таблица»), Selectors, Dashboard Tabs.

**Спек:** `docs/superpowers/specs/2026-05-15-start-list-prep-design.md`

---

## Задача 1: Датасет `ds_leads_checks`

*Датасет нужен только как «точка входа» для подключения — QL-чарты используют raw SQL напрямую, но им нужно выбрать датасет при создании.*

- [ ] **Шаг 1: Открыть DataLens → Коллекции**

Перейти в DataLens. Открыть папку проекта KM Track (или создать подпапку `Стартовые проверки`).

- [ ] **Шаг 2: Создать датасет**

Нажать «Создать» → «Датасет».  
Выбрать существующее подключение к MySQL КМ-трек.  
В разделе «Источники» выбрать таблицу `leads`.  
Нажать «Сохранить», назвать: `ds_leads_checks`.

- [ ] **Шаг 3: Убедиться что датасет работает**

На вкладке «Предпросмотр» должны отображаться строки таблицы `leads` (id, surname, name, email, birthday и т.д.).  
Если ошибка подключения — проверить, что MySQL-подключение активно в разделе «Подключения».

---

## Задача 2: Новая вкладка в дашборде

- [ ] **Шаг 1: Открыть существующий дашборд**

Перейти в существующий дашборд DataLens (тот где уже есть другие вкладки — Результаты, Трекер и т.д.).

- [ ] **Шаг 2: Добавить вкладку**

Нажать «Редактировать» (карандаш).  
В панели вкладок снизу нажать «+» → «Добавить вкладку».  
Назвать вкладку: **Подготовка стартовых**.

- [ ] **Шаг 3: Сохранить**

Нажать «Сохранить». Убедиться что вкладка появилась в панели и открывается пустой канвас.

---

## Задача 3: Селекторы

*Оба селектора создаются на вкладке «Подготовка стартовых» и затем будут привязаны ко всем QL-чартам.*

- [ ] **Шаг 1: Добавить селектор «Событие»**

На канвасе вкладки нажать «Добавить» → «Селектор».  
Настройки:
- Датасет: `ds_leads_checks`
- Поле: `event_name`
- Тип операции: равно (=)
- Множественный выбор: **выкл**
- Заголовок: `Событие`
- Значение по умолчанию: оставить пустым (DataLens подставит первое значение)

Нажать «Добавить». Разместить в верхней левой части канваса (ширина ~300px, высота ~60px).

- [ ] **Шаг 2: Добавить селектор «Год»**

«Добавить» → «Селектор».  
Настройки:
- Датасет: `ds_leads_checks`
- Поле: `event_year`
- Тип операции: равно (=)
- Множественный выбор: **выкл**
- Заголовок: `Год`
- Значение по умолчанию: оставить пустым

Разместить правее первого селектора (ширина ~200px, высота ~60px).

- [ ] **Шаг 3: Сохранить черновик**

Нажать «Сохранить». Убедиться что оба селектора видны на вкладке.

---

## Задача 4: Чарт ① — Льготные категории (Индикатор)

- [ ] **Шаг 1: Создать QL-чарт типа «Индикатор»**

В DataLens: «Создать» → «Чарт» → «QL-чарт».  
Выбрать датасет: `ds_leads_checks`.  
Тип визуализации: **Индикатор**.

- [ ] **Шаг 2: Вставить SQL**

```sql
SELECT COUNT(*) AS `Льготные категории`
FROM leads l
WHERE l.event_name = {{event_name}}
  AND l.event_year = {{event_year}}
  AND (
      (l.products LIKE '%Дети%' AND ({{event_year}} - YEAR(l.birthday)) >= 18)
      OR (l.products LIKE '%Пенсионер%' AND l.sex = 'М' AND ({{event_year}} - YEAR(l.birthday)) < 60)
      OR (l.products LIKE '%Пенсионер%' AND l.sex = 'Ж' AND ({{event_year}} - YEAR(l.birthday)) < 55)
      OR (l.products LIKE '%18-22%' AND ({{event_year}} - YEAR(l.birthday)) NOT BETWEEN 18 AND 22)
  )
```

- [ ] **Шаг 3: Настроить параметры QL-чарта**

В разделе «Параметры» добавить два параметра:
- `event_name` — тип: строка, значение по умолчанию: `Ночной забег`
- `event_year` — тип: целое число, значение по умолчанию: `2025`

Нажать «Запустить» — должно появиться число.

- [ ] **Шаг 4: Сохранить чарт**

Нажать «Сохранить», назвать: `① Льготные — индикатор`.

---

## Задача 5: Чарт ① — Льготные категории (Таблица)

- [ ] **Шаг 1: Создать QL-чарт типа «Таблица»**

«Создать» → «Чарт» → «QL-чарт».  
Датасет: `ds_leads_checks`.  
Тип визуализации: **Таблица**.

- [ ] **Шаг 2: Вставить SQL**

```sql
SELECT
    l.id AS `ID`,
    CONCAT(l.surname, ' ', l.name) AS `Фамилия Имя`,
    l.email AS `Email`,
    l.sex AS `Пол`,
    YEAR(l.birthday) AS `Г.р.`,
    ({{event_year}} - YEAR(l.birthday)) AS `Возраст`,
    l.event_distance AS `Дистанция`,
    TRIM(SUBSTRING_INDEX(SUBSTRING_INDEX(l.products, 'Выберите категорию:', -1), ';', 1)) AS `Категория в заявке`,
    CASE
        WHEN l.products LIKE '%Дети%' AND ({{event_year}} - YEAR(l.birthday)) >= 18
            THEN 'Возраст ≥ 18'
        WHEN l.products LIKE '%Пенсионер%' AND l.sex = 'М' AND ({{event_year}} - YEAR(l.birthday)) < 60
            THEN 'М < 60 лет'
        WHEN l.products LIKE '%Пенсионер%' AND l.sex = 'Ж' AND ({{event_year}} - YEAR(l.birthday)) < 55
            THEN 'Ж < 55 лет'
        WHEN l.products LIKE '%18-22%' AND ({{event_year}} - YEAR(l.birthday)) NOT BETWEEN 18 AND 22
            THEN 'Возраст не 18-22'
    END AS `Несоответствие`
FROM leads l
WHERE l.event_name = {{event_name}}
  AND l.event_year = {{event_year}}
  AND (
      (l.products LIKE '%Дети%' AND ({{event_year}} - YEAR(l.birthday)) >= 18)
      OR (l.products LIKE '%Пенсионер%' AND l.sex = 'М' AND ({{event_year}} - YEAR(l.birthday)) < 60)
      OR (l.products LIKE '%Пенсионер%' AND l.sex = 'Ж' AND ({{event_year}} - YEAR(l.birthday)) < 55)
      OR (l.products LIKE '%18-22%' AND ({{event_year}} - YEAR(l.birthday)) NOT BETWEEN 18 AND 22)
  )
ORDER BY l.surname, l.name
```

- [ ] **Шаг 3: Добавить параметры**

Параметры (те же что в индикаторе):
- `event_name` — строка, дефолт: `Ночной забег`
- `event_year` — целое число, дефолт: `2025`

Нажать «Запустить» — должна появиться таблица с несоответствиями.

- [ ] **Шаг 4: Настроить условное форматирование колонки «Несоответствие»**

На вкладке «Разметка таблицы» (или «Цвета») — выбрать колонку `Несоответствие`.  
Добавить правило: если значение не пустое → цвет текста `#ff6b6b` (красный).

- [ ] **Шаг 5: Сохранить чарт**

Назвать: `① Льготные — таблица`.

---

## Задача 6: Чарты ② — Именные промокоды

- [ ] **Шаг 1: Создать индикатор**

«Создать» → «Чарт» → «QL-чарт» → тип «Индикатор».  
Датасет: `ds_leads_checks`.

SQL:
```sql
SELECT COUNT(*) AS `Промокоды *99`
FROM leads l
WHERE l.event_name = {{event_name}}
  AND l.event_year = {{event_year}}
  AND l.promocode LIKE '%99'
```

Параметры: `event_name` (строка, `Ночной забег`), `event_year` (int, `2025`).  
Сохранить: `② Промокоды — индикатор`.

- [ ] **Шаг 2: Создать таблицу**

«Создать» → «Чарт» → «QL-чарт» → тип «Таблица».  
Датасет: `ds_leads_checks`.

SQL:
```sql
SELECT
    l.id AS `ID`,
    CONCAT(l.surname, ' ', l.name) AS `Фамилия Имя`,
    l.email AS `Email`,
    l.promocode AS `Промокод`,
    l.event_distance AS `Дистанция`,
    YEAR(l.birthday) AS `Г.р.`,
    DATE_FORMAT(l.created_at, '%d.%m.%Y') AS `Дата заявки`
FROM leads l
WHERE l.event_name = {{event_name}}
  AND l.event_year = {{event_year}}
  AND l.promocode LIKE '%99'
ORDER BY l.created_at DESC
```

Параметры: те же.  
Сохранить: `② Промокоды — таблица`.

---

## Задача 7: Чарты ③ — Дубликаты

- [ ] **Шаг 1: Создать индикатор**

QL-чарт, тип «Индикатор», датасет `ds_leads_checks`.

SQL:
```sql
SELECT COUNT(*) AS `Дубликаты`
FROM leads l
WHERE l.event_name = {{event_name}}
  AND l.event_year = {{event_year}}
  AND l.is_duplicate = 1
```

Параметры: `event_name`, `event_year`.  
Сохранить: `③ Дубликаты — индикатор`.

- [ ] **Шаг 2: Создать таблицу**

QL-чарт, тип «Таблица», датасет `ds_leads_checks`.

SQL:
```sql
SELECT
    l.id AS `ID`,
    CONCAT(l.surname, ' ', l.name) AS `Фамилия Имя`,
    l.email AS `Email`,
    l.event_distance AS `Дистанция`,
    (
        SELECT DATE_FORMAT(MIN(l2.created_at), '%d.%m.%Y')
        FROM leads l2
        WHERE l2.email = l.email
          AND l2.event_name = l.event_name
          AND l2.event_year = l.event_year
          AND l2.is_duplicate = 0
    ) AS `Дата 1-й заявки`,
    DATE_FORMAT(l.created_at, '%d.%m.%Y') AS `Дата дубля`
FROM leads l
WHERE l.event_name = {{event_name}}
  AND l.event_year = {{event_year}}
  AND l.is_duplicate = 1
ORDER BY l.surname, l.name
```

Параметры: `event_name`, `event_year`.  
Сохранить: `③ Дубликаты — таблица`.

---

## Задача 8: Чарты ④ — Ошибки года рождения

- [ ] **Шаг 1: Создать индикатор**

QL-чарт, тип «Индикатор», датасет `ds_leads_checks`.

SQL:
```sql
SELECT COUNT(*) AS `Ошибки г.р.`
FROM leads l
WHERE l.event_name = {{event_name}}
  AND l.event_year = {{event_year}}
  AND (YEAR(l.birthday) < 1900 OR YEAR(l.birthday) > {{event_year}})
```

Параметры: `event_name`, `event_year`.  
Сохранить: `④ Ошибки г.р. — индикатор`.

- [ ] **Шаг 2: Создать таблицу**

QL-чарт, тип «Таблица», датасет `ds_leads_checks`.

SQL:
```sql
SELECT
    l.id AS `ID`,
    CONCAT(l.surname, ' ', l.name) AS `Фамилия Имя`,
    l.email AS `Email`,
    YEAR(l.birthday) AS `Введённый г.р.`,
    l.birthday AS `Полная дата`,
    l.event_distance AS `Дистанция`,
    CASE
        WHEN YEAR(l.birthday) < 1900 THEN 'Год < 1900'
        WHEN YEAR(l.birthday) > {{event_year}} THEN 'Год > года события'
    END AS `Проблема`
FROM leads l
WHERE l.event_name = {{event_name}}
  AND l.event_year = {{event_year}}
  AND (YEAR(l.birthday) < 1900 OR YEAR(l.birthday) > {{event_year}})
ORDER BY l.surname, l.name
```

Параметры: `event_name`, `event_year`.  
Условное форматирование колонки `Проблема`: не пустое → текст `#ff6b6b`.  
Сохранить: `④ Ошибки г.р. — таблица`.

---

## Задача 9: Чарты ⑤ — Минимальный возраст

- [ ] **Шаг 1: Создать индикатор**

QL-чарт, тип «Индикатор», датасет `ds_leads_checks`.

SQL:
```sql
SELECT COUNT(*) AS `Мин. возраст`
FROM leads l
WHERE l.event_name = {{event_name}}
  AND l.event_year = {{event_year}}
  AND ({{event_year}} - YEAR(l.birthday)) < CASE
        WHEN l.event_distance LIKE '%21%' THEN 18
        WHEN l.event_distance LIKE '%Северная ходьба%' AND l.event_name = 'Жара' THEN 7
        WHEN l.event_distance LIKE '%Северная ходьба%' THEN 12
        WHEN l.event_distance LIKE '%2 км%' THEN 7
        WHEN l.event_distance LIKE '%5 км%' THEN 12
        WHEN l.event_distance LIKE '%7 км%' THEN 12
        WHEN l.event_distance LIKE '%10 км%' THEN 12
        ELSE 0
    END
```

Параметры: `event_name`, `event_year`.  
Сохранить: `⑤ Мин. возраст — индикатор`.

- [ ] **Шаг 2: Создать таблицу**

QL-чарт, тип «Таблица», датасет `ds_leads_checks`.

SQL:
```sql
SELECT
    l.id AS `ID`,
    CONCAT(l.surname, ' ', l.name) AS `Фамилия Имя`,
    l.email AS `Email`,
    l.event_distance AS `Дистанция`,
    YEAR(l.birthday) AS `Г.р.`,
    ({{event_year}} - YEAR(l.birthday)) AS `Возраст`,
    CASE
        WHEN l.event_distance LIKE '%21%' THEN 18
        WHEN l.event_distance LIKE '%Северная ходьба%' AND l.event_name = 'Жара' THEN 7
        WHEN l.event_distance LIKE '%Северная ходьба%' THEN 12
        WHEN l.event_distance LIKE '%2 км%' THEN 7
        WHEN l.event_distance LIKE '%5 км%' THEN 12
        WHEN l.event_distance LIKE '%7 км%' THEN 12
        WHEN l.event_distance LIKE '%10 км%' THEN 12
        ELSE 0
    END AS `Мин. возраст`,
    CONCAT('−', (
        CASE
            WHEN l.event_distance LIKE '%21%' THEN 18
            WHEN l.event_distance LIKE '%Северная ходьба%' AND l.event_name = 'Жара' THEN 7
            WHEN l.event_distance LIKE '%Северная ходьба%' THEN 12
            WHEN l.event_distance LIKE '%2 км%' THEN 7
            WHEN l.event_distance LIKE '%5 км%' THEN 12
            WHEN l.event_distance LIKE '%7 км%' THEN 12
            WHEN l.event_distance LIKE '%10 км%' THEN 12
            ELSE 0
        END - ({{event_year}} - YEAR(l.birthday))
    ), ' лет') AS `Нарушение`
FROM leads l
WHERE l.event_name = {{event_name}}
  AND l.event_year = {{event_year}}
  AND ({{event_year}} - YEAR(l.birthday)) < CASE
        WHEN l.event_distance LIKE '%21%' THEN 18
        WHEN l.event_distance LIKE '%Северная ходьба%' AND l.event_name = 'Жара' THEN 7
        WHEN l.event_distance LIKE '%Северная ходьба%' THEN 12
        WHEN l.event_distance LIKE '%2 км%' THEN 7
        WHEN l.event_distance LIKE '%5 км%' THEN 12
        WHEN l.event_distance LIKE '%7 км%' THEN 12
        WHEN l.event_distance LIKE '%10 км%' THEN 12
        ELSE 0
    END
ORDER BY l.surname, l.name
```

Параметры: `event_name`, `event_year`.  
Условное форматирование колонки `Нарушение`: не пустое → текст `#ff6b6b`.  
Сохранить: `⑤ Мин. возраст — таблица`.

---

## Задача 10: Раскладка виджетов на канвасе

*Все 10 чартов + 2 селектора уже созданы. Теперь — добавить их на вкладку и настроить связи.*

- [ ] **Шаг 1: Открыть дашборд → вкладка «Подготовка стартовых» → Редактировать**

- [ ] **Шаг 2: Добавить все 10 QL-чартов**

«Добавить» → «Чарт». Выбрать из списка сохранённых. Добавить по одному:
```
① Льготные — индикатор
① Льготные — таблица
② Промокоды — индикатор
② Промокоды — таблица
③ Дубликаты — индикатор
③ Дубликаты — таблица
④ Ошибки г.р. — индикатор
④ Ошибки г.р. — таблица
⑤ Мин. возраст — индикатор
⑤ Мин. возраст — таблица
```

- [ ] **Шаг 3: Разместить по сетке**

Целевая раскладка (5 строк ниже селекторов):
```
[ Селектор: Событие ~300px ]  [ Селектор: Год ~200px ]     (высота ~60px)
─────────────────────────────────────────────────────────
[ Инд ① ~155px ]  [ Таблица ①                         ]   (высота ~160px)
[ Инд ② ~155px ]  [ Таблица ②                         ]   (высота ~140px)
[ Инд ③ ~155px ]  [ Таблица ③                         ]   (высота ~130px)
[ Инд ④ ~155px ]  [ Таблица ④                         ]   (высота ~130px)
[ Инд ⑤ ~155px ]  [ Таблица ⑤                         ]   (высота ~160px)
```

Таблица в каждой строке занимает оставшуюся ширину канваса.

- [ ] **Шаг 4: Привязать селекторы к чартам**

Для каждого из двух селекторов — зайти в настройки селектора (три точки → «Настройки»).  
В разделе «Связанные чарты» включить все 10 QL-чартов.  
Убедиться что в каждом QL-чарте есть параметры с теми же именами: `event_name` и `event_year`.

- [ ] **Шаг 5: Сохранить дашборд**

Нажать «Сохранить». Переключиться из режима редактирования.

---

## Задача 11: Верификация

- [ ] **Проверка 1: Селекторы работают**

Выбрать событие «Ночной забег», год «2025».  
Все 10 виджетов должны обновиться.  
Индикаторы показывают числа (не ошибку). Таблицы показывают строки или пустые (если нарушений нет).

- [ ] **Проверка 2: Льготные категории**

Выбрать событие и год где точно есть участники с льготными категориями.  
Индикатор ① должен показывать число > 0.  
В таблице ① — только строки с реальными несоответствиями, колонка «Несоответствие» заполнена.

- [ ] **Проверка 3: Промокоды**

Если в `leads` есть строки с `promocode LIKE '%99'` — они отображаются в таблице ②.  
Если нет — таблица пустая, индикатор = 0. Это нормально.

- [ ] **Проверка 4: Дубликаты**

Если `is_duplicate = 1` строки существуют — отображаются в таблице ③.

- [ ] **Проверка 5: Ошибки года рождения**

Таблица ④ содержит только строки где `YEAR(birthday) < 1900` или `YEAR(birthday) > event_year`.

- [ ] **Проверка 6: Минимальный возраст**

Таблица ⑤ содержит только строки где возраст участника меньше минимального для его дистанции.  
Проверить граничный случай: для Жары + Северная ходьба порог должен быть 7 лет (не 12).

- [ ] **Проверка 7: Смена события**

Переключить событие на другое (напр. «Весна»).  
Все 10 виджетов должны обновиться с данными нового события.

---

## Примечания по отладке

**QL-чарт возвращает ошибку «Unknown parameter»:**  
→ Убедиться что параметр добавлен в раздел «Параметры» QL-чарта с точно таким же именем как в SQL (`event_name`, `event_year`).

**Таблица всегда пустая даже при смене события:**  
→ Проверить что селектор привязан к этому чарту (раздел «Связанные чарты» в настройках селектора).  
→ Убедиться что имена параметров совпадают.

**SUBSTRING_INDEX возвращает пустую строку:**  
→ Проверить в MySQL как именно записана строка в поле `products`. Разделитель может быть `;\n` или `;` — скорректировать SUBSTRING_INDEX.

**Индикатор показывает 0, но в таблице есть строки:**  
→ Это невозможно если SQL одинаковый. Проверить что оба чарта привязаны к одним и тем же селекторам.
