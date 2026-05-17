# Load Testing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Установить и запустить нагрузочное тестирование KM_track против VPS (Locust для HTTP + k6 для SSE), провести тесты на 4 уровнях (500 / 2000 / 5000 / 10000 пользователей), применить найденные оптимизации и сформировать итоговый отчёт с рекомендациями по конфигурации VPS.

**Architecture:** Locust тестирует HTTP (страницы, API, polling) с 5 классами пользователей. k6 тестирует SSE (`/api/sse/tracker`) — долгоживущие соединения трекера (2/3 всей нагрузки). Оркестратор `run_load_test.py` запускает оба инструмента одновременно для каждого уровня L1→L4. Мониторинг VPS через SSH-скрипт фиксирует CPU/RAM/TCP параллельно.

**Tech Stack:** Python 3.13, Locust 2.43.4, k6 (Go-based), Bash, nginx, systemd

---

## Файловая карта

| Файл | Статус | Назначение |
|------|--------|-----------|
| `locustfile.py` | Изменить | Добавить StartListUser, BusinessUser; обновить веса и EVENT_IDS |
| `tests/load/sse_test.js` | Создать | k6 SSE сценарий |
| `tests/load/monitor_vps.sh` | Создать | Мониторинг CPU/RAM/TCP на VPS |
| `tests/load/run_load_test.py` | Создать | Оркестратор L1-L4 |
| `deploy/nginx.conf` | Изменить | Добавить worker_connections, SSE-буфер, rate limiting |
| `deploy/km_track.service` | Изменить | LimitNOFILE=65535 |
| `reports/load/.gitkeep` | Создать | Создать директорию |

---

## Task 1: Установить k6

**Files:**
- Нет файлов изменяется — только установка инструмента

- [ ] **Шаг 1: Скачать и установить k6 на Windows**

```powershell
# Через winget (рекомендуется)
winget install k6 --source winget

# Или через Chocolatey
choco install k6

# Или вручную: скачать MSI с https://dl.k6.io/msi/k6-latest-amd64.msi
```

- [ ] **Шаг 2: Проверить установку**

```powershell
k6 version
```

Ожидаемый вывод: `k6 v0.x.x (go...)` — любая актуальная версия.

- [ ] **Шаг 3: Установить k6 на VPS**

```bash
# SSH на VPS, затем:
sudo gpg -k
sudo gpg --no-default-keyring --keyring /usr/share/keyrings/k6-archive-keyring.gpg \
  --keyserver hkp://keyserver.ubuntu.com:80 --recv-keys C5AD17C747E3415A3642D57D77C6C491D6AC1D69
echo "deb [signed-by=/usr/share/keyrings/k6-archive-keyring.gpg] https://dl.k6.io/deb stable main" \
  | sudo tee /etc/apt/sources.list.d/k6.list
sudo apt-get update && sudo apt-get install k6 -y
k6 version
```

---

## Task 2: Обновить locustfile.py

**Files:**
- Modify: `locustfile.py`

- [ ] **Шаг 1: Перечитать текущий locustfile.py**

Убедиться что знаем текущую структуру перед правкой (3 класса: ResultsUser, TrackerUser, SearchUser).

- [ ] **Шаг 2: Переписать locustfile.py**

