import paramiko
import time
from deploy._vps_config import VPS_HOST, VPS_USER, VPS_PASSWORD

HOST = VPS_HOST
USER = "root"
PASSWORD = VPS_PASSWORD

def run(client, cmd, timeout=120):
    print(f"\n>>> {cmd[:100]}")
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout, get_pty=True)
    out = []
    for line in iter(stdout.readline, ""):
        print(line, end="")
        out.append(line)
    return "".join(out)

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, username=USER, password=PASSWORD, timeout=30)
print("Подключился")

# Check DNS resolves to this server
run(client, "dig +short results.krasmarafon.ru || nslookup results.krasmarafon.ru | grep Address | tail -1")

# Check nginx status
run(client, "systemctl status nginx --no-pager | head -5")

# Get SSL cert — webroot-метод (НЕ --nginx): certbot только кладёт файл
# проверки в /var/lib/letsencrypt (порт-80 блок results.krasmarafon.ru в
# nginx.conf уже отдаёт его статикой), не редактирует живой nginx.conf
# напрямую — деплой всё равно перезаписывает его из git на каждый пуш,
# так что прямые правки certbot всё равно потерялись бы при следующем
# деплое. Тот же паттерн уже используется для live.siberman515.com.
run(client, "certbot certonly --webroot -w /var/lib/letsencrypt -d results.krasmarafon.ru --non-interactive --agree-tos -m admin@krasmarafon.ru", timeout=120)

# certbot certonly не трогает nginx.conf — 443-блок для results.krasmarafon.ru
# добавляется в deploy/nginx.conf отдельным коммитом ПОСЛЕ этого скрипта
# (см. комментарий в nginx.conf), reload делать пока не нужно

# Final check
run(client, "curl -s http://127.0.0.1:8000/health")

client.close()
print("\n=== SSL ГОТОВ ===")
