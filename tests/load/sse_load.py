"""
SSE нагрузочный тест: открывает N параллельных SSE-соединений через requests
(stream=True) в ThreadPoolExecutor и держит их HOLD_SECONDS секунд.

Почему не k6 http.get(): k6 возвращается после первого SSE-чанка вместо
удержания соединения. Почему не aiohttp: над HTTPS не получает SSE-чанки
из-за буферизации. requests + threads — проверенный рабочий подход.

Запуск:
    python tests/load/sse_load.py --vus 335 --hold 30 --host https://analytics.krasmarafon.ru
    python tests/load/sse_load.py --smoke --host https://analytics.krasmarafon.ru
"""

import argparse
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

try:
    import requests
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except ImportError:
    print("Установи requests: pip install requests")
    sys.exit(1)


@dataclass
class Stats:
    lock: threading.Lock = field(default_factory=threading.Lock)
    connected: int = 0
    held: int = 0
    quick_fail: int = 0
    error: int = 0
    ttfb_ms: list = field(default_factory=list)
    hold_ms: list = field(default_factory=list)

    def add_connected(self, ttfb: float):
        with self.lock:
            self.connected += 1
            self.ttfb_ms.append(ttfb)

    def add_result(self, result: str, duration_ms: float):
        with self.lock:
            self.hold_ms.append(duration_ms)
            if result == "held":
                self.held += 1
            elif result == "quick_fail":
                self.quick_fail += 1
            else:
                self.error += 1


def sse_connect(url: str, vu_id: int, hold_seconds: int, stats: Stats) -> None:
    headers = {
        "Accept": "text/event-stream",
        "Cache-Control": "no-cache",
        "X-Forwarded-For": f"{(vu_id % 223) + 1}.{(vu_id // 223) % 254 + 1}.1.1",
    }
    t0 = time.monotonic()
    connected = False
    try:
        with requests.get(
            url, headers=headers, stream=True,
            timeout=(15, hold_seconds + 60),  # (connect_timeout, read_timeout)
            verify=True,
        ) as resp:
            if resp.status_code != 200:
                stats.add_result("error", (time.monotonic() - t0) * 1000)
                return

            for chunk in resp.iter_content(chunk_size=None):
                if not connected:
                    ttfb = (time.monotonic() - t0) * 1000
                    stats.add_connected(ttfb)
                    connected = True

                elapsed = time.monotonic() - t0
                if elapsed >= hold_seconds:
                    break

            elapsed_total = (time.monotonic() - t0) * 1000
            if elapsed_total >= hold_seconds * 1000 * 0.9:
                stats.add_result("held", elapsed_total)
            elif elapsed_total < 1000:
                stats.add_result("quick_fail", elapsed_total)
            else:
                stats.add_result("error", elapsed_total)

    except requests.exceptions.ReadTimeout:
        elapsed_total = (time.monotonic() - t0) * 1000
        if connected and elapsed_total >= hold_seconds * 1000 * 0.9:
            stats.add_result("held", elapsed_total)
        elif elapsed_total < 1000:
            stats.add_result("quick_fail", elapsed_total)
        else:
            stats.add_result("error", elapsed_total)
    except requests.exceptions.ConnectionError:
        elapsed = (time.monotonic() - t0) * 1000
        if elapsed < 1000:
            stats.add_result("quick_fail", elapsed)
        else:
            stats.add_result("error", elapsed)
    except Exception:
        elapsed = (time.monotonic() - t0) * 1000
        stats.add_result("quick_fail" if elapsed < 1000 else "error", elapsed)


def percentile(data: list, p: int) -> float:
    if not data:
        return 0.0
    s = sorted(data)
    idx = int(len(s) * p / 100)
    return s[min(idx, len(s) - 1)]


