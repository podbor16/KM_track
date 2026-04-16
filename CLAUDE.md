# KM_track — инструкции для Claude

## Память проекта

**ВАЖНО:** Вся память этого проекта хранится в `.claude/memory/` внутри директории проекта:
`c:\Users\podbo\Работа\КРАСМАРАФОН\KM_track\.claude\memory\`

При сохранении воспоминаний (user, feedback, project, reference) — **всегда писать туда**, а не в глобальный `~/.claude/projects/...`.

Индекс памяти: `.claude/memory/MEMORY.md`

При чтении памяти читать из `.claude/memory/`.

---

## Проект

**KM_track** — веб-приложение для отслеживания и анализа результатов беговых мероприятий Красноярского марафона. Дипломная работа, требования к production-уровню кода.

### Стек

- **Backend:** Python 3.13, FastAPI 0.104.1, Pydantic 2.5
- **БД:** MySQL (mysql-connector-python, без ORM; TIME-поля возвращаются как `datetime.timedelta`)
- **Frontend:** Leaflet.js, JavaScript (tracker.js), HTML/CSS
- **Тесты:** pytest, pytest-mock (conda base env)
- **Окружение:** Windows 11, кириллические пути, conda base

### Ключевые модули

| Путь | Назначение |
|------|-----------|
| `src/tracker/router.py` | 18+ API endpoints |
| `src/tracker/services/runners_service.py` | `calculate_live_position()` — live-скорость маркеров |
| `src/tracker/services/routes_service.py` | `RouteCalculator` — позиция на маршруте |
| `src/analytics/db_connection_optimized.py` | Пул соединений, все DB-функции |
| `static/js/tracker.js` | Leaflet-анимация маркеров, fetch `/api/event-results` |
| `tests/` | unit + integration тесты |

### Важные нюансы

- Frontend (`tracker.js`) использует `/api/event-results?event_id=104`, **не** `/api/runners`
- `fetch_route_from_osm()` кеширует маршрут внутри `routes_service.py` (не в `AppState`)
- `RouteCalculator` инициализируется без аргументов: `RouteCalculator(); rc.set_path(coords)`
- Все checkpoint-времена в БД — тип TIME, возвращаются как `timedelta`
- DB connection: `db_connection_optimized.py` (пул), `db_connection.py` (legacy, не использовать)

---

## Соглашения по разработке

- Отвечать на русском языке
- Давать готовый рабочий код сразу
- Не добавлять фичи сверх запрошенного
- Не добавлять docstrings/комментарии к неизменённому коду
- Перед изменением файла — прочитать его
- Тесты запускать: `conda run -n base python -m pytest tests/unit/ -v`

## Obsidian Knowledge Vault
Хранилище знаний: C:\Users\...\ObsidianMyProject\
### При старте сессии
Прочитай 00-home/index.md и текущие приоритеты.md.
Если задача касается модуля — прочитай заметку из knowledge/.
### При завершении (пользователь: "сохрани сессию")
1. Создай заметку в sessions/ с датой
2. Обнови текущие приоритеты.md
3. Если решение — создай в knowledge/decisions/
4. Если баг — создай в knowledge/debugging/
5. Обнови index.md если новые заметки