# 🏃 KM_track - Система отслеживания и анализа беговых мероприятий

> **Дипломный проект** | Красноярский марафон трекинг-система | Python FastAPI + JavaScript

## 📋 Описание

KM_track — веб-приложение для реального времени отслеживания участников беговых мероприятий на интерактивной карте с последующим анализом и статистикой результатов. Система предоставляет как живой трекер для зрителей, так и аналитические инструменты для организаторов.

**Основные возможности:**
- 🗺️ Реальный трекер участников на карте (GPS отслеживание)
- 🔍 Поиск участников по имени/номеру
- 📊 Аналитика результатов (скорость, время, позиция)
- 👥 Профили спортсменов
- 📈 История результатов
- 🎯 Анализ сегментов маршрута

---

## 📁 Архитектура проекта

```
KM_track/
├── app.py                              # 🚀 Главная точка входа FastAPI
├── main.py                             # Альтернативный запуск сервера
├── requirements.txt                    # Python зависимости
│
├── src/                                # 📦 Основной исходный код
│   ├── config/
│   │   └── settings.py                 # Конфигурация приложения
│   ├── core/
│   │   ├── dependencies.py             # Зависимости (DI)
│   │   ├── exceptions.py               # Кастомные исключения
│   │   └── state.py                    # Глобальное состояние
│   ├── analytics/
│   │   ├── db_connection.py            # DB подключение
│   │   ├── db_connection_optimized.py  # Оптимизированный пул соединений
│   │   └── analytics_service.py        # Расчеты и аналитика
│   └── tracker/
│       ├── router.py                   # API маршруты
│       ├── race_data.json              # Данные участников
│       ├── models/                     # Pydantic модели
│       │   ├── runner.py               # Модель бегуна
│       │   ├── event.py                # Модель события
│       │   ├── route.py                # Модель маршрута
│       │   ├── segment.py              # Модель сегмента
│       │   └── analytics.py            # Модели аналитики
│       ├── parsers/                    # Парсеры и фетчеры
│       │   ├── copernico_fetcher.py    # Fetcher для Copernico API
│       │   └── ParsingRaceInMap.py     # Парсер данных гонки
│       ├── services/                   # Бизнес-логика
│       │   ├── runners_service.py      # Сервис участников
│       │   ├── routes_service.py       # Сервис маршрутов
│       │   ├── analytics_service.py    # Сервис аналитики
│       │   └── pace_calculator.py      # Калькулятор темпа
│       └── data/                       # Кеш и промежуточные данные
│
├── static/                             # 🎨 Статические ресурсы
│   ├── css/
│   │   ├── navigation.css              # Навигационные стили
│   │   ├── tracker.css                 # Стили трекера
│   │   ├── analytics.css               # Стили аналитики
│   │   ├── athlete-profile.css         # Стили профилей
│   │   ├── history.css                 # Стили истории
│   │   ├── race-analysis.css           # Стили анализа гонки
│   │   ├── krasmarafon-header.css      # Брендированные стили
│   │   └── krasmarafon-footer.css      # Футер стили
│   ├── js/
│   │   ├── tracker.js                  # Логика трекера (Leaflet/карта)
│   │   ├── analytics-results.js        # Таблица результатов
│   │   ├── analytics-start-list.js     # Стартовая таблица
│   │   └── race-analysis.js            # Анализ гонки
│   ├── images/
│   │   └── events/
│   │       ├── logo/                   # Логотипы мероприятий
│   │       └── logo1x1/                # Квадратные логотипы
│   └── map/
│       └── 2026/                       # GPX файлы маршрутов
│           └── night_run.gpx           # Маршрут ночного забега
│
├── templates/                          # 🌐 HTML шаблоны
│   ├── tracker.html                    # Главная страница трекера
│   ├── race-analysis.html              # Анализ гонки
│   ├── results.html                    # Страница результатов
│   ├── start_list.html                 # Стартовый лист
│   ├── athlete-profile.html            # Профиль спортсмена
│   ├── history.html                    # История результатов
│   ├── header.html                     # Шапка (общий компонент)
│   ├── krasmarafon_header.html         # Брендированная шапка
│   └── krasmarafon_footer.html         # Брендированный футер
│
├── tests/                              # 🧪 Тесты
│   ├── test_api.py                     # Тесты API
│   └── ...
│
├── logs/                               # 📝 Логи приложения
│
├── backups/                            # 💾 Резервные копии
│   └── legacy_static_backup_*.*/       # Старые версии статики
│
└── SQL_INDEXES_OPTIMIZATION.sql        # SQL оптимизация индексов
```

