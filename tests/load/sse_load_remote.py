"""
SSE нагрузочный тест, запускаемый С VPS через SSH.
Генерирует нагрузку непосредственно с сервера — без ISP/прокси буферизации.

Создаёт bash-скрипт на VPS с N параллельными curl SSE-соединениями,
запускает их и считает сколько держится HOLD_SECONDS секунд.

Запуск:
    python tests/load/sse_load_remote.py --vus 335 --hold 30
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


def run_remote(vus: int, hold_seconds: int) -> bool:
    print(f"\nSSE нагрузочный тест (VPS remote via SSH)")
    print(f"  URL:    {SSE_URL}")
    print(f"  VUs:    {vus}")
    print(f"  Hold:   {hold_seconds}s")

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(VPS_HOST, username=VPS_USER, password=VPS_PASSWORD, timeout=30)

    # Bash скрипт: N параллельных curl SSE + подсчёт успешных
    # Каждый curl держит соединение ровно hold_seconds секунд
    # Если получен `: connected` — соединение живое
    bash_script = f"""#!/bin/bash
VUS={vus}
HOLD={hold_seconds}
URL="{SSE_URL}"
TMPDIR=$(mktemp -d)

echo "Starting $VUS SSE connections, hold ${{HOLD}}s..."
t_start=$(date +%s)

for i in $(seq 1 $VUS); do
    IP="$((i % 223 + 1)).$((i / 223 % 254 + 1)).1.$i"
    curl -s --max-time $HOLD \\
        -H "Accept: text/event-stream" \\
        -H "X-Forwarded-For: $IP" \\
        "$URL" > "$TMPDIR/vu_$i.txt" 2>/dev/null &
    if [ $((i % 20)) -eq 0 ]; then sleep 1; fi
done

echo "All VUs started. Waiting for completion..."
wait

t_end=$(date +%s)
elapsed=$((t_end - t_start))

connected=0
held=0
quick_fail=0

for i in $(seq 1 $VUS); do
    f="$TMPDIR/vu_$i.txt"
    if [ -f "$f" ] && grep -q ': connected' "$f" 2>/dev/null; then
        connected=$((connected + 1))
        held=$((held + 1))
    else
        quick_fail=$((quick_fail + 1))
    fi
done

rm -rf "$TMPDIR"

echo ""
echo "======================================================="
echo "SSE Load Test Results"
echo "======================================================="
echo "Total VUs:       $VUS"
echo "Connected:       $connected ($((connected * 100 / VUS))%)"
echo "Held ${{HOLD}}s:     $held ($((held * 100 / VUS))%)"
echo "Quick fail:      $quick_fail"
echo "Total time:      ${{elapsed}}s"
echo "======================================================="
echo ""

if [ $connected -ge $((VUS * 95 / 100)) ]; then
    echo "RESULT: PASSED (>=95% VUs connected)"
    exit 0
else
    echo "RESULT: FAILED (<95% VUs connected)"
    exit 1
fi
"""

    print(f"\n  Запускаем на VPS...")
    t0 = time.monotonic()

    # Загружаем скрипт на VPS и запускаем
    sftp = client.open_sftp()
    with sftp.open("/tmp/sse_load_test.sh", "w") as f:
        f.write(bash_script)
    sftp.chmod("/tmp/sse_load_test.sh", 0o755)
    sftp.close()

    # Запускаем с увеличенным timeout (hold + рэмп + буфер)
    timeout = hold_seconds + vus // 20 + 60
    stdin, stdout, stderr = client.exec_command(
        "bash /tmp/sse_load_test.sh", timeout=timeout
    )

    # Стримим вывод
    ok = False
    for line in stdout:
        line = line.rstrip()
        print(f"  {line}")
        if "ПРОЙДЕН" in line or "PROVALEN" in line:
            ok = "ПРОЙДЕН" in line

    err = stderr.read().decode("utf-8", errors="replace").strip()
    if err:
        print(f"  STDERR: {err}")

    exit_code = stdout.channel.recv_exit_status()
    ok = exit_code == 0
    elapsed = time.monotonic() - t0
    print(f"\n  Тест завершён за {elapsed:.1f}s (exit={exit_code})")
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
