"""Добавляет второй swap-файл 2 GB на VPS для защиты от OOM под нагрузкой."""
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from deploy._vps_config import VPS_HOST, VPS_USER, VPS_PASSWORD
import paramiko

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(VPS_HOST, username=VPS_USER, password=VPS_PASSWORD, timeout=30)

def run(cmd, timeout=60):
    _, out, err = client.exec_command(cmd)
    result = out.read().decode("utf-8", errors="replace").strip()
    if result:
        print(result)
    return result

print("=== Текущий swap ===")
run("swapon --show")

print("\n=== Создаём /swapfile2 (2 GB) ===")
run("fallocate -l 2G /swapfile2", timeout=30)
run("chmod 600 /swapfile2")
run("mkswap /swapfile2")
run("swapon /swapfile2")

print("\n=== Проверяем ===")
run("swapon --show")
run("free -h")

print("\n=== Добавляем в /etc/fstab для автомонтирования ===")
run("grep -q '/swapfile2' /etc/fstab || echo '/swapfile2 none swap sw 0 0' >> /etc/fstab")

client.close()
print("\nSwap 2 GB добавлен.")
