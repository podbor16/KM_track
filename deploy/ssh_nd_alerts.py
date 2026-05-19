"""
Деплоит конфигурацию Netdata-алертов на VPS:
  - /etc/netdata/custom-notify.sh   — отправка уведомлений через ntfy.sh
  - /etc/netdata/health_alarm_notify.conf (дополнение) — SEND_CUSTOM=YES
  - /etc/netdata/health.d/km_track.conf — 4 правила алертов
После загрузки перезагружает health-правила (netdatacli reload-health).

Флаг --test запускает smoke-тест custom-notify.sh.
"""
import io
import sys
import paramiko
from deploy._vps_config import VPS_HOST, VPS_USER, VPS_PASSWORD

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HOST = VPS_HOST

# ---------------------------------------------------------------------------
# Контент файлов
# ---------------------------------------------------------------------------

CUSTOM_NOTIFY_SH = """\
#!/bin/bash
# Called by Netdata alarm-notify.sh for CUSTOM notifications
NTFY_URL="https://ntfy.sh/km-analytics-monitoring-2026"
PRIORITY="default"
[ "$status" = "CRITICAL" ] && PRIORITY="urgent"
[ "$status" = "WARNING" ]  && PRIORITY="high"

curl -s -X POST "$NTFY_URL" \\
  -H "Title: KM_track — $alarm on $host" \\
  -H "Priority: $PRIORITY" \\
  -H "Tags: warning,server" \\
  -d "$status: $alarm
Chart: $chart
Value: $value $units
Info: $info"
"""

NOTIFY_CONF_BLOCK = """
###############################################################################
# KM_track custom ntfy sender
###############################################################################
SEND_CUSTOM=YES
DEFAULT_RECIPIENT_CUSTOM="admin"
CUSTOM_SENDER_ENABLED=YES

SEND_EMAIL=NO
SEND_SLACK=NO
SEND_TELEGRAM=NO
SEND_PD=NO
SEND_TWILIO=NO
"""

KM_TRACK_HEALTH_CONF = """\
# KM_track custom health rules

alarm: km_track_cpu_high
    on: system.cpu
lookup: average -3m unaligned of user,system
 units: %
 every: 1m
  warn: $this > 80
  crit: $this > 95
  info: CPU utilization high
    to: admin
  delay: up 0 down 3m multiplier 1.5 max 1h

alarm: km_track_ram_high
    on: mem.ram
lookup: average -1m unaligned of used
 units: %
 every: 1m
  warn: $this > 75
  crit: $this > 90
  info: RAM usage high
    to: admin
  delay: up 0 down 5m multiplier 1.5 max 1h

alarm: km_track_service_down
    on: systemd_service_units.service_unit_state
 filter: *km_track*
lookup: average -30s unaligned of active
 units: state
 every: 30s
  crit: $this != 1
  info: km_track.service is not active
    to: admin
  delay: up 0 down 0 multiplier 1 max 1h

alarm: redis_down
    on: redis.operations
lookup: average -30s unaligned of operations
 units: operations/s
 every: 30s
  crit: $this == nan
  info: Redis is not responding
    to: admin
  delay: up 0 down 0 multiplier 1 max 1h
"""

# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------

def run(client, cmd, timeout=60, check=False):
    print(f">>> {cmd[:120]}")
    _, sout, serr = client.exec_command(cmd, timeout=timeout, get_pty=False)
    out = sout.read().decode("utf-8", errors="replace").strip()
    err = serr.read().decode("utf-8", errors="replace").strip()
    exit_code = sout.channel.recv_exit_status()
    if out:
        print(out[:600])
    if err and not any(x in err.lower() for x in ["warning", "deprecated", "notice"]):
        print(f"[err] {err[:300]}")
    if check and exit_code != 0:
        print(f"ERROR: command exited with code {exit_code}: {cmd[:120]}")
        raise SystemExit(1)
    return out


def upload_text(sftp, content, remote_path):
    with sftp.open(remote_path, "w") as f:
        f.write(content)
    print(f"Загружен {remote_path}")


def read_remote(sftp, remote_path):
    with sftp.open(remote_path, "r") as f:
        return f.read().decode("utf-8", errors="replace")


# ---------------------------------------------------------------------------
# Основной деплой
# ---------------------------------------------------------------------------

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, username=VPS_USER, password=VPS_PASSWORD, timeout=30)
print(f"Подключился к {HOST}\n")

sftp = client.open_sftp()

# 1. Загружаем custom-notify.sh
print("=== 1. Загрузка custom-notify.sh ===")
upload_text(sftp, CUSTOM_NOTIFY_SH, "/etc/netdata/custom-notify.sh")
run(client, "chmod +x /etc/netdata/custom-notify.sh", check=True)
run(client, "chown netdata:netdata /etc/netdata/custom-notify.sh", check=True)

# 2. Патчим health_alarm_notify.conf (добавляем блок, если ещё нет)
print("\n=== 2. Патч health_alarm_notify.conf ===")
NOTIFY_CONF_PATH = "/etc/netdata/health_alarm_notify.conf"
already = run(client, f"grep -c 'SEND_CUSTOM=YES' {NOTIFY_CONF_PATH} 2>/dev/null || echo 0")
if already.strip() != "0":
    print("SEND_CUSTOM=YES уже присутствует — пропускаем патч")
else:
    file_exists = run(client, f"test -f {NOTIFY_CONF_PATH} && echo yes || echo no")
    if file_exists.strip() == "yes":
        current_content = read_remote(sftp, NOTIFY_CONF_PATH)
    else:
        print(f"{NOTIFY_CONF_PATH} не найден — создаём с нуля")
        current_content = ""
    new_content = current_content + NOTIFY_CONF_BLOCK
    upload_text(sftp, new_content, NOTIFY_CONF_PATH)
    print("Блок SEND_CUSTOM добавлен")

# 3. Загружаем health.d/km_track.conf
print("\n=== 3. Загрузка health.d/km_track.conf ===")
run(client, "mkdir -p /etc/netdata/health.d")
upload_text(sftp, KM_TRACK_HEALTH_CONF, "/etc/netdata/health.d/km_track.conf")
run(client, "chown netdata:netdata /etc/netdata/health.d/km_track.conf", check=True)

sftp.close()

# 4. Перезагружаем health-правила
print("\n=== 4. Перезагрузка Netdata health ===")
run(client, "netdatacli reload-health", check=True)

# 5. Smoke-тест (флаг --test)
if "--test" in sys.argv:
    print("\n=== Smoke-тест custom-notify.sh ===")
    smoke_cmd = (
        'status=WARNING alarm=test_alarm host=$(hostname) chart=system.cpu '
        'value=85 units="%" info="Smoke test from deploy script" '
        '/etc/netdata/custom-notify.sh'
    )
    run(client, smoke_cmd, timeout=15)
    print("Smoke-тест отправлен — проверь ntfy.sh/km-analytics-monitoring-2026")

client.close()
print("\n=== ГОТОВО ===")
print("Алерты Netdata развёрнуты.")
print("Канал ntfy: https://ntfy.sh/km-analytics-monitoring-2026")
