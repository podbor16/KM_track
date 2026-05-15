# Спецификация: Вкладка «Подготовка стартовых» — DataLens

> **Дата:** 2026-05-15  
> **Скоуп:** Новая вкладка в существующем дашборде DataLens с 5 проверками регистраций  
> **Принцип:** Только нарушения. Всё на одной странице без переключения вкладок внутри DataLens.

---

## Контекст

Перед каждым забегом организаторам нужно вручную проверять регистрации на несколько классов ошибок: неверные льготные категории, подозрительные промокоды, дубли, опечатки в году рождения, нарушения минимального возраста. Сейчас это делается вручную в Excel. Цель — автоматизировать проверки в DataLens-дашборде с фильтрами по событию и году.

Одобрённый дизайн: Вариант B — 5 строк «Индикатор слева (155px) + QL-таблица справа», Селекторы события и года вверху.

---

## Источник данных

**Таблица:** `leads`

**Ключевые поля:**

| Поле | Описание |
|------|----------|
| `id` | ID заявки (первичный ключ) |
| `surname` | Фамилия |
| `name` | Имя |
| `email` | Email |
| `sex` | Пол (`М` / `Ж`) |
| `birthday` | Дата рождения (DATE) |
| `products` | Строка с категорией — содержит подстроку после «Выберите категорию:» |
| `event_name` | Название события (напр. «Ночной забег», «Жара») |
| `event_year` | Год проведения (INT, напр. 2025) |
| `event_distance` | Дистанция (напр. «5 км», «21.1 км», «Северная ходьба 2 км») |
| `promocode` | Промокод (VARCHAR, может быть NULL или пустым) |
| `is_duplicate` | Флаг дубликата (0/1) |
| `created_at` | Дата создания заявки |

**Льготные категории (значения подстроки в `products`):**
- `Дети младше 18 лет`
- `Дети 12-17 лет`
- `Дети 7-17 лет`
- `Дети до 18 лет`
- `Пенсионеры`
- `Участники 18-22 года`

**Извлечение категории из products:**
```sql
TRIM(SUBSTRING_INDEX(SUBSTRING_INDEX(products, 'Выберите категорию:', -1), ';', 1))
```

---

## Структура вкладки

### Селекторы (вверху, применяются ко всем QL-чартам)
- **Событие** (`event_name`) — тип: список, мультивыбор отключён
- **Год** (`event_year`) — тип: список, числовой

### 5 строк проверок (Вариант B)
Каждая строка: `grid-template-columns: 155px 1fr`, gap 10px.

- **Левая ячейка:** Индикатор DataLens — большое число + подпись + мини-справочник правил
- **Правая ячейка:** QL-чарт (таблица) — только нарушения/записи требующие проверки

**Первый столбец каждой таблицы:** ID заявки (синий, monospace), для быстрого поиска в БД.

---

## Чарт ①: Льготные категории

**Индикатор:**
- Число: count несоответствий
- Подпись: «несоответствий»
- Правила (мини-текст):
  - Дети: возраст ≥ 18 лет
  - Пенсионер М: < 60 лет
  - Пенсионер Ж: < 55 лет
  - Студент: не 18–22 года

**QL-таблица — только несоответствия:**

Колонки: `ID` | `Фамилия Имя` | `Email` | `Пол` | `Г.р.` | `Возраст` | `Дистанция` | `Категория в заявке` | `Несоответствие`

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

---

## Чарт ②: Именные промокоды

**Индикатор:**
- Число: count заявок с промокодом `%99`
- Подпись: «заявок с кодом *99»
- Правила: «Требует ручной сверки со списком льготников»

**Примечание:** Список авторизованных льготников — Google Sheet (интеграция отдельная задача). Таблица — список для ручной сверки.

**QL-таблица:**

Колонки: `ID` | `Фамилия Имя` | `Email` | `Промокод` | `Дистанция` | `Г.р.` | `Дата заявки`

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

---

## Чарт ③: Дубликаты

**Индикатор:**
- Число: count дублей
- Подпись: «повторных заявок»

**QL-таблица:**

Колонки: `ID` | `Фамилия Имя` | `Email` | `Дистанция` | `Дата 1-й заявки` | `Дата дубля`

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

---

## Чарт ④: Ошибки года рождения

**Индикатор:**
- Число: count некорректных дат
- Подпись: «некорректных дат»
- Правила:
  - Год < 1900 → опечатка
  - Год > event_year → невозможно

**QL-таблица:**

Колонки: `ID` | `Фамилия Имя` | `Email` | `Введённый г.р.` | `Полная дата` | `Дистанция` | `Проблема`

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

---

## Чарт ⑤: Минимальный возраст

**Индикатор:**
- Число: count нарушений
- Подпись: «нарушений»
- Правила:
  - 2 км → от 7 лет
  - Северная ходьба → от 12 лет (на всех кроме Жары, Жара → от 7 лет)
  - 5 / 7 / 10 км → от 12 лет
  - 21.1 км → от 18 лет

**Возраст:** `event_year - YEAR(birthday)` (по состоянию на 31 декабря года забега)

**QL-таблица:**

Колонки: `ID` | `Фамилия Имя` | `Email` | `Дистанция` | `Г.р.` | `Возраст` | `Мин. возраст` | `Нарушение`

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

---

## Инструкция по реализации в DataLens

### Шаг 1: Создать датасет

- Подключение: существующее к MySQL
- Источник: таблица `leads`
- Датасет назвать: `ds_leads_checks`

### Шаг 2: Создать Селекторы

| Селектор | Поле | Тип | Дефолт |
|----------|------|-----|--------|
| `event_name` | `event_name` | Список | первое значение |
| `event_year` | `event_year` | Список | текущий год |

Оба селектора — без мультивыбора. Привязать ко всем 10 QL-чартам (5 индикаторов + 5 таблиц).

### Шаг 3: Создать 5 пар виджетов (Индикатор + QL-таблица)

Для каждого индикатора — QL-чарт типа «Индикатор» с `SELECT COUNT(*) AS ...` и теми же условиями WHERE что у таблицы.

### Шаг 4: Раскладка на канвасе

```
[ Селектор: Событие ]  [ Селектор: Год ]
─────────────────────────────────────────
[ Инд ① ]  [ Таблица ①: Льготные категории   ]
[ Инд ② ]  [ Таблица ②: Именные промокоды    ]
[ Инд ③ ]  [ Таблица ③: Дубликаты            ]
[ Инд ④ ]  [ Таблица ④: Ошибки года рождения ]
[ Инд ⑤ ]  [ Таблица ⑤: Минимальный возраст  ]
```

Ширина Индикатора ~155px, таблица занимает остаток.

### Шаг 5: Условное форматирование

Для таблиц ①, ④, ⑤ — колонки «Несоответствие» / «Проблема» / «Нарушение»:
- Красный цвет текста для ненулевых значений

---

## Вне скоупа

- Интеграция с Google Sheet для сверки промокодов
- Кнопки удаления дублей (DataLens read-only)
- Уведомления участникам
