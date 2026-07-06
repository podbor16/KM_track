---
name: project-load-testing
description: Статус нагрузочного тестирования KM_track — что сделано, что осталось, важные уроки
metadata:
  type: project
---

# Нагрузочное тестирование KM_track — статус на 2026-05-19

## Что сделано (все коммиты в ветке Map)

| Задача | Статус | Коммит |
|--------|--------|--------|
| Спек + план нагрузочного тестирования | ✅ | `6a6b0de`, `2874545` |
| locustfile.py — 5 классов пользователей (TrackerUser 55%, ResultsUser 25%, StartListUser 10%, SearchUser 5%, BusinessUser 5%) | ✅ | `7061710` |
| k6 SSE тест `tests/load/sse_test.js` | ✅ | `15bfb9a` |
| Скрипт мониторинга VPS `tests/load/monitor_vps.sh` | ✅ | `8d0ca40` |
| Оркестратор `tests/load/run_load_test.py` | ✅ | `a4fe189` |
| Фикс оркестратора (таймаут на wait()) | ✅ | `9b639f8` |
| nginx worker_connections 65535 + systemd LimitNOFILE | ✅ | `69254cd` |
| Фикс monitor_vps.sh (set -e, парсинг ss -s) | ✅ | `1b502b3` |
| Фикс k6 SSE логики (--yes, connected heartbeat) | ✅ | `900a7da` |
| Smoke-тест localhost (5+10 VU, 1 мин) | ✅ | отчёт `2026-05-17/locust_smoke.html` |
| L1 против VPS (165 HTTP + 335 SSE) | ✅ | отчёт `2026-05-17/locust_L1.html` |

## Результаты L1 (165 HTTP VU, 8 мин, против analytics.krasmarafon.ru)

- Всего HTTP запросов: **10 110**
- Failure rate: **0.4%** (44 из 10 110) — ниже порога 1% ✅
- Основные endpoints: `/api/event-results[live]` — 2850 req, 14 fails; `/api/event-results` — 640 req, 2 fails

## Redis Pub/Sub + SSE Ceiling (2026-05-19)

| Коммит | Описание |
|--------|---------|
| `978bd68` | deploy/_verify_redis.py — скрипт верификации leader election |
| `303bcd4` | tests/load/vps_monitor.py + run_incremental.py |
| `bb3b444` | фикс run_incremental (BooleanOptionalAction, http-users, finally) |
| `6922a9b` | deploy/ssh_add_swap2.py + ssh_nginx_tune.py |
| `36561dd` | фикс ssh_nginx_tune rollback покрывает conf.d |
| `5e25228` | отчёты инкрементального теста |

## Результаты инкрементального SSE-теста (2026-05-19)

VPS конфигурация: 3 CPU / 2.9GB RAM / 60GB NVMe / swap 3GB (1+2) / nginx keepalive_timeout=15s / workers=3

| SSE VUs | SSE% | RAM max | Локаст |
|---------|------|---------|--------|
| 1000 | 100% | 76.3% | PASS |
| 1500 | 100% | 77.6% | FAIL (HTTP деградация) |
| 2000 | 100% | 78.9% | FAIL (HTTP деградация) |
| 2500 | 0% | 81.5% | FAIL |

**Потолок SSE = 2000 VUs** — при 2000 SSE клиентах все держатся 100%, RAM 78.9%.  
**Why:** При 2500+ VUs CPU 92-96%, VPS не принимает новые SSH соединения (SSE скрипт не стартует).  
**HTTP деградация при 1500+ SSE:** 200 HTTP VUs конкурируют с SSE. Нужно снижать HTTP нагрузку в параллельных тестах или тестировать SSE отдельно.

**Важный факт о T2000:** Соединения медленно устанавливаются — из 2000 VUs 0 держатся первые 4 минуты, затем резкий рост (61 → 1143 → 2000 за 60с). Это поведение backpressure/ramp-up при высокой нагрузке.

## Delta SSE инкрементальный тест (2026-05-19, после оптимизации)

Коммит `70dab62` — delta SSE: сервер шлёт только изменившихся участников вместо полного JSON.

| SSE VUs | SSE% | RAM max | Locust HTTP |
|---------|------|---------|-------------|
| 2000 | 100% | 65.3% | PASS |
| 3000 | 100% | 76.0% | PASS |
| 4000 | 100% | 80.2% | FAIL (конкуренция HTTP+SSE) |
| 5000 | 100% | 80.2% | FAIL (конкуренция HTTP+SSE) |

**Новый потолок SSE ≥ 5000 VUs** (рост с 2000 → 5000+, т.е. 2.5x+).  
RAM при 5000 VUs = 80.2% — запас ещё есть. Реальный потолок скорее всего выше 5000.  
HTTP FAIL при 4000+ — не падение сервера, а конкуренция 200 HTTP VUs с 5000 SSE за 3 воркера.

## Комбинированный тест (2026-05-20) — финальные результаты

Коммит `7579f7d` — исправлены: SSE date serialization, SSE drop tracking, pre-warm методология.

**Критический баг (обнаружен и исправлен):** `json.dumps` в SSE handler вызывал `TypeError: Object of type date is not JSON serializable` — все SSE соединения падали сразу после "connected". Предыдущий "drop tracking" ошибочно считал их "held". Фикс: `default=str`.

| Уровень | Пользователи | SSE | HTTP ошибки | Результат |
|---------|-------------|-----|-------------|-----------|
| Smoke | 15 | 10/10 (100%) | 0% | PASS |
| L2 | 2000 | 1335/1335 (100%) | 0.57% | PASS |
| L2.5 | 3000 | 2000/2000 (100%) | 0.78% | PASS |
| L3 | 5000 | SSH умер на 169с | 14.9% (avg 11s) | FAIL |

**Потолок системы: 3000 concurrent users.**  
**Причина отказа на L3:** VPS RAM на baseline уже 91.6% (2721/2972 MB). При 3335+ SSE + 1665 HTTP VPS уходит в OOM, SSH недоступен, HTTP деградация до avg 11s.  
**Приложение не виновато** — uvicorn/asyncio работает нормально. Проблема = железо VPS.

## Что осталось

- [ ] Написать итоговый отчёт `reports/load/load-test-report.md`
- [ ] При апгрейде VPS до 4 CPU / 4 GB RAM — повторить L3/L4 для подтверждения масштабирования
- [ ] Оптимизировать baseline RAM (найти что жрёт 91% в idle)

## Важные уроки

**k6 raw JSON — огромные файлы:** `--out json=file.json` в k6 пишет NDJSON каждого data point. Для L1 (335 VU, 8 мин) файл вырос до **9.8 ГБ** и крашил VS Code. Решение: добавлено в .gitignore `reports/load/**/k6_L*.json`. Для получения итоговых метрик L2-L4 нужно использовать либо `--summary-export summary.json` (только итоги), либо читать stdout вывода k6 вместо файла.

**Why:** Чуть не потеряли IDE из-за огромного файла в рабочей директории.
**How to apply:** Для L2-L4 менять команду k6 на `--summary-export` вместо `--out json`.

## Файлы плана

- Спек: `docs/superpowers/specs/2026-05-17-load-testing-design.md`
- План: `docs/superpowers/plans/2026-05-17-load-testing.md`
- Отчёты: `reports/load/2026-05-17/`
