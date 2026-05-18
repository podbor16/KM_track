# Server Metrics Dashboard v2 — Design Spec

**Дата:** 2026-05-18  
**Проект:** KM_track  
**Задача:** Расширение дашборда `/admin/server-metrics` — системные метрики (CPU/RAM), индикатор нагрузки, история 1 год, авто-обновление раз в минуту, 8 диапазонов.

---

## 1. Цель

Расширить существующий дашборд:
- Добавить CPU % и RAM % в реальном времени и в истории
- Комбинированный индикатор нагрузки (Low / Moderate / High / Critical)
- Хранить историю **1 год** (вместо 30 дней)
- Изменить интервал flush 5с → **60с** (bucket = 1 минута)
- Авто-обновление страницы каждые 60с с countdown-таймером
- 8 диапазонов: 1ч / 6ч / 24ч / 7д / 30д / 3м / 6м / 12м

---

## 2. Изменяемые файлы

| Файл | Изменение |
|------|-----------|
| `src/monitoring/collector.py` | Flush 5с→60с, CPU/RAM из /proc, новые столбцы, схема миграции, новый downsampling |
| `app.py` | `_metrics_flusher`: sleep 5 → 60 |
| `src/tracker/routers/api.py` | Обновить `hours_to_bucket_secs`, добавить новые диапазоны |
| `templates/server-metrics.html` | 8 KPI-карточек, 4 графика, countdown, новые кнопки диапазона |

---

## 3. Схема данных

### Миграция SQLite

При старте `MetricsCollector._init_db()` выполняет `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` для новых столбцов — безопасно для существующих данных:

```sql
-- Новые столбцы (добавляются к существующей таблице)
ALTER TABLE metrics ADD COLUMN cpu_percent    REAL    DEFAULT 0;
ALTER TABLE metrics ADD COLUMN ram_used_mb    INTEGER DEFAULT 0;
ALTER TABLE metrics ADD COLUMN ram_total_mb   INTEGER DEFAULT 0;

-- Retention меняется: 30 дней → 365 дней
-- DELETE FROM metrics WHERE ts < now - 365*86400
```

Итоговая схема:

```sql
CREATE TABLE IF NOT EXISTS metrics (
    ts                INTEGER NOT NULL,
    worker_id         INTEGER NOT NULL,
    unique_ips        INTEGER NOT NULL,
    total_requests    INTEGER NOT NULL,
    http_errors       INTEGER NOT NULL,
    total_response_ms REAL    NOT NULL,
    sse_connections   INTEGER NOT NULL,
    cpu_percent       REAL    DEFAULT 0,
    ram_used_mb       INTEGER DEFAULT 0,
    ram_total_mb      INTEGER DEFAULT 0,
    PRIMARY KEY (ts, worker_id)
);
```

**Объём:** 43 200 строк/месяц × 12 = 516 000 строк/год ≈ **50 MB**.

---

## 4. Downsampling — новая таблица

| Диапазон (hours) | bucket_secs | Точек ≤ |
|------------------|-------------|---------|
| 1 (1ч)           | 60          | 60      |
| 6 (6ч)           | 300         | 72      |
| 24 (24ч)         | 600         | 144     |
| 168 (7д)         | 3600        | 168     |
| 720 (30д)        | 7200        | 360     |
| 2160 (3м)        | 21600       | 360     |
| 4320 (6м)        | 43200       | 360     |
| 8760 (12м)       | 86400       | 365     |

Функция `hours_to_bucket_secs(hours: int) -> int` обновляется под новую таблицу.

---

## 5. Сбор системных метрик

Системные метрики собираются в `flush()` раз в 60с. Только Linux (`/proc`), нулевые зависимости.

### RAM (`/proc/meminfo`)

```python
def _read_ram() -> tuple[int, int]:
    """Возвращает (used_mb, total_mb)."""
    info = {}
    with open("/proc/meminfo") as f:
        for line in f:
            k, v = line.split(":")
            info[k.strip()] = int(v.split()[0])  # kB
    total = info["MemTotal"]
    available = info.get("MemAvailable", info.get("MemFree", 0))
    used = total - available
    return used // 1024, total // 1024  # → MB
```

### CPU (`/proc/stat`)

CPU % вычисляется как дельта между двумя опросами (предыдущий и текущий flush):

```python
def _read_cpu_stat() -> tuple[int, int]:
    """Возвращает (idle_jiffies, total_jiffies) для воркера."""
    with open("/proc/stat") as f:
        line = f.readline()  # cpu  user nice system idle iowait irq softirq
    vals = [int(x) for x in line.split()[1:]]
    idle = vals[3] + vals[4]   # idle + iowait
    total = sum(vals)
    return idle, total

# В flush():
idle_now, total_now = _read_cpu_stat()
if self._prev_cpu:
    idle_prev, total_prev = self._prev_cpu
    delta_total = total_now - total_prev
    delta_idle  = idle_now  - idle_prev
    cpu_pct = (1 - delta_idle / delta_total) * 100 if delta_total else 0
else:
    cpu_pct = 0
self._prev_cpu = (idle_now, total_now)
```

### Аптайм (`/proc/uptime`)

```python
def _read_uptime_secs() -> int:
    with open("/proc/uptime") as f:
        return int(float(f.read().split()[0]))
```

Аптайм передаётся в API как поле `meta.uptime_secs` — **не хранится в SQLite** (всегда актуален из /proc).

### Fallback для не-Linux