```python
"""
Нагрузочный тест KM_track — до 10 000 одновременных пользователей (HTTP-часть).
SSE-нагрузка — отдельно в tests/load/sse_test.js (k6).

Запуск:
    locust -f locustfile.py --config locust.conf
    # или через оркестратор:
    python tests/load/run_load_test.py
"""

import os
import random
from locust import HttpUser, task, between

# Event IDs, которые реально есть в БД
EVENT_IDS = [67, 71, 75, 104, 106, 121]

# Текущее live-событие (трекер поллит именно этот event_id)
LIVE_EVENT_ID = os.environ.get("LOCUST_LIVE_EVENT_ID", "106")

# Пароль для бизнес-аналитики (из .env или переменной окружения)
ADMIN_PASSWORD = os.environ.get("LOCUST_ADMIN_PASSWORD", "km2026admin")


class TrackerUser(HttpUser):
    """55% трафика — открыли трекер и polling каждые 2–4s."""
    weight = 55
    wait_time = between(2, 4)

    @task(1)
    def view_tracker(self):
        self.client.get("/tracker", name="/tracker")

    @task(8)
    def poll_event_results(self):
        self.client.get(
            f"/api/event-results?event_id={LIVE_EVENT_ID}",
            name="/api/event-results[live]",
        )


class ResultsUser(HttpUser):
    """25% трафика — просматривают и переключают результаты событий."""
    weight = 25
    wait_time = between(3, 10)

    @task(3)
    def view_results_page(self):
        self.client.get("/results", name="/results")

    @task(5)
    def load_event_results(self):
        eid = random.choice(EVENT_IDS)
        self.client.get(f"/api/event-results?event_id={eid}", name="/api/event-results")

    @task(1)
    def view_analytics(self):
        self.client.get("/race-analysis", name="/race-analysis")


class StartListUser(HttpUser):
    """10% трафика — смотрят стартовый список."""
    weight = 10
    wait_time = between(5, 15)

    @task(2)
    def view_start_list_page(self):
        self.client.get("/start_list", name="/start_list")

    @task(3)
    def get_registered_runners_api(self):
        self.client.get(
            f"/api/registered-runners?event_id={LIVE_EVENT_ID}",
            name="/api/registered-runners",
        )

    @task(1)
    def view_history(self):
        self.client.get("/history", name="/history")


class SearchUser(HttpUser):
    """5% трафика — ищут конкретного спортсмена."""
    weight = 5
    wait_time = between(5, 15)

    QUERIES = ["Ива", "Пет", "Алек", "Сер", "Мар", "Ан", "Дм", "Ол"]

    @task(3)
    def search_athlete(self):
        q = random.choice(self.QUERIES)
        self.client.get(f"/api/search-athletes?q={q}", name="/api/search-athletes")

    @task(1)
    def health_check(self):
        self.client.get("/health", name="/health")


class BusinessUser(HttpUser):
    """5% трафика — организаторы в бизнес-аналитике."""
    weight = 5
    wait_time = between(10, 30)

    def on_start(self):
        """Войти один раз при старте VU — cookie сохраняется автоматически."""
        self.client.post(
            "/login",
            data={"password": ADMIN_PASSWORD},
            name="/login",
            allow_redirects=True,
        )

    @task(1)
    def view_business_analytics(self):
        self.client.get("/business-analytics", name="/business-analytics")
```

- [ ] **Шаг 3: Обновить locust.conf**

```ini
# Конфигурация нагрузочного теста KM_track
# Запуск: locust -f locustfile.py --config locust.conf
# Уровни нагрузки задаются через CLI или run_load_test.py

host = https://analytics.krasmarafon.ru
web-host = 0.0.0.0
users = 165
spawn-rate = 20
run-time = 8m
headless = false
html = reports/load/locust_smoke.html
```

- [ ] **Шаг 4: Проверить синтаксис**

```powershell
conda run -n base python -c "import ast; ast.parse(open('locustfile.py').read()); print('OK')"
```

Ожидаемый вывод: `OK`

- [ ] **Шаг 5: Коммит**

```powershell
git add locustfile.py locust.conf
git commit -m "feat: обновлён locustfile — StartListUser, BusinessUser, веса 55/25/10/5/5"
```

---

## Task 3: Создать k6 SSE тест

**Files:**
- Create: `tests/load/sse_test.js`

- [ ] **Шаг 1: Создать директорию**

```powershell
New-Item -ItemType Directory -Force tests\load
```

- [ ] **Шаг 2: Создать tests/load/sse_test.js**

