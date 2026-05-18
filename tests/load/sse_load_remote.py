"""
SSE нагрузочный тест, запускаемый С VPS через SSH.
Вместо N процессов curl — один Python asyncio скрипт (N async задач).
Экономия памяти: 1x50MB vs N×2MB (для N=335: 670MB → 50MB).

Запуск:
    python tests/load/sse_load_remote.py --vus 335 --hold 460
    python tests/load/sse_load_remote.py --smoke
"""

import argparse
import sys
import time
import paramiko

VPS_HOST = "89.108.88.104"
VPS_USER = "root"
VPS_PASSWORD = "shsfzw5fHiQY8v6g"

SSE_URL = "http://127.0.0.1:8000/api/sse/tracker?event_id=104"

SSH_RETRIES = 5
SSH_RETRY_DELAY = 10


def _ssh_connect() -> paramiko.SSHClient:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    last_exc = None
    for attempt in range(1, SSH_RETRIES + 1):
        try:
            client.connect(VPS_HOST, username=VPS_USER, password=VPS_PASSWORD, timeout=30)
            return client
        except Exception as e:
            last_exc = e
            print(f"  SSH connect attempt {attempt}/{SSH_RETRIES} failed: {e}")
            if attempt < SSH_RETRIES:
                time.sleep(SSH_RETRY_DELAY)
    raise last_exc


# asyncio Python script uploaded and executed on VPS.
# Uses raw asyncio.open_connection (no external deps), one process for all VUs.
ASYNC_SSE_SCRIPT = '''\
import asyncio, sys, time, random

HOST = "127.0.0.1"
PORT = 8000
SSE_PATH = "/api/sse/tracker?event_id=104"
PASS_THRESHOLD = 95  # % VUs connected

REQUEST = (
    f"GET {SSE_PATH} HTTP/1.1\\r\\n"
    f"Host: {HOST}:{PORT}\\r\\n"
    f"Accept: text/event-stream\\r\\n"
    f"Cache-Control: no-cache\\r\\n"
    f"Connection: keep-alive\\r\\n"
    f"\\r\\n"
).encode()


async def sse_vu(vu_id, hold_seconds, results):
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
        writer.write(REQUEST)
        await writer.drain()

        start = time.monotonic()
        connected = False

        # Phase 1: wait for ': connected' in first ~30s
        deadline_connect = start + 30
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

        # Phase 2: hold connection for remaining time (read heartbeats)
        while time.monotonic() - start < total_hold:
            try:
                chunk = await asyncio.wait_for(reader.read(4096), timeout=30)
                if not chunk:
                    break
            except asyncio.TimeoutError:
                pass  # heartbeat expected every 25s - continue

        results[vu_id] = "held"
    except Exception as e:
        results[vu_id] = f"err:{type(e).__name__}"
    finally:
        try:
            writer.close()
            await asyncio.wait_for(writer.wait_closed(), timeout=2)
        except Exception:
            pass


async def run_load(vus, hold_seconds):
    print(f"Starting {vus} SSE VUs (asyncio), hold {hold_seconds}+0..30s...")
    t_start = time.monotonic()
    results = {}

    tasks = []
    for i in range(vus):
        task = asyncio.create_task(sse_vu(i, hold_seconds, results))
        tasks.append(task)
        if (i + 1) % 20 == 0:
            await asyncio.sleep(1)

    await asyncio.gather(*tasks)

    elapsed = time.monotonic() - t_start
    held = sum(1 for v in results.values() if v == "held")
    no_conn = sum(1 for v in results.values() if v == "no_connected")
    errors = vus - held - no_conn

    pct = held * 100 // vus if vus else 0
    print("")
    print("=======================================================")
    print("SSE Load Test Results (asyncio)")
    print("=======================================================")
    print(f"Total VUs:       {vus}")
    print(f"Connected+held:  {held} ({pct}%)")
    print(f"No :connected:   {no_conn}")
    print(f"Errors:          {errors}")
    print(f"Total time:      {elapsed:.0f}s")
    print("=======================================================")
    print("")

    if held >= vus * PASS_THRESHOLD // 100:
        print(f"RESULT: PASSED (>={PASS_THRESHOLD}% VUs connected)")
        return True
    else:
        print(f"RESULT: FAILED (<{PASS_THRESHOLD}% VUs connected)")
        return False


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--vus", type=int, default=335)
    parser.add_argument("--hold", type=int, default=30)
    args = parser.parse_args()

    ok = asyncio.run(run_load(args.vus, args.hold))
    sys.exit(0 if ok else 1)
'''


def run_remote(vus: int, hold_seconds: int) -> bool:
    print(f"\nSSE load test (VPS asyncio via SSH)")
    print(f"  URL:    {SSE_URL}")
    print(f"  VUs:    {vus}")
    print(f"  Hold:   {hold_seconds}s")

    client = _ssh_connect()

    sftp = client.open_sftp()
    with sftp.open("/tmp/sse_async_test.py", "w") as f:
        f.write(ASYNC_SSE_SCRIPT)
    sftp.close()

    python = "/opt/km_track/venv/bin/python3"
    cmd = f"{python} /tmp/sse_async_test.py --vus {vus} --hold {hold_seconds}"

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
    ok = exit_code == 0
    elapsed = time.monotonic() - t0
    print(f"\n  Test completed in {elapsed:.1f}s (exit={exit_code})")
    client.close()
    return ok


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--vus", type=int, default=335)
    parser.add_argument("--hold", type=int, default=30)
    parser.add_argument("--smoke", action="store_true", help="10 VUs, 15s hold")
    args = parser.parse_args()

    if args.smoke:
        vus, hold = 10, 15
    else:
        vus, hold = args.vus, args.hold

    ok = run_remote(vus, hold)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
