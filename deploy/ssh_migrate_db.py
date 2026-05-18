"""
Перенос MySQL БД на VPS.
Выполняет шаги 1-7 плана последовательно с проверками.
"""
import sys
import time
import paramiko

VPS_HOST = "89.108.88.104"
VPS_USER = "root"
VPS_PASS = "shsfzw5fHiQY8v6g"

REMOTE_HOST = "79.174.89.159"
REMOTE_PORT = 16171
DB_USER = "km_analytic"
DB_PASS = "CneZbvlOS2H-BLsQ"
DB_NAME = "krasmarafon"

ENV_PATH = "/opt/km_track/.env"
DUMP_PATH = "/tmp/krasmarafon_dump.sql"

MYSQL_CONFIG = """[mysqld]
innodb_buffer_pool_size = 128M
max_connections = 20
bind-address = 127.0.0.1
"""


def connect():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(VPS_HOST, username=VPS_USER, password=VPS_PASS, timeout=30)
    return client


def run(client, cmd, timeout=120, abort_on_error=True):
    print(f">>> {cmd[:120]}")
    transport = client.get_transport()
    channel = transport.open_session()
    channel.settimeout(None)  # no socket timeout — reads block until data arrives
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
            deadline = time.time() + timeout  # reset deadline on activity
        if channel.recv_stderr_ready():
            chunk = channel.recv_stderr(4096).decode(errors="replace")
            err_parts.append(chunk)
            deadline = time.time() + timeout
        if channel.exit_status_ready():
            # drain remaining output
            while channel.recv_ready():
                chunk = channel.recv(4096).decode(errors="replace")
                out_parts.append(chunk)
                for line in chunk.splitlines():
                    if line.strip():
                        print(line)
            while channel.recv_stderr_ready():
                err_parts.append(channel.recv_stderr(4096).decode(errors="replace"))
            break
        if time.time() > deadline:
            print(f"[timeout] Команда выполняется дольше {timeout}с без вывода. Прерываем.")
            channel.close()
            if abort_on_error:
                sys.exit(1)
            return "", "", -1
        time.sleep(0.2)

    rc = channel.recv_exit_status()
    channel.close()
    out = "".join(out_parts).strip()
    err = "".join(err_parts).strip()
    if err and "Warning" not in err and "warning" not in err:
        print(f"[stderr] {err}")
    if rc != 0 and abort_on_error:
        print(f"\n❌ Команда завершилась с кодом {rc}. Стоп.")
        sys.exit(1)
    return out, err, rc


def step(n, title):
    print(f"\n{'='*60}")
    print(f"  Шаг {n}: {title}")
    print(f"{'='*60}")


client = connect()
print(f"✅ Подключились к {VPS_HOST}")

# ── Шаг 1: Установить MySQL ──────────────────────────────────────────────────
step(1, "Установить MySQL Server")
out, _, _ = run(client, "which mysql 2>/dev/null || echo 'not found'", abort_on_error=False)
if "not found" in out or not out:
    print("MySQL не найден — устанавливаем...")
    run(client,
        "DEBIAN_FRONTEND=noninteractive apt-get update -qq && "
        "DEBIAN_FRONTEND=noninteractive apt-get install -y mysql-server",
        timeout=300)
else:
    print("MySQL уже установлен, пропускаем.")

run(client, "systemctl enable mysql && systemctl start mysql")
run(client, "systemctl is-active mysql")

# ── Шаг 2: Настройка MySQL (минимальный RAM footprint) ──────────────────────
step(2, "Настроить innodb_buffer_pool_size=128M, max_connections=20")
config_cmd = f"cat > /etc/mysql/mysql.conf.d/km_track.cnf << 'EOFCFG'\n{MYSQL_CONFIG}\nEOFCFG"
run(client, config_cmd)
run(client, "systemctl restart mysql")
time.sleep(3)
run(client, "systemctl is-active mysql")
print("MySQL настроен и перезапущен.")

# ── Шаг 3: Создать БД и пользователя ────────────────────────────────────────
step(3, "Создать БД и пользователя km_analytic")
sql = (
    f"CREATE DATABASE IF NOT EXISTS {DB_NAME} "
    f"CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci; "
    f"CREATE USER IF NOT EXISTS '{DB_USER}'@'localhost' IDENTIFIED BY '{DB_PASS}'; "
    f"GRANT ALL PRIVILEGES ON {DB_NAME}.* TO '{DB_USER}'@'localhost'; "
    f"FLUSH PRIVILEGES;"
)
run(client, f'mysql -u root -e "{sql}"')
out, _, _ = run(client,
    f"mysql -u root -e \"SELECT User, Host FROM mysql.user WHERE User='{DB_USER}';\"")
