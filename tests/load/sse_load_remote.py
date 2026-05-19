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
from deploy._vps_config import VPS_HOST, VPS_USER, VPS_PASSWORD

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
            # Keepalive every 30s prevents SSH idle-timeout disconnect during long tests
            client.get_transport().set_keepalive(30)
            return client
        except Exception as e:
            last_exc = e
            print(f"  SSH connect attempt {attempt}/{SSH_RETRIES} failed: {e}")
            if attempt < SSH_RETRIES:
                time.sleep(SSH_RETRY_DELAY)
    raise last_exc


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
                chunk = await asyncio.wait_for(reader.read(4096), timeout=15)
            except asyncio.TimeoutError:
                continue  # server is slow under load — keep waiting until deadline_connect
            if not chunk:
                break
            buf += chunk
            if b"connected" in buf:
                connected = True
                break
        if not connected:
            results[vu_id] = "no_connected"
            return
        hold_start = time.monotonic()
        dropped = False
        while time.monotonic() - hold_start < total_hold:
            try:
                chunk = await asyncio.wait_for(reader.read(4096), timeout=30)
                if not chunk:
                    dropped = True
                    break
            except asyncio.TimeoutError:
                pass
        actual_hold = time.monotonic() - hold_start
        results[vu_id] = "held" if not dropped else f"drop_{actual_hold:.0f}s"
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
        t_drop = sum(1 for v in t_res.values() if isinstance(v, str) and v.startswith("drop_"))
        n_held = sum(1 for v in n_res.values() if v == "held")
        elapsed = time.monotonic() - t_start
        print(
            f"  [{elapsed:.0f}s] tracker={len(t_res)}/{vus} held={t_held} drop={t_drop} active={vus - len(t_res)}"
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
    t_drop = sum(1 for v in tracker_results.values() if isinstance(v, str) and v.startswith("drop_"))
    n_held = sum(1 for v in notify_results.values() if v == "held")
    t_pct = t_held * 100 // vus if vus else 100
    n_pct = n_held * 100 // notify_vus if notify_vus else 100

    print("")
    print("=======================================================")
    print("SSE Load Test Results (asyncio)")
    print("=======================================================")
    print(f"Tracker SSE ({vus} VUs):       {t_held} held ({t_pct}%) | {t_drop} early-drop")
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


if __name__ == "__main__":
    main()
