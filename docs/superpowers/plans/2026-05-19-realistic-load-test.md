# Realistic Load Test + /history SSE Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Добавить live SSE-уведомления на страницу /history и реалистичный нагрузочный тест с 3000 симулированными участниками забега и двумя SSE-каналами (tracker + notify).

**Architecture:** История участия подписывается на `/api/sse/notify` и показывает бейдж при новых финишах. `setup_race_data.py` вставляет/удаляет 3000 тест-бегунов в `results` для event_id=104 (bibs 90001–93000). `race_simulator.py` запускается параллельно с тестом и имитирует финиши/регистрации, активируя `_results_watcher` и `_startlist_watcher`. `sse_load_remote.py` получает `--notify-vus` и гонит оба типа SSE в одном asyncio event loop на VPS. `run_load_test.py --realistic` оркестрирует все компоненты.

**Tech Stack:** paramiko SSH, mysql-connector-python (на VPS), asyncio raw TCP, locust, Python 3.12

---

### Task 1: SSE live badge на странице /history

**Files:**
- Modify: `templates/history.html:68` — добавить script tag для realtime.js + div бейджа
- Modify: `static/js/history.js:152` — добавить SSEClient подписку

- [ ] **Step 1: Добавить realtime.js и бейдж в history.html**

В `templates/history.html` найти строку 68:
```html
    <script src="/static/js/history.js?v=1"></script>
```
Заменить на:
```html
    <script src="/static/js/realtime.js?v=1"></script>
    <script src="/static/js/history.js?v=2"></script>
```

Найти в том же файле строку с `<div class="container">` и добавить бейдж сразу после неё (перед `<h1>`):
```html
        <div id="live-race-badge" style="display:none; background:#e8f5e9; border:1px solid #4caf50; border-radius:6px; padding:8px 16px; margin-bottom:16px; color:#2e7d32; font-size:0.9rem;"></div>
```

- [ ] **Step 2: Добавить SSEClient в history.js**

В `static/js/history.js` найти последние 2 строки:
```javascript
    searchInput.focus();
});
```
Заменить на:
```javascript
    searchInput.focus();

    new SSEClient('/api/sse/notify', {
        results_updated: () => {
            const badge = document.getElementById('live-race-badge');
            if (badge) {
                badge.style.display = 'block';
                badge.textContent = '🟢 Появились новые финиши в текущем забеге';
            }
        }
    });
});
```

- [ ] **Step 3: Проверить в браузере**

Открыть http://localhost:8000/history → DevTools → Network → отфильтровать EventStream.
Должно быть соединение к `/api/sse/notify` со статусом 200 (pending — SSE держит соединение).

- [ ] **Step 4: Commit**

```bash
git add templates/history.html static/js/history.js
git commit -m "feat: SSE live badge на /history — уведомление о новых финишах"
```

---

### Task 2: setup_race_data.py — генерация и очистка тест-данных

**Files:**
- Create: `tests/load/setup_race_data.py`

**Context:** event_id=104 ("Ночной забег"), 5 км, checkpoint_distances=[0, 2.5, 5.0].
Реальные bibs: 0–1106. Реальные client_id: до 34137.
Тест-данные: bibs 90001–93000, client_id 999000001–999003000 — не пересекаются.
Распределение: 40% до KT1, 35% прошли KT1, 25% финишировали.

- [ ] **Step 1: Создать setup_race_data.py**

Создать `tests/load/setup_race_data.py`:

