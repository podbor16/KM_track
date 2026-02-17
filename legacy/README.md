# Legacy Frontend Integration - KM Track

## 📋 Обзор

Папка `legacy/` содержит интегрированный старый фронт-энд приложения. Функциональность и отображение остаются идентичными оригинальной версии.

## 📁 Структура

```
legacy/
├── templates/           # HTML шаблоны
│   ├── header.html     # Общий хэдер для всех страниц
│   ├── tracker.html    # Страница трекера маршрутов
│   └── analytics.html  # Страница аналитики и результатов
└── static/             # Статические ресурсы
    ├── navigation.css  # Стили навигации
    ├── tracker.css    # Стили трекера
    ├── analytics.css  # Стили аналитики
    ├── tracker.js     # JavaScript для трекера
    ├── analytics.js   # JavaScript для аналитики
    ├── logo.jpg       # Логотип приложения
    └── houschkapro_demibold.otf  # Кастомный шрифт
```

## 🔗 URL маршруты

Следующие маршруты используют legacy шаблоны:

- **`/`** - Главная страница (перенаправляет на трекер)
- **`/tracker`** - Страница трекера маршрутов
- **`/tracker/{event}`** - Трекер для конкретного события
- **`/analytics`** - Страница со стартовым списком и результатами

## 🎨 Общий хэдер

Все страницы используют единый хэдер (`header.html`) с помощью Jinja2 `{% include %}`:

```html
{% include 'header.html' %}
```

### Особенности хэдера:
- ✅ Адаптивное мобильное меню
- ✅ Автоматическая подсветка активной страницы
- ✅ Логотип и навигационные ссылки
- ✅ Красивая градиент-панель

## 📦 Подключение в FastAPI

### В `app.py`:
```python
# Подключение legacy статических файлов
if LEGACY_STATIC_DIR.exists():
    app.mount("/legacy/static", StaticFiles(directory=str(LEGACY_STATIC_DIR)), name="legacy_static")

# Подключение legacy шаблонов
legacy_templates = Jinja2Templates(directory=str(LEGACY_TEMPLATES_DIR))
```

### В `src/tracker/router.py`:
```python
# Инициализация legacy шаблонов
LEGACY_TEMPLATES_DIR = BASE_DIR / "legacy" / "templates"
legacy_templates = Jinja2Templates(directory=str(LEGACY_TEMPLATES_DIR))

# Использование в маршрутах
return legacy_templates.TemplateResponse("tracker.html", context)
return legacy_templates.TemplateResponse("analytics.html", context)
```

## 🚀 API интеграция

JavaScript файлы обращаются к следующим API endpoints:

### Трекер (`tracker.js`):
- `GET /api/current-event` - Текущее событие
- `GET /api/route` - Маршрут события
- `GET /api/runners` - Список участников
- `GET /api/analytics` - Аналитические данные
- `GET /api/search-runners` - Поиск участников
- `POST /api/select-runner` - Выбрать участника
- `POST /api/deselect-runner` - Отменить выбор

### Аналитика (`analytics.js`):
- `GET /api/registered-runners` - Зарегистрированные участники (до гонки)
- `GET /api/race-results` - Результаты гонки (во время/после)

## 🎯 Основной функционал

### Страница Трекера (tracker.html)
- 📍 Интерактивная карта (Leaflet)
- 🔍 Поиск участников в реальном времени
- 📍 Отслеживание до 5 участников одновременно
- 📊 Блок аналитики с общей статистикой

### Страница Аналитики (analytics.html)
- 📋 Переключение между режимами: "Стартовый список" ↔ "Результаты"
- 🔍 Фильтрация по полу и возрастной группе
- 📑 Сортировка по любому столбцу
- 🎨 Цветной статус-индикатор (мужчина/женщина)
- ⏱️ Отображение времени и темпа (мин/км)

## 🎨 CSS переменные

Основные цвета определены в `navigation.css`:
```css
:root {
    --primary-color: #EE2D62;        /* Розовый */
    --primary-dark: #1a1a1a;         /* Чёрный */
    --background: #faf8fa;           /* Светлый фон */
    --shadow: 0 2px 8px rgba(0,0,0,0.1);
}
```

## 📱 Адаптивность

Все компоненты отзывчивы и работают на:
- ✅ Десктопах (1200px+)
- ✅ Планшетах (768px - 1200px)
- ✅ Мобильных телефонах (<768px)

## 🔄 Обновления данных

- **Трекер**: Автоматическое обновление каждые 2 секунды
- **Аналитика**: Обновление при переключении режима или применении фильтров
- **LocalStorage**: Сохранение выбранных участников в браузере

## 📝 Примечания

1. **Шрифт**: Используется кастомный шрифт "Houschka Pro" для оригинального стиля
2. **Логотип**: Логотип должен быть в формате JPG в `legacy/static/`
3. **API Base**: По умолчанию установлен на `http://localhost:5000/api`
4. **Кэширование**: Используется версионирование URL (`?v=timestamp`) для избежания кэша

## 🐛 Отладка

Для отладки JavaScript откройте консоль браузера (F12) и посмотрите логи:
```javascript
// Трекер логирует события инициализации и обновления
console.log('✓ Событие загружено:', CONFIG.EVENT_NAME);
console.log('💾 Сохранено в localStorage:', selectedArray);

// Аналитика логирует загрузку данных
console.log('Загрузка данных начата, режим:', currentMode);
```

## 📚 Дополнительная информация

- Шаблоны используют **Jinja2** для рендеринга на сервере
- Стилизация использует современный **CSS** с поддержкой gradients и animations
- JavaScript написан на ванильном **ES6+** без зависимостей (кроме Leaflet для карты)
- Все API запросы используют современный **Fetch API**