---

## 🚀 Установка и запуск

### Предварительные требования
- Python 3.9+
- Virtual Environment (venv)
- MySQL (опционально, для продакшена)

### Установка

```bash
# 1. Клонировать репозиторий
cd x:\"Мой гараж\Учеба\0. ДИПЛОМ\KM_track"

# 2. Создать виртуальное окружение
python -m venv .venv-1
.\.venv-1\Scripts\Activate.ps1

# 3. Установить зависимости
pip install -r requirements.txt
```

### Запуск

**Вариант 1: Использовать app.py (рекомендуется)**
```bash
python -m uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

**Вариант 2: Использовать main.py**
```bash
python main.py
```

**После запуска**, приложение доступно по адресам:
- 🌐 **Приложение**: http://localhost:8000
- 📖 **API документация (Swagger)**: http://localhost:8000/docs
- 📘 **API документация (ReDoc)**: http://localhost:8000/redoc
- 🗺️ **Трекер**: http://localhost:8000/tracker
- 📊 **Аналитика**: http://localhost:8000/analytics

---

## 🔗 API Endpoints

### Трекер (Tracker)
| Метод | Endpoint | Описание |
|-------|----------|---------|
| GET | `/tracker` | Страница трекера (HTML) |
| GET | `/api/race/runners` | Текущие позиции участников (JSON) |
| GET | `/api/race/route` | Маршрут гонки (GeoJSON) |
| GET | `/api/race/events` | Список всех мероприятий |
| GET | `/api/race/runner/{id}` | Инфо о конкретном участнике |

### Аналитика (Analytics)
| Метод | Endpoint | Описание |
|-------|----------|---------|
| GET | `/analytics` | Страница аналитики (HTML) |
| GET | `/api/analytics/results` | Результаты гонки |
| GET | `/api/analytics/start-list` | Стартовый лист |
| GET | `/api/analytics/runner/{id}/stats` | Статистика по участнику |
| GET | `/api/analytics/segments` | Результаты по сегментам |

### Системные
| Метод | Endpoint | Описание |
|-------|----------|---------|
| GET | `/docs` | Swagger UI |
| GET | `/redoc` | ReDoc |
| GET | `/health` | Статус приложения |

---

## 📊 Структура данных

### Race Data (race_data.json)
```json
{
  "event_id": "snow7_2026",
  "runners": [
    {
      "id": "RUN001",
      "name": "Иван Петров",
      "bib": "42",
      "category": "М40",
      "status": "running",
      "position": {"lat": 56.015, "lng": 93.05},
      "current_segment": 3,
      "time_elapsed": "00:45:23"
    }
  ],
  "segments": [
    {
      "id": "SEG_001",
      "name": "Старт - 5км",
      "distance": 5.0,
      "coordinates": [...]
    }
  ]
}
```

---

## 🎨 Интерфейс пользователя

### Главная страница (Трекер)
- **Интерактивная карта** (Leaflet.js)
- **Поиск** по имени/номеру участника
- **Фильтры** по категориям
- **Информационная панель** с выбранным участником
- **Легенда** с обозначениями статусов

### Страница аналитики
- **Таблица результатов** с сортировкой
- **Профили спортсменов**
- **График прогресса**
- **Статистика по сегментам**
- **История участия**

---

## 🛠️ Технологический стек

### Backend
- **Framework**: FastAPI 0.104+
- **Server**: Uvicorn
- **ORM**: SQLAlchemy (если используется)
- **Database**: MySQL Connector Python
- **Validation**: Pydantic 2.5+
- **Environment**: python-dotenv

### Frontend
- **Maps**: Leaflet.js
- **Styles**: CSS3 (Grid, Flexbox)
- **API Client**: Fetch API
- **Template Engine**: Jinja2

### Data Processing
- **Format**: JSON, GeoJSON, GPX
- **API**: Copernico API для парсинга данных

---

## 📈 Features

### ✅ Реализовано
- [x] Реальный трекер участников
- [x] Поиск по участникам
- [x] Хранение GPS координат
- [x] Аналитика результатов
- [x] Профили спортсменов
- [x] История результатов
- [x] Оптимизация БД (пул соединений, индексы)
- [x] Адаптивный дизайн
- [x] API документация

### 🔄 В процессе
- [ ] Real-time WebSocket обновления
- [ ] Экспорт результатов (PDF/Excel)
- [ ] Сравнение результатов между забегами
- [ ] Интеграция с социальными сетями

### 📋 Планируется
- [ ] Mobile app (React Native)
- [ ] Machine Learning для прогнозов
- [ ] Integration с GPS часами
- [ ] Сертификаты участников

---

## 📝 Конфигурация

### settings.py
```python
# API
API_TITLE = "KM_track"
API_VERSION = "1.0.0"

