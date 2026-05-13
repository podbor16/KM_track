"""
Автоматизированная браузерная проверка KM_track.
Запуск: python tests/browser_check.py
"""
import asyncio
import time
import httpx
from playwright.async_api import async_playwright

BASE = "http://localhost:8000"

def fmt(ms): return f"{ms:.0f}ms"

def hdr(title):
    print(f"\n{'='*60}\n  {title}\n{'='*60}")

async def wait_server(timeout=90):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            async with httpx.AsyncClient() as c:
                r = await c.get(f"{BASE}/health", timeout=3)
                if r.status_code == 200:
                    print(f"OK Server up: {r.json()}")
                    return True
        except Exception:
            pass
        await asyncio.sleep(3)
    print("FAIL Server not ready after 90s")
    return False


# ─── API checks ───────────────────────────────────────────────────────────────

async def check_api():
    hdr("API ENDPOINTS")
    endpoints = [
        "/health",
        "/api/current-event",
        "/api/event-results?event_id=104",
        "/api/event-results?event_id=67",
        "/api/registered-runners?event_id=104",
        "/api/registered-runners?event_id=67",
        "/api/search-athletes?q=Иванов",
        "/api/athlete/Иванов/Иван",
        "/api/status",
    ]
    async with httpx.AsyncClient(base_url=BASE, timeout=30) as c:
        for path in endpoints:
            t0 = time.perf_counter()
            try:
                r = await c.get(path)
                elapsed = (time.perf_counter() - t0) * 1000
                srv = r.headers.get("x-process-time", "?")
                size = len(r.content)
                ok = "OK" if r.status_code == 200 else f"WARN {r.status_code}"
                print(f"  {ok:10} {fmt(elapsed):>8} srv:{srv}s  {size:>7}B  {path}")
            except Exception as e:
                print(f"  ERROR      {path}: {e}")


# ─── SSE check ────────────────────────────────────────────────────────────────

async def check_sse():
    hdr("SSE ENDPOINTS (35s window each)")

    async def read_sse(url, label, window=35):
        received_data = []
        heartbeats = 0
        t0 = time.perf_counter()
        try:
            async with httpx.AsyncClient(base_url=BASE, timeout=httpx.Timeout(window + 5)) as c:
                async with c.stream("GET", url) as r:
                    ct = r.headers.get("content-type", "")
                    if "text/event-stream" not in ct:
                        print(f"  [{label}] FAIL wrong content-type: {ct}")
                        return
                    print(f"  [{label}] OK text/event-stream — listening {window}s...")
                    async for line in r.aiter_lines():
                        if time.perf_counter() - t0 >= window:
                            break
                        if line.startswith("data:"):
                            payload = line[5:].strip()
                            elapsed = (time.perf_counter() - t0) * 1000
                            received_data.append(elapsed)
                            size = len(payload)
                            preview = payload[:100] + ("..." if size > 100 else "")
                            print(f"  [{label}] DATA @{fmt(elapsed)}: {size}B  {preview}")
                            if len(received_data) >= 3:
                                break
                        elif line.startswith(":"):
                            heartbeats += 1
        except Exception as e:
            if "timed out" not in str(e).lower() and "cancel" not in str(e).lower():
                print(f"  [{label}] error: {e}")

        elapsed = (time.perf_counter() - t0) * 1000
        if received_data:
            intervals = [received_data[i] - received_data[i-1] for i in range(1, len(received_data))]
            avg = sum(intervals) / len(intervals) if intervals else 0
            print(f"  [{label}] RESULT: {len(received_data)} data events, {heartbeats} hb, avg_interval={fmt(avg)}")
        else:
            print(f"  [{label}] RESULT: 0 data events, {heartbeats} heartbeats in {fmt(elapsed)} — no active race data")

    await asyncio.gather(
        read_sse("/api/sse/tracker?event_id=104", "tracker:104", window=35),
        read_sse("/api/sse/tracker?event_id=67",  "tracker:67",  window=35),
        read_sse("/api/sse/notify",               "notify",      window=35),
    )


# ─── Browser checks ───────────────────────────────────────────────────────────

async def check_browser():
    hdr("BROWSER CHECKS (headless Chromium)")

    pages = [
        ("/tracker",         "Tracker"),
        ("/results",         "Results"),
        ("/start_list",      "Start list"),
        ("/history",         "History"),
        ("/athlete-profile", "Athlete profile"),
    ]

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()

        for path, label in pages:
            page = await context.new_page()
            console_errors = []
            js_errors = []
            sse_urls = []
            api_calls = []

            page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
            page.on("pageerror", lambda err: js_errors.append(str(err)))

            def on_request(req):
                if "/api/sse/" in req.url:
                    sse_urls.append(req.url.split("?")[0] + ("?" + req.url.split("?")[1] if "?" in req.url else ""))
                elif "/api/" in req.url:
                    api_calls.append(req.url.split("?")[0])

            page.on("request", on_request)

            t0 = time.perf_counter()
            try:
                resp = await page.goto(f"{BASE}{path}", wait_until="load", timeout=30000)
                load_ms = (time.perf_counter() - t0) * 1000

                # Ждём 4 сек чтобы async JS инициализировал SSE и загрузил данные
                await page.wait_for_timeout(4000)

                title = await page.title()
                status = resp.status if resp else "?"

                print(f"\n  --- {label} ({path}) ---")
                print(f"  HTTP {status} | load: {fmt(load_ms)} | title: {title}")

                if sse_urls:
                    print(f"  SSE OK: {sse_urls}")
                else:
                    print(f"  SSE WARN: no SSE connection detected")

                unique_apis = list(dict.fromkeys(api_calls))
                print(f"  API calls: {unique_apis}")

                if js_errors:
                    print(f"  JS ERRORS: {js_errors}")
                elif console_errors:
                    print(f"  Console errors: {console_errors[:3]}")
                else:
                    print(f"  JS: no errors")

                # Tracker: маркеры и статус (JS уже прогрелся 4с)
                if path == "/tracker":
                    marker_count = len(await page.query_selector_all(".leaflet-marker-icon"))
                    status_el = await page.query_selector("#status-message")
                    status_txt = await status_el.text_content() if status_el else "not found"
                    print(f"  Markers on map: {marker_count}")
                    print(f"  Status text: {status_txt}")
                    # Ждём ещё 5 сек — статус должен обновиться через SSE
                    await page.wait_for_timeout(5000)
                    status_txt2 = await status_el.text_content() if status_el else "not found"
                    print(f"  Status after +5s: {status_txt2}")

                if path == "/results":
                    await page.wait_for_timeout(2000)
                    rows = len(await page.query_selector_all("tbody tr"))
                    print(f"  Table rows: {rows}")

                if path == "/start_list":
                    await page.wait_for_timeout(2000)
                    rows = len(await page.query_selector_all("tbody tr"))
                    print(f"  Table rows: {rows}")

                if path == "/history":
                    await page.wait_for_timeout(2000)
                    rows = len(await page.query_selector_all("tbody tr"))
                    print(f"  Table rows: {rows}")

            except Exception as e:
                print(f"  ERROR {label}: {e}")
            finally:
                await page.close()

        await context.close()
        await browser.close()


# ─── main ─────────────────────────────────────────────────────────────────────

async def main():
    print("KM_track browser check")
    print(f"Target: {BASE}")

    if not await wait_server():
        return

    await check_api()
    await check_sse()
    await check_browser()

    hdr("DONE")

if __name__ == "__main__":
    asyncio.run(main())