```python
"""
Генератор тестовых данных для нагрузочного теста.
Вставляет 3000 тест-бегунов в event_id=104 (bibs 90001-93000) и удаляет их после теста.

Использование:
    python tests/load/setup_race_data.py --setup
    python tests/load/setup_race_data.py --teardown
"""

import argparse
import sys
import paramiko

VPS_HOST = "VPS_HOST"
VPS_USER = "root"
VPS_PASSWORD = "VPS_PASSWORD"

N_RUNNERS = 3000
EVENT_ID = 104
START_BIB = 90001


SETUP_SCRIPT = r"""
import mysql.connector
import random

random.seed(42)

conn = mysql.connector.connect(
    host="127.0.0.1", user="km_analytic",
    password="CneZbvlOS2H-BLsQ", database="krasmarafon"
)
cur = conn.cursor()

N = 3000
EVENT_ID = 104
START_BIB = 90001

cur.execute(
    "DELETE FROM results WHERE event_id=%s AND start_number BETWEEN %s AND %s",
    (EVENT_ID, START_BIB, START_BIB + N - 1)
)
conn.commit()

surnames = ["Иванов", "Петров", "Сидоров", "Козлов", "Новиков",
            "Морозов", "Попов", "Лебедев", "Соколов", "Федоров"]
names_m = ["Александр", "Дмитрий", "Сергей", "Андрей", "Максим", "Алексей", "Иван"]
names_f = ["Анна", "Мария", "Елена", "Ольга", "Наталья", "Татьяна", "Ирина"]

rows = []
for i in range(N):
    bib = START_BIB + i
    client_id = 999000001 + i
    is_male = (i % 10) < 7
    sex = "мужской" if is_male else "женский"
    name = random.choice(names_m if is_male else names_f)
    surname = "ТЕСТ_" + random.choice(surnames)
    category = "мужчины до 49 лет" if is_male else "женщины до 49 лет"

    stage = i % 100
    kt1 = None
    gun_finish = None
    clear_finish = None
    race_status = "Not started"

    if stage < 40:
        pass  # 40%: до KT1 (0-2.5 км)
    elif stage < 75:
        # 35%: прошли KT1 (2.5 км), темп 4:30-8:00 мин/км
        pace_sec = random.randint(270, 480)
        s = int(2.5 * pace_sec)
        kt1 = f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}"
    else:
        # 25%: финишировали (5 км), темп 4:30-7:00 мин/км
        pace_sec = random.randint(270, 420)
        s1 = int(2.5 * pace_sec)
        s2 = int(5.0 * pace_sec)
        kt1 = f"{s1 // 3600:02d}:{(s1 % 3600) // 60:02d}:{s1 % 60:02d}"
        clear_finish = f"{s2 // 3600:02d}:{(s2 % 3600) // 60:02d}:{s2 % 60:02d}"
        gun_sec = s2 + random.randint(0, 10)
        gun_finish = f"{gun_sec // 3600:02d}:{(gun_sec % 3600) // 60:02d}:{gun_sec % 60:02d}"
        race_status = "Finished"

    rows.append((
        surname, name, "1990-01-01", client_id, EVENT_ID,
        sex, bib, category, race_status,
        "00:00:00", "00:00:00",
        gun_finish, clear_finish,
        kt1, None,
    ))

cur.executemany("""
    INSERT INTO results (
        surname, name, birthday, client_id, event_id,
        sex, start_number, category, race_status,
        time_gun_start, time_clear_start,
        time_gun_finish, time_clear_finish,
        time_clear_kt1, time_clear_kt2
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
""", rows)
conn.commit()
print(f"OK: inserted {N} test runners for event_id={EVENT_ID}, bibs {START_BIB}-{START_BIB+N-1}")
cur.close()
conn.close()
"""

TEARDOWN_SCRIPT = r"""
import mysql.connector

conn = mysql.connector.connect(
    host="127.0.0.1", user="km_analytic",
    password="CneZbvlOS2H-BLsQ", database="krasmarafon"
)
cur = conn.cursor()
cur.execute(
    "DELETE FROM results WHERE event_id=%s AND start_number BETWEEN %s AND %s",
    (104, 90001, 93000)
)
deleted = cur.rowcount
conn.commit()
cur.execute("DELETE FROM leads WHERE event_id=104 AND client_id >= 999900000")
leads_deleted = cur.rowcount
conn.commit()
cur.close()
conn.close()
print(f"OK: deleted {deleted} test runners, {leads_deleted} sim leads")
"""


def _ssh_connect() -> paramiko.SSHClient:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(VPS_HOST, username=VPS_USER, password=VPS_PASSWORD, timeout=30)
    return client


def run_script(script: str, description: str) -> bool:
    print(f"\n{description}...")
    client = _ssh_connect()
    sftp = client.open_sftp()
    with sftp.open("/tmp/race_data_op.py", "w") as f:
        f.write(script)
    sftp.close()
    python = "/opt/km_track/venv/bin/python3"
    stdin, stdout, stderr = client.exec_command(f"{python} /tmp/race_data_op.py", timeout=60)
    out = stdout.read().decode("utf-8", errors="replace").strip()
    err = stderr.read().decode("utf-8", errors="replace").strip()
    exit_code = stdout.channel.recv_exit_status()
    client.close()
    if out:
        print(f"  {out}")
    if err:
        print(f"  STDERR: {err}")
    return exit_code == 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--setup", action="store_true", help="Вставить 3000 тест-бегунов")
    parser.add_argument("--teardown", action="store_true", help="Удалить тест-данные")
    args = parser.parse_args()

    if args.setup:
        ok = run_script(SETUP_SCRIPT, f"Вставка {N_RUNNERS} тест-бегунов в event_id={EVENT_ID}")
    elif args.teardown:
        ok = run_script(TEARDOWN_SCRIPT, "Очистка тест-данных")
    else:
        parser.print_help()
        sys.exit(1)

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Проверить --setup**

```bash
python tests/load/setup_race_data.py --setup
```
Ожидаемый вывод:
```
Вставка 3000 тест-бегунов в event_id=104...
  OK: inserted 3000 test runners for event_id=104, bibs 90001-93000