```javascript
/**
 * k6 нагрузочный тест SSE-соединений KM_track.
 * Каждый VU держит SSE-соединение K6_CONN_HOLD секунд (по умолчанию 30),
 * затем переподключается — имитирует реального зрителя трекера.
 *
 * Запуск:
 *   k6 run tests/load/sse_test.js --vus 335 --duration 8m
 *
 * Переменные окружения:
 *   K6_HOST        — хост (по умолч. https://analytics.krasmarafon.ru)
 *   K6_EVENT_ID    — event_id для SSE (по умолч. 106)
 *   K6_CONN_HOLD   — секунд держать соединение (по умолч. 30)
 */

import http from 'k6/http';
import { check } from 'k6';
import { Rate, Trend } from 'k6/metrics';

const HOST = __ENV.K6_HOST || 'https://analytics.krasmarafon.ru';
const EVENT_ID = __ENV.K6_EVENT_ID || '106';
const CONN_HOLD_S = parseInt(__ENV.K6_CONN_HOLD || '30', 10);

// Кастомные метрики
const sseErrorRate = new Rate('sse_error_rate');
const sseTimeToFirstByte = new Trend('sse_ttfb_ms', true);

export const options = {
  // vus и duration задаются снаружи через CLI
  thresholds: {
    'sse_error_rate': ['rate<0.01'],           // < 1% ошибок подключения
    'sse_ttfb_ms': ['p(95)<3000'],             // TTFB p95 < 3с
    'http_req_failed': ['rate<0.01'],
  },
};

export default function () {
  const url = `${HOST}/api/sse/tracker?event_id=${EVENT_ID}`;

  const res = http.get(url, {
    headers: {
      'Accept': 'text/event-stream',
      'Cache-Control': 'no-cache',
    },
    timeout: `${CONN_HOLD_S + 10}s`,
  });

  const ok = check(res, {
    'SSE: статус 200': (r) => r.status === 200,
    'SSE: content-type text/event-stream': (r) =>
      (r.headers['Content-Type'] || '').includes('text/event-stream'),
  });

  sseErrorRate.add(!ok);
  if (res.timings) {
    sseTimeToFirstByte.add(res.timings.waiting);
  }
}
```

- [ ] **Шаг 3: Smoke-проверка синтаксиса**

```powershell
k6 inspect tests/load/sse_test.js
```

Ожидаемый вывод: информация о скрипте без ошибок синтаксиса.

- [ ] **Шаг 4: Коммит**

```powershell
git add tests/load/sse_test.js
git commit -m "feat: k6 SSE нагрузочный тест — /api/sse/tracker"
```

---

## Task 4: Создать скрипт мониторинга VPS

**Files:**
- Create: `tests/load/monitor_vps.sh`

- [ ] **Шаг 1: Создать tests/load/monitor_vps.sh**

```bash
#!/bin/bash
# Мониторинг CPU/RAM/TCP-соединений на VPS во время нагрузочного теста.
# Запускать НА VPS в отдельной SSH-сессии параллельно с тестом.
#
# Использование:
#   chmod +x monitor_vps.sh
#   ./monitor_vps.sh L1
#
# Лог сохраняется в vps_monitor_L1.csv — скопировать на тест-машину после теста:
#   scp km@<VPS_IP>:~/vps_monitor_L1.csv reports/load/YYYY-MM-DD/

set -e

LEVEL="${1:-test}"
LOG="vps_monitor_${LEVEL}.csv"

echo "timestamp,cpu_pct,ram_used_mb,ram_total_mb,tcp_established,tcp_time_wait" > "$LOG"
echo "Мониторинг запущен → $LOG (Ctrl+C для остановки)"
echo "Уровень: $LEVEL"

while true; do
    ts=$(date +%s)
    # CPU% — берём idle из vmstat, вычитаем из 100
    cpu_idle=$(vmstat 1 2 | tail -1 | awk '{print $15}')
    cpu=$((100 - cpu_idle))
    # RAM
    ram_used=$(free -m | awk '/^Mem:/{print $3}')
    ram_total=$(free -m | awk '/^Mem:/{print $2}')
    # TCP соединения
    tcp_est=$(ss -s 2>/dev/null | awk '/estab/{gsub(",","",$4); print $4+0}')
    tcp_tw=$(ss -s 2>/dev/null | awk '/time.wait/{gsub(",","",$4); print $4+0}')

    echo "${ts},${cpu:-0},${ram_used:-0},${ram_total:-0},${tcp_est:-0},${tcp_tw:-0}" >> "$LOG"
    sleep 5
done
```

- [ ] **Шаг 2: Коммит**

