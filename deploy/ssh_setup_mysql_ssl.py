"""
Настройка MySQL для DataLens:
- Let's Encrypt сертификат → MySQL SSL
- bind-address 0.0.0.0 (внешний доступ)
- ufw: порт 3306 только для IP DataLens
- MySQL пользователь km_analytic@'%' REQUIRE SSL
- renewal-hook для автообновления сертификата
"""
import sys
import time
import paramiko
from deploy._vps_config import VPS_HOST, VPS_USER, VPS_PASSWORD

VPS_HOST = VPS_HOST
VPS_USER = "root"
VPS_PASS = VPS_PASSWORD

DOMAIN = "analytics.krasmarafon.ru"
LE_DIR = f"/etc/letsencrypt/live/{DOMAIN}"
MYSQL_SSL_DIR = "/etc/mysql/ssl"
DB_USER = "km_analytic"
DB_PASS = "CneZbvlOS2H-BLsQ"
DB_NAME = "krasmarafon"

# DataLens исходящие IP-диапазоны (из документации Яндекс Облака)
DATALENS_IPS = [
    "178.154.242.128/28",
    "178.154.242.144/28",
    "178.154.242.160/28",
    "178.154.242.176/28",
    "178.154.242.192/28",
    "178.154.242.208/28",
    "130.193.60.0/28",
]

MYSQL_CONFIG = f"""[mysqld]
innodb_buffer_pool_size = 128M
max_connections = 20
bind-address = 0.0.0.0

# SSL — Let's Encrypt сертификат
ssl-ca   = {MYSQL_SSL_DIR}/ca.pem
ssl-cert = {MYSQL_SSL_DIR}/server-cert.pem
ssl-key  = {MYSQL_SSL_DIR}/server-key.pem
"""

RENEWAL_HOOK = f"""#!/bin/bash
# Копирует Let's Encrypt сертификаты в MySQL-директорию после обновления
set -e
mkdir -p {MYSQL_SSL_DIR}
cp {LE_DIR}/chain.pem        {MYSQL_SSL_DIR}/ca.pem
cp {LE_DIR}/cert.pem         {MYSQL_SSL_DIR}/server-cert.pem
cp {LE_DIR}/privkey.pem      {MYSQL_SSL_DIR}/server-key.pem
chown -R mysql:mysql {MYSQL_SSL_DIR}
chmod 640 {MYSQL_SSL_DIR}/*.pem
systemctl reload mysql
echo "[renewal-hook] MySQL SSL сертификаты обновлены"
"""


def connect():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(VPS_HOST, username=VPS_USER, password=VPS_PASS, timeout=30)
    return client


def run(client, cmd, timeout=60, abort_on_error=True):
    print(f">>> {cmd[:100]}")
    transport = client.get_transport()
    channel = transport.open_session()
    channel.settimeout(None)
    channel.exec_command(cmd)
    out_parts, err_parts = [], []
    deadline = time.time() + timeout
    while True:
        if channel.recv_ready():
            chunk = channel.recv(4096).decode(errors="replace")
            out_parts.append(chunk)
            for line in chunk.splitlines():
                if line.strip():
                    print(line)
            deadline = time.time() + timeout
        if channel.recv_stderr_ready():
            chunk = channel.recv_stderr(4096).decode(errors="replace")
            err_parts.append(chunk)
            deadline = time.time() + timeout
        if channel.exit_status_ready():
            while channel.recv_ready():
                out_parts.append(channel.recv(4096).decode(errors="replace"))
            while channel.recv_stderr_ready():
                err_parts.append(channel.recv_stderr(4096).decode(errors="replace"))
            break
        if time.time() > deadline:
            channel.close()
            if abort_on_error:
                print("❌ Timeout")
                sys.exit(1)
            return "", "", -1
        time.sleep(0.2)
    rc = channel.recv_exit_status()
    channel.close()
    out = "".join(out_parts).strip()
    err = "".join(err_parts).strip()
    if err and "Warning" not in err and "warning" not in err:
        print(f"[stderr] {err[:300]}")
    if rc != 0 and abort_on_error:
        print(f"❌ Код {rc}. Стоп.")
        sys.exit(1)
    return out, err, rc


def step(n, title):
    print(f"\n{'='*60}")
    print(f"  Шаг {n}: {title}")
    print(f"{'='*60}")


client = connect()
print(f"✅ Подключились к {VPS_HOST}")

# ── Шаг 1: Проверить Let's Encrypt сертификат ───────────────────────────────
step(1, "Проверить Let's Encrypt сертификат")
out, _, rc = run(client, f"ls {LE_DIR}/", abort_on_error=False)
if rc != 0:
    print(f"❌ Let's Encrypt сертификат не найден в {LE_DIR}")
    sys.exit(1)
