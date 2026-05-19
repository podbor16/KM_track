"""Диагностика SSE: проверяем заголовки и держание соединения под нагрузкой."""
import paramiko, sys
from deploy._vps_config import VPS_HOST, VPS_USER, VPS_PASSWORD

HOST = VPS_HOST
USER = "root"
PASSWORD = VPS_PASSWORD

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, username=USER, password=PASSWORD, timeout=30)

def run(cmd, timeout=20):
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode("utf-8", errors="replace").strip()
    err = stderr.read().decode("utf-8", errors="replace").strip()
    sys.stdout.buffer.write((f">>> {cmd}\n").encode())
    if out: sys.stdout.buffer.write((out + "\n").encode())
    if err: sys.stdout.buffer.write(("ERR: " + err + "\n").encode())
    sys.stdout.buffer.write(b"\n")
    sys.stdout.buffer.flush()

# 1. Полные заголовки SSE-ответа (verbose)
run('curl -sv --max-time 5 -H "Accept: text/event-stream" "http://localhost:8000/api/sse/tracker?event_id=104" 2>&1 | head -40')

# 2. Считаем активных SSE-подписчиков (сколько очередей в tracker_hub)
run("ss -tnp | grep 8000 | wc -l")

# 3. Открываем 5 параллельных SSE и смотрим сколько держится 10 сек
run("for i in 1 2 3 4 5; do curl -s --max-time 10 -H 'Accept: text/event-stream' 'http://localhost:8000/api/sse/tracker?event_id=104' & done; sleep 10; wait; echo DONE")

# 4. Статус uvicorn workers
run("systemctl status km_track | grep -E 'Active|Main PID|workers'")
run("cat /etc/systemd/system/km_track.service | grep -E 'ExecStart|workers'")

# 5. Лимиты сокетов
run("cat /proc/sys/net/core/somaxconn")
run("cat /proc/sys/net/ipv4/tcp_max_syn_backlog")

client.close()
