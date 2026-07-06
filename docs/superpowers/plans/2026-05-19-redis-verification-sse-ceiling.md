# Redis Verification & SSE Ceiling Discovery — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Верифицировать работу Redis Pub/Sub на VPS, найти реальный SSE-потолок на текущем железе (2 CPU / ~3 GB RAM) через инкрементальные тесты с реалистичными данными, применить оптимизации (swap, nginx) и зафиксировать эффект.

**Architecture:** Redis уже развёрнут в app.py (leader election + pub/sub). Новый скрипт `run_incremental.py` запускает SSE-тесты с кастомными уровнями и мониторит RAM/CPU через SSH. Два deploy-скрипта применяют оптимизации на VPS.

**Tech Stack:** Python 3.13, paramiko, asyncio, Locust, sse_load_remote, dotenv

---

## Файловая структура

| Файл | Действие | Ответственность |
|------|----------|----------------|
| `tests/load/run_incremental.py` | Создать | Инкрементальный SSE-тест: кастомные уровни, realistic режим, VPS-мониторинг |
| `deploy/ssh_add_swap2.py` | Создать | Добавление 2 GB swap на VPS |
| `deploy/ssh_nginx_tune.py` | Создать | Снижение nginx keepalive_timeout до 15s |
| `tests/load/run_load_test.py` | Изменить | Исправить ADMIN_PASSWORD + добавить PYTHONPATH (уже сделано) |

---

## Task 1: Верификация Redis по логам VPS

**Files:**
- Create: `deploy/_verify_redis.py`

- [ ] **Step 1: Создать скрипт проверки**

```python
"""Верификация Redis leader election и pub/sub по логам VPS."""
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from deploy._vps_config import VPS_HOST, VPS_USER, VPS_PASSWORD
import paramiko

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(VPS_HOST, username=VPS_USER, password=VPS_PASSWORD, timeout=30)

def run(cmd):
    _, out, _ = client.exec_command(cmd)
    return out.read().decode("utf-8", errors="replace").strip()

print("=== Redis статус ===")
print(run("systemctl is-active redis-server && redis-cli ping"))

print("\n=== Workers подключились к Redis ===")
connected = run("journalctl -u km_track --since '10 minutes ago' --no-pager | grep 'Redis.*Connected'")
print(connected or "  (нет строк — перезапусти сервис)")
count = len([l for l in connected.splitlines() if l.strip()])
print(f"  Найдено строк Connected: {count} (ожидается 3 для workers=3)")

print("\n=== Leader election ===")
leader = run("journalctl -u km_track --since '10 minutes ago' --no-pager | grep 'Leader acquired'")
print(leader or "  (нет строк — лидер ещё не выбран или лог устарел)")
count_l = len([l for l in leader.splitlines() if l.strip()])
print(f"  Найдено строк Leader acquired: {count_l} (ожидается 1)")

print("\n=== Текущий лидер в Redis ===")
print(run("redis-cli get tracker:leader"))

print("\n=== RAM ===")
print(run("free -m | awk 'NR==2{printf \"%d/%d MB (%.1f%%)\", $3,$2,$3*100/$2}'"))

client.close()
print("\nВерификация завершена.")
```

- [ ] **Step 2: Запустить проверку**

```bash
python -m deploy._verify_redis
```

Ожидаемый результат:
```
=== Redis статус ===
active
PONG

=== Workers подключились к Redis ===
  Найдено строк Connected: 3

=== Leader election ===
  Найдено строк Leader acquired: 1

=== Текущий лидер в Redis ===
<pid одного из workers>
```

Если `Connected: 0` — сервис нужно перезапустить: `systemctl restart km_track`.

- [ ] **Step 3: Commit**

```bash
git add deploy/_verify_redis.py
git commit -m "feat: скрипт верификации Redis leader election"
```

---

## Task 2: Smoke-тест с реалистичными данными

**Files:**
- Modify: `tests/load/run_load_test.py` (уже исправлен — проверить)

- [ ] **Step 1: Проверить что ADMIN_PASSWORD читается из .env**

```bash
python -c "
from dotenv import load_dotenv; load_dotenv('.env')
import os; print('ADMIN_PASSWORD:', bool(os.environ.get('ADMIN_PASSWORD')))
"
```

Ожидается: `ADMIN_PASSWORD: True`

- [ ] **Step 2: Запустить smoke с realistic**

```bash
python tests/load/run_load_test.py --smoke --realistic --yes
```

Ожидаемый результат:
```
SSE сводка:
  RESULT: PASSED (>=95% on all channels)

Locust: OK (exit 0)
SSE:    OK (exit 0)
```

