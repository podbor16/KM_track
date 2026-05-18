# Redis Pub/Sub для SSE — Дизайн-спек

**Дата:** 2026-05-19  
**Статус:** Реализовано

---

## Context

Нагрузочный тест L2 (2000 users = 665 HTTP + 1335 SSE) провален по SSE: 1018/1335 (76%) против порога 95%.  
Корневая причина: при 2 uvicorn workers event loop насыщается при ~667 SSE-корутинах на воркер во время ramp-up.  
Целевой уровень: L4 (10 000 users) на одном VPS с 4 CPU / 4 GB (апгрейд позже).

---

## Архитектура

### До
```
Worker-0: _tracker_broadcast() → DB query → TrackerHub.broadcast() → 667 SSE clients
Worker-1: _tracker_broadcast() → DB query → TrackerHub.broadcast() → 668 SSE clients
(2 DB-запроса/2с, 667 корутин на worker)
```

### После
```
Worker-0 (лидер): _tracker_broadcast() → DB → redis.publish("tracker:event:104", json)
                  _redis_tracker_subscriber() → TrackerHub.broadcast() → 333 SSE clients
Worker-1:         _redis_tracker_subscriber() → TrackerHub.broadcast() → 333 SSE clients
Worker-2:         _redis_tracker_subscriber() → TrackerHub.broadcast() → 333 SSE clients
Worker-3:         _redis_tracker_subscriber() → TrackerHub.broadcast() → 333 SSE clients
(1 DB-запрос/2с независимо от числа workers)
```

### Leader Election
- Ключ Redis: `tracker:leader`, TTL 6 сек
- `SET tracker:leader {pid} NX EX 6` → атомарный SETNX
- Лидер обновляет TTL каждые 2 сек через `EXPIRE tracker:leader 6`
- Если лидер падает → через 6 сек следующий worker берёт ключ автоматически

---

## Redis-каналы

| Канал | Издатель | Подписчики | Содержимое |
|-------|----------|-----------|-----------|
| `tracker:event:{event_id}` | лидер | все workers | JSON RaceResultsResponse |
| `tracker:notification` | лидер | все workers | `{"type": "results_updated", "event_id": N}` или `{"type": "startlist_updated"}` |

---

## Изменённые файлы

| Файл | Изменение |
|------|-----------|
| `requirements.txt` | + `redis[hiredis]>=5.0` |
| `app.py` | Redis client в lifespan; 3 → 6 background tasks; pool_size=5→3 |
| `deploy/km_track.service` | `--workers 2` → `--workers 4` |
| `deploy/ssh_redis.py` | Новый — установка Redis на VPS |

---

## Background tasks (app.py)

| Task | Роль | Частота |
|------|------|---------|
| `_tracker_broadcast` | лидер: DB → Redis PUBLISH | каждые 2с |
| `_redis_tracker_subscriber` | все: Redis SUBSCRIBE → TrackerHub | непрерывно |
| `_results_watcher` | лидер: DB → Redis PUBLISH | каждые 5с |
| `_startlist_watcher` | лидер: DB → Redis PUBLISH | каждые 15с |
| `_redis_notification_subscriber` | все: Redis SUBSCRIBE → NotificationHub | непрерывно |
| `_metrics_flusher` | все: SQLite flush | каждые 60с |

---

## Параметры

- `pool_size=3`, `workers=4` → 12 DB-соединений < `max_connections=20` ✅
- Redis: `127.0.0.1:6379`, без аутентификации (локально)
- Subscriber retry: catch Exception → sleep(1) → reconnect

---

## Тестирование

1. `python deploy/ssh_redis.py` → PONG
2. Smoke: 0 ошибок, SSE 10/10
3. L2: цель SSE ≥95% (1268+/1335)
