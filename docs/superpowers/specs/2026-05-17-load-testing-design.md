# Спек: Нагрузочное тестирование KM_track

**Дата:** 2026-05-17  
**Статус:** Approved  
**Цель:** Найти и устранить узкие места, подтвердить 10 000 одновременных пользователей, дать рекомендации по конфигурации VPS для заказчика.

---

## 1. Архитектура тестирования

Два инструмента работают одновременно против VPS:

```
Тест-машина (ноутбук)
├── Locust  — HTTP-нагрузка (страницы, API, polling)
└── k6      — SSE-нагрузка (долгоживущие соединения трекера)

                    ↓ HTTPS ↓
          analytics.krasmarafon.ru
          Nginx → Uvicorn → FastAPI → MySQL (WAN)
```

Мониторинг VPS запускается параллельно через SSH (`tests/load/monitor_vps.sh`).

---

## 2. Уровни нагрузки

Соотношение SSE : HTTP = 2 : 1 (трекер доминирует).

| Уровень | HTTP (Locust) | SSE (k6) | Итого |
|---------|--------------|----------|-------|
| L1 | 165 | 335 | 500 |
| L2 | 665 | 1335 | 2000 |
| L3 | 1665 | 3335 | 5000 |
| L4 | 3335 | 6665 | 10000 |

**Профиль каждого прогона:** 2 мин прогрев → 5 мин стабильная нагрузка → 1 мин спад.  
**Пауза между уровнями:** 2 минуты (VPS остывает).  
**Общее время:** ~40 минут на полный тест всех уровней.

---

## 3. HTTP-нагрузка (Locust)

### Классы пользователей

| Класс | Поведение | Вес |
|-------|-----------|-----|
| `TrackerUser` | GET `/tracker`, поллинг `/api/event-results` каждые 2–4с | 55% |
| `ResultsUser` | GET `/results`, `/api/event-results` по разным event_id | 25% |
| `StartListUser` | GET `/start_list`, `/api/registered-runners` | 10% |
| `SearchUser` | GET `/api/search-athletes`, `/health` | 5% |
| `BusinessUser` | POST логин → GET `/business-analytics` (cookie-сессия) | 5% |

### Файлы

- `locustfile.py` — обновляется: добавляются `StartListUser`, `BusinessUser`; корректируются веса
- `locust.conf` — таргет `https://analytics.krasmarafon.ru`

### Запуск одного уровня

```bash
locust -f locustfile.py \
  --host https://analytics.krasmarafon.ru \
  --users 165 --spawn-rate 20 --run-time 8m \
  --html reports/load/locust_L1.html --headless
```

---

## 4. SSE-нагрузка (k6)

### Поведение VU

Каждый виртуальный пользователь:
1. Открывает `GET /api/sse/tracker?event_id=106` с заголовком `Accept: text/event-stream` (event_id берётся из переменной окружения `K6_EVENT_ID`, по умолчанию 106)
2. Держит соединение открытым 6 минут (реальный зритель на трекере)
3. Считает количество полученных событий и время до первого события

### Файлы

- `tests/load/sse_test.js` — новый k6-сценарий

### Запуск одного уровня

```bash
k6 run tests/load/sse_test.js \
  --vus 335 --duration 8m \
  --out json=reports/load/k6_L1.json
```

---

## 5. Мониторинг VPS

### Файл

`tests/load/monitor_vps.sh` — запускается через SSH параллельно с тестом.

### Что собирается (каждые 5 сек)

```
timestamp  cpu%  ram_used_mb  tcp_established  tcp_time_wait
```

Лог сохраняется локально: `reports/load/vps_monitor_L1.csv`.

---

## 6. Оркестратор

`tests/load/run_load_test.py` — запускает все 4 уровня последовательно:

1. Стартует `monitor_vps.sh` через SSH
2. Запускает Locust (headless) + k6 одновременно для текущего уровня
3. Ждёт завершения обоих
4. Делает паузу 2 мин
5. Переходит к следующему уровню
6. Останавливает мониторинг

---

## 7. Структура файлов

```
tests/load/
├── sse_test.js          # k6 SSE сценарий
├── monitor_vps.sh       # мониторинг CPU/RAM/соединений на VPS
└── run_load_test.py     # оркестратор: запускает L1→L4

reports/load/YYYY-MM-DD/
├── locust_L1.html  ... locust_L4.html
├── k6_L1.json      ... k6_L4.json
├── vps_monitor_L1.csv ... vps_monitor_L4.csv
└── load-test-report.md  # итоговый отчёт
```

---

## 8. Метрики и критерии успеха

### HTTP (Locust)

| Метрика | Цель |
|---------|------|
| RPS | максимизировать до деградации |
| p95 latency | < 500 мс |
| p99 latency | < 2000 мс |
| Failure rate | < 1% |

### SSE (k6)

| Метрика | Цель |
|---------|------|
| `sse_time_to_first_event` p95 | < 3 сек |
| `sse_connection_errors` | < 1% |
| События на VU за 6 мин | > 0 (соединение живое) |

### VPS

| Метрика | Цель |
|---------|------|
| CPU% пик | < 80% |
| RAM используемая | < 80% от доступной |
| TCP соединения | не упирается в ulimit |

---

## 9. Шаблон рекомендаций по VPS

Итоговый отчёт содержит конкретные рекомендации по результатам теста:

| Параметр | Текущее (SSD-1) | Рекомендация |
|----------|----------------|--------------|
| Uvicorn workers | `--workers 2` | `2 × vCPU + 1` |
| Nginx `worker_connections` | 1024 | 4096–65535 |
| `ulimit -n` (open files) | 1024 | 65535 |
| `net.core.somaxconn` | 128 | 65535 |
| `net.ipv4.tcp_tw_reuse` | 0 | 1 |
| RAM VPS | 1 GB (SSD-1) | 4 GB (SSD-3) если деградация на L2 |
| vCPU | 1 | 2–4 если CPU > 80% на L2 |

---

## 10. Итоговый отчёт (`load-test-report.md`)

Структура:

1. Методология (инструменты, уровни, длительность)
2. Сводная таблица результатов (RPS / p95 / errors / CPU% / RAM / SSE errors)
3. Точка отказа — уровень, на котором деградация критична
4. Узкие места — что именно упёрлось (CPU, RAM, соединения, DB, код)
5. Применённые фиксы (с коммитами)
6. Рекомендации по конфигурации VPS для 10 000 пользователей