```

- [ ] **Step 3: Проверить --teardown**

```bash
python tests/load/setup_race_data.py --teardown
```
Ожидаемый вывод:
```
Очистка тест-данных...
  OK: deleted 3000 test runners, 0 sim leads
```

- [ ] **Step 4: Commit**

```bash
git add tests/load/setup_race_data.py
git commit -m "feat: setup_race_data.py — генерация/очистка 3000 тест-бегунов для event_id=104"
```

---

### Task 3: race_simulator.py — симулятор хода забега

**Files:**
- Create: `tests/load/race_simulator.py`

**Context:** Запускается параллельно с нагрузочным тестом. Каждые 30с UPDATE 10 тест-бегунов → `race_status='Finished'`, `time_clear_finish` → `_results_watcher` видит изменение COUNT(*) → Redis publish `results_updated` → notify SSE клиенты получают событие. Каждые 60с INSERT 1 лид → `_startlist_watcher` → `startlist_updated`.

- [ ] **Step 1: Создать race_simulator.py**

Создать `tests/load/race_simulator.py`:

```python
"""
Симулятор хода забега для нагрузочного теста.
Каждые 30с "финишируют" 10 тест-бегунов → results_updated SSE событие.
Каждые 60с регистрируется новый участник → startlist_updated SSE событие.

Запуск:
    python tests/load/race_simulator.py --duration 480
"""

import argparse
import sys
import time
import paramiko

VPS_HOST = "VPS_HOST"
VPS_USER = "root"
VPS_PASSWORD = "VPS_PASSWORD"