Если SSE FAIL — проверить логи VPS: `journalctl -u km_track -n 30 --no-pager`

---

## Task 3: VPS-мониторинг в реальном времени

**Files:**
- Create: `tests/load/vps_monitor.py`

- [ ] **Step 1: Создать модуль мониторинга**

```python
"""
Мониторинг RAM/CPU на VPS во время нагрузочного теста.
Запускается в фоновом потоке, пишет метрики в CSV каждые 10 секунд.

Использование:
    from tests.load.vps_monitor import VpsMonitor
    mon = VpsMonitor(report_path)
    mon.start()
    # ... тест ...
    mon.stop()
"""
import csv
import threading
import time
from pathlib import Path
import paramiko
from deploy._vps_config import VPS_HOST, VPS_USER, VPS_PASSWORD


class VpsMonitor:
    def __init__(self, csv_path: Path, interval_s: int = 10):
        self._csv_path = csv_path
        self._interval = interval_s
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._thread.join(timeout=15)

    def _run(self):
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            client.connect(VPS_HOST, username=VPS_USER, password=VPS_PASSWORD, timeout=30)
            client.get_transport().set_keepalive(30)
        except Exception as e:
            print(f"  [monitor] SSH connect failed: {e}")
            return

        with open(self._csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["ts", "ram_used_mb", "ram_total_mb", "ram_pct", "cpu_idle_pct"])

            while not self._stop.is_set():
                try:
                    _, out, _ = client.exec_command(
                        "free -m | awk 'NR==2{print $3,$2}'; "
                        "vmstat 1 2 | tail -1 | awk '{print $15}'"
                    )
                    lines = out.read().decode("utf-8", errors="replace").strip().splitlines()
                    if len(lines) >= 2:
                        parts = lines[0].split()
                        ram_used, ram_total = int(parts[0]), int(parts[1])
                        ram_pct = round(ram_used / ram_total * 100, 1)
                        cpu_idle = int(lines[1].strip())
                        ts = int(time.time())
                        writer.writerow([ts, ram_used, ram_total, ram_pct, cpu_idle])
                        f.flush()
                        print(
                            f"  [VPS] RAM {ram_used}/{ram_total}MB ({ram_pct}%) "
                            f"CPU {100-cpu_idle}%"
                        )
                except Exception as e:
                    print(f"  [monitor] error: {e}")

                self._stop.wait(self._interval)

        client.close()
```

- [ ] **Step 2: Commit**

```bash
git add tests/load/vps_monitor.py
git commit -m "feat: VPS RAM/CPU монитор для нагрузочных тестов"
```

---

## Task 4: run_incremental.py — инкрементальный тест-раннер

**Files:**
- Create: `tests/load/run_incremental.py`

- [ ] **Step 1: Создать скрипт**

