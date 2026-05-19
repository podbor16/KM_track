# KM_track — Итоговый отчёт нагрузочного тестирования

**Дата:** 2026-05-19 / 2026-05-20  
**Ветка:** Map  
**VPS:** 3 CPU / 2.9 GB RAM / 60 GB NVMe  
**Стек:** FastAPI + uvicorn 2 workers + nginx + MySQL (localhost) + Redis

---

## Итог

| Уровень | HTTP users | SSE VUs | Всего | SSE результат | HTTP ошибки | Вердикт |
|---------|-----------|---------|-------|--------------|-------------|---------|
| Smoke   | 5         | 10      | 15    | 10/10 (100%) | 0%          | **PASS** |
| L2      | 665       | 1335    | 2000  | 1335/1335 (100%) | 0.57%   | **PASS** |
| L2.5    | 1000      | 2000    | 3000  | 2000/2000 (100%) | 0.78%   | **PASS** |
| L3      | 1665      | 3335    | 5000  | SSH обрыв ~240s | 14.9%   | **FAIL** |

**Потолок системы на текущем железе: 3000 одновременных пользователей.**

---

## Методология

### Структура нагрузки

Каждый уровень запускается в два этапа:

1. **SSE pre-warm** — сначала поднимаются SSE-соединения (asyncio скрипт на VPS, 20 VU/s). Время pre-warm ≈ N_vus/20 + 30s.
2. **HTTP поверх SSE** — Locust запускается поверх уже установленных SSE-соединений. Имитирует race-day: пользователи подключились к трекеру утром, HTTP-нагрузка начинается со стартом гонки.

### Классы пользователей Locust

| Класс | Вес | Поведение |
|-------|-----|-----------|
| TrackerUser | 55% | Загрузка трекера, просмотр live-результатов |
| ResultsUser | 25% | Просмотр финальных результатов |
| StartListUser | 10% | Старт-лист |
| SearchUser | 5% | Поиск участника |
| BusinessUser | 5% | Бизнес-аналитика (требует логин) |

### SSE тест (VPS asyncio)

Запускается на самом VPS через SSH: одна Python asyncio задача на VU, устанавливает TCP-соединение на 127.0.0.1:8000 и держит его N секунд. Критерий успеха: ≥95% VUs удержали соединение до конца.

---

## Детальные результаты

### Smoke (15 users)

- Locust: 0 ошибок, exit 0
- SSE: 10/10 held (100%), 0 early-drop, total time 75s
- VPS RAM: ~250 MB в базе

### L2 — 2000 users (665 HTTP + 1335 SSE)

- **SSE: 1335/1335 held (100%) | 0 early-drop** — PASS
- Locust: 12620 запросов, 72 ошибки (0.57%) — все ConnectTimeoutError к HTTPS
- Avg response: 353ms, 95th: 420ms
- Locust exit 1 (на любую ошибку) — по реальному порогу <1% **PASS**
- VPS RAM: до ~1.1 GB в пике

### L2.5 — 3000 users (1000 HTTP + 2000 SSE)

- **SSE: 2000/2000 held (100%) | 0 early-drop** — PASS
- Locust: 18871 запросов, 148 ошибок (0.78%) — все ConnectTimeoutError
- Avg response: 459ms, 95th: ~1.4s
- Locust exit 1 — по реальному порогу <1% **PASS**
- VPS RAM: до ~1.5 GB в пике

### L3 — 5000 users (1665 HTTP + 3335 SSE) — FAIL

**Первая попытка** (после L2 + L2.5, baseline RAM = 91.6% = 2721 MB):
- SSE SSH умер на 169s — VPS без памяти сразу
- HTTP: 14.9% ошибок, avg 11s

**Вторая попытка** (после рестарта сервиса, baseline RAM = 29.5% = 878 MB):
- SSE SSH умер на 260s — на 91s дольше, но тот же исход
- HTTP: аналогичная деградация

**Анализ по VPS метрикам (vps_L3.csv):**

| Время | RAM | RAM% | TCP estab |
|-------|-----|------|----------|
| t=0s  | 878 MB | 29.5% | 39 |
| t=12s | 1282 MB | 43.1% | 519 |
| t=24s | 1734 MB | 58.3% | — (SSH мониторинг пропал) |
| t=240s | — | — | SSH основного канала обрывается |

Рост RAM: +404 MB за 12s при 519 соединениях ≈ **~780 KB на SSE-соединение** (uvicorn asyncio task + Queue + TCP буферы 2×64KB loopback + Python fragmentation).

Проекция для 3335 VUs: 3335 × 780 KB ≈ **2.6 GB только под SSE**, превышает весь доступный RAM VPS после baseline.

---

## Ключевые фиксы в ходе тестирования

### Критический баг: TypeError — date not JSON serializable

**Симптом:** Все предыдущие SSE тесты показывали "100% held" при реальном немедленном обрыве.

**Причина:** `json.dumps({'results': initial.results, ...})` в SSE handler поднимал `TypeError: Object of type date is not JSON serializable` сразу после отправки `": connected\n\n"`. Сервер закрывал соединение, но старый код трекинга всегда выставлял `results[vu_id] = "held"` после hold-цикла — даже при немедленном разрыве.

**Фикс:** `json.dumps(..., default=str)` + флаг `dropped = True` при пустом чанке.

**Коммит:** `7579f7d`

### Locust runner.quit() — крашил весь тест

`BusinessUser.on_start()` вызывал `self.environment.runner.quit()` при любом таймауте логина. Один таймаут убивал все 1000 Locust VUs.

**Фикс:** убран `runner.quit()`.

### SSE initial snapshot cache — thundering herd

При одновременном подключении 2000+ VUs каждый вызывал `build_event_results()` через thread executor (7 воркеров). Добавлен кеш с TTL 3s: первое соединение строит снэпшот, остальные берут из кеша.

---

## Потолок и масштабирование

**Текущий потолок: ~3000 concurrent users** (L2.5 PASS).

Для достижения L3 (5000):
- Нужно ~4 GB RAM (сейчас 3 GB, и 2.6 GB уходит только на SSE при 3335 VUs)
- Либо снизить footprint на SSE-соединение: jemalloc как аллокатор Python, уменьшить asyncio.Queue(maxsize=5→2)

Для production race day (~500–800 одновременных участников + зрители):
- **Текущая конфигурация более чем достаточна** — L2.5 (3000 users) с запасом

---

## Отчёты

```
reports/load/2026-05-19/
  locust_smoke.html, sse_smoke_stdout.txt, vps_smoke.csv
  locust_L2.html,    sse_L2_stdout.txt,    vps_L2.csv
  locust_L2.5.html,  sse_L2.5_stdout.txt
reports/load/2026-05-20/
  locust_L3.html,    sse_L3_stdout.txt,    vps_L3.csv   (2 попытки)
```
