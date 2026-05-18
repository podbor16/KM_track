"""Тест SSE через HTTPS (внешний адрес) прямо с VPS."""
import paramiko, sys

HOST = "89.108.88.104"
USER = "root"
PASSWORD = "shsfzw5fHiQY8v6g"

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, username=USER, password=PASSWORD, timeout=30)

def run(cmd, timeout=20):
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode("utf-8", errors="replace").strip()
    err = stderr.read().decode("utf-8", errors="replace").strip()
    sys.stdout.buffer.write((f">>> {cmd}\n{out}\n").encode())
    if err: sys.stdout.buffer.write(("ERR: " + err + "\n").encode())
    sys.stdout.buffer.write(b"\n")
    sys.stdout.buffer.flush()

# SSE через HTTPS (внешний адрес) — с таймаутом 10s
run('curl -sv --max-time 10 -H "Accept: text/event-stream" "https://analytics.krasmarafon.ru/api/sse/tracker?event_id=104" 2>&1')

# Gzip включён для SSE или нет?
run('curl -sI -H "Accept: text/event-stream" "https://analytics.krasmarafon.ru/api/sse/tracker?event_id=104" --max-time 5')

# nginx.conf — есть ли gzip на http-уровне?
run("grep -n 'gzip' /etc/nginx/nginx.conf")

client.close()
