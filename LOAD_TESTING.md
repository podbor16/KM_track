# Нагрузочное тестирование KM_track

Цель: 10 000 одновременных пользователей, время ответа p95 ≤ 2 секунды.

## Установка

```bash
conda run -n base pip install locust
```

## Запуск теста

**1. Запустить сервер** (в отдельном терминале):
```bash
conda run -n base uvicorn app:app --host 0.0.0.0 --port 8000 --log-level warning
```
Флаг `--log-level warning` убирает INFO-логи — при 10K пользователях они замедляют сервер.

**2. Запустить Locust**:
```bash
conda run -n base locust -f locustfile.py --config locust.conf
```

**3. Открыть Locust Web UI**: http://localhost:8089

**4. Нажать «Start»** — пользователи спаунятся по 200/сек, за ~50 сек достигнут 10 000.

**5. Дождаться 5 минут** (или остановить вручную), Locust сохранит `locust_report.html`.

## Критерии прохождения

| Метрика | Целевое значение |
|---------|-----------------|
| p50 (медиана) | ≤ 500 ms |
| p95 | ≤ 2000 ms |
| p99 | ≤ 5000 ms |
| Failure rate | < 1% |
| 500-ошибок в логах сервера | 0 |

## Чтение отчёта (`locust_report.html`)

- **Request statistics** — таблица с медианой, p95, p99, RPS по каждому эндпоинту
- **Charts → Response Times** — динамика времён ответа во время теста
- **Charts → Users** — рост числа виртуальных пользователей
- **Failures** — список ошибок с трейсбеком (должен быть пуст)

## Сценарии пользователей

| Класс | Вес | Поведение |
|-------|-----|-----------|
| `ResultsUser` | 50% | Открывает `/results`, запрашивает `/api/event-results` для разных событий |
| `TrackerUser` | 40% | Открывает `/tracker`, polling `/api/event-results?event_id=104` каждые 2–4s |
| `SearchUser` | 10% | Поиск спортсменов, стартовый список |

## Архитектурные ограничения (Windows)

На Windows uvicorn работает в 1 процесс (нет `fork` для `--workers N`).
Для production-деплоя на Linux использовать:

```bash
gunicorn app:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000 --log-level warning
```

4 workers × pool_size=20 = до 80 одновременных DB-соединений.