```python
import platform
_IS_LINUX = platform.system() == "Linux"

# В flush() и current_snapshot():
if _IS_LINUX:
    cpu_pct = ...
    ram_used_mb, ram_total_mb = ...
else:
    cpu_pct, ram_used_mb, ram_total_mb = 0, 0, 0
```

---

## 6. Load Score

Вычисляется в `current_snapshot()` и передаётся в каждой SSE-точке.

```python
def _load_score(ram_pct: float, avg_ms: float, err_rate: float) -> tuple[float, str]:
    """Возвращает (score 0-100, label)."""
    # Response time grade
    if avg_ms < 500:      rt = 0.0
    elif avg_ms < 1500:   rt = 35.0
    elif avg_ms < 3000:   rt = 70.0
    else:                 rt = 100.0

    score = ram_pct * 0.4 + rt * 0.4 + err_rate * 0.2

    if score < 25:    label = "Низкая"
    elif score < 55:  label = "Умеренная"
    elif score < 80:  label = "Высокая"
    else:             label = "Критическая"

    return round(score, 1), label
```

`err_rate = (http_errors / total_requests * 100)` если total_requests > 0, иначе 0.

---

## 7. API

### `GET /api/admin/metrics?hours=N`

Допустимые значения hours: `1, 6, 24, 168, 720, 2160, 4320, 8760`.

Ответ расширен новыми полями в каждой точке и в `meta`:

```json
{
  "points": [
    {
      "ts": 1747600000,
      "unique_ips": 12,
      "total_requests": 47,
      "http_errors": 0,
      "avg_response_ms": 340.5,
      "sse_connections": 8,
      "cpu_percent": 34.2,
      "ram_used_mb": 712,
      "ram_total_mb": 960
    }
  ],
  "meta": {
    "from_ts": 1747596400,
    "to_ts": 1747600000,
    "bucket_secs": 600,
    "hours": 24,
    "uptime_secs": 86412
  }
}
```

### `GET /api/admin/metrics/live` (SSE)

Точка раз в 60с. Расширена теми же полями + `load_score`, `load_label`:

```json
{
  "ts": 1747600060,
  "unique_ips": 14,
  "total_requests": 52,
  "http_errors": 0,
  "avg_response_ms": 312.0,
  "sse_connections": 9,
  "cpu_percent": 28.5,
  "ram_used_mb": 698,
  "ram_total_mb": 960,
  "load_score": 31.2,
  "load_label": "Умеренная"
}
```

---

## 8. Frontend

### KPI-карточки (8 штук, 2 ряда)

```
┌──────────────┬──────────┬──────────┬──────────┐
│ НАГРУЗКА     │ IP сейчас│ SSE      │ RPS      │
│ 🟡 Умеренная │   42     │   18     │  14.3    │
├──────────────┼──────────┼──────────┼──────────┤
│ RAM          │ CPU      │ Ср.время │ Ошибки   │
│ 74%          │ 38%      │ 1 240 мс │ 0.2%     │
└──────────────┴──────────┴──────────┴──────────┘
```

Карточка «Нагрузка» — цветная рамка по уровню (зелёная / жёлтая / оранжевая / красная).

### Countdown в шапке

```
● live · обновление через 43с
```

Реализация: `setInterval(tick, 1000)`, countdown от 60 до 0, при 0 вызывает `loadHistory(currentHours)` и сбрасывается.

### Кнопки диапазона

```
1ч | 6ч | 24ч | 7д | 30д | 3м | 6м | 12м
```

`data-h` атрибуты: 1, 6, 24, 168, 720, 2160, 4320, 8760.

### Четыре графика

```
┌─────────────────────────────────────────────────┐
│  Пользователи на сервере (IP + SSE)   [wide]    │
├──────────────────────┬──────────────────────────┤
│  RAM % и CPU %       │  RPS и Ошибки/с          │
├──────────────────────┴──────────────────────────┤
│  Время ответа сервера (мс)            [wide]    │
└─────────────────────────────────────────────────┘
```

График RAM/CPU: обе оси 0–100%, единицы `%`. Датасеты:
- RAM %: `ram_used_mb / ram_total_mb * 100`, оранжевый
- CPU %: `cpu_percent`, синий

### Аптайм в футере

```
Данные обновляются каждую минуту · Аптайм: 2д 14ч 32м · История 1 год
```

---

## 9. Обработка ошибок

| Ситуация | Поведение |
|----------|-----------|
| `/proc` недоступен (не Linux) | cpu/ram = 0, fallback через `platform.system()` |
| Первый flush (нет prev_cpu) | cpu_percent = 0 |
| ALTER TABLE уже выполнен (столбцы существуют) | try/except, продолжаем |
| SSE разорван | Клиент переподключается через 3с, countdown не сбрасывается |
| ram_total_mb = 0 | RAM% = 0, не делить на ноль |

---

## 10. Что НЕ входит в scope

- Дисковые метрики (I/O, занятость)
- Сетевые метрики (bandwidth)
- Метрики пула БД MySQL
- Алерты / уведомления при превышении порогов
- Пиковые значения за день (можно добавить в v3)
- История аптайма (только текущий)

---

## 11. Порядок реализации

1. `src/monitoring/collector.py` — миграция схемы, CPU/RAM чтение, load_score, новый downsampling, flush 60с
2. `app.py` — изменить sleep в `_metrics_flusher`: 5 → 60
3. `src/tracker/routers/api.py` — обновить `hours_to_bucket_secs`, добавить новые hours в allowed set, включить cpu/ram/uptime в ответ
4. `templates/server-metrics.html` — 8 KPI, 4 графика, countdown, 8 кнопок диапазона