def run(vus: int, hold_seconds: int, host: str, event_id: str, spawn_rate: int) -> bool:
    url = f"{host}/api/sse/tracker?event_id={event_id}"
    stats = Stats()
    t_start = time.monotonic()

    print(f"\nSSE нагрузочный тест (requests+threads)")
    print(f"  URL:       {url}")
    print(f"  VUs:       {vus}")
    print(f"  Hold:      {hold_seconds}s")
    print(f"  Spawn:     {spawn_rate} VU/s")

    # Прогресс в отдельном потоке
    stop_progress = threading.Event()
    def progress_reporter():
        while not stop_progress.is_set():
            time.sleep(5)
            elapsed = int(time.monotonic() - t_start)
            with stats.lock:
                c, h, qf, e = stats.connected, stats.held, stats.quick_fail, stats.error
            done = h + qf + e
            active = vus - done
            print(f"  [{elapsed:3d}s] connected={c} held={h} quick_fail={qf} error={e} active={active}")

    progress_thread = threading.Thread(target=progress_reporter, daemon=True)
    progress_thread.start()

    print(f"\n  Открываем соединения (spawn_rate={spawn_rate}/s)...")

    # ThreadPoolExecutor с постепенным запуском VUs
    with ThreadPoolExecutor(max_workers=vus + 10) as executor:
        futures = []
        for i in range(vus):
            f = executor.submit(sse_connect, url, i + 1, hold_seconds, stats)
            futures.append(f)
            if spawn_rate > 0 and (i + 1) % spawn_rate == 0:
                time.sleep(1.0)

        # Ждём завершения всех
        for f in as_completed(futures):
            pass

    stop_progress.set()

    elapsed = time.monotonic() - t_start
    total_done = stats.connected + stats.quick_fail + stats.error

    print(f"\n{'=' * 55}")
    print(f"  Результаты SSE нагрузочного теста")
    print(f"{'=' * 55}")
    print(f"  Всего VUs:          {vus}")
    print(f"  Успешно connected:  {stats.connected} ({stats.connected/vus*100:.1f}%)")
    print(f"  Держались {hold_seconds}s:  {stats.held} ({stats.held/vus*100:.1f}%)")
    print(f"  Быстрый отказ <1s:  {stats.quick_fail}")
    print(f"  Другие ошибки:      {stats.error}")
    if stats.ttfb_ms:
        print(f"\n  TTFB (время до 1-го события):")
        print(f"    p50={percentile(stats.ttfb_ms, 50):.0f}ms  "
              f"p95={percentile(stats.ttfb_ms, 95):.0f}ms  "
              f"max={max(stats.ttfb_ms):.0f}ms")
    if stats.hold_ms:
        print(f"\n  Длительность соединений:")
        print(f"    p50={percentile(stats.hold_ms, 50)/1000:.1f}s  "
              f"p95={percentile(stats.hold_ms, 95)/1000:.1f}s  "
              f"max={max(stats.hold_ms)/1000:.1f}s")
    print(f"\n  Общее время теста: {elapsed:.1f}s")
    print(f"{'=' * 55}\n")

    ok = stats.held >= vus * 0.95
    print(f"  ИТОГ: {'ПРОЙДЕН' if ok else 'ПРОВАЛЕН'} "
          f"(порог: 95% VUs держали {hold_seconds}s)")
    print()
    return ok


def main():
    parser = argparse.ArgumentParser(description="SSE нагрузочный тест (requests+threads)")
    parser.add_argument("--vus", type=int, default=335)
    parser.add_argument("--hold", type=int, default=30, help="Секунд держать SSE соединение")
    parser.add_argument("--host", default="https://analytics.krasmarafon.ru")
    parser.add_argument("--event-id", default="104")
    parser.add_argument("--spawn-rate", type=int, default=20)
    parser.add_argument("--smoke", action="store_true", help="10 VUs, 15s hold")
    args = parser.parse_args()

    if args.smoke:
        vus, hold = 10, 15
    else:
        vus, hold = args.vus, args.hold

    ok = run(vus, hold, args.host, args.event_id, args.spawn_rate)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
