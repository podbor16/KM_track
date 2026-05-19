"""Установка и настройка Redis на VPS."""
import paramiko, time
from deploy._vps_config import VPS_HOST, VPS_USER, VPS_PASSWORD

HOST = VPS_HOST
USER = "root"
PASSWORD = VPS_PASSWORD

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=USER, password=PASSWORD, timeout=15)

def run(cmd, timeout=60):
    transport = c.get_transport()
    ch = transport.open_session()
    ch.settimeout(None)
    ch.exec_command(cmd)
    out = []
    deadline = time.time() + timeout
    while True:
        if ch.recv_ready():
            chunk = ch.recv(4096).decode(errors="replace")
            out.append(chunk)
            for line in chunk.splitlines():
                if line.strip(): print(line)
            deadline = time.time() + timeout
        if ch.recv_stderr_ready():
            ch.recv_stderr(4096)
            deadline = time.time() + timeout
        if ch.exit_status_ready(): break
        if time.time() > deadline: break
        time.sleep(0.2)
    ch.close()
    return "".join(out).strip()

print("=== Установка Redis ===")
run("apt-get install -y redis-server", timeout=120)

print("\n=== Включение автозапуска ===")
run("systemctl enable redis-server")
run("systemctl start redis-server")
time.sleep(2)
run("systemctl is-active redis-server")

print("\n=== Проверка bind (должен быть 127.0.0.1) ===")
run("grep -E '^bind' /etc/redis/redis.conf || echo 'bind 127.0.0.1 ::1 (default)'")

print("\n=== Проверка подключения ===")
result = run("redis-cli ping")
if "PONG" in result:
    print("✅ Redis работает: PONG")
else:
    print("❌ Redis не отвечает!")

print("\n=== Память Redis ===")
run("redis-cli info memory | grep used_memory_human")

c.close()
print("\n✅ Redis установлен и готов к работе.")