```python
"""
Инкрементальный SSE-тест: запускает серию уровней с растущим числом SSE-клиентов,
мониторит VPS RAM/CPU, останавливается при первом провале.

Запуск:
    python tests/load/run_incremental.py
    python tests/load/run_incremental.py --sse-levels 1000,1500,2000,2500,3000
    python tests/load/run_incremental.py --realistic
"""
import argparse
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).parent.parent.parent
load_dotenv(REPO_ROOT / ".env")

HOST = os.environ.get("LOAD_TEST_HOST", "https://analytics.krasmarafon.ru")
LIVE_EVENT_ID = os.environ.get("LIVE_EVENT_ID", "104")
ADMIN_PASSWORD = os.environ.get("LOCUST_ADMIN_PASSWORD") or os.environ.get("ADMIN_PASSWORD", "")

DURATION = "5m"
HTTP_USERS = 200
HTTP_SPAWN_RATE = 20
PASS_THRESHOLD_PCT = 95
STOP_RAM_PCT = 90


def _duration_to_seconds(d: str) -> int:
    if d.endswith("m"): return int(d[:-1]) * 60
    if d.endswith("s"): return int(d[:-1])
    return int(d)


def _setup_race_data() -> bool:
    print("\n  [realistic] Генерация тест-данных (3000 бегунов)...")
    r = subprocess.run(
        [sys.executable, str(REPO_ROOT / "tests" / "load" / "setup_race_data.py"), "--setup"],
        cwd=REPO_ROOT, timeout=120,
    )
    return r.returncode == 0


def _teardown_race_data():
    print("\n  [realistic] Очистка тест-данных...")
    subprocess.run(
        [sys.executable, str(REPO_ROOT / "tests" / "load" / "setup_race_data.py"), "--teardown"],
        cwd=REPO_ROOT, timeout=60,
    )


def run_level(sse_vus: int, report_dir: Path, duration: str, realistic: bool) -> dict:
    """Возвращает dict с результатами: sse_pct, ram_max_pct, locust_ok."""
    name = f"T{sse_vus}"
    total = HTTP_USERS + sse_vus
    print(f"\n{'=' * 60}")
    print(f"  {name}: {HTTP_USERS} HTTP + {sse_vus} SSE = {total} users | {duration}")
    print(f"{'=' * 60}")
    report_dir.mkdir(parents=True, exist_ok=True)

    # VPS мониторинг
    from tests.load.vps_monitor import VpsMonitor
    mon_path = report_dir / f"vps_{name}.csv"
    monitor = VpsMonitor(mon_path)
    monitor.start()

    env = {
        **os.environ,
        "LOCUST_LIVE_EVENT_ID": LIVE_EVENT_ID,
        "LOCUST_ADMIN_PASSWORD": ADMIN_PASSWORD,
        "PYTHONIOENCODING": "utf-8",
        "PYTHONPATH": str(REPO_ROOT),
    }

    sim_proc = sim_log = None
    if realistic:
        if not _setup_race_data():
            monitor.stop()
            return {"sse_pct": 0, "ram_max_pct": 0, "locust_ok": False, "error": "setup failed"}
        time.sleep(10)
        sim_dur = _duration_to_seconds(duration) + 30
        sim_log_path = report_dir / f"simulator_{name}.txt"
        sim_log = open(sim_log_path, "w", encoding="utf-8")
        sim_proc = subprocess.Popen(
            [sys.executable, str(REPO_ROOT / "tests" / "load" / "race_simulator.py"),
             "--duration", str(sim_dur)],
            stdout=sim_log, stderr=subprocess.STDOUT, cwd=REPO_ROOT,
        )

    locust_report = report_dir / f"locust_{name}.html"
    locust_cmd = [
        sys.executable, "-m", "locust",
        "-f", str(REPO_ROOT / "locustfile.py"),
        "--host", HOST,
        "--users", str(HTTP_USERS),
        "--spawn-rate", str(HTTP_SPAWN_RATE),
        "--run-time", duration,
        "--html", str(locust_report),
        "--headless",
    ]

    hold_s = _duration_to_seconds(duration) - 20
    sse_stdout = report_dir / f"sse_{name}_stdout.txt"
    sse_cmd = [
        sys.executable,
        str(REPO_ROOT / "tests" / "load" / "sse_load_remote.py"),
        "--vus", str(sse_vus),
        "--hold", str(hold_s),
    ]

    locust_proc = subprocess.Popen(locust_cmd, env=env, cwd=REPO_ROOT)
    with open(sse_stdout, "w", encoding="utf-8") as sf:
        sse_proc = subprocess.Popen(sse_cmd, env=env, cwd=REPO_ROOT,
                                    stdout=sf, stderr=subprocess.STDOUT)

    timeout = _duration_to_seconds(duration) + 60
    try:
        locust_proc.wait(timeout=timeout)
        sse_proc.wait(timeout=120)
    except subprocess.TimeoutExpired:
        for p in (locust_proc, sse_proc):
            p.terminate(); p.wait()

    monitor.stop()
    if sim_proc:
        sim_proc.terminate(); sim_proc.wait()
    if sim_log:
        sim_log.close()
    if realistic:
        _teardown_race_data()

    # Парсим SSE%
    sse_pct = 0
    if sse_stdout.exists():
        for line in sse_stdout.read_text(encoding="utf-8", errors="replace").splitlines():
            print(f"    {line}")
            if "held (" in line:
                import re
                m = re.search(r"\((\d+)%\)", line)
                if m:
                    sse_pct = max(sse_pct, int(m.group(1)))

    # Макс RAM из CSV
    ram_max = 0.0
    if mon_path.exists():
        import csv
        with open(mon_path, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                ram_max = max(ram_max, float(row.get("ram_pct", 0)))

    locust_ok = locust_proc.returncode == 0
    result = {
        "sse_pct": sse_pct,
        "ram_max_pct": round(ram_max, 1),
        "locust_ok": locust_ok,
    }
    print(f"\n  Результат {name}: SSE {sse_pct}% | RAM max {ram_max:.1f}% | Locust {'OK' if locust_ok else 'FAIL'}")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sse-levels", default="1000,1500,2000,2500,3000",
                        help="Уровни SSE через запятую")
    parser.add_argument("--http-users", type=int, default=HTTP_USERS)
    parser.add_argument("--duration", default=DURATION)
    parser.add_argument("--realistic", action="store_true")
    parser.add_argument("--stop-on-fail", action="store_true", default=True)
    parser.add_argument("--yes", "-y", action="store_true")
    args = parser.parse_args()

    levels = [int(x) for x in args.sse_levels.split(",")]
    date_str = datetime.now().strftime("%Y-%m-%d")
    report_dir = REPO_ROOT / "reports" / "load" / date_str

    print(f"\nKM_track Incremental SSE Test")
    print(f"Хост: {HOST} | Уровни SSE: {levels}")
    print(f"Режим: {'realistic' if args.realistic else 'synthetic'} | Длительность: {args.duration}")

    if not args.yes:
        try:
            input("\nНажмите Enter для начала или Ctrl+C для отмены...")
        except EOFError:
            pass

    results = []
    for sse_vus in levels:
        res = run_level(sse_vus, report_dir, args.duration, args.realistic)
        res["sse_vus"] = sse_vus
        results.append(res)

        if args.stop_on_fail and res["sse_pct"] < PASS_THRESHOLD_PCT:
            print(f"\n  СТОП: SSE {res['sse_pct']}% < {PASS_THRESHOLD_PCT}% на {sse_vus} VUs")
            break
        if res["ram_max_pct"] > STOP_RAM_PCT:
            print(f"\n  СТОП: RAM {res['ram_max_pct']}% > {STOP_RAM_PCT}%")
            break

        if sse_vus != levels[-1]:
            print(f"\n  Пауза 60с перед следующим уровнем...")
            time.sleep(60)

    print(f"\n{'=' * 60}")
    print("  ИТОГИ:")
    print(f"  {'SSE VUs':>8} | {'SSE%':>6} | {'RAM max':>8} | {'Locust':>7}")
    print(f"  {'-'*8}-+-{'-'*6}-+-{'-'*8}-+-{'-'*7}")
    for r in results:
        status = "PASS" if r["sse_pct"] >= PASS_THRESHOLD_PCT else "FAIL"
        print(f"  {r['sse_vus']:>8} | {r['sse_pct']:>5}% | {r['ram_max_pct']:>7}% | {status:>7}")
    ceiling = max((r["sse_vus"] for r in results if r["sse_pct"] >= PASS_THRESHOLD_PCT), default=0)
    print(f"\n  Потолок SSE на текущем железе: {ceiling} VUs")
    print(f"  Отчёты: {report_dir}")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Commit**

```bash
git add tests/load/run_incremental.py tests/load/vps_monitor.py
git commit -m "feat: инкрементальный SSE-тест с VPS мониторингом"
```

---

## Task 5: Оптимизация O1 — Swap 1 GB → 2 GB

**Files:**
- Create: `deploy/ssh_add_swap2.py`

- [ ] **Step 1: Создать скрипт**

```python
"""Добавляет второй swap-файл 2 GB на VPS для защиты от OOM под нагрузкой."""
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from deploy._vps_config import VPS_HOST, VPS_USER, VPS_PASSWORD
import paramiko, time

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(VPS_HOST, username=VPS_USER, password=VPS_PASSWORD, timeout=30)

