# 📋 Архитектура проекта трекера забега

## Модульная структура

После рефакторинга проект разбит на следующие модули для удобства обслуживания:

### Backend (Flask) - `server/`

```
server/
├── flask_server.py          # ✨ Главный файл - объединяет все модули
├── config.py                # ⚙️ Конфигурация и константы
├── models.py                # 🏗️ Классы: RouteCalculator, RaceConfig
├── routes_service.py        # 🛣️ Работа с маршрутами (OSM, JSON)
├── runners_service.py       # 🏃 Обработка данных участников
├── api.py                   # 🔌 API endpoints (init_routes)
├── ParsingRaceInMap.py      # 📊 Парсер данных (не трогали)
└── static/
    ├── tracker.js           # 🎯 Основная логика клиента
    └── tracker.css          # 🎨 Стили
```

### Frontend - `maps/`

```
maps/
├── rosneft.html             # 🏃 Трекер Роснефти (использует tracker.js)
├── snow7.html               # ❄️ Трекер Снежной семерки
└── update_html.py           # 🔧 Вспомогательный скрипт
```

## Описание модулей

### `config.py` - Конфигурация
- Централизованные константы (скорость, дистанции)
- Конфигурация мероприятий (события, маршруты)
- Параметры кеширования

### `models.py` - Модели данных
- **`RouteCalculator`** - расчет позиции бегуна на маршруте
  - `set_path()` - загрузить геометрию маршрута
  - `get_shuttle_position()` - позиция на челночном маршруте
  - `get_position_on_loop()` - позиция на кольцевом маршруте
- **`RaceConfig`** - конфигурация забега (чекпоинты, дистанции)

### `routes_service.py` - Работа с маршрутами
- `fetch_route_from_osm()` - загрузка из OpenStreetMap или JSON
- `load_route_from_json()` - загрузка из локального JSON
- `process_osm_route_data()` - парсинг данных OSM
- `get_route_calculator()` - получить глобальный калькулятор

### `runners_service.py` - Работа с участниками
- `fetch_copernico_data()` - загрузка данных из файла
- `transform_copernico_data()` - преобразование в структуру бегуна
- `update_runner_positions()` - обновление позиций и статусов

### `api.py` - REST API endpoints
- `init_routes(app)` - регистрирует все endpoints в Flask
- **Endpoints:**
  - `/api/route` - получить маршрут
  - `/api/runners` - список участников с позициями
  - `/api/search-runners` - поиск по номеру/фамилии
  - `/api/select-runner` - выбрать участника
  - `/api/deselect-runner` - отменить выбор
  - `/api/selected-runners` - получить выбранных
  - `/api/race-config` - конфигурация забега
  - `/api/events` - список мероприятий

### `flask_server.py` - Главный файл
- Инициализация Flask приложения
- Импорт и регистрация всех модулей
- Запуск сервера

### `tracker.js` - Клиентская логика
- Инициализация карты (Leaflet)
- Управление маркерами бегунов
- Поиск и выбор участников
- Автообновление позиций
- localStorage для сохранения выбора

## Интеграция модулей

```
flask_server.py (главный)
    ├── config.py (константы)
    ├── models.py (классы)
    ├── routes_service.py (маршруты)
    ├── runners_service.py (участники)
    └── api.py (endpoints)
         └── init_routes(app) регистрирует все endpoints
```

## Запуск

```bash
cd server
python flask_server.py
```

Откройте http://127.0.0.1:5000

## Добавление новых функций

### Добавить новый API endpoint?
1. Добавьте функцию в `api.py`
2. Оформите как route: `@app.route('/api/...')`

### Добавить новую конфигурацию?
1. Добавьте в `config.py` в `EVENTS_CONFIG`

### Изменить логику позиций бегунов?
1. Модифицируйте `RouteCalculator` в `models.py`
2. Обновите `update_runner_positions()` в `runners_service.py`

### Добавить новую фичу на фронтенде?
1. Добавьте в `tracker.js`
2. Обновите `rosneft.html` и `snow7.html` если нужно

## Преимущества модульной структуры

✅ **Читаемость** - каждый файл отвечает за одно  
✅ **Обслуживаемость** - легко найти и исправить код  
✅ **Расширяемость** - просто добавлять новые функции  
✅ **Тестируемость** - модули можно тестировать отдельно  
✅ **Переиспользование** - модули можно использовать в других проектах  

---

**Версия:** 2.0 (после рефакторинга)  
**Дата:** 19 декабря 2025  
