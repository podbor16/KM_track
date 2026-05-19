"""Снижает nginx keepalive_timeout до 15s для быстрого освобождения соединений."""
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
# Если директива уже есть — меняем значение; иначе вставляем в http-блок
existing = run("grep -c 'keepalive_timeout' /etc/nginx/nginx.conf || true")
if existing and int(existing) > 0:
    run("sed -i 's/keepalive_timeout[[:space:]]*[0-9]*/keepalive_timeout 15/' /etc/nginx/nginx.conf")
else:
    run(r"sed -i '/http {/a\    keepalive_timeout 15;' /etc/nginx/nginx.conf")
run("sed -i 's/keepalive_timeout[[:space:]]*[0-9]*/keepalive_timeout 15/' /etc/nginx/conf.d/*.conf 2>/dev/null || true")

print("\n=== Проверка конфига ===")
test = run("nginx -t 2>&1")
print(test)

if "successful" in test:
    run("nginx -s reload")
    print("nginx перезагружен")
else:
    print("Ошибка конфига — откат")
    run("sed -i 's/keepalive_timeout 15/keepalive_timeout 65/' /etc/nginx/nginx.conf")
    run("sed -i 's/keepalive_timeout 15/keepalive_timeout 65/' /etc/nginx/conf.d/*.conf 2>/dev/null || true")

print("\n=== Новый keepalive_timeout ===")
print(run("grep keepalive_timeout /etc/nginx/nginx.conf"))

client.close()
