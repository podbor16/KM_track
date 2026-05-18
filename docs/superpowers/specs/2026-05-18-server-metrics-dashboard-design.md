# Server Metrics Dashboard — Design Spec

**Дата:** 2026-05-18  
**Проект:** KM_track  
**Задача:** Дашборд реальной нагрузки на сервер с момента запуска — уникальные IP, SSE-соединения, RPS, время ответа, ошибки. История 30 дней в SQLite.

---

## 1. Цель

Страница `/admin/server-metrics` (за авторизацией) показывает:
- Сколько пользователей сейчас на сайте (уникальные IP) и сколько из них на живом трекере (SSE)
- RPS и процент ошибок в реальном времени
- Время ответа сервера (среднее)
- Историю за выбранный диапазон: 1ч / 6ч / 24ч / 7д / 30д
- Позволяет определить порог нагрузки при котором сервер деградирует

---

## 2. Новые файлы

```
src/monitoring/
    __init__.py
    collector.py        # MetricsCollector — сбор, flush, SQLite
templates/
    server-metrics.html # дашборд (Chart.js, SSE live-update)
data/
    server_metrics.db   # SQLite, создаётся автоматически при старте
```

**Изменяемые файлы:**
- `app.py` — регистрация collector'а, middleware hook, фоновый таск
- `src/tracker/routers/api.py` — 2 новых endpoint'а
- `src/tracker/routers/pages.py` — 1 новая страница
- `src/tracker/services/notification_hub.py` — метод `total_sse_count()`

---

## 3. Схема данных

### SQLite таблица `metrics`

```sql
CREATE TABLE IF NOT EXISTS metrics (
    ts              INTEGER PRIMARY KEY,  -- unix timestamp закрытия bucket
    unique_ips      INTEGER NOT NULL,
    total_requests  INTEGER NOT NULL,
    http_errors     INTEGER NOT NULL,     -- статусы 4xx + 5xx
    avg_response_ms REAL    NOT NULL,
    sse_connections INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_metrics_ts ON metrics(ts);
```

- **Гранулярность:** 1 строка = 5 секунд реального времени
- **Объём за 30 дней:** 518 400 строк ≈ 25–30 MB
- **Удаление старых:** `DELETE FROM metrics WHERE ts < now - 30*86400` при каждом flush

### In-memory bucket (между flush'ами)

```python
@dataclass
class _Bucket:
    ips: set[str]          # уникальные IP за текущий 5-секундный интервал
    requests: int = 0
    errors: int = 0
    total_ms: float = 0.0  # сумма для вычисления среднего
```

---

## 4. MetricsCollector (`src/monitoring/collector.py`)

```python
class MetricsCollector:
    def __init__(self, db_path: str, retention_days: int = 30): ...

    def record(self, ip: str, duration_ms: float, status: int) -> None:
        """Вызывается из middleware на каждый HTTP-запрос. Неблокирующий."""

    async def flush(self, sse_connections: int) -> None:
        """Вызывается фоновым таском каждые 5с. Пишет в SQLite."""

    def query(self, since_ts: int, until_ts: int, bucket_secs: int) -> list[dict]:
        """Возвращает downsampled данные для API."""

    def current_snapshot(self) -> dict:
        """Текущее состояние без flush — для live-индикаторов."""
```

**Многопроцессность (2 workers):**  
Каждый worker пишет в SQLite со своим `worker_id` (из `os.getpid()`). При чтении строки за одинаковый временной интервал суммируются по полям. SQLite открывается в режиме `WAL` (`PRAGMA journal_mode=WAL`) — concurrent writes без блокировок.

Альтернатива (проще): только один worker делает flush. Worker определяется по `os.getenv("UVICORN_WORKER_ID")` или по тому, кто первым создал lock-файл. Оба worker'а вызывают `record()` в памяти, но flush делает только один.