# Database
DATABASE_URL = "mysql+mysqlconnector://user:password@localhost/kmtrack"

# Paths
DATA_DIR = Path(__file__).parent.parent.parent / "data"
REPORTS_DIR = DATA_DIR / "reports"
```

### Environment Variables (.env)
```env
DATABASE_URL=mysql+mysqlconnector://root:password@localhost/kmtrack
LOG_LEVEL=INFO
CORS_ORIGINS=*
```

---

## 🧪 Тестирование

```bash
# Запуск тестов
pytest tests/

# С покрытием
pytest tests/ --cov=src
```

---

## 📊 Оптимизация

### SQL Индексы
Смотрите `SQL_INDEXES_OPTIMIZATION.sql` для оптимизации запросов БД

### Пул соединений
Используется оптимизированный пул соединений MySQL:
```python
from src.analytics.db_connection_optimized import initialize_connection_pool
pool = initialize_connection_pool(pool_size=5)
```

---

## 🤝 Как внести вклад

1. Fork репозитория
2. Create feature branch (`git checkout -b feature/имя-фичи`)
3. Commit changes (`git commit -m 'Add новая фича'`)
4. Push to branch (`git push origin feature/имя-фичи`)
5. Open Pull Request

---

## 📝 Лицензия

Дипломный проект. Все права принадлежат автору.

---

## 📞 Контакты

**Разработчик**: [Ваше имя]  
**Email**: your.email@example.com  
**Проект**: Дипломная работа, КрасГАУ

---

## 📚 Дополнительные ресурсы

- [LOAD_RACE_RESULTS_README.md](LOAD_RACE_RESULTS_README.md) - Инструкция по загрузке результатов
- [SQL_INDEXES_OPTIMIZATION.sql](SQL_INDEXES_OPTIMIZATION.sql) - SQL оптимизация
- [FastAPI документация](https://fastapi.tiangolo.com/)
- [Leaflet.js документация](https://leafletjs.com/)

---

**Последнее обновление**: 9 апреля 2026 г.
| GET | `/` | Главная страница трекера |
| GET | `/analytics` | Страница результатов |
| GET | `/api/runners` | Список бегунов |
| GET | `/api/route` | Маршрут гонки |
| GET | `/api/analytics` | Данные аналитики |
| GET | `/api/registered-runners` | Зарегистрированные участники |
| GET | `/api/race-results` | Результаты гонки |

## 📱 Адаптивность

- ✅ Desktop (1024px+)
- ✅ Tablet (768px - 1023px)
- ✅ Mobile (< 768px)
  - Навигация преобразуется в выпадающее меню
  - Оптимизирован для сенсорных экранов

## 💡 Дальнейшие улучшения

- [ ] Темная тема
- [ ] Переключение между мероприятиями в UI
- [ ] Фильтры аналитики
- [ ] Экспорт результатов
- [ ] Push-уведомления