print("Файлы сертификата:", out)
out, _, _ = run(client, f"openssl x509 -in {LE_DIR}/cert.pem -noout -dates")
print("✅ Сертификат найден")

# ── Шаг 2: Скопировать сертификаты в /etc/mysql/ssl/ ────────────────────────
step(2, "Скопировать сертификаты в /etc/mysql/ssl/")
run(client, f"mkdir -p {MYSQL_SSL_DIR}")
run(client, f"cp {LE_DIR}/chain.pem {MYSQL_SSL_DIR}/ca.pem")
run(client, f"cp {LE_DIR}/cert.pem {MYSQL_SSL_DIR}/server-cert.pem")
run(client, f"cp {LE_DIR}/privkey.pem {MYSQL_SSL_DIR}/server-key.pem")
run(client, f"chown -R mysql:mysql {MYSQL_SSL_DIR}")
run(client, f"chmod 640 {MYSQL_SSL_DIR}/*.pem")
run(client, f"ls -la {MYSQL_SSL_DIR}/")
print("✅ Сертификаты скопированы")

# ── Шаг 3: Renewal hook для автообновления ──────────────────────────────────
step(3, "Создать renewal-hook для автообновления")
hook_path = "/etc/letsencrypt/renewal-hooks/deploy/mysql-ssl.sh"
hook_cmd = f"cat > {hook_path} << 'EOFHOOK'\n{RENEWAL_HOOK}\nEOFHOOK"
run(client, hook_cmd)
run(client, f"chmod +x {hook_path}")
print("✅ Renewal hook создан — сертификат будет обновляться автоматически")

# ── Шаг 4: Обновить конфиг MySQL ────────────────────────────────────────────
step(4, "Обновить MySQL конфиг (bind-address + SSL)")
config_cmd = f"cat > /etc/mysql/mysql.conf.d/km_track.cnf << 'EOFCFG'\n{MYSQL_CONFIG}\nEOFCFG"
run(client, config_cmd)
run(client, "systemctl restart mysql")
time.sleep(3)
run(client, "systemctl is-active mysql")

# Проверяем что MySQL видит SSL
out, _, _ = run(client, "mysql -u root -e \"SHOW VARIABLES LIKE 'ssl_%';\"")
print("MySQL SSL статус:", out[:200])
print("✅ MySQL перезапущен с SSL")

# ── Шаг 5: Добавить MySQL пользователя для DataLens ─────────────────────────
step(5, "Создать km_analytic@'%' REQUIRE SSL")
sql = (
    f"CREATE USER IF NOT EXISTS '{DB_USER}'@'%' IDENTIFIED BY '{DB_PASS}'; "
    f"GRANT SELECT ON {DB_NAME}.* TO '{DB_USER}'@'%'; "
    f"ALTER USER '{DB_USER}'@'%' REQUIRE SSL; "
    f"FLUSH PRIVILEGES;"
)
run(client, f'mysql -u root -e "{sql}"')
out, _, _ = run(client,
    f"mysql -u root -e \"SELECT User, Host, ssl_type FROM mysql.user WHERE User='{DB_USER}';\"")
print("Пользователи:", out)
print("✅ Пользователь DataLens создан (только SSL)")

# ── Шаг 6: Настроить ufw — порт 3306 только для DataLens ────────────────────
step(6, "ufw: открыть порт 3306 только для DataLens IP")
run(client, "ufw --force enable", abort_on_error=False)

# Сначала убедимся что 22 (SSH) открыт
run(client, "ufw allow 22/tcp", abort_on_error=False)
run(client, "ufw allow 80/tcp", abort_on_error=False)
run(client, "ufw allow 443/tcp", abort_on_error=False)
run(client, "ufw allow 8000/tcp", abort_on_error=False)

for ip in DATALENS_IPS:
    run(client, f"ufw allow from {ip} to any port 3306 proto tcp")
    print(f"  ✅ {ip} → 3306")

run(client, "ufw status numbered")
print("✅ Firewall настроен")

# ── Шаг 7: Верификация ───────────────────────────────────────────────────────
step(7, "Верификация")
run(client, "ss -tlnp | grep 3306")
out, _, _ = run(client,
    "mysql -u root -e \"SHOW STATUS LIKE 'Ssl_cipher';\"")
print("SSL cipher:", out)
out, _, _ = run(client, "free -m | head -2")
print("RAM:", out)

step("✓", "Итог")
print("\n✅ MySQL готов к подключению из DataLens:")
print(f"   Хост: {VPS_HOST}")
print(f"   Порт: 3306")
print(f"   БД: {DB_NAME}")
print(f"   Пользователь: {DB_USER}")
print(f"   TLS: Вкл (Let's Encrypt, CA-файл не нужен)")
print(f"\n⚠️  Порт 3306 доступен только с IP DataLens ({len(DATALENS_IPS)} диапазонов)")

client.close()