def run(cmd, timeout=60):
    _, out, err = client.exec_command(cmd)
    result = out.read().decode("utf-8", errors="replace").strip()
    if result:
        print(result)
    return result

print("=== Текущий swap ===")
run("swapon --show")

print("\n=== Создаём /swapfile2 (2 GB) ===")
run("fallocate -l 2G /swapfile2", timeout=30)
run("chmod 600 /swapfile2")
run("mkswap /swapfile2")
run("swapon /swapfile2")

print("\n=== Проверяем ===")
run("swapon --show")
run("free -h")

print("\n=== Добавляем в /etc/fstab для автомонтирования ===")
run("grep -q '/swapfile2' /etc/fstab || echo '/swapfile2 none swap sw 0 0' >> /etc/fstab")

client.close()
print("\n✅ Swap 2 GB добавлен.")
```

- [ ] **Step 2: Запустить**

```bash
python -m deploy.ssh_add_swap2
```

Ожидаемый результат — в `swapon --show` появляется `/swapfile2` размером 2G.

- [ ] **Step 3: Commit**

```bash
git add deploy/ssh_add_swap2.py
git commit -m "feat: скрипт добавления swap 2GB на VPS"
```

---

## Task 6: Оптимизация O2 — nginx keepalive_timeout

**Files:**
- Create: `deploy/ssh_nginx_tune.py`

- [ ] **Step 1: Создать скрипт**

```python
"""Снижает nginx keepalive_timeout с 65s до 15s для быстрого освобождения соединений."""
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from deploy._vps_config import VPS_HOST, VPS_USER, VPS_PASSWORD
import paramiko

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(VPS_HOST, username=VPS_USER, password=VPS_PASSWORD, timeout=30)