print("Пользователь создан:", out)

# ── Шаг 4: Dump с удалённой БД ──────────────────────────────────────────────
step(4, "Снять dump с удалённой БД (может занять 1-2 минуты)")
dump_cmd = (
    f"mysqldump --single-transaction --no-tablespaces --skip-lock-tables "
    f"-h {REMOTE_HOST} -P {REMOTE_PORT} "
    f"-u {DB_USER} -p'{DB_PASS}' "
    f"{DB_NAME} > {DUMP_PATH} 2>/tmp/dump_err.txt"
)
_, _, rc = run(client, dump_cmd, timeout=300, abort_on_error=False)
out, _, _ = run(client, f"ls -lh {DUMP_PATH} 2>/dev/null || echo 'файл не создан'")
print("Размер dump:", out)
out_err, _, _ = run(client, "cat /tmp/dump_err.txt 2>/dev/null", abort_on_error=False)
if out_err and "Error" in out_err:
    print(f"❌ Ошибка dump:\n{out_err}")
    sys.exit(1)
# Проверяем что файл не пустой
out, _, _ = run(client, f"wc -c {DUMP_PATH}")
size_bytes = int(out.split()[0])
if size_bytes < 10000:
    print(f"❌ Dump подозрительно мал ({size_bytes} байт). Проверьте вручную.")
    sys.exit(1)
print(f"✅ Dump получен: {size_bytes:,} байт")

# ── Шаг 5: Восстановить дамп ────────────────────────────────────────────────
step(5, "Восстановить дамп в локальный MySQL")
run(client,
    f"mysql -u root {DB_NAME} < {DUMP_PATH}",
    timeout=120)
# Верификация строк
for table, expected in [("results", 6447), ("leads", 11186), ("clients", 9461)]:
    out, _, _ = run(client,
        f"mysql -u {DB_USER} -p'{DB_PASS}' {DB_NAME} "
        f"-e 'SELECT COUNT(*) FROM {table};' --skip-column-names")
    cnt = int(out.strip()) if out.strip().isdigit() else -1
    status = "✅" if cnt >= expected * 0.95 else "⚠️"
    print(f"{status} {table}: {cnt} строк (ожидалось ≥{expected})")

# ── Шаг 6: Обновить .env на VPS ─────────────────────────────────────────────
step(6, "Обновить .env на VPS (DB_HOST → 127.0.0.1, DB_PORT → 3306)")
# Показываем текущие значения
run(client, f"grep -E 'DB_HOST|DB_PORT' {ENV_PATH}")
run(client, f"sed -i 's/^DB_HOST=.*/DB_HOST=127.0.0.1/' {ENV_PATH}")
run(client, f"sed -i 's/^DB_PORT=.*/DB_PORT=3306/' {ENV_PATH}")
out, _, _ = run(client, f"grep -E 'DB_HOST|DB_PORT' {ENV_PATH}")
print("Новые значения в .env:", out)

# ── Шаг 7: Перезапустить приложение ─────────────────────────────────────────
step(7, "Перезапустить km_track и проверить health")
run(client, "systemctl restart km_track")
time.sleep(4)
run(client, "systemctl is-active km_track")
run(client, "systemctl status km_track --no-pager | head -5")
out, _, rc = run(client,
    "curl -s http://127.0.0.1:8000/health",
    abort_on_error=False)
if '"status": "ok"' in out or '"status":"ok"' in out:
    print("✅ Health check: OK")
else:
    print(f"⚠️  Health: {out}")
    run(client, "journalctl -u km_track --no-pager -n 20")

# ── Финал ────────────────────────────────────────────────────────────────────
step("✓", "Итог")
run(client, "free -m | head -2")
run(client, "df -h /")
print("\n✅ Перенос БД завершён.")
print("   БД теперь на localhost:3306")
print("\n📋 Ручные шаги:")
print("   1. DBeaver: переключить соединение на SSH-tunnel → 89.108.88.104 → localhost:3306")
print(f"   2. DataLens: обновить коннектор: {REMOTE_HOST}:{REMOTE_PORT} → {VPS_HOST}:3306")
print(f"   3. Старый .env: DB_HOST={REMOTE_HOST} больше не нужен")

client.close()