SIMULATOR_SCRIPT = r"""
import mysql.connector
import time
import sys

duration = int(sys.argv[1]) if len(sys.argv) > 1 else 480

conn = mysql.connector.connect(
    host="127.0.0.1", user="km_analytic",
    password="CneZbvlOS2H-BLsQ", database="krasmarafon"
)
cur = conn.cursor()

start = time.time()
tick = 0
print(f"Simulator started, duration={duration}s", flush=True)

while time.time() - start < duration:
    # Финишируют 10 тест-бегунов → _results_watcher видит изменение COUNT(*)
    cur.execute("""
        UPDATE results
        SET race_status='Finished',
            time_gun_finish='00:25:00',
            time_clear_finish='00:25:00'
        WHERE event_id=104
          AND start_number BETWEEN 90001 AND 93000
          AND race_status='Not started'
          AND time_clear_kt1 IS NOT NULL
        LIMIT 10
    """)
    conn.commit()
    finishes = cur.rowcount

    # Каждые 60с (каждый 2й тик): новая регистрация → _startlist_watcher
    new_lead = 0
    if tick % 2 == 0:
        client_id = 999900000 + tick
        cur.execute("""
            INSERT INTO leads (
                surname, name, sex, city, birthday,
                event_name, event_distance, event_year, client_id, event_id,
                email, phone, products, status, is_new, is_new_event
            ) VALUES (
                'ТЕСТ_Симуляция', 'Участник', 'мужской', 'Красноярск', '1990-01-01',
                'Ночной забег', '5 км', 2026, %s, 104,
                'test@test.ru', '+7-000-000-0000', '5 км Ночной забег', 0, 0, 0
            )
        """, (client_id,))
        conn.commit()
        new_lead = 1

    elapsed = time.time() - start
    print(f"  [{elapsed:.0f}s] +{finishes} finishes, +{new_lead} lead", flush=True)
    tick += 1
    time.sleep(30)

cur.close()
conn.close()
print("Simulator stopped", flush=True)
"""


def _ssh_connect() -> paramiko.SSHClient:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(VPS_HOST, username=VPS_USER, password=VPS_PASSWORD, timeout=30)
    client.get_transport().set_keepalive(30)
    return client


def run_simulator(duration: int) -> bool:
    print(f"\nСтарт симулятора забега (duration={duration}s)...")
    client = _ssh_connect()
    sftp = client.open_sftp()
    with sftp.open("/tmp/race_simulator.py", "w") as f:
        f.write(SIMULATOR_SCRIPT)
    sftp.close()
    python = "/opt/km_track/venv/bin/python3"
    stdin, stdout, stderr = client.exec_command(
        f"{python} /tmp/race_simulator.py {duration}", timeout=duration + 30
    )
    stdout.channel.settimeout(None)
    for line in iter(lambda: stdout.readline(), ""):
        print(f"  [sim] {line}", end="", flush=True)
    exit_code = stdout.channel.recv_exit_status()
    client.close()
    return exit_code == 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration", type=int, default=480)
    args = parser.parse_args()
    ok = run_simulator(args.duration)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Проверить симулятор (35с)**

Предварительно: `python tests/load/setup_race_data.py --setup`

```bash
python tests/load/race_simulator.py --duration 35
```
Ожидаемый вывод:
```
Старт симулятора забега (duration=35s)...
  [sim] Simulator started, duration=35s
  [sim]   [0s] +10 finishes, +1 lead
  [sim]   [30s] +10 finishes, +0 lead
  [sim] Simulator stopped
```

Очистить: `python tests/load/setup_race_data.py --teardown`

- [ ] **Step 3: Commit**

```bash
git add tests/load/race_simulator.py
git commit -m "feat: race_simulator.py — симулирует финиши и регистрации во время теста"
```

---

### Task 4: Notify SSE VUs в sse_load_remote.py

**Files:**
- Modify: `tests/load/sse_load_remote.py`

**Context:** Добавляем `--notify-vus N`. Скрипт на VPS получает общую функцию `_sse_client(request, ...)`, которую используют и tracker, и notify VU — отличаются только HTTP-запросом. Оба типа стартуют в одном asyncio event loop. Прогресс и итоги выводятся раздельно.

- [ ] **Step 1: Заменить ASYNC_SSE_SCRIPT в sse_load_remote.py**

В `tests/load/sse_load_remote.py` найти переменную `ASYNC_SSE_SCRIPT = '''\` и заменить её целиком (до закрывающего `'''`) на:

```python
ASYNC_SSE_SCRIPT = '''\
import asyncio, sys, time, random, argparse