def run(cmd):
    _, out, _ = client.exec_command(cmd)
    return out.read().decode("utf-8", errors="replace").strip()

print("=== Текущий keepalive_timeout ===")
print(run("grep keepalive_timeout /etc/nginx/nginx.conf || grep -r keepalive_timeout /etc/nginx/conf.d/"))

print("\n=== Применяем keepalive_timeout 15s ===")
run("sed -i 's/keepalive_timeout[[:space:]]*[0-9]*/keepalive_timeout 15/' /etc/nginx/nginx.conf")
run("sed -i 's/keepalive_timeout[[:space:]]*[0-9]*/keepalive_timeout 15/' /etc/nginx/conf.d/*.conf 2>/dev/null || true")

print("\n=== Проверка конфига ===")
test = run("nginx -t 2>&1")
print(test)

if "successful" in test:
    run("nginx -s reload")
    print("✅ nginx перезагружен")
else:
    print("❌ Ошибка конфига — откат")
    run("sed -i 's/keepalive_timeout 15/keepalive_timeout 65/' /etc/nginx/nginx.conf")

print("\n=== Новый keepalive_timeout ===")
print(run("grep keepalive_timeout /etc/nginx/nginx.conf"))

client.close()
```

- [ ] **Step 2: Запустить**

```bash
python -m deploy.ssh_nginx_tune
```

Ожидается: `nginx -t` → `syntax is ok / test is successful`, затем `nginx -s reload`.

- [ ] **Step 3: Commit**

```bash
git add deploy/ssh_nginx_tune.py
git commit -m "feat: скрипт nginx keepalive_timeout tuning"
```

---

## Task 7: Выполнение трёхфазного плана

- [ ] **Фаза 1: Верификация Redis**

```bash
python -m deploy._verify_redis
```

Критерий: `Connected: 3`, `Leader acquired: 1`. Если нет — `systemctl restart km_track` на VPS и повторить.

- [ ] **Фаза 1b: Smoke с realistic**

```bash
python tests/load/run_load_test.py --smoke --realistic --yes
```

Критерий: `SSE: OK`, `Locust: OK`.

- [ ] **Фаза 2: Инкрементальный поиск потолка (без оптимизаций)**

```bash
python tests/load/run_incremental.py --realistic --yes
```

Записать таблицу результатов (SSE% по уровням, RAM max). Зафиксировать первый уровень с SSE < 95%.

- [ ] **Фаза 2b: Применить оптимизацию O1 (swap)**

```bash
python -m deploy.ssh_add_swap2
```

- [ ] **Фаза 2c: Применить оптимизацию O2 (nginx)**

```bash
python -m deploy.ssh_nginx_tune
```

- [ ] **Фаза 2d: Повторить тест с того уровня где упало**

```bash
python tests/load/run_incremental.py --realistic --yes --sse-levels <уровень_слома>,<следующий>
```

- [ ] **Фаза 3: Если RAM > 85% — снизить workers до 2**

Только если RAM критична. Изменить в `deploy/km_track.service`:
```
--workers 2
```
Задеплоить и перезапустить:
```bash
python -m deploy.ssh_update
systemctl daemon-reload && systemctl restart km_track
```

- [ ] **Итог: Зафиксировать потолок**

Обновить `00-home/текущие приоритеты.md` с таблицей результатов:

```
| SSE VUs | SSE% | RAM max | После оптимизаций |
```

- [ ] **Commit финальных отчётов**

```bash
git add reports/load/$(date +%Y-%m-%d)/
git commit -m "test: инкрементальный SSE потолок — результаты"
```

---

## Self-Review

**Spec coverage:**
- ✅ Фаза 1 (Redis верификация) → Task 1 + Task 7 Фаза 1
- ✅ Фаза 2 (инкрементальный поиск) → Task 3 + Task 4 + Task 7 Фаза 2
- ✅ O1 swap → Task 5
- ✅ O2 nginx → Task 6
- ✅ Realistic режим → интегрирован в run_incremental.py
- ✅ VPS мониторинг → Task 3 (VpsMonitor)
- ✅ Stop-on-fail логика → run_incremental.py строки --stop-on-fail

**Placeholder scan:** нет TBD/TODO ✅

**Type consistency:** `VpsMonitor.start()/stop()` используются в Task 4 корректно ✅
