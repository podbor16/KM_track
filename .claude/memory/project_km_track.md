---
name: KM_track Project Context
description: Контекст проекта KM_track — цель, архитектура, ключевые модули, текущий статус
type: project
---

KM_track — дипломный веб-проект для отслеживания и анализа результатов беговых мероприятий Красноярского марафона.

**Why:** Дипломная работа с требованиями к реальной функциональности.

**How to apply:** Предлагать решения production-уровня, учитывать масштабируемость и корректность работы с GPS/временными данными.

**Стек:**
- Backend: Python 3.13, FastAPI 0.104.1
- Frontend: JavaScript (tracker-api.js, tracker-map.js, analytics-results.js), HTML, CSS
- БД: MySQL (mysql-connector-python, без ORM; TIME поля → timedelta)
- Интеграция: Copernico API (хронометраж), GPX-маршруты

**Ключевые модули:**
- `load_race_results.py` — загрузчик данных из Copernico, расчёт времён/мест
- `src/tracker/router.py` — 18+ API endpoints
- `src/tracker/services/runners_service.py` — `calculate_live_position()`
- `src/analytics/db_results.py` — запросы результатов, `create_connection()`
- `static/js/tracker-map.js` — Leaflet-анимация маркеров
- `static/js/analytics-results.js` — страница результатов с авто-обновлением 30с

**Copernico-специфика:**
- `times.official_:::start:::` — волновая задержка участника от выстрела (мс)
- `times.official_:::finish:::` — официальное gun-время финиша (мс)
- Чистое время = `official_finish − official_start`
- `times.real_:::finish:::` — chip-время (Первомайский не предоставляет)

**Текущее состояние (2026-05-13):**
- Ветка: `Map`
- SSE-архитектура реализована и протестирована (Фаза 1 завершена)
- Следующее: Фаза 2 — инфраструктура (Docker, nginx, SSL) + деплой на VDS nic.ru до 17.05
- Весна 2026 (event_id=106): тестовые данные в БД (result_ids 39201-39203), старт 17.05.2026
- Запуск сервера: `python app.py` (с reload) или `python -m uvicorn app:app --port 8000` (production)

**SSE-архитектура:**
- `src/tracker/services/notification_hub.py` — TrackerHub + NotificationHub
- `static/js/realtime.js` — SSEClient класс
- `tracker-api.js` использует EventSource вместо setInterval
- Фоновые задачи в `app.py`: tracker_broadcast (2с), results_watcher (5с), startlist_watcher (15с)

**How to apply:** При старте сессии — проверить статус деплоя. При работе с SSE — помнить что сервер нужно рестартовать при изменениях (без --reload).