HOST = "127.0.0.1"
PORT = 8000
SSE_PATH = "/api/sse/tracker?event_id=104"
NOTIFY_PATH = "/api/sse/notify"
PASS_THRESHOLD = 95

SSE_REQUEST = (
    f"GET {SSE_PATH} HTTP/1.1\\r\\n"
    f"Host: {HOST}:{PORT}\\r\\n"
    f"Accept: text/event-stream\\r\\n"
    f"Cache-Control: no-cache\\r\\n"
    f"Connection: keep-alive\\r\\n"
    f"\\r\\n"
).encode()

NOTIFY_REQUEST = (
    f"GET {NOTIFY_PATH} HTTP/1.1\\r\\n"
    f"Host: {HOST}:{PORT}\\r\\n"
    f"Accept: text/event-stream\\r\\n"
    f"Cache-Control: no-cache\\r\\n"
    f"Connection: keep-alive\\r\\n"
    f"\\r\\n"
).encode()


async def _sse_client(vu_id, request, hold_seconds, results):
    jitter = random.randint(0, 30)
    total_hold = hold_seconds + jitter
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(HOST, PORT), timeout=15
        )
    except Exception as e:
        results[vu_id] = f"conn_err:{type(e).__name__}"
        return
    try:
        writer.write(request)
        await writer.drain()
        start = time.monotonic()
        connected = False
        deadline_connect = start + 60
        buf = b""
        while time.monotonic() < deadline_connect:
            try:
                chunk = await asyncio.wait_for(reader.read(4096), timeout=5)
            except asyncio.TimeoutError:
                break
            if not chunk:
                break
            buf += chunk
            if b"connected" in buf:
                connected = True
                break
        if not connected:
            results[vu_id] = "no_connected"
            return
        while time.monotonic() - start < total_hold:
            try:
                chunk = await asyncio.wait_for(reader.read(4096), timeout=30)
                if not chunk:
                    break
            except asyncio.TimeoutError:
                pass
        results[vu_id] = "held"
    except Exception as e:
        results[vu_id] = f"err:{type(e).__name__}"
    finally:
        try:
            writer.close()
            await asyncio.wait_for(writer.wait_closed(), timeout=2)
        except Exception:
            pass


async def progress_reporter(t_res, n_res, vus, notify_vus, t_start, interval=60):
    while True:
        await asyncio.sleep(interval)
        t_held = sum(1 for v in t_res.values() if v == "held")
        n_held = sum(1 for v in n_res.values() if v == "held")
        elapsed = time.monotonic() - t_start
        print(
            f"  [{elapsed:.0f}s] tracker={len(t_res)}/{vus} held={t_held} active={vus - len(t_res)}"
            f" | notify={len(n_res)}/{notify_vus} held={n_held} active={notify_vus - len(n_res)}",
            flush=True
        )