**Выбор реализации:** вариант с суммированием по `worker_id` — точнее (учитывает нагрузку на оба worker'а). Реализуем его.

**Схема с worker_id:**
```sql
-- Таблица хранит данные от каждого worker отдельно
ALTER TABLE metrics ADD COLUMN worker_id INTEGER DEFAULT 0;
PRIMARY KEY (ts, worker_id)

-- При чтении — агрегируем:
SELECT ts, SUM(unique_ips), SUM(total_requests), ...
FROM metrics GROUP BY ts ORDER BY ts
```

---

## 5. Интеграция в app.py

### 5.1 Инициализация в lifespan (startup)

```python
from src.monitoring.collector import MetricsCollector

metrics_collector = MetricsCollector(db_path="data/server_metrics.db")

# В lifespan startup:
async def _metrics_flusher():
    while True:
        await asyncio.sleep(5)
        sse_count = tracker_hub.total_sse_count()
        await metrics_collector.flush(sse_connections=sse_count)

asyncio.create_task(_metrics_flusher())
```

### 5.2 Middleware hook (4 строки в существующем middleware)

```python
@app.middleware("http")
async def log_request_duration(request: Request, call_next):
    if request.url.path.startswith("/api/sse"):
        return await call_next(request)
    start = _time.time()
    response = await call_next(request)
    duration_ms = (_time.time() - start) * 1000
    metrics_collector.record(                  # ← новая строка
        ip=request.client.host,
        duration_ms=duration_ms,
        status=response.status_code,
    )
    # ... остальная логика без изменений
    return response
```

### 5.3 Добавление `total_sse_count()` в TrackerHub

```python
# notification_hub.py
def total_sse_count(self) -> int:
    return sum(len(queues) for queues in self._subs.values())
```

---

## 6. API Endpoints

Оба за `Depends(require_auth)`.

### `GET /api/admin/metrics`

Query params:
- `hours: int = 24` — диапазон (1, 6, 24, 168, 720)

Логика downsampling по диапазону:

| hours | bucket_secs | Точек в ответе |
|-------|-------------|----------------|
| 1     | 5           | ≤ 720          |
| 6     | 60          | ≤ 360          |
| 24    | 300         | ≤ 288          |
| 168   | 1800        | ≤ 336          |
| 720   | 7200        | ≤ 360          |

Ответ:
```json
{
  "points": [
    {"ts": 1747600000, "unique_ips": 12, "total_requests": 47,
     "http_errors": 0, "avg_response_ms": 340.5, "sse_connections": 8},
    ...
  ],
  "meta": {"from_ts": ..., "to_ts": ..., "bucket_secs": 300}
}
```

### `GET /api/admin/metrics/live` (SSE)

Отправляет одну точку каждые 5 секунд сразу после flush. Использует тот же `EventSourceResponse` что и остальные SSE в приложении.

```
data: {"ts":1747600005,"unique_ips":14,"total_requests":52,"http_errors":0,"avg_response_ms":312.0,"sse_connections":9}
```

---

## 7. Страница `/admin/server-metrics`

Защищена `Depends(require_auth)`, шаблон `server-metrics.html`.

### Макет

```
┌──────────────────────────────────────────────────────────────────┐
│  Мониторинг сервера · KM_track          ● live    [выйти]        │
├──────────┬──────────┬──────────┬──────────┬──────────────────────┤
│ IP сейчас│ SSE сейч.│ RPS      │ Ср. время│ Ошибки               │
│   42     │   18     │  14.3    │  1.4 с   │  0.0%                │
├──────────┴──────────┴──────────┴──────────┴──────────────────────┤
│                                    [1ч] [6ч] [24ч] [7д] [30д]   │
│  Пользователи на сервере                                         │
│  ─────IP──────                                                   │
│       ───SSE──                                                   │
├──────────────────────────────────────────────────────────────────┤
│  Запросы в секунду (RPS) и ошибки                                │
│  ████ rps ████                   · errors ·                      │
├──────────────────────────────────────────────────────────────────┤
│  Время ответа сервера (мс)                                       │
│  ──── среднее ────                                               │
└──────────────────────────────────────────────────────────────────┘
```

### Поведение

- При загрузке: `fetch /api/admin/metrics?hours=24` → рисует 3 графика
- Кнопки диапазона: повторный fetch с нужным `hours`, перерисовка
- Живое обновление: подключается к `/api/admin/metrics/live` (SSE), каждые 5с добавляет точку в правый край графиков и сдвигает окно. KPI-карточки обновляются из `current_snapshot`.
- Индикатор `● live` зелёный = SSE подключен, серый = переподключение

### Стек frontend

- Chart.js 4.x (CDN, тот же что в load test dashboard)
- Vanilla JS, без фреймворков
- Тёмная тема в стиле существующего `business-analytics.html`

---

## 8. Обработка ошибок

| Ситуация | Поведение |
|----------|-----------|
| SQLite недоступен при старте | Логируем warning, collector работает только in-memory |
| Ошибка записи в SQLite | Логируем, не крашим приложение |
| SSE live-стрим разорван | Клиент переподключается через 3с (стандартный `retry:`) |
| Worker перезапущен | При старте читает существующий DB, история сохранена |
| `request.client` is None | `record()` пропускает IP, счётчики запросов не теряются |

---

## 9. Что НЕ входит в scope

- Алерты / уведомления при превышении порогов
- Разбивка метрик по endpoint'ам (только агрегат по серверу)
- Геолокация IP
- Метрики CPU и RAM (только прикладные метрики FastAPI)
- Аутентификация отдельным логином — используем существующий `require_auth`

---

## 10. Порядок реализации

1. `src/monitoring/collector.py` — MetricsCollector (SQLite + in-memory bucket)
2. `src/tracker/services/notification_hub.py` — добавить `total_sse_count()`
3. `app.py` — регистрация collector'а, middleware hook, таск `_metrics_flusher`
4. `src/tracker/routers/api.py` — `/api/admin/metrics` и `/api/admin/metrics/live`
5. `src/tracker/routers/pages.py` — страница `/admin/server-metrics`
6. `templates/server-metrics.html` — Chart.js дашборд