```powershell
git add tests/load/monitor_vps.sh
git commit -m "feat: скрипт мониторинга VPS для нагрузочного теста"
```

---

## Task 5: Создать оркестратор run_load_test.py

**Files:**
- Create: `tests/load/run_load_test.py`
- Create: `reports/load/.gitkeep`

- [ ] **Шаг 1: Создать reports/load/.gitkeep**

```powershell
New-Item -ItemType Directory -Force reports\load
New-Item -ItemType File -Force reports\load\.gitkeep
```

- [ ] **Шаг 2: Создать tests/load/run_load_test.py**

```python
"""
Оркестратор нагрузочного тестирования KM_track.
Запускает Locust + k6 одновременно для каждого уровня L1→L4.

Запуск:
    python tests/load/run_load_test.py
    python tests/load/run_load_test.py --level L1   # только один уровень
    python tests/load/run_load_test.py --smoke       # smoke (5 пользователей, 1 мин)

Переменные окружения:
    LOAD_TEST_HOST          — хост (по умолч. https://analytics.krasmarafon.ru)
    LIVE_EVENT_ID           — event_id live-гонки (по умолч. 106)
    LOCUST_ADMIN_PASSWORD   — пароль бизнес-аналитики (по умолч. km2026admin)
"""

import argparse
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

HOST = os.environ.get("LOAD_TEST_HOST", "https://analytics.krasmarafon.ru")
LIVE_EVENT_ID = os.environ.get("LIVE_EVENT_ID", "106")
ADMIN_PASSWORD = os.environ.get("LOCUST_ADMIN_PASSWORD", "km2026admin")

LEVELS = [
    {"name": "L1", "locust_users": 165,  "k6_vus": 335,  "spawn_rate": 20},
    {"name": "L2", "locust_users": 665,  "k6_vus": 1335, "spawn_rate": 40},
    {"name": "L3", "locust_users": 1665, "k6_vus": 3335, "spawn_rate": 80},
    {"name": "L4", "locust_users": 3335, "k6_vus": 6665, "spawn_rate": 100},
]

SMOKE = {"name": "smoke", "locust_users": 5, "k6_vus": 10, "spawn_rate": 5}

DURATION = "8m"
PAUSE_BETWEEN_S = 120  # 2 минуты

REPO_ROOT = Path(__file__).parent.parent.parent


def run_level(level: dict, report_dir: Path, duration: str = DURATION) -> bool:
    name = level["name"]
    total = level["locust_users"] + level["k6_vus"]

    print(f"\n{'=' * 60}")
    print(f"  Уровень {name}: {level['locust_users']} HTTP + {level['k6_vus']} SSE = {total} пользователей")
    print(f"  Хост: {HOST}  |  Live event_id: {LIVE_EVENT_ID}")
    print(f"{'=' * 60}")

    report_dir.mkdir(parents=True, exist_ok=True)
    locust_report = report_dir / f"locust_{name}.html"
    k6_report = report_dir / f"k6_{name}.json"

    locust_cmd = [
        sys.executable, "-m", "locust",
        "-f", str(REPO_ROOT / "locustfile.py"),
        "--host", HOST,
        "--users", str(level["locust_users"]),
        "--spawn-rate", str(level["spawn_rate"]),
        "--run-time", duration,
        "--html", str(locust_report),
        "--headless",
    ]

    k6_cmd = [
        "k6", "run",
        str(REPO_ROOT / "tests" / "load" / "sse_test.js"),
        "--vus", str(level["k6_vus"]),
        "--duration", duration,
        "--out", f"json={k6_report}",
        "--env", f"K6_HOST={HOST}",
        "--env", f"K6_EVENT_ID={LIVE_EVENT_ID}",
    ]

    env = {
        **os.environ,
        "LOCUST_LIVE_EVENT_ID": LIVE_EVENT_ID,
        "LOCUST_ADMIN_PASSWORD": ADMIN_PASSWORD,
    }

    print(f"\n  Запуск Locust + k6 одновременно...")
    locust_proc = subprocess.Popen(locust_cmd, env=env, cwd=REPO_ROOT)
    k6_proc = subprocess.Popen(k6_cmd, cwd=REPO_ROOT)

    locust_proc.wait()
    k6_proc.wait()

    locust_ok = locust_proc.returncode == 0
    k6_ok = k6_proc.returncode == 0

    print(f"\n  Locust: {'OK' if locust_ok else 'FAIL'} (exit {locust_proc.returncode})")
    print(f"  k6:     {'OK' if k6_ok else 'FAIL'} (exit {k6_proc.returncode})")
    print(f"  Отчёты: {locust_report.name}, {k6_report.name}")

    return locust_ok and k6_ok


def main():
    parser = argparse.ArgumentParser(description="Оркестратор нагрузочного тестирования KM_track")
    parser.add_argument("--level", choices=["L1", "L2", "L3", "L4"], help="Запустить только один уровень")
    parser.add_argument("--smoke", action="store_true", help="Smoke-тест (5+10 users, 1 мин)")
    args = parser.parse_args()

    date_str = datetime.now().strftime("%Y-%m-%d")
    report_dir = REPO_ROOT / "reports" / "load" / date_str

    print(f"\nKM_track Load Test Orchestrator")
    print(f"Хост: {HOST}")
    print(f"Отчёты: {report_dir}")
    print(f"\nВАЖНО: Перед запуском войдите на VPS и запустите:")
    print(f"  ./monitor_vps.sh <LEVEL>")

    if args.smoke:
        levels = [SMOKE]
        duration = "1m"
        print(f"\nRежим: SMOKE (5+10 users, 1 мин)")
    elif args.level:
        levels = [next(l for l in LEVELS if l["name"] == args.level)]
        duration = DURATION
        print(f"\nRежим: одиночный уровень {args.level}")
    else:
        levels = LEVELS
        duration = DURATION
        print(f"\nRежим: ПОЛНЫЙ тест L1→L4 (~40 мин)")

    input("\nНажмите Enter для начала или Ctrl+C для отмены...")

    all_ok = True
    for i, level in enumerate(levels):
        ok = run_level(level, report_dir, duration)
        all_ok = all_ok and ok

        if i < len(levels) - 1:
            print(f"\n  Пауза {PAUSE_BETWEEN_S // 60} мин перед следующим уровнем...")
            time.sleep(PAUSE_BETWEEN_S)

    print(f"\n{'=' * 60}")
    status = "ВСЕ УРОВНИ ПРОЙДЕНЫ" if all_ok else "ЕСТЬ ОШИБКИ — проверь отчёты"
    print(f"  {status}")
    print(f"  Отчёты: {report_dir}")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
```