async def run_load(vus, notify_vus, hold_seconds):
    print(f"Starting {vus} tracker SSE + {notify_vus} notify SSE VUs, hold {hold_seconds}+0..30s...")
    t_start = time.monotonic()
    tracker_results = {}
    notify_results = {}

    reporter = asyncio.create_task(
        progress_reporter(tracker_results, notify_results, vus, notify_vus, t_start)
    )
    tasks = []
    for i in range(vus):
        tasks.append(asyncio.create_task(
            _sse_client(i, SSE_REQUEST, hold_seconds, tracker_results)
        ))
        if (i + 1) % 20 == 0:
            await asyncio.sleep(1)
    for i in range(notify_vus):
        tasks.append(asyncio.create_task(
            _sse_client(i, NOTIFY_REQUEST, hold_seconds, notify_results)
        ))
        if (i + 1) % 20 == 0:
            await asyncio.sleep(1)
    await asyncio.gather(*tasks)
    reporter.cancel()

    elapsed = time.monotonic() - t_start
    t_held = sum(1 for v in tracker_results.values() if v == "held")
    n_held = sum(1 for v in notify_results.values() if v == "held")
    t_pct = t_held * 100 // vus if vus else 100
    n_pct = n_held * 100 // notify_vus if notify_vus else 100

    print("")
    print("=======================================================")
    print("SSE Load Test Results (asyncio)")
    print("=======================================================")
    print(f"Tracker SSE ({vus} VUs):       {t_held} held ({t_pct}%)")
    if notify_vus:
        print(f"Notify  SSE ({notify_vus} VUs):       {n_held} held ({n_pct}%)")
    print(f"Total time:  {elapsed:.0f}s")
    print("=======================================================")

    tracker_pass = t_held >= vus * PASS_THRESHOLD // 100
    notify_pass = notify_vus == 0 or n_held >= notify_vus * PASS_THRESHOLD // 100

    if tracker_pass and notify_pass:
        print(f"RESULT: PASSED (>={PASS_THRESHOLD}% on all channels)")
        return True
    if not tracker_pass:
        print(f"RESULT: FAILED tracker SSE ({t_pct}% < {PASS_THRESHOLD}%)")
    if not notify_pass:
        print(f"RESULT: FAILED notify SSE ({n_pct}% < {PASS_THRESHOLD}%)")
    return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--vus", type=int, default=335)
    parser.add_argument("--notify-vus", type=int, default=0)
    parser.add_argument("--hold", type=int, default=30)
    args = parser.parse_args()
    ok = asyncio.run(run_load(args.vus, args.notify_vus, args.hold))
    sys.exit(0 if ok else 1)
