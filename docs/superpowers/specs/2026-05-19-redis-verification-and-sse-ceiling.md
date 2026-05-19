# Redis Verification & SSE Ceiling Discovery — Design Spec

**Date:** 2026-05-19  
**Context:** Redis Pub/Sub уже реализован в app.py и задеплоен на VPS (workers=3, Redis активен). L3 (3335 SSE) провален — сервер роняет соединения. Цель: убедиться что Redis работает корректно, найти реальный SSE-потолок на текущем железе (2 CPU / ~3 GB RAM), применить оптимизации и измерить эффект каждой.

---

## Архитектура

Redis Pub/Sub уже в production:
- 3 uvicorn workers, каждый подписан на `tracker:event:*`
- Leader election через Redis SETNX `tracker:leader` TTL=6s
- Лидер: 1 DB-запрос/2s → `PUBLISH tracker:event:{id}` → все workers рассылают локальным SSE-клиентам
- RAM baseline: 2004/2972 MB (67%) до нагрузки

---

## Фаза 1: Верификация Redis

**Цель:** убедиться что leader election и pub/sub работают до начала нагрузочных тестов.

**Проверки:**
1. VPS-логи содержат `[Redis] Connected` — ровно 3 строки (по одной на worker)
2. VPS-логи содержат `[SSE] Leader acquired` — ровно 1 строка (один лидер)
3. Smoke-тест с `--realistic`: 10 SSE + 5 HTTP, 2 мин — `{"ok": true}` на SSE, данные обновляются каждые 2с

**Realistic режим:**
- Вставляет 3000 тест-бегунов в event_id=104
- Запускает `race_simulator.py`: каждые 30с финишируют 10 бегунов (`results_updated`), каждые 60с новый участник (`startlist_updated`)
- Очищает данные после теста

---

## Фаза 2: Инкрементальный поиск потолка

Серия тестов по 5 минут, `--realistic`, HTTP фиксирован на 200 (лёгкая фоновая нагрузка), SSE растёт:

| Тест | SSE VUs | HTTP VUs | Критерий PASS |
|------|---------|----------|---------------|
| T1   | 1000    | 200      | ≥95% SSE held |
| T2   | 1500    | 200      | ≥95% SSE held |
| T3   | 2000    | 200      | ≥95% SSE held |
| T4   | 2500    | 200      | ≥95% SSE held |
| T5   | 3000    | 200      | ≥95% SSE held |

**Остановка:** тест прерывается на первом уровне где SSE < 70% или RAM > 90%.

**Мониторинг во время теста:** SSH-процесс собирает RAM/CPU каждые 10с, пишет в `reports/load/YYYY-MM-DD/vps_monitor_T{N}.csv`.

---

## Фаза 3: Оптимизации

Применяются поочерёдно между тестами, каждая измеряется:

### O1: Swap 1 GB → 2 GB
- `fallocate -l 2G /swapfile2 && mkswap /swapfile2 && swapon /swapfile2`
- Эффект: защита от OOM при пиковой нагрузке, деградация вместо краша
- Риск: низкий (zero downtime)

### O2: nginx keepalive_timeout 65s → 15s
- Освобождает worker connections быстрее после завершения запроса
- Актуально для 1665 HTTP-клиентов Locust
- Риск: низкий (nginx reload, ~1s)

### O3: Workers 3 → 2 (если RAM критична)
- Экономия ~200-300 MB RAM
- Компромисс: меньше CPU параллелизма, каждый worker держит больше SSE
- Применяем только если RAM > 85% при T2

---

## Новые файлы

| Файл | Назначение |
|------|-----------|
| `tests/load/run_incremental.py` | Скрипт инкрементальных тестов с кастомными уровнями SSE/HTTP и realistic режимом |
| `deploy/ssh_add_swap2.py` | Добавление второго swap-файла 2 GB на VPS |
| `deploy/ssh_nginx_tune.py` | Применение nginx keepalive_timeout=15s |

`run_incremental.py` параметры:
- `--sse-levels 1000,1500,2000,2500,3000` — список уровней SSE
- `--http-users 200` — фиксированный HTTP
- `--duration 5m` — длительность каждого теста
- `--realistic` — вставка тест-данных + симулятор
- `--stop-on-fail` — стоп при первом провале

---

## Success Criteria

- Найден максимальный SSE-уровень где ≥95% held без краша сервера
- Известна RAM в момент достижения потолка
- Зафиксирован эффект каждой оптимизации (+N SSE к потолку)
- Логи подтверждают корректную работу Redis leader election

---

## Исключения из scope

- Изменение архитектуры Redis (уже реализована, не трогаем)
- Апгрейд VPS (отдельное решение после измерений)
- L4 тест (10k users) — только после апгрейда железа