- [ ] **Шаг 3: Коммит**

```powershell
git add tests/load/run_load_test.py reports/load/.gitkeep
git commit -m "feat: оркестратор нагрузочных тестов run_load_test.py"
```

---

## Task 6: Smoke-тест против localhost

Проверяем что оба инструмента работают корректно перед запуском против VPS.

**Files:** нет изменений

- [ ] **Шаг 1: Запустить сервер локально**

```powershell
# Терминал 1
conda run -n base python -m uvicorn app:app --host 127.0.0.1 --port 8000
```

Дождаться: `Application startup complete.`

- [ ] **Шаг 2: Smoke-тест**

```powershell
# Терминал 2
$env:LOAD_TEST_HOST = "http://localhost:8000"
conda run -n base python tests/load/run_load_test.py --smoke
```

Ожидаемый вывод:
```
  Уровень smoke: 5 HTTP + 10 SSE = 15 пользователей
  Locust: OK (exit 0)
  k6:     OK (exit 0)
```

- [ ] **Шаг 3: Проверить отчёт Locust**

Открыть `reports/load/YYYY-MM-DD/locust_smoke.html`. Должны быть все 5 классов, Failure Rate = 0%.

- [ ] **Шаг 4: Проверить k6 вывод**

В выводе k6 убедиться что:
- `sse_error_rate` = 0%
- `http_req_failed` = 0%
- `sse_ttfb_ms` присутствует

---

## Task 7: Применить конфигурацию VPS для высокой нагрузки

Без этих изменений VPS упрётся в системные лимиты уже на L1 (1024 open files по умолчанию).