'''
```

- [ ] **Step 2: Обновить run_remote() для поддержки notify_vus**

В `tests/load/sse_load_remote.py` найти функцию `def run_remote(vus: int, hold_seconds: int) -> bool:` и заменить целиком:

```python
def run_remote(vus: int, hold_seconds: int, notify_vus: int = 0) -> bool:
    print(f"\nSSE load test (VPS asyncio via SSH)")
    print(f"  URL:    {SSE_URL}")
    print(f"  VUs:    {vus} tracker + {notify_vus} notify")
    print(f"  Hold:   {hold_seconds}s")

    client = _ssh_connect()
    sftp = client.open_sftp()
    with sftp.open("/tmp/sse_async_test.py", "w") as f:
        f.write(ASYNC_SSE_SCRIPT)
    sftp.close()

    python = "/opt/km_track/venv/bin/python3"
    cmd = (
        f"ulimit -n 65535 && {python} /tmp/sse_async_test.py"
        f" --vus {vus} --notify-vus {notify_vus} --hold {hold_seconds}"
    )

    print(f"\n  Running on VPS...")
    t0 = time.monotonic()
    stdin, stdout, stderr = client.exec_command(cmd)
    stdout.channel.settimeout(None)

    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace").strip()
    for line in out.splitlines():
        print(f"  {line}")
    if err:
        print(f"  STDERR: {err}")

    exit_code = stdout.channel.recv_exit_status()
    elapsed = time.monotonic() - t0
    print(f"\n  Test completed in {elapsed:.1f}s (exit={exit_code})")
    client.close()
    return exit_code == 0
```

- [ ] **Step 3: Обновить main() в sse_load_remote.py**

Найти функцию `main()` и заменить целиком:

```python
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--vus", type=int, default=335)
    parser.add_argument("--hold", type=int, default=30)
    parser.add_argument("--notify-vus", type=int, default=0)
    parser.add_argument("--smoke", action="store_true", help="10 VUs, 15s hold")
    args = parser.parse_args()

    if args.smoke:
        vus, hold, notify_vus = 7, 15, 3
    else:
        vus, hold, notify_vus = args.vus, args.hold, args.notify_vus

    ok = run_remote(vus, hold, notify_vus)
    sys.exit(0 if ok else 1)
```

- [ ] **Step 4: Проверить с notify VUs**

```bash
python tests/load/sse_load_remote.py --vus 5 --notify-vus 3 --hold 20
```
Ожидаемый вывод:
```
SSE load test (VPS asyncio via SSH)
  VUs:    5 tracker + 3 notify
  Hold:   20s

  Running on VPS...
  Starting 5 tracker SSE + 3 notify SSE VUs, hold 20+0..30s...
  ...
  Tracker SSE (5 VUs):       5 held (100%)
  Notify  SSE (3 VUs):       3 held (100%)
  RESULT: PASSED (>=95% on all channels)
```

- [ ] **Step 5: Commit**

```bash
git add tests/load/sse_load_remote.py
git commit -m "feat: sse_load_remote.py — поддержка --notify-vus для notify SSE канала"
```

---

### Task 5: Флаг --realistic в run_load_test.py

**Files:**
- Modify: `tests/load/run_load_test.py`

**Context:** При `--realistic`: setup → 10s прогрев → race_simulator в фоне → тест с split SSE (2/3 tracker + 1/3 notify) → стоп симулятора → teardown. SSE split вычисляется динамически из `sse_vus`, LEVELS не меняются.

- [ ] **Step 1: Добавить --realistic в парсер аргументов**

В `tests/load/run_load_test.py` найти:
```python
    parser.add_argument("--yes", "-y", action="store_true", help="Не спрашивать подтверждение (для conda run / CI)")
    args = parser.parse_args()
```
Заменить на:
```python
    parser.add_argument("--yes", "-y", action="store_true", help="Не спрашивать подтверждение (для conda run / CI)")
    parser.add_argument("--realistic", action="store_true", help="3000 участников + notify SSE + race simulator")
    args = parser.parse_args()
```

- [ ] **Step 2: Добавить вспомогательные функции setup/teardown**

В `tests/load/run_load_test.py` после строки `REPO_ROOT = Path(__file__).parent.parent.parent` добавить:

```python

def _setup_race_data() -> bool:
    print("\n  [realistic] Генерация тест-данных (3000 бегунов)...")
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "tests" / "load" / "setup_race_data.py"), "--setup"],
        cwd=REPO_ROOT, timeout=120,
    )
    return result.returncode == 0


def _teardown_race_data() -> bool:
    print("\n  [realistic] Очистка тест-данных...")
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "tests" / "load" / "setup_race_data.py"), "--teardown"],
        cwd=REPO_ROOT, timeout=60,
    )
    return result.returncode == 0
```

- [ ] **Step 3: Обновить сигнатуру run_level() и добавить realistic-логику**

Найти:
```python
def run_level(level: dict, report_dir: Path, duration: str = DURATION) -> bool:
```
Заменить на:
```python
def run_level(level: dict, report_dir: Path, duration: str = DURATION, realistic: bool = False) -> bool:
```

Найти внутри `run_level()`:
```python
    sse_cmd = [
        sys.executable,
        str(REPO_ROOT / "tests" / "load" / "sse_load_remote.py"),
        "--vus", str(level["sse_vus"]),
        "--hold", str(hold_s),
    ]
```
Заменить на:
```python
    if realistic:
        tracker_vus = level["sse_vus"] * 2 // 3
        notify_vus = level["sse_vus"] - tracker_vus
    else:
        tracker_vus = level["sse_vus"]
        notify_vus = 0

    sse_cmd = [
        sys.executable,
        str(REPO_ROOT / "tests" / "load" / "sse_load_remote.py"),
        "--vus", str(tracker_vus),
        "--notify-vus", str(notify_vus),
        "--hold", str(hold_s),
    ]
```

- [ ] **Step 4: Добавить setup + simulator перед запуском процессов**

В `run_level()` найти строку:
```python
    print(f"\n  Запуск Locust (HTTP) + sse_load.py (SSE) одновременно...")
```
И добавить перед ней:

```python
    sim_proc = None
    sim_log = None
    if realistic:
        if not _setup_race_data():
            print("  [realistic] ОШИБКА: не удалось вставить тест-данные")
            return False
        print("  [realistic] Пауза 10с для прогрева кеша трекера...")
        time.sleep(10)
        sim_duration = _duration_to_seconds(duration) + 30
        sim_log_path = report_dir / f"simulator_{name}.txt"
        sim_log = open(sim_log_path, "w", encoding="utf-8")
        sim_proc = subprocess.Popen(
            [sys.executable, str(REPO_ROOT / "tests" / "load" / "race_simulator.py"),
             "--duration", str(sim_duration)],
            stdout=sim_log, stderr=subprocess.STDOUT, cwd=REPO_ROOT,
        )
        print(f"  [realistic] Симулятор запущен (pid={sim_proc.pid})")

```

- [ ] **Step 5: Добавить остановку симулятора и teardown после теста**

В `run_level()` найти:
```python
    locust_ok = locust_proc.returncode == 0  # строгий: любая ошибка = FAIL
    sse_ok = sse_proc.returncode == 0
```
И добавить после этих строк:

```python
    if sim_proc:
        sim_proc.terminate()
        sim_proc.wait()
    if sim_log:
        sim_log.close()
    if realistic:
        _teardown_race_data()
```

- [ ] **Step 6: Передать realistic в вызовы run_level() в main()**

В `main()` найти все вызовы `run_level(...)` и добавить `realistic=args.realistic`:

```python
# Для одного уровня:
ok = run_level(level, report_dir, realistic=args.realistic)

# Для smoke:
ok = run_level(SMOKE, report_dir, duration="1m", realistic=args.realistic)

# В цикле по всем уровням (если есть):
all_ok = all(run_level(lvl, report_dir, realistic=args.realistic) for lvl in LEVELS)
```

- [ ] **Step 7: Commit**

```bash
git add tests/load/run_load_test.py
git commit -m "feat: run_load_test.py --realistic — 3000 участников + notify SSE + race simulator"
```

---

### Task 6: Smoke-тест реалистичного режима

- [ ] **Step 1: Запустить smoke --realistic**

```bash
python tests/load/run_load_test.py --smoke --realistic --yes
```

Ожидаемый вывод (ключевые строки):
```
  [realistic] Генерация тест-данных (3000 бегунов)...
    OK: inserted 3000 test runners for event_id=104, bibs 90001-93000
  [realistic] Пауза 10с для прогрева кеша трекера...
  [realistic] Симулятор запущен (pid=XXXXX)

  Tracker SSE (7 VUs):       7 held (100%)
  Notify  SSE (3 VUs):       3 held (100%)
  RESULT: PASSED (>=95% on all channels)

  [realistic] Очистка тест-данных...
    OK: deleted 3000 test runners, N sim leads
```

- [ ] **Step 2: Убедиться что тест-данные удалены**

```bash
python -c "
import paramiko
c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect('VPS_HOST', username='root', password='VPS_PASSWORD', timeout=30)
_, out, _ = c.exec_command(\"mysql -u km_analytic -pCneZbvlOS2H-BLsQ krasmarafon -e 'SELECT COUNT(*) FROM results WHERE event_id=104 AND start_number BETWEEN 90001 AND 93000;'\", timeout=15)
print('Remaining test runners:', out.read().decode().strip())
c.close()
"
```
Ожидаемый вывод: `0`

---

### Task 7: L2 --realistic полный тест

- [ ] **Step 1: Запустить L2 --realistic**

```bash
python tests/load/run_load_test.py --level L2 --realistic --yes
```

SSE split для L2 (sse_vus=1335): tracker=890 VUs, notify=445 VUs.

Целевые показатели:
- Tracker SSE: ≥95% → ≥846/890 held
- Notify SSE: ≥95% → ≥423/445 held
- Locust HTTP: ошибки <1%
- Мониторинг: CPU пик при ramp-up, затем стабилизируется

- [ ] **Step 2: Push и сохранить отчёт**

```bash
git add reports/load/
git push origin Map
git commit -m "test: L2 realistic — нагрузочный тест с 3000 участниками и двумя SSE-каналами"
```
