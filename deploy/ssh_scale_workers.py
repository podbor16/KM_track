"""Увеличивает uvicorn workers с 2 до 4 и перезапускает сервис."""
import paramiko, sys

HOST = "89.108.88.104"
USER = "root"
PASSWORD = "shsfzw5fHiQY8v6g"

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, username=USER, password=PASSWORD, timeout=30)

def run(cmd, timeout=30):
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode("utf-8", errors="replace").strip()
    err = stderr.read().decode("utf-8", errors="replace").strip()
    print(f">>> {cmd}")
    if out: print(out)
    if err: print("ERR:", err)
    print()

# Показываем текущий конфиг
run("cat /etc/systemd/system/km_track.service | grep -A3 ExecStart")

# Меняем --workers 2 → --workers 4
run("sed -i 's/--workers 2/--workers 4/' /etc/systemd/system/km_track.service")

# Проверяем
run("grep workers /etc/systemd/system/km_track.service")

# Применяем
run("systemctl daemon-reload")
run("systemctl restart km_track")
run("sleep 3 && systemctl status km_track | head -8")
run("curl -sf http://localhost:8000/ -o /dev/null && echo 'HEALTH OK' || echo 'HEALTH FAIL'")
run("ps aux | grep uvicorn | grep -v grep")

client.close()