**Files:**
- Modify: `deploy/nginx.conf`
- Modify: `deploy/km_track.service`

- [ ] **Шаг 1: Обновить deploy/nginx.conf**

Найти начало файла (перед первым `server {`) и добавить/обновить блоки верхнего уровня:

```nginx
# --- Добавить в начало файла, ДО блоков server {} ---
worker_processes auto;
worker_rlimit_nofile 65535;

events {
    worker_connections 65535;
    use epoll;
    multi_accept on;
}

http {
    sendfile on;
    tcp_nopush on;
    tcp_nodelay on;
    keepalive_timeout 65;
    types_hash_max_size 2048;

    # Лимиты запросов (защита от DDoS)
    limit_req_zone $binary_remote_addr zone=api:10m rate=30r/s;
    limit_conn_zone $binary_remote_addr zone=addr:10m;
```

В блок `location /api/sse/` добавить (уже есть в nginx.conf, дополнить):

```nginx
    location /api/sse/ {
        proxy_pass          http://127.0.0.1:8000;
        proxy_http_version  1.1;
        proxy_set_header    Connection "";
        proxy_buffering     off;
        proxy_cache         off;
        proxy_read_timeout  3600s;
        proxy_set_header    Host $host;
        proxy_set_header    X-Real-IP $remote_addr;
        proxy_set_header    X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header    X-Forwarded-Proto $scheme;
        # Ограничение одновременных SSE-соединений с одного IP
        limit_conn addr 50;
    }
```

В блок `location /` добавить rate limiting:

```nginx
    location / {
        limit_req zone=api burst=50 nodelay;
        proxy_pass http://127.0.0.1:8000;
        # ... остальное без изменений
    }
```

- [ ] **Шаг 2: Обновить deploy/km_track.service**

Добавить в секцию `[Service]`:

```ini
[Service]
# ... существующие строки без изменений ...
LimitNOFILE=65535
LimitNPROC=65535
```

- [ ] **Шаг 3: Коммит**

```powershell
git add deploy/nginx.conf deploy/km_track.service
git commit -m "perf: nginx worker_connections 65535 + LimitNOFILE для высокой нагрузки"
```

- [ ] **Шаг 4: Деплой на VPS**

```bash
# На VPS:
cd /opt/km_track
git pull origin Map

# Применить nginx конфиг
sudo cp deploy/nginx.conf /etc/nginx/nginx.conf
sudo nginx -t  # проверить синтаксис — должно быть "syntax is ok"
sudo systemctl reload nginx

# Применить systemd сервис
sudo cp deploy/km_track.service /etc/systemd/system/km_track.service
sudo systemctl daemon-reload
sudo systemctl restart km_track

# Применить системные лимиты сокетов
sudo sysctl -w net.core.somaxconn=65535
sudo sysctl -w net.ipv4.tcp_tw_reuse=1
sudo sysctl -w net.core.netdev_max_backlog=65535
# Сделать постоянными:
echo "net.core.somaxconn=65535
net.ipv4.tcp_tw_reuse=1
net.core.netdev_max_backlog=65535" | sudo tee -a /etc/sysctl.conf
sudo sysctl -p
```

- [ ] **Шаг 5: Проверить что VPS работает**

```bash
# На VPS:
sudo systemctl status km_track
curl -s http://localhost:8000/health
# Ожидаемо: {"status":"ok",...}

# Проверить лимиты:
ulimit -n
# Ожидаемо: 65535
ss -s
# Проверить что нет ошибок
```

---

## Task 8: Запустить L1 против VPS — первый production-тест

- [ ] **Шаг 1: Открыть SSH на VPS для мониторинга**

```bash
# SSH-сессия 2 (параллельная):
scp tests/load/monitor_vps.sh km@<VPS_IP>:~/
ssh km@<VPS_IP>
chmod +x monitor_vps.sh
./monitor_vps.sh L1
```

- [ ] **Шаг 2: Запустить L1**

```powershell
# На тест-машине:
conda run -n base python tests/load/run_load_test.py --level L1
```

- [ ] **Шаг 3: Скопировать лог мониторинга с VPS**

