import paramiko, sys

HOST = "89.108.88.104"
USER = "root"
PASSWORD = "shsfzw5fHiQY8v6g"

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, username=USER, password=PASSWORD, timeout=30)

def run(cmd, timeout=10):
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode("utf-8", errors="replace").strip()
    err = stderr.read().decode("utf-8", errors="replace").strip()
    sys.stdout.buffer.write((f">>> {cmd}\n{out}\n").encode())
    if err: sys.stdout.buffer.write(("ERR: " + err + "\n").encode())
    sys.stdout.buffer.write(b"\n")
    sys.stdout.buffer.flush()

# nginx версия и HTTP/2
run("nginx -V 2>&1 | head -5")
# ALPN — поддерживает ли nginx h2?
run("openssl s_client -connect analytics.krasmarafon.ru:443 -alpn h2 -brief 2>&1 | head -5")
# Проверим заголовок X-Accel-Buffering через https
run("curl -sv --max-time 5 -H 'Accept: text/event-stream' https://analytics.krasmarafon.ru/api/sse/tracker?event_id=104 2>&1 | head -30")

client.close()
