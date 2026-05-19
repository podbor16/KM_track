"""
Деплоит конфигурацию Netdata-алертов на VPS:
  - /etc/netdata/health_alarm_notify.conf (дополнение) — нативный ntfy-sender
  - /etc/netdata/health.d/km_track.conf — 4 правила алертов
После загрузки перезагружает health-правила (netdatacli reload-health).

Флаг --test запускает smoke-тест через alarm-notify.sh test.
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

# Метка-разделитель — всё от неё до конца файла заменяется при повторном деплое
_BLOCK_MARKER = "# KM_track ntfy notifications"

NOTIFY_CONF_BLOCK = f"""\
{_BLOCK_MARKER}
###############################################################################
SEND_NTFY=YES
DEFAULT_RECIPIENT_NTFY="https://ntfy.sh/km-analytics-monitoring-2026"

SEND_CUSTOM=NO
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
    to: sysadmin
  delay: up 0 down 3m multiplier 1.5 max 1h

alarm: km_track_ram_high
    on: system.ram
lookup: average -1m unaligned percentage of used
 units: %
 every: 1m
  warn: $this > 75
  crit: $this > 90
  info: RAM usage high
    to: sysadmin
  delay: up 0 down 5m multiplier 1.5 max 1h

alarm: km_track_service_down
    on: systemdunits_service-units.unit_km_track_service_state
lookup: average -30s unaligned of active
 units: state
 every: 30s
  crit: $this < 1
  info: km_track.service is not active
    to: sysadmin
  delay: up 0 down 0 multiplier 1 max 1h

alarm: redis_down
    on: redis_local.ping_latency
lookup: average -30s unaligned of avg
 units: ms
 every: 30s
  crit: $this == nan
  info: Redis is not responding
    to: sysadmin
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

# 1. Патчим health_alarm_notify.conf
# Всё от маркера до конца файла заменяется — идемпотентный деплой
print("=== 1. Патч health_alarm_notify.conf ===")
NOTIFY_CONF_PATH = "/etc/netdata/health_alarm_notify.conf"
file_exists = run(client, f"test -f {NOTIFY_CONF_PATH} && echo yes || echo no")
if file_exists.strip() == "yes":
    current_content = read_remote(sftp, NOTIFY_CONF_PATH)
    # Обрезаем всё от нашего маркера вниз (предыдущий деплой или старый custom-блок)
    for old_marker in (_BLOCK_MARKER, "# KM_track custom ntfy sender"):
        if old_marker in current_content:
            current_content = current_content[:current_content.index(old_marker)]
            break
else:
    print(f"{NOTIFY_CONF_PATH} не найден — создаём с нуля")
    current_content = ""
new_content = current_content.rstrip("\n") + "\n\n" + NOTIFY_CONF_BLOCK
upload_text(sftp, new_content, NOTIFY_CONF_PATH)
print("Блок ntfy записан")

# 2. Загружаем health.d/km_track.conf
print("\n=== 2. Загрузка health.d/km_track.conf ===")
run(client, "mkdir -p /etc/netdata/health.d")
upload_text(sftp, KM_TRACK_HEALTH_CONF, "/etc/netdata/health.d/km_track.conf")
run(client, "chown netdata:netdata /etc/netdata/health.d/km_track.conf", check=True)

sftp.close()

# 3. Перезагружаем health-правила
print("\n=== 3. Перезагрузка Netdata health ===")
run(client, "netdatacli reload-health", check=True)

# 4. Smoke-тест (флаг --test) — через alarm-notify.sh test
if "--test" in sys.argv:
    print("\n=== Smoke-тест ntfy (alarm-notify.sh test) ===")
    run(client, "/usr/libexec/netdata/plugins.d/alarm-notify.sh test", timeout=30)
    print("Smoke-тест отправлен — проверь ntfy.sh/km-analytics-monitoring-2026")

client.close()
print("\n=== ГОТОВО ===")
print("Алерты Netdata развёрнуты.")
print("Канал ntfy: https://ntfy.sh/km-analytics-monitoring-2026")