После завершения L1 (Ctrl+C в мониторинге):
```bash
# На VPS:
# Ctrl+C в monitor_vps.sh

# На тест-машине:
scp km@<VPS_IP>:~/vps_monitor_L1.csv reports/load/YYYY-MM-DD/
```

- [ ] **Шаг 4: Проанализировать результаты L1**

Проверить в `reports/load/YYYY-MM-DD/locust_L1.html`:
- Failure Rate: должен быть < 1%
- p95 latency `/api/event-results[live]`: цель < 500мс
- Если есть ошибки 503/502: проблема с Uvicorn workers или nginx upstream

Проверить в `reports/load/YYYY-MM-DD/k6_L1.json`:
```powershell
# Быстрый просмотр ключевых метрик:
Get-Content reports/load/YYYY-MM-DD/k6_L1.json | Select-String "sse_error_rate|sse_ttfb|http_req_failed"
```

- [ ] **Шаг 5: Если есть проблемы — применить фиксы**

| Симптом | Диагноз | Фикс |
|---------|---------|------|
| 502 Bad Gateway | Uvicorn не успевает | Увеличить workers в km_track.service: `--workers 4` |
| CPU > 90% на L1 | Нужен апгрейд VPS | Задокументировать — рекомендация для отчёта |
| RAM > 80% на L1 | Нужен апгрейд VPS | Задокументировать — рекомендация для отчёта |
| `sse_error_rate` > 1% | nginx worker_connections мало | Проверить nginx error.log: `sudo tail -100 /var/log/nginx/error.log` |
| Много TIME_WAIT | tcp_tw_reuse не применился | Повторить `sudo sysctl -w net.ipv4.tcp_tw_reuse=1` |

---

## Task 9: Запустить L2–L4 и собрать все результаты

- [ ] **Шаг 1: Запустить L2**

```bash
# На VPS — мониторинг:
./monitor_vps.sh L2
```
```powershell
# Тест-машина:
conda run -n base python tests/load/run_load_test.py --level L2
```

- [ ] **Шаг 2: Скопировать лог L2 с VPS**

```powershell
scp km@<VPS_IP>:~/vps_monitor_L2.csv reports/load/YYYY-MM-DD/
```

- [ ] **Шаг 3: Запустить L3 и L4 аналогично (повторить шаги 1-2 для каждого уровня)**

Если VPS деградирует на L2 (CPU > 90% или Failure Rate > 10%) — фиксируем это как "точку отказа" и всё равно запускаем L3/L4 для документирования характера деградации.

- [ ] **Шаг 4: Скопировать все отчёты**

```powershell
# Проверить что все файлы на месте:
Get-ChildItem reports/load/YYYY-MM-DD/
# Должны быть: locust_L1-L4.html, k6_L1-L4.json, vps_monitor_L1-L4.csv
```

---

## Task 10: Написать итоговый отчёт

**Files:**
- Create: `reports/load/YYYY-MM-DD/load-test-report.md`

- [ ] **Шаг 1: Создать отчёт по шаблону**

Создать `reports/load/YYYY-MM-DD/load-test-report.md`:

```markdown
# Отчёт нагрузочного тестирования KM_track

**Дата:** YYYY-MM-DD  
**Хост:** analytics.krasmarafon.ru  
**VPS:** nic.ru [тариф], [vCPU] vCPU / [RAM] GB RAM

---

## 1. Методология

- **HTTP-нагрузка:** Locust 2.x, 5 классов пользователей
  (TrackerUser 55% / ResultsUser 25% / StartListUser 10% / SearchUser 5% / BusinessUser 5%)
- **SSE-нагрузка:** k6, каждый VU держит соединение `/api/sse/tracker` 30 сек
- **Соотношение:** HTTP : SSE = 1 : 2 (трекер доминирует)
- **Профиль:** 2 мин прогрев → 5 мин стабильная нагрузка → 1 мин спад
- **Уровни:** L1=500, L2=2000, L3=5000, L4=10000 пользователей

---

## 2. Сводная таблица результатов

| Уровень | Всего | RPS | p95 ms | Errors% | CPU% | RAM MB | TCP conn | SSE err% |
|---------|-------|-----|--------|---------|------|--------|----------|---------|
| L1 | 500 | | | | | | | |
| L2 | 2000 | | | | | | | |
| L3 | 5000 | | | | | | | |
| L4 | 10000 | | | | | | | |

_Заполнить из отчётов Locust (RPS, p95, Errors) и vps_monitor CSV (CPU, RAM, TCP)._

---

## 3. Точка отказа

**Уровень деградации:** L[N]  
**Критерий:** [что именно упёрлось: CPU / RAM / nginx connections / Uvicorn]  
**Поведение:** [описание — 502 ошибки / медленный рост latency / обрыв SSE]

---

## 4. Узкие места

[Заполнить по результатам — CPU-bound / RAM / network / DB latency]

---

## 5. Применённые оптимизации

| # | Изменение | Коммит | Эффект |
|---|-----------|--------|--------|
| 1 | nginx worker_connections 65535 | [hash] | [измеренный эффект] |
| 2 | LimitNOFILE=65535 в systemd | [hash] | [измеренный эффект] |
| 3 | sysctl tcp_tw_reuse=1 | — | снижение TIME_WAIT сокетов |

---

## 6. Рекомендации по конфигурации VPS

### Для 500 пользователей (текущий SSD-1)

| Параметр | Значение |
|----------|---------|
| Тариф | SSD-1 (1 vCPU / 1 GB RAM) |
| Uvicorn workers | 2 |
| nginx worker_connections | 65535 |
| LimitNOFILE | 65535 |

### Для 2000 пользователей

| Параметр | Значение |
|----------|---------|
| Тариф | [рекомендуемый тариф по результатам теста] |
| ... | ... |

### Для 10 000 пользователей (цель ТЗ)

| Параметр | Значение |
|----------|---------|
| Тариф | [рекомендуемый тариф] |
| ... | ... |
```

- [ ] **Шаг 2: Заполнить таблицы данными из отчётов**

Из Locust HTML (открыть в браузере):
- RPS — поле "Requests/s" в итоговой таблице
- p95 — колонка "95%ile" для `/api/event-results[live]`
- Errors% — колонка "Failures"

Из k6 JSON (`k6_L1.json` и т.д.):
```powershell
# Быстрый парсинг ключевых метрик:
$json = Get-Content reports/load/YYYY-MM-DD/k6_L1.json | ConvertFrom-Json
# Смотреть поля: metrics.sse_error_rate, metrics.sse_ttfb_ms, metrics.http_req_failed
```

Из `vps_monitor_L1.csv`:
```powershell
Import-Csv reports/load/YYYY-MM-DD/vps_monitor_L1.csv | 
  Measure-Object -Property cpu_pct -Maximum -Average |
  Select-Object Maximum, Average
```

- [ ] **Шаг 3: Финальный коммит**

```powershell
git add reports/load/ tests/load/
git commit -m "test: нагрузочное тестирование L1-L4 — отчёты и результаты"
git push origin Map
```

---

## Самопроверка плана

**Покрытие спека:**
- ✅ VPS как целевой хост
- ✅ 5 классов HTTP-пользователей (TrackerUser 55%, ResultsUser 25%, StartListUser 10%, SearchUser 5%, BusinessUser 5%)
- ✅ SSE через k6 с метриками TTFB и error rate
- ✅ 4 уровня: L1=500, L2=2000, L3=5000, L4=10000
- ✅ Соотношение HTTP:SSE = 1:2
- ✅ Мониторинг VPS (CPU/RAM/TCP)
- ✅ Конфигурация VPS: nginx worker_connections, LimitNOFILE, sysctl
- ✅ Итоговый отчёт с таблицей результатов и рекомендациями

**Константы и типы согласованы:**
- `LIVE_EVENT_ID` используется одинаково в locustfile.py, sse_test.js (через K6_EVENT_ID) и run_load_test.py
- Пароль `LOCUST_ADMIN_PASSWORD` / `ADMIN_PASSWORD` — одно окружение, одна переменная
- Пути к отчётам единообразны: `reports/load/YYYY-MM-DD/`
